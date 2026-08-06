"""The command layer, and the three bugs it inherited fixes for.

Every one of these was a real failure in the old stack. They are tests now so
the fixes cannot be lost in a rewrite.
"""
from __future__ import annotations

import pytest

from assist_desktop.commands import COMMANDS, execute, match, match_and_execute


def sent(record: list):
    def send(payload: str):
        record.append(payload)
        return True, ""
    return send


def failing(payload: str):
    return False, "ConnectError: simulator unreachable"


# -- asking about a command must never run it -----------------------------

@pytest.mark.parametrize("question", [
    "how do i start spraying",
    "how do i fold the boom",
    "what is the procedure to start spraying",
    "when should i fold the boom",
    "can you tell me how to unfold the boom",
    "should i stop spraying now",
    "why does the boom fold",
])
def test_questions_are_answered_not_executed(question):
    """The whole reason for the question-word guard: these all contain a
    command phrase, and substring matching would fire on every one."""
    assert match(question) is None


# -- but instructions must run --------------------------------------------

@pytest.mark.parametrize("order,expected", [
    ("start spraying", "start_spraying"),
    ("begin spraying", "start_spraying"),
    ("stop spraying", "stop_spraying"),
    ("fold the boom", "fold_boom"),
    ("unfold the boom", "unfold_boom"),
    ("please fold it", "fold_boom"),
    ("go ahead and unfold the boom", "unfold_boom"),
    ("just stop spraying", "stop_spraying"),
    ("unfold it for me", "unfold_boom"),
])
def test_instructions_are_executed(order, expected):
    assert match(order) == expected


def test_politeness_still_counts_as_an_order():
    """An operator with their hands full says 'could you fold the boom' and
    means it as an instruction."""
    assert match("could you fold the boom for me") == "fold_boom"


# -- the substring bug ----------------------------------------------------

@pytest.mark.parametrize("order", [
    "unfold boom",
    "unfold the boom",
    "please unfold the boom",
    "can you unfold it",
])
def test_unfold_is_never_mistaken_for_fold(order):
    """'fold boom' is a substring of 'unfold boom'. Declaring fold first made
    'unfold the boom' FOLD it — the machine did the opposite of what was
    asked. Longest phrase wins, so declaration order cannot matter."""
    assert match(order) == "unfold_boom"


# -- normalisation --------------------------------------------------------

@pytest.mark.parametrize("order", [
    "Start Spraying!",
    "  start   spraying  ",
    "START SPRAYING",
    "start spraying.",
])
def test_punctuation_and_case_do_not_matter(order):
    assert match(order) == "start_spraying"


def test_speech_to_text_phrasing_is_matched():
    """Transcripts arrive as full sentences with capitals and a full stop."""
    assert match("Unfold the boom.") == "unfold_boom"


# -- execution ------------------------------------------------------------

def test_executing_sends_the_payload_the_simulator_expects():
    record: list[str] = []
    result = execute("start_spraying", send=sent(record))
    assert result.ok is True
    assert record == ["Turn on Spraying"]
    assert "activated" in result.spoken.lower()


@pytest.mark.parametrize("name,payload", [
    ("start_spraying", "Turn on Spraying"),
    ("stop_spraying", "Turn off Spraying"),
    ("fold_boom", "Fold the Boom"),
    ("unfold_boom", "Unfold the boom"),
])
def test_payloads_match_the_original_scripts(name, payload):
    """The simulator matches on these strings; they are a wire contract."""
    record: list[str] = []
    execute(name, send=sent(record))
    assert record == [payload]


def test_an_unreachable_simulator_says_nothing_happened():
    """The operator must not be told the boom folded when it did not."""
    result = execute("fold_boom", send=failing)
    assert result.ok is False
    assert "not" in result.spoken.lower()
    assert "simulator unreachable" in result.detail


def test_match_and_execute_returns_none_for_a_question():
    record: list[str] = []
    assert match_and_execute("how do i fold the boom", send=sent(record)) is None
    assert record == [], "a question must not touch the machine"


def test_every_command_has_a_payload_and_something_to_say():
    for name, c in COMMANDS.items():
        assert c["payload"], name
        assert c["spoken"], name
        assert c["phrases"], name


# -- the polite-order versus polite-question distinction -------------------

@pytest.mark.parametrize("order", [
    "can you unfold the boom",
    "could you fold it",
    "would you stop spraying",
    "can you unfold it for me",
])
def test_polite_orders_run(order):
    """'can/could/would' open an instruction as often as a question, so they
    are not treated as question words."""
    assert match(order) is not None


@pytest.mark.parametrize("question", [
    "can you tell me how to unfold the boom",
    "could you explain how to fold the boom",
    "can you walk me through starting spraying",
    "would you show me how to stop spraying",
])
def test_polite_questions_do_not_run(question):
    """...which leaves these: questions that open with a polite-order word.
    They are separated by asking-phrases, not by the first word."""
    assert match(question) is None
