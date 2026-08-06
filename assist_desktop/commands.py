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

  No mishearing aliases. tools.py carried "start spring", "start solution bump",
  "start solution hump" and "start solution dump" as aliases for "start
  spraying" — someone papering over speech recognition errors one transcript at
  a time. That belongs upstream, and now lives there.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from .logs import get as get_logger

log = get_logger("commands")

# Where the simulator listens. The old scripts hardcoded a Windows machine on
# the lab network; this is the same endpoint, made configurable.
TRIGGER_URL = os.environ.get("ASSIST_TRIGGER_URL", "http://192.168.94.11:5000/trigger")
TRIGGER_TIMEOUT_S = float(os.environ.get("ASSIST_TRIGGER_TIMEOUT_S", "5"))

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


def _send(payload: str) -> tuple[bool, str]:
    """Tell the simulator. Never raises — a dead simulator must not look like a
    crash, and the operator needs to hear that nothing happened."""
    import httpx
    body = {"timestamp": datetime.now().isoformat(), "command": payload}
    try:
        r = httpx.post(TRIGGER_URL, json=body, timeout=TRIGGER_TIMEOUT_S)
        r.raise_for_status()
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


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
