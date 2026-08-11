"""The two messages between the welcome kiosk and this laptop.

Real sockets throughout: this is a wire protocol between two machines, and a
test that mocks the wire proves nothing about the thing that keeps failing --
what goes out on it, and how fast the answer comes back.
"""
from __future__ import annotations

import json
import threading
import time

import httpx
import pytest

from assist_desktop import kiosk


# -- receiving a sign-in ----------------------------------------------------

@pytest.fixture
def listening():
    """The listener on an ephemeral port, plus what it was told."""
    seen: list[tuple[str, bool]] = []
    arrived = threading.Event()

    def on_login(name: str, new_user: bool) -> None:
        seen.append((name, new_user))
        arrived.set()

    listener = kiosk.LoginListener(on_login, host="127.0.0.1", port=0)
    assert listener.start()
    yield f"http://127.0.0.1:{listener.port}", seen, arrived
    listener.stop()


SIGN_IN = {
    "timestamp": "2026-08-11T00:12:29.123456",
    "event": "operator_login",
    "new_user": False,
    "user": {
        "id": "priya-sharma",
        "name": "Priya Sharma",
        "created_at": "2026-08-10T18:02:11+00:00",
        "last_seen": "2026-08-11T00:12:29+00:00",
    },
}


def test_health_says_the_laptop_is_up(listening):
    base, _, _ = listening
    r = httpx.get(f"{base}/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_a_sign_in_is_answered_and_acted_on(listening):
    base, seen, arrived = listening
    r = httpx.post(f"{base}/login", json=SIGN_IN)
    assert r.status_code == 200
    assert arrived.wait(5), "the sign-in never reached the callback"
    assert seen == [("Priya Sharma", False)]


def test_the_answer_comes_back_before_the_work_is_done():
    """The kiosk gives up after five seconds and tells the operator the
    handoff failed. Signing somebody in takes longer than that on a cold
    start, so the 200 must not wait for it."""
    slow = threading.Event()

    def hold(*_args):
        slow.wait(10)

    listener = kiosk.LoginListener(hold, host="127.0.0.1", port=0)
    assert listener.start()
    try:
        started = time.perf_counter()
        r = httpx.post(f"http://127.0.0.1:{listener.port}/login",
                       json=SIGN_IN, timeout=5)
        answered = time.perf_counter() - started
        assert r.status_code == 200
        assert answered < 1.0, f"took {answered:.1f}s to answer"
    finally:
        slow.set()
        listener.stop()


def test_a_new_user_is_flagged(listening):
    base, seen, arrived = listening
    httpx.post(f"{base}/login", json={**SIGN_IN, "new_user": True})
    assert arrived.wait(5)
    assert seen[0][1] is True


def test_the_same_sign_in_twice_is_delivered_twice(listening):
    """Try again re-sends the identical payload. The listener passes both on;
    ignoring the repeat is the app's decision, not the socket's."""
    base, seen, arrived = listening
    for _ in range(2):
        assert httpx.post(f"{base}/login", json=SIGN_IN).status_code == 200
    deadline = time.time() + 5
    while len(seen) < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert seen == [("Priya Sharma", False)] * 2


@pytest.mark.parametrize("body", [
    {},
    {"event": "operator_login"},
    {"user": {}},
    {"user": {"name": "   "}},
    {"user": {"name": 42}},
])
def test_a_sign_in_with_no_name_is_still_answered(listening, body):
    """Answering is what keeps the kiosk from reporting a failure. It has
    nobody to sign in, which is different from being unreachable."""
    base, seen, _ = listening
    r = httpx.post(f"{base}/login", json=body)
    assert r.status_code == 200
    assert r.json()["ok"] is False
    time.sleep(0.1)
    assert seen == []


def test_a_body_that_is_not_json_does_not_kill_the_listener(listening):
    base, seen, arrived = listening
    r = httpx.post(f"{base}/login", content=b"<html>not json</html>",
                   headers={"Content-Type": "application/json"})
    assert r.status_code == 200

    # Still up for the next person.
    httpx.post(f"{base}/login", json=SIGN_IN)
    assert arrived.wait(5)
    assert seen == [("Priya Sharma", False)]


def test_a_callback_that_throws_does_not_kill_the_listener():
    calls: list[str] = []

    def boom(name, _new):
        calls.append(name)
        raise RuntimeError("the UI was not ready")

    listener = kiosk.LoginListener(boom, host="127.0.0.1", port=0)
    assert listener.start()
    try:
        base = f"http://127.0.0.1:{listener.port}"
        assert httpx.post(f"{base}/login", json=SIGN_IN).status_code == 200
        assert httpx.post(f"{base}/login", json=SIGN_IN).status_code == 200
        assert httpx.get(f"{base}/health").json()["ok"] is True
    finally:
        listener.stop()


def test_an_unknown_path_is_404(listening):
    base, _, _ = listening
    assert httpx.get(f"{base}/nope").status_code == 404
    assert httpx.post(f"{base}/nope", json={}).status_code == 404


def test_a_port_already_held_is_reported_not_raised():
    """window_listener.py from the old stack sits on 5000. The app still has
    to come up -- its own sign-in screen is unaffected."""
    first = kiosk.LoginListener(lambda *_: None, host="127.0.0.1", port=0)
    assert first.start()
    try:
        second = kiosk.LoginListener(lambda *_: None, host="127.0.0.1",
                                     port=first.port)
        assert second.start() is False
        assert second.running is False
    finally:
        first.stop()


def test_stop_is_safe_twice():
    listener = kiosk.LoginListener(lambda *_: None, host="127.0.0.1", port=0)
    listener.start()
    listener.stop()
    listener.stop()


class TestReadingASignIn:
    def test_the_documented_shape(self):
        assert kiosk.sign_in(SIGN_IN) == ("Priya Sharma", False)

    def test_a_bare_name(self):
        assert kiosk.sign_in({"name": "Marcus Chen"})[0] == "Marcus Chen"

    def test_a_user_that_is_a_string(self):
        assert kiosk.sign_in({"user": "Marcus Chen"})[0] == "Marcus Chen"

    def test_nothing_that_names_anybody(self):
        assert kiosk.sign_in({"event": "operator_login"}) == (None, False)
        assert kiosk.sign_in(None) == (None, False)
        assert kiosk.sign_in([1, 2, 3]) == (None, False)

    def test_a_log_line_is_not_a_name(self):
        assert kiosk.sign_in({"name": "x" * 200})[0] is None


# -- sending a logout -------------------------------------------------------

class _Kiosk:
    """The board's /api/logout and /api/session, near enough to answer."""

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        received: list = []
        self.received = received

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def _json(self, status, body):
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                received.append(json.loads(raw or b"{}"))
                self._json(200, {"ok": True, "was": "Priya Sharma"})

            def do_GET(self):
                self._json(200, {"user": {"name": "Priya Sharma"}})

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def board(monkeypatch):
    server = _Kiosk()
    monkeypatch.setenv("ASSIST_KIOSK_URL", server.url)
    yield server
    server.stop()


def test_the_logout_carries_the_name(board):
    ok, detail = kiosk.report_logout("Priya Sharma")
    assert (ok, detail) == (True, "")
    assert board.received == [{"user": {"name": "Priya Sharma"}}]


def test_a_logout_without_a_name_is_still_a_logout(board):
    """A deleted operator has no profile left to read a name from, and the
    kiosk ends whatever session it has open regardless."""
    assert kiosk.report_logout()[0] is True
    assert board.received == [{}]


def test_an_unreachable_kiosk_is_reported_not_raised(monkeypatch):
    # Port 9 discards; nothing is listening on it.
    monkeypatch.setenv("ASSIST_KIOSK_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("ASSIST_KIOSK_TIMEOUT_S", "1")
    ok, detail = kiosk.report_logout("Priya Sharma")
    assert ok is False
    assert detail

def test_the_address_is_read_per_send_not_at_import(board, monkeypatch):
    """The board's IP is DHCP-assigned. Editing .env must take effect on the
    next message, not the next restart."""
    monkeypatch.setenv("ASSIST_KIOSK_URL", "http://127.0.0.1:9")
    assert kiosk.report_logout("Priya Sharma")[0] is False
    monkeypatch.setenv("ASSIST_KIOSK_URL", board.url)
    assert kiosk.report_logout("Priya Sharma")[0] is True


def test_asking_who_is_signed_in(board):
    ok, session = kiosk.who_is_signed_in()
    assert ok
    assert session["user"]["name"] == "Priya Sharma"


# -- both halves, wired to the app ------------------------------------------

@pytest.fixture
def wired(tmp_path, board):
    """A real Api behind a real listener, with the board stubbed out.

    The devkit address goes nowhere on purpose: none of this asks it anything,
    and a test that needed the board running to prove a sign-in arrived would
    be testing the wrong machine.
    """
    from assist_desktop.api import Api
    from assist_desktop.config import Config

    events: list[tuple[str, dict]] = []
    api = Api(Config(devkit_url="http://127.0.0.1:9", timeout_s=1.0),
              emit=lambda name, data: events.append((name, data)),
              log_path=tmp_path / "turns.jsonl",
              db_path=tmp_path / "assist.db")
    listener = kiosk.LoginListener(api.external_login, host="127.0.0.1", port=0)
    assert listener.start()
    yield f"http://127.0.0.1:{listener.port}", api, events, board
    listener.stop()


def _wait_for(events, name, count=1, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len([e for e in events if e[0] == name]) >= count:
            return [data for kind, data in events if kind == name]
        time.sleep(0.02)
    raise AssertionError(f"only saw {[e[0] for e in events]}")


def test_a_card_tap_signs_the_operator_in_here(wired):
    base, api, events, _ = wired
    assert httpx.post(f"{base}/login", json=SIGN_IN).status_code == 200

    seen = _wait_for(events, "external_login")
    assert seen[0]["user"]["name"] == "Priya Sharma"
    assert seen[0]["user"]["id"] == "priya-sharma"
    assert seen[0]["new_user"] is False
    # The voice thread has no idea who is at the machine unless this happened.
    _wait_for(events, "active_user")
    assert api._active_user == "priya-sharma"


def test_try_again_does_not_replay_the_welcome(wired):
    """The kiosk re-sends the identical payload behind its Try again button.
    A second welcome over a session in progress is worse than nothing."""
    base, api, events, _ = wired
    httpx.post(f"{base}/login", json=SIGN_IN)
    _wait_for(events, "external_login")
    httpx.post(f"{base}/login", json=SIGN_IN)
    time.sleep(0.3)

    assert len([e for e in events if e[0] == "external_login"]) == 1
    assert api._active_user == "priya-sharma"


def test_the_next_card_replaces_the_last_operator(wired):
    base, api, events, board = wired
    httpx.post(f"{base}/login", json=SIGN_IN)
    _wait_for(events, "external_login")

    httpx.post(f"{base}/login",
               json={"event": "operator_login",
                     "user": {"id": "marcus-chen", "name": "Marcus Chen"}})
    seen = _wait_for(events, "external_login", count=2)
    assert seen[1]["user"]["name"] == "Marcus Chen"
    assert api._active_user == "marcus-chen"
    # The kiosk sent that swap. Reporting a sign-out back would end the
    # session it has just opened.
    assert board.received == []


def test_signing_out_here_tells_the_kiosk(wired):
    base, api, events, board = wired
    httpx.post(f"{base}/login", json=SIGN_IN)
    _wait_for(events, "external_login")

    api.set_active_user("")                     # the Sign out button
    api._told_kiosk.join(timeout=5)
    assert board.received == [{"user": {"name": "Priya Sharma"}}]


def test_a_kiosk_that_is_off_does_not_break_signing_out(wired, monkeypatch):
    base, api, events, _ = wired
    httpx.post(f"{base}/login", json=SIGN_IN)
    _wait_for(events, "external_login")

    monkeypatch.setenv("ASSIST_KIOSK_URL", "http://127.0.0.1:9")
    assert api.set_active_user("")["ok"] is True
    api._told_kiosk.join(timeout=5)
    assert api._active_user == ""
