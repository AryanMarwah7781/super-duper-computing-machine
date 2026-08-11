"""Turning a spoken reply into a choice.

Chris asks a question and the operator answers out loud. This is the part that
decides what they meant. It is pure text in, decision out -- no audio, no
state -- because every interesting case here is a sentence somebody said, and
those are cheap to write down and expensive to reproduce in front of a
microphone.

Two questions get asked:

    "chatbot or lesson plan?"        -> choice(text)
    "which lesson?"                  -> lesson(text, catalog)

Both may answer "I did not catch that", and that is a first-class outcome
rather than a failure. Guessing between two options when the room was noisy
puts somebody in the wrong place with no idea why; asking again costs seven
seconds.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from . import commands

# Whisper is asked to transcribe a short reply in a workshop, so these are
# matched against what it actually produces rather than what somebody would
# type. "Lesson" comes back as "listen" often enough to be worth naming.
CHAT_PHRASES = (
    "chatbot", "chat bot", "chat", "talk", "ask", "question", "sprayer",
    "learn about the sprayer", "learn about sprayer", "manual",
    "take me to chatbot", "take me to the chatbot", "open the chatbot",
    "i want to ask", "ask a question", "ask something", "chatting",
)

LESSON_PHRASES = (
    "lesson", "lessons", "lesson plan", "start lesson", "start a lesson",
    "start my lesson", "continue lesson", "continue my lesson",
    "training", "practice", "practise", "course",
    "take me to lessons", "open lessons", "carry on", "continue",
    # Heard from Whisper in the workshop for "lesson".
    "listen plan", "less on",
)

# Said in reply to "chatbot or lesson plan?" and meaning neither.
CANCEL_PHRASES = (
    "nothing", "neither", "cancel", "never mind", "nevermind", "no thanks",
    "no thank you", "stop", "go away", "not now", "wait",
)

NUMBER_WORDS = {
    "one": 1, "first": 1, "won": 1,
    "two": 2, "second": 2, "to": 2, "too": 2,
    "three": 3, "third": 3, "tree": 3,
    "four": 4, "fourth": 4, "for": 4, "fore": 4,
    "five": 5, "fifth": 5,
    "six": 6, "sixth": 6, "sicks": 6,
    "seven": 7, "seventh": 7,
    "eight": 8, "eighth": 8, "ate": 8,
    "nine": 9, "ninth": 9,
    "ten": 10, "tenth": 10,
    "eleven": 11, "eleventh": 11,
    "twelve": 12, "twelfth": 12,
}

_WORD = re.compile(r"[a-z0-9]+")

# Dropped before matching a lesson name. "the" and "how do i" carry no
# information about which lesson was meant, and leaving them in makes a short
# title look less similar to what was said than it really is.
STOPWORDS = frozenset({
    "the", "a", "an", "to", "for", "of", "on", "in", "and", "my", "me",
    "please", "lesson", "number", "start", "open", "begin", "do", "how", "i",
    "want", "take", "go", "show", "chris", "hey", "can", "you", "let", "us",
    "lets", "would", "like",
})


def normalise(text: str) -> str:
    """Lower case, words only, single-spaced."""
    return " ".join(_WORD.findall((text or "").lower()))


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _contains_phrase(said: str, phrase: str) -> bool:
    """Whole-word containment, so "chat" does not match "chatter"."""
    return f" {phrase} " in f" {said} "


def choice(text: str) -> Optional[str]:
    """"chat", "lesson", "cancel", or None when it was not clear.

    The longest matching phrase wins, across both options. "start lesson"
    contains neither option's short word by accident, but "i want to ask about
    the lesson" contains both -- and the longer, more specific phrase is the
    one that carries the intent. This is the same rule the spoken commands
    use, and it was paid for there: with declaration order deciding, "unfold
    the boom" folded it.
    """
    said = normalise(text)
    if not said:
        return None

    best: tuple[int, Optional[str]] = (0, None)
    for name, phrases in (("chat", CHAT_PHRASES), ("lesson", LESSON_PHRASES),
                          ("cancel", CANCEL_PHRASES)):
        for phrase in phrases:
            if len(phrase) > best[0] and _contains_phrase(said, phrase):
                best = (len(phrase), name)
    return best[1]


def spoken_number(text: str) -> Optional[int]:
    """The lesson number in a spoken reply, if there is one.

    Digits win over words: "lesson 2" is unambiguous, while "two" also arrives
    as "to" and "too" from a decoder that had no reason to expect a number.
    Those homophones are accepted, but only when nothing clearer is present.
    """
    words = _words(text)
    for word in words:
        if word.isdigit():
            value = int(word)
            if 1 <= value <= 99:
                return value

    homophones = {"to", "too", "for", "fore", "won", "ate", "tree", "sicks"}
    for i, word in enumerate(words):
        if word not in NUMBER_WORDS or word in homophones:
            continue
        # "one" is a pronoun as often as it is a number. After a stopword it
        # counts -- "lesson one", "number one" -- but after a real word it is
        # standing in for that word: "the boom one" means the boom lesson, and
        # reading it as lesson 1 opens the solution pump instead.
        if word == "one" and i > 0 and words[i - 1] not in STOPWORDS:
            continue
        return NUMBER_WORDS[word]

    # A homophone only counts when it is the entire reply. In a sentence they
    # are function words: "start the solution pump lesson FOR me" read as
    # "lesson four" and opened the parking brake instead -- a different
    # procedure on a real machine, chosen by a preposition.
    if len(words) == 1 and words[0] in NUMBER_WORDS:
        return NUMBER_WORDS[words[0]]
    return None


# Said about the training itself rather than about the machine. These never
# reach the manual: it is a procedure corpus for an R4045 and has never heard
# of a lesson plan, so "what lesson plans are there" spent ten seconds
# retrieving and answered "I don't know".
LESSON_TOPIC_PHRASES = (
    "lesson", "lessons", "lesson plan", "lesson plans", "lesson number",
    "training plan", "my training", "course", "curriculum",
    "what can i learn", "what should i learn",
    # What Whisper makes of them.
    "listen plan", "listen plans",
)


def asks_about_lessons(text: str) -> bool:
    """Is this about the training, rather than about the machine?

    Deliberately narrow. "how do i fold the boom" is a manual question that
    happens to be the subject of a lesson, and answering it with a menu would
    be useless to somebody standing at the sprayer.
    """
    said = normalise(text)
    return any(_contains_phrase(said, phrase) for phrase in LESSON_TOPIC_PHRASES)


def looks_like_a_question(text: str) -> bool:
    """Asking ABOUT a lesson, rather than asking for it.

    Standing on the lesson list and saying "how do I fold the boom" is a
    question for the manual, not a request to start the Fold the Boom lesson --
    the words are almost identical and only the opening tells them apart.
    This is the same guard the spoken commands use, and for the same reason:
    there, substring matching started the sprayer when somebody asked how to.
    """
    said = normalise(text)
    if not said:
        return False
    if said.split(" ", 1)[0] in commands._QUESTION_WORDS:
        return True
    return any(marker in said for marker in commands._ASKING)


def _score(said: set[str], title: set[str]) -> float:
    """How much of a lesson's title was actually said, 0..1.

    Measured against the title rather than against what was said: an operator
    who adds "please can you start" should not score lower than one who did
    not. Every word of a short title being present is a strong signal; half
    the words of a long one is not.
    """
    if not title:
        return 0.0
    return len(said & title) / len(title)


def lesson(text: str, lessons: Iterable[dict],
           threshold: float = 0.6) -> Optional[str]:
    """The id of the lesson that was asked for, or None.

    `lessons` are dicts with at least `id` and `title`, in the order they are
    shown -- a spoken number refers to the position on the screen, because
    that is the only numbering the operator can see.

    None rather than a guess. Starting the wrong procedure on a real sprayer
    is worse than asking again.
    """
    items = list(lessons)
    if not items or not (text or "").strip():
        return None

    number = spoken_number(text)
    if number is not None:
        # The catalog's own numbering when it has one, so "lesson two" means
        # the same lesson whether or not the admin withheld lesson one.
        for item in items:
            if item.get("number") == number:
                return item.get("id")
        if 1 <= number <= len(items):
            return items[number - 1].get("id")
        return None

    said = set(_words(text)) - STOPWORDS
    if not said:
        return None

    best_id, best_score, runner_up = None, 0.0, 0.0
    for item in items:
        title = set(_words(item.get("title", ""))) - STOPWORDS
        score = _score(said, title)
        if score > best_score:
            best_id, best_score, runner_up = item.get("id"), score, best_score
        elif score > runner_up:
            runner_up = score

    if best_score < threshold:
        return None
    # A tie is not an answer. Two lessons matching equally well means the
    # words that would tell them apart were the ones that did not survive the
    # room, and picking the first is picking at random.
    if best_score - runner_up < 1e-9:
        return None
    return best_id
