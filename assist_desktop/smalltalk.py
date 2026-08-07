"""Deciding what Chris answers and what the manual answers.

Greetings go straight to the language model; anything about the machine goes to
retrieval and is shown in the manual's own words. This module is that fork, and
it is a safety boundary rather than a convenience: a wrong turn toward the
manual costs a few seconds and an "I don't know", while a wrong turn toward the
model can put an invented procedure in front of someone standing next to a
running sprayer.

So the default is retrieval. Only recognised conversation goes to Chris.
"""
from __future__ import annotations

import re

# Say any of these and you are talking about the machine, whatever else is in
# the sentence. Checked first, so "hi, how do i fold the boom" is a boom
# question rather than a greeting.
MACHINE_WORDS = {
    "boom", "booms", "spray", "spraying", "sprayer", "nozzle", "nozzles",
    "tank", "tanks", "solution", "rinse", "pump", "valve", "hydraulic",
    "hydraulics", "engine", "oil", "fuel", "coolant", "filter", "filters",
    "tyre", "tire", "tyres", "tires", "pressure", "wheel", "wheels", "axle",
    "brake", "brakes", "cab", "seat", "mirror", "light", "lights", "beacon",
    "calibrate", "calibration", "exactapply", "commandarm", "commandcenter",
    "boomtrac", "r4045", "manual", "page", "screen", "menu", "display",
    "sensor", "sensors", "switch", "throttle", "transmission", "gear",
    "hitch", "pto", "agitation", "product", "chemical", "rate", "flow",
    "meter", "gauge", "warning", "alarm", "code", "fault", "service",
    "maintenance", "grease", "lubricate", "torque", "capacity", "fold",
    "unfold", "raise", "lower", "transport", "field", "section", "sections",
}

# Recognised conversation. Anchored where a loose match would be wrong:
# "hi" must be the whole greeting, not the "hi" inside "hitch".
_SMALLTALK_PATTERNS = [
    r"^(hi|hello|hey|yo|hiya)\b",
    r"^good (morning|afternoon|evening|day)\b",
    r"\bhow are (you|things|we)\b",
    r"\bhow'?s it going\b",
    r"\bhow do you do\b",
    r"\b(are )?you (there|awake|listening|up|ready)\b",
    r"\bcan you hear me\b",
    r"^(thanks|thank you|thankyou|cheers|ta)\b",
    r"\b(thanks|thank you) (a lot|so much|very much|for that|that helped)\b",
    r"\bappreciate (it|that)\b",
    r"\bwho are you\b",
    r"\bwhat are you\b",
    r"\bwhat'?s your name\b",
    r"\bwhat (can|do) you do\b",
    r"\bintroduce yourself\b",
    r"\btell me about yourself\b",
    r"^(bye|goodbye|see you|see ya|later|good night|goodnight)\b",
    r"^(that'?s all|that is all|nothing|never mind|nevermind|forget it)\b",
]
_SMALLTALK = [re.compile(p) for p in _SMALLTALK_PATTERNS]

# The operator says the wake word and the question in one breath, so Whisper
# hands both over: "hey chris how do i fold the boom". Left in place, every
# question would open like a greeting.
_WAKE = re.compile(r"^\s*(hey|hi|hello|ok|okay)?\s*chris\b[\s,.!?-]*", re.I)


def strip_wake_word(text: str) -> str:
    """Remove a leading "hey chris" so the rest can be judged on its own."""
    return _WAKE.sub("", text or "", count=1).strip()


def _normalise(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_smalltalk(text: str) -> bool:
    """True if Chris should answer this instead of the manual."""
    body = strip_wake_word(text or "")
    if not body.strip():
        # Nothing but the wake word. Someone said "hey chris" and stopped;
        # Chris answers that, the manual cannot.
        return bool((text or "").strip())

    norm = _normalise(body)
    if not norm:
        return False

    # The machine wins over any conversational opening.
    if MACHINE_WORDS & set(norm.split()):
        return False

    return any(p.search(norm) for p in _SMALLTALK)
