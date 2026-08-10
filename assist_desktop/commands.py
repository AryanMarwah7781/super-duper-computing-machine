"""Spoken commands that DO something, rather than explain how.

Ported from the old stack's tools.py. "Start spraying" should act; "how do I
start spraying" should answer. Everything below exists to keep those apart.

Three behaviours were paid for in bugs over there, and are kept deliberately:

  Question words come first. "how do i start spraying" contains the phrase
  "start spraying", and substring matching would fire on it. A leading
  question word means the operator is asking ABOUT the command.

  Longest phrase wins, across every command. "fold boom" is a substring of
  "unfold boom", so declaring fold first meant saying "unfold the boom" folded
  it. Sorting by length removes the dependence on declaration order.

  Polite forms are commands. "can you unfold it for me" is an instruction, not
  a question, and an operator with their hands full will phrase it that way.

Two things are done differently here:

  No subprocess. The old handlers shelled out to `python scripts/fold_boom.py`,
  which posted an HTTP request — from a process that was already Python. The
  request is made directly, so failures are catchable and reportable instead of
  vanishing into a child process's stderr.

  No listener when there is nothing to listen across. window_listener.py exists
  to receive an order over the network and append it to a JSON file the
  simulator reads. On one machine that is a Flask server, a socket and a second
  console window standing between a process and a file it can already write.
  Same file, same shape, written directly. See `_deliver_locally`.

  No mishearing aliases. tools.py carried "start spring", "start solution bump",
  "start solution hump" and "start solution dump" as aliases for "start
  spraying" — someone papering over speech recognition errors one transcript at
  a time. That belongs upstream, and now lives there.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from .logs import get as get_logger

log = get_logger("commands")

# Where the simulator listens. The old scripts hardcoded a Windows machine on
# the lab network; this is the same endpoint, made configurable.
DEFAULT_TRIGGER_URL = "http://192.168.94.11:5000/trigger"

# What window_listener.py writes, and what the simulator reads. When the app is
# on the same machine, this file is the whole interface — the HTTP hop exists
# only to cross a network that is not there.
DEFAULT_COMMAND_FILE = r"C:\simulator\voice_commands.json"

_LOOPBACK = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}
_file_lock = threading.Lock()


def trigger_url() -> str:
    """The simulator's address, read now rather than at import.

    This used to be a module constant. api.py imports commands before anything
    imports config -- and config is what reads .env -- so the constant captured
    the default before .env had been loaded, and setting ASSIST_TRIGGER_URL
    there did nothing at all. Orders went to the old lab machine with no error.
    Reading it per send also means the address can change without a restart.
    """
    return os.environ.get("ASSIST_TRIGGER_URL", DEFAULT_TRIGGER_URL)


def trigger_timeout_s() -> float:
    return float(os.environ.get("ASSIST_TRIGGER_TIMEOUT_S", "5"))


def command_file() -> Path:
    return Path(os.environ.get("ASSIST_COMMAND_FILE", DEFAULT_COMMAND_FILE))


def trigger_mode() -> str:
    """`local`, `http`, or `auto` — the default, which means "local when the
    address points at this machine"."""
    mode = (os.environ.get("ASSIST_TRIGGER_MODE") or "auto").strip().lower()
    if mode in ("local", "file"):
        return "local"
    if mode in ("http", "remote", "network"):
        return "http"
    if mode != "auto":
        log.warning("unknown ASSIST_TRIGGER_MODE %r, using auto", mode)
    return "auto"


@lru_cache(maxsize=8)
def is_this_machine(url: str) -> bool:
    """Does this address lead back to the process asking?

    Cached: an order is rare but a DNS lookup on a lab network is not free, and
    a machine's own addresses do not change while it is running.
    """
    host = (urlsplit(url).hostname or "").lower()
    if host in _LOOPBACK:
        return True
    try:
        mine = {info[4][0] for info in
                socket.getaddrinfo(socket.gethostname(), None)}
        mine |= {"127.0.0.1", "::1"}
        theirs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, OSError, UnicodeError):
        # An address that will not resolve is not this machine. Let the HTTP
        # attempt fail and report, rather than guessing local and writing a
        # file nothing reads.
        return False
    return bool(mine & theirs)


def delivery() -> tuple[str, str]:
    """How an order will be delivered, and where. Logged at startup so the
    route is answerable without reading code."""
    mode = trigger_mode()
    local = mode == "local" or (mode == "auto" and is_this_machine(trigger_url()))
    if local:
        return "local", str(command_file())
    return "http", trigger_url()

# A leading question word means they are asking about the command, not issuing
# it. Without this, "how do i start spraying" starts the sprayer.
#
# Note what is NOT here: can, could, would. Those open a polite ORDER —
# "can you unfold the boom" is an instruction, and an operator with their hands
# full will phrase it that way.
_QUESTION_WORDS = {
    "how", "what", "why", "when", "where", "which", "who",
    "is", "are", "do", "does", "should",
}

# ...which leaves "can you tell me how to unfold the boom", a question that
# opens with a polite-order word. These phrases mark asking wherever they
# appear, so the two are separable.
_ASKING = (
    "how do", "how to", "how can", "how should", "how would", "how does",
    "tell me", "explain", "what is", "what are", "walk me through",
    "steps to", "procedure for", "instructions for", "show me how",
)


# What the decoder produces anyway, having already been primed. Only
# command-shaped phrases appear here: "spring" alone is an ordinary word and
# must never be repaired, or "check the spring tension" starts the sprayer.
MISHEARD: dict[str, str] = {
    "start spring": "start_spraying",
    "start spinning": "start_spraying",
    "start speaking": "start_spraying",
    "start solution bump": "start_spraying",
    "start solution dump": "start_spraying",
    "start solution hump": "start_spraying",
    # The confusion is in "spraying", so it survives a change of verb. These
    # are inferred from the same phonetics rather than separately observed.
    "stop spring": "stop_spraying",
    "stop spinning": "stop_spraying",
    "stop speaking": "stop_spraying",
}


@dataclass(frozen=True)
class CommandResult:
    name: str
    spoken: str
    ok: bool
    detail: str = ""


def _normalise(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text)


def _politely(verb: str, thing: str) -> list[str]:
    """The many ways an operator tells the machine to do one thing."""
    forms = [f"{verb} {thing}", f"{verb} the {thing}", f"{verb} it"]
    for lead in ("please", "just", "go ahead and", "go ahead", "yes", "yes please",
                 "you", "can you", "could you", "would you"):
        forms += [f"{lead} {verb} the {thing}", f"{lead} {verb} it"]
    forms += [f"{verb} it for me", f"{verb} the {thing} for me",
              f"{verb} it please", f"{verb} the {thing} please",
              f"can you {verb} the {thing} for me", f"can you {verb} it for me"]
    return forms


COMMANDS: dict[str, dict] = {
    "start_spraying": {
        "phrases": ["start spraying", "begin spraying", "start spray",
                    "start the sprayer", "start solution pump"],
        "payload": "Turn on Spraying",
        "spoken": "Sprayer system activated.",
    },
    "stop_spraying": {
        "phrases": ["stop spraying", "end spraying", "stop spray",
                    "stop the sprayer", "stop solution pump"],
        "payload": "Turn off Spraying",
        "spoken": "Sprayer system deactivated.",
    },
    "unfold_boom": {
        "phrases": _politely("unfold", "boom"),
        "payload": "Unfold the boom",
        "spoken": "Unfolding the boom.",
    },
    "fold_boom": {
        "phrases": _politely("fold", "boom"),
        "payload": "Fold the Boom",
        "spoken": "Folding the boom.",
    },
}


def _deliver_locally(body: dict) -> tuple[bool, str]:
    """Append the order to the file the simulator reads.

    Byte-for-byte what window_listener.py would have written on receiving the
    same POST — same keys, same `received_at` stamp, same whole-array rewrite —
    because the simulator side is reading it and has not changed.

    Rewriting in place rather than writing a temporary file and renaming: the
    listener does exactly this, so the reader already copes with it, and a
    rename can fail outright while the file is held open on Windows.
    """
    path = command_file()
    entry = {**body, "received_at": datetime.now().isoformat()}
    with _file_lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            entries: list = []
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    try:
                        entries = json.loads(text)
                    except json.JSONDecodeError:
                        log.warning("%s is not valid JSON, starting a new list",
                                    path)
                        entries = []
            if not isinstance(entries, list):
                entries = []
            entries.append(entry)
            path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            return True, ""
        except OSError as e:
            return False, f"{type(e).__name__}: {e}"


def _post(body: dict) -> tuple[bool, str]:
    import httpx
    try:
        r = httpx.post(trigger_url(), json=body, timeout=trigger_timeout_s())
        r.raise_for_status()
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _send(payload: str) -> tuple[bool, str]:
    """Tell the simulator, over the network or straight to its file. Never
    raises — a dead simulator must not look like a crash, and the operator
    needs to hear that nothing happened."""
    body = {"timestamp": datetime.now().isoformat(), "command": payload}
    route, where = delivery()
    ok, detail = (_deliver_locally(body) if route == "local" else _post(body))
    if not ok:
        log.warning("order not delivered %s -> %s: %s", route, where, detail)
    return ok, detail


def match(text: str) -> Optional[str]:
    """The command this text issues, or None to let the manual answer it."""
    norm = _normalise(text)
    if not norm:
        return None

    if norm.split(" ", 1)[0] in _QUESTION_WORDS:
        return None
    if any(marker in norm for marker in _ASKING):
        return None

    # Longest phrase first, across every command — see the module docstring.
    candidates = sorted(
        ((_normalise(p), name) for name, c in COMMANDS.items() for p in c["phrases"]),
        key=lambda pair: -len(pair[0]),
    )
    for phrase, name in candidates:
        if phrase and phrase in norm:
            return name

    # Only once nothing legitimate matched. The question guards above still
    # apply, so a misheard question stays a question.
    for phrase, name in sorted(MISHEARD.items(), key=lambda kv: -len(kv[0])):
        if phrase in norm:
            log.info("repaired mishearing %r -> %s", norm, name)
            return name
    return None


def execute(name: str,
            send: Optional[Callable[[str], tuple[bool, str]]] = None) -> CommandResult:
    # Resolved at call time, not bound as a default: a default argument
    # captures the function at import, which makes it impossible to substitute
    # — including in tests, where a real HTTP call to a machine that is not
    # there costs a five second timeout per case.
    send = send or _send
    command = COMMANDS[name]
    ok, detail = send(command["payload"])
    if ok:
        log.info("command %s -> %r", name, command["payload"])
        return CommandResult(name=name, spoken=command["spoken"], ok=True)
    log.warning("command %s FAILED: %s", name, detail)
    return CommandResult(
        name=name,
        spoken="I could not reach the machine. Nothing has changed.",
        ok=False,
        detail=detail,
    )


def match_and_execute(text: str,
                      send: Optional[Callable[[str], tuple[bool, str]]] = None
                      ) -> Optional[CommandResult]:
    name = match(text)
    return execute(name, send=send) if name else None
