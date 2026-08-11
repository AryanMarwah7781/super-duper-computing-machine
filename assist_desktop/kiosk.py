"""The pipe between the welcome kiosk on the board and this laptop.

Two messages cross the demo network, both plain JSON over HTTP, no auth and no
queue:

    kiosk -> here   POST :5000/login       an operator tapped their ID card
    here -> kiosk   POST :8080/api/logout  that operator's session ended here

Three things about the inbound half are not style choices, they are what the
kiosk's operator sees when we get them wrong:

  Answer first, act second. The kiosk waits five seconds for a 2xx and then
  tells the person in front of it that the handoff failed. Signing somebody in,
  loading their history and starting the voice takes longer than that on a cold
  start, so the 200 goes out before any of it begins.

  A repeat is not a second person. When its first attempt fails the kiosk
  re-sends the identical payload behind a "Try again" button, so the same
  sign-in arriving twice has to be harmless -- see `Api.external_login`, which
  ignores a repeat of the operator already at the machine rather than replaying
  the welcome over a session in progress.

  Nothing here may raise. A malformed body, a name we cannot find, a callback
  that throws: all of them still answer the kiosk, because a listener that
  drops the connection looks exactly like a laptop that is switched off.

Both addresses are read per call rather than at import, so editing `.env` takes
effect on the next message instead of on the next restart -- the board's IP is
DHCP-assigned and does move.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

from .login_watch import KEYS, MAX_NAME
from .logs import get as get_logger

log = get_logger("kiosk")

# The SiMa board, as it is addressed from here. Base only: two endpoints hang
# off it and a third would otherwise mean a third setting.
DEFAULT_KIOSK_URL = "http://192.168.94.15:8080"

# What the board is configured to POST to (WELCOME_JD_URL on its side).
DEFAULT_PORT = 5000

# A sign-in is a few hundred bytes. This is not a security boundary -- the
# network is closed -- it is a guard against reading a body that never ends.
MAX_BODY = 64 * 1024

# Where a sign-in may land. `/login` is what the board sends; `/api/login` is
# accepted so a curl written from memory still works.
LOGIN_PATHS = ("/login", "/api/login")

OnLogin = Callable[[str, bool], None]


def kiosk_url() -> str:
    return os.environ.get("ASSIST_KIOSK_URL", DEFAULT_KIOSK_URL).rstrip("/")


def kiosk_timeout_s() -> float:
    try:
        return float(os.environ.get("ASSIST_KIOSK_TIMEOUT_S", "5"))
    except ValueError:
        return 5.0


def listen_port() -> int:
    try:
        return int(os.environ.get("ASSIST_LOGIN_PORT", str(DEFAULT_PORT)))
    except ValueError:
        log.warning("ASSIST_LOGIN_PORT is not a number, using %d", DEFAULT_PORT)
        return DEFAULT_PORT


def listen_host() -> str:
    """0.0.0.0 deliberately: the whole point is a message from another machine,
    and 127.0.0.1 would refuse the board without ever logging why."""
    return os.environ.get("ASSIST_LOGIN_HOST", "0.0.0.0")


# -- reading a sign-in ------------------------------------------------------

def name_in(obj) -> Optional[str]:
    """The operator's name in whatever arrived, or None.

    The documented shape is `{"user": {"name": "Priya Sharma"}}`, but the same
    generosity the login file gets applies here for the same reason: accepting
    one more spelling of "name" costs a dictionary lookup, and rejecting it
    costs an operator standing in front of a black screen.
    """
    if isinstance(obj, str):
        return obj.strip() or None
    if not isinstance(obj, dict):
        return None
    for key in KEYS:
        # `user` is one of KEYS and is usually a nested object here, so this
        # recurses into `{"user": {...}}` without a special case for it.
        found = name_in(obj.get(key))
        if found:
            return found
    return None


def sign_in(payload) -> tuple[Optional[str], bool]:
    """(name to greet, whether the kiosk says they are new). Never raises.

    `new_user` is the kiosk's opinion of its own card roster, not ours. It is
    passed on for the record; whether this laptop has met them before is
    decided by our own database, which is the thing holding their history.
    """
    name = name_in(payload)
    if name and len(name) > MAX_NAME:
        log.warning("sign-in carried a %d character name; ignoring it",
                    len(name))
        name = None
    new_user = bool(isinstance(payload, dict) and payload.get("new_user"))
    return name, new_user


class _Handler(BaseHTTPRequestHandler):
    on_login: OnLogin

    server_version = "assist-jd"
    # HTTP/1.0, so every response closes its connection. Nothing here benefits
    # from keep-alive and a half-read body on a reused socket is a class of bug
    # this listener has no reason to own.
    protocol_version = "HTTP/1.0"

    def log_message(self, *args) -> None:
        """Quiet. What matters is logged by hand, with names in it."""

    # -- routes ------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self._route() == "/health":
            self._reply(200, {"ok": True, "app": "assist"})
            return
        self._reply(404, {"ok": False, "error": "no such path"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if self._route() not in LOGIN_PATHS:
            self._reply(404, {"ok": False, "error": "no such path"})
            return

        payload = self._body()
        name, new_user = sign_in(payload)

        # Before anything is done about it. See the module docstring.
        self._reply(200, {"ok": bool(name), "user": name})

        if not name:
            log.warning("sign-in arrived with no name in it: %.200r", payload)
            return
        log.info("sign-in from the kiosk: %s%s", name,
                 " (new to the kiosk)" if new_user else "")
        # Off the socket's thread, so a slow sign-in cannot hold the connection
        # open behind an answer the kiosk has already had.
        threading.Thread(target=self._act, args=(name, new_user),
                         name="kiosk-login", daemon=True).start()

    def _act(self, name: str, new_user: bool) -> None:
        try:
            self.on_login(name, new_user)
        except Exception:
            # The kiosk has its 200 and the operator is walking over. Log it
            # and stay up for the next person.
            log.exception("sign-in for %r could not be acted on", name)

    # -- plumbing ----------------------------------------------------------
    def _route(self) -> str:
        return self.path.split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/"

    def _body(self):
        """The parsed JSON body, or None. Never raises."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length <= 0:
            return None
        try:
            raw = self.rfile.read(min(length, MAX_BODY))
        except OSError:
            return None
        try:
            return json.loads(raw.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            log.warning("body was not JSON: %.200r", raw)
            return None

    def _reply(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
        except OSError:
            # The kiosk gave up and closed the socket. Nothing to do about it.
            log.debug("could not answer %s", self.path)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR does not mean "reuse a port left in TIME_WAIT",
    # it means "bind on top of whoever already holds it": two listeners on
    # 5000, and each sign-in goes to whichever the OS happens to pick. Refusing
    # the bind is the honest answer, and the log then names the real problem
    # instead of the demo losing every other card tap.
    allow_reuse_address = os.name != "nt"


class LoginListener:
    """Receives sign-ins from the kiosk. Starting it is never fatal.

    If port 5000 is already held -- window_listener.py from the old stack is
    the usual culprit -- the app still comes up with its own sign-in screen,
    and the log says exactly what is missing. A demo that refuses to start
    because one of two ways in is unavailable is worse than one that starts.
    """

    def __init__(self, on_login: OnLogin, host: Optional[str] = None,
                 port: Optional[int] = None) -> None:
        self._on_login = on_login
        self._host = listen_host() if host is None else host
        self._port = listen_port() if port is None else port
        self._httpd: Optional[_Server] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        """The port actually bound, which is what 0 resolves to in tests."""
        return self._httpd.server_address[1] if self._httpd else self._port

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> bool:
        if self._httpd is not None:
            return True
        handler = type("BoundHandler", (_Handler,),
                       {"on_login": staticmethod(self._on_login)})
        try:
            self._httpd = _Server((self._host, self._port), handler)
        except OSError as e:
            log.error("cannot listen on %s:%d - %s. Sign-ins from the kiosk "
                      "will not arrive; the sign-in screen still works.",
                      self._host, self._port, e)
            self._httpd = None
            return False
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="kiosk-listener", daemon=True)
        self._thread.start()
        log.info("listening for sign-ins on http://%s:%d/login",
                 self._host, self.port)
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


# -- telling the kiosk ------------------------------------------------------

def report_logout(name: str = "") -> tuple[bool, str]:
    """Tell the kiosk this operator's session here has ended.

    The name is optional and only decides what the kiosk's sign-out notice
    says; any POST to that path ends whatever session it has open. Never
    raises -- a kiosk that cannot be reached must not turn signing out on this
    laptop into an error the operator has to get past.
    """
    import httpx

    url = f"{kiosk_url()}/api/logout"
    body = {"user": {"name": name}} if name else {}
    try:
        r = httpx.post(url, json=body, timeout=kiosk_timeout_s())
        r.raise_for_status()
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        log.warning("kiosk not told about the sign-out (%s): %s", url, detail)
        return False, detail
    log.info("kiosk told that %s signed out", name or "the operator")
    return True, ""


def report_logout_later(name: str = "") -> threading.Thread:
    """`report_logout` off the caller's thread.

    Sign-out redraws the screen, and a kiosk that is off or unplugged would
    otherwise hold that redraw for the whole timeout -- five seconds of a
    frozen panel because the other machine is missing.
    """
    thread = threading.Thread(target=report_logout, args=(name,),
                              name="kiosk-logout", daemon=True)
    thread.start()
    return thread


def who_is_signed_in() -> tuple[bool, dict]:
    """Ask the kiosk who it thinks is at the machine. Diagnostics only."""
    import httpx

    url = f"{kiosk_url()}/api/session"
    try:
        r = httpx.get(url, timeout=kiosk_timeout_s())
        r.raise_for_status()
        return True, r.json()
    except Exception as e:
        return False, {"error": f"{type(e).__name__}: {e}"}
