"""Prove the pipe between the welcome kiosk and this laptop, before the demo.

    python tools/kiosk_check.py                     both directions, read-only
    python tools/kiosk_check.py --login "Priya Sharma"   pretend to be the kiosk
    python tools/kiosk_check.py --logout            end the kiosk's session

Read-only by default: it asks the kiosk who is signed in and asks this laptop
whether it is listening, and changes nothing on either machine. The two flags
send real messages -- `--login` signs somebody in on this laptop exactly as a
card tap does, `--logout` returns the kiosk to its card rail.

Both machines have to be running for a clean result. `--login` works against
the app on its own, which is the useful half when the board is not on the
bench yet.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from assist_desktop import kiosk  # noqa: E402

OK, FAIL = "  OK  ", " FAIL "


def say(status: str, what: str, detail: str = "") -> None:
    print(f"[{status}] {what}" + (f"\n         {detail}" if detail else ""))


def my_addresses() -> list[str]:
    """Every address this machine answers on, so the one in WELCOME_JD_URL on
    the board can be checked against it rather than assumed."""
    try:
        return sorted({info[4][0] for info in
                       socket.getaddrinfo(socket.gethostname(), None)
                       if info[0] == socket.AF_INET})
    except OSError:
        return []


def check_listener(port: int) -> bool:
    """Is this laptop's half up? Asked over the loopback, because a firewall
    prompt that has not been answered is a separate problem from a listener
    that never started."""
    url = f"http://127.0.0.1:{port}/health"
    try:
        r = httpx.get(url, timeout=3)
        r.raise_for_status()
    except Exception as e:
        say(FAIL, f"this laptop is not listening on {port}",
            f"{type(e).__name__}: {e} — is the app running?")
        return False
    say(OK, f"this laptop is listening on {port}", url)
    addresses = ", ".join(my_addresses()) or "unknown"
    print(f"         the board should be sending to one of: {addresses}")
    return True


def check_kiosk() -> bool:
    ok, session = kiosk.who_is_signed_in()
    if not ok:
        say(FAIL, f"the kiosk at {kiosk.kiosk_url()} did not answer",
            session.get("error", ""))
        return False
    user = (session or {}).get("user")
    who = user.get("name") if isinstance(user, dict) else None
    say(OK, f"the kiosk at {kiosk.kiosk_url()} answered",
        f"signed in there: {who or 'nobody'}")
    return True


def send_login(port: int, name: str) -> bool:
    """The message the board sends on a card tap, byte for byte."""
    payload = {
        "timestamp": datetime.now().isoformat(),
        "event": "operator_login",
        "new_user": False,
        "user": {"id": name.strip().lower().replace(" ", "-"), "name": name},
    }
    url = f"http://127.0.0.1:{port}/login"
    try:
        r = httpx.post(url, json=payload, timeout=6)
        r.raise_for_status()
    except Exception as e:
        say(FAIL, f"sign-in was not accepted at {url}", f"{type(e).__name__}: {e}")
        return False
    say(OK, f"sign-in accepted for {name}", json.dumps(r.json()))
    print("         the app should now be greeting them on the chat panel.")
    return True


def send_logout(name: str) -> bool:
    ok, detail = kiosk.report_logout(name)
    if not ok:
        say(FAIL, "the kiosk was not told about the sign-out", detail)
        return False
    say(OK, "the kiosk was told about the sign-out",
        "it should be back on the card rail within about two seconds")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(prog="kiosk_check")
    parser.add_argument("--login", metavar="NAME",
                        help="send a sign-in to this laptop, as the kiosk does")
    parser.add_argument("--logout", action="store_true",
                        help="tell the kiosk the session here has ended")
    parser.add_argument("--name", default="",
                        help="the name to put in the sign-out notice")
    parser.add_argument("--port", type=int, default=kiosk.listen_port())
    args = parser.parse_args()

    print(f"kiosk    {kiosk.kiosk_url()}")
    print(f"here     port {args.port}\n")

    results = [check_listener(args.port), check_kiosk()]
    if args.login:
        results.append(send_login(args.port, args.login))
    if args.logout:
        results.append(send_logout(args.name))

    print()
    if all(results):
        print("Both directions work.")
        return 0
    print("Something is not connected. See above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
