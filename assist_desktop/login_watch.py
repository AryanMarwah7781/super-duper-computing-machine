"""Who just logged in, according to a file somebody else writes.

The operator signs in somewhere outside this app, and that system drops the
name in a file. Which file, and in what shape, was still being decided when
this was written -- so the path is configuration and the reader takes the name
out of whatever it finds:

    ASSIST_LOGIN_FILE=C:/simulator/current_user.json

    {"name": "Priya Sharma"}          preferred
    {"username": "Priya Sharma"}      also fine: user, operator, displayName
    ["...", {"name": "Priya Sharma"}] a log -- the last entry wins
    Priya Sharma                      a bare line of text

Being generous here is deliberate. The cost of accepting one more spelling of
"name" is a dictionary lookup; the cost of rejecting it is an operator standing
in front of a black screen while somebody reads the source to find out which
key it wanted.

Partial reads are expected, not exceptional. The writer is another process and
there is no lock between us, so a read can land mid-write and see half a JSON
object. That returns None and the next poll picks it up -- roughly 200 ms later
and invisible to anyone watching.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from .logs import get as get_logger

log = get_logger("login")

# In order of preference. `name` is what we document; the rest are what other
# systems tend to call it.
KEYS = ("name", "username", "user", "operator", "displayName", "display_name",
        "full_name", "fullName")

POLL_S = 0.2

# A name is a name, not a file. Anything longer than this is a stray log line
# that happened to land in the file, and greeting the room with 400 characters
# of stack trace is worse than not greeting anybody.
MAX_NAME = 80


def default_path() -> Path:
    return Path(os.environ.get("ASSIST_LOGIN_FILE",
                               r"C:/simulator/current_user.json"))


def _from_obj(obj) -> Optional[str]:
    """Pull a name out of parsed JSON, whatever shape it arrived in."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for key in KEYS:
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None
    if isinstance(obj, list):
        # A log rather than a state file: the last entry is who is here now.
        for entry in reversed(obj):
            found = _from_obj(entry)
            if found:
                return found
    return None


def parse(text: str) -> Optional[str]:
    """The name in `text`, or None. Never raises."""
    # The BOM comes off before the emptiness check, not after: Python does not
    # count \ufeff as whitespace, so a file containing nothing but a BOM --
    # which is what PowerShell leaves when it writes an empty string -- looks
    # non-empty right up until something tries to index it.
    stripped = (text or "").lstrip("\ufeff").strip()
    if not stripped:
        return None

    try:
        name = _from_obj(json.loads(stripped))
    except (ValueError, TypeError):
        # Not JSON. Treat it as a plain name, but only if it looks like one --
        # a partial write of `{"name": "Priya` must not be greeted as a person
        # called `{"name": "Priya`.
        if stripped[0] in "{[":
            return None
        name = stripped.splitlines()[-1] if stripped else None

    if not name:
        return None
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        return None
    return name


def read(path: Optional[Path] = None) -> Optional[str]:
    """The name currently in the login file, or None if there isn't one."""
    path = default_path() if path is None else path
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    except OSError as exc:
        # Locked by the writer, or a network path that blinked. Not fatal.
        log.debug("login file unreadable: %s", exc)
        return None
    return parse(text)


class LoginWatcher:
    """Calls back with the name whenever the login file starts naming someone.

    Polls rather than watching. The file is small, the interval is 200 ms, and
    a filesystem watcher on a path that may be a network share is a great deal
    more machinery for the same answer.
    """

    def __init__(self, on_login: Callable[[str], None],
                 path: Optional[Path] = None, poll_s: float = POLL_S) -> None:
        self._on_login = on_login
        self._path = default_path() if path is None else path
        self._poll_s = poll_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last: Optional[str] = None

    @property
    def path(self) -> Path:
        return self._path

    def current(self) -> Optional[str]:
        return read(self._path)

    def poll_once(self) -> Optional[str]:
        """Read, and fire the callback if the name changed. Returns the name.

        Split out from the loop so the behaviour can be tested without a
        thread or a clock.
        """
        name = read(self._path)
        if name and name != self._last:
            self._last = name
            try:
                self._on_login(name)
            except Exception:
                # A failing callback must not kill the watcher; the next
                # person to log in still deserves a greeting.
                log.exception("login callback failed for %r", name)
        elif not name:
            # The file was cleared: signing out lets the same person be
            # greeted again next time rather than being silently ignored.
            self._last = None
        return name

    def _run(self) -> None:
        while not self._stop.wait(self._poll_s):
            self.poll_once()

    def start(self) -> None:
        if self._thread:
            return
        log.info("watching %s for the signed-in operator", self._path)
        self._thread = threading.Thread(target=self._run, name="login-watch",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
