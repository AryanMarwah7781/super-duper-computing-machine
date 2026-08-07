"""Deciding what Chris answers and what the manual answers.

The split is the safety boundary. Anything about the machine must reach
retrieval and be shown in the manual's own words; only conversation reaches the
language model. A mistake in one direction wastes a few seconds, and a mistake
in the other puts an invented procedure in front of someone standing next to a
sprayer.
"""
from __future__ import annotations

import pytest

from assist_desktop.smalltalk import is_smalltalk, strip_wake_word


# -- conversation goes to Chris -------------------------------------------

@pytest.mark.parametrize("said", [
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "How are you?",
    "how's it going",
    "are you there",
    "you there?",
    "thanks",
    "thank you",
    "thanks, that helped",
    "cheers",
    "who are you",
    "what are you",
    "what's your name",
    "what can you do",
    "what do you do",
    "bye",
    "goodbye",
    "see you later",
])
def test_conversation_reaches_chris(said):
    assert is_smalltalk(said) is True


# -- anything about the machine goes to the manual -------------------------

@pytest.mark.parametrize("said", [
    "how do i fold the boom",
    "what tyre pressure should i run",
    "how do i fill the solution tank",
    "what does the ExactApply nozzle do",
    "engine oil capacity",
    "how do i calibrate the flow meter",
    "where is the rinse tank",
    "show me the CommandArm",
    "what page is the safety section on",
    "hydraulic pressure",
])
def test_machine_questions_reach_the_manual(said):
    assert is_smalltalk(said) is False


def test_a_greeting_wrapped_around_a_machine_question_goes_to_the_manual():
    """'Hi, how do I fold the boom' opens like conversation and is not. The
    machine words decide, not the greeting."""
    assert is_smalltalk("hi, how do i fold the boom") is False
    assert is_smalltalk("hey there, what tyre pressure should i run") is False


def test_an_unknown_sentence_goes_to_the_manual():
    """The default has to be retrieval. Sending an unrecognised question to
    Chris risks an invented answer; sending it to the manual risks 'I don't
    know', which is safe."""
    assert is_smalltalk("the left section keeps cutting out mid pass") is False
    assert is_smalltalk("something is wrong with it") is False


def test_empty_input_is_not_smalltalk():
    assert is_smalltalk("") is False
    assert is_smalltalk("   ") is False


# -- the wake word leaks into transcripts ---------------------------------

@pytest.mark.parametrize("heard,expected", [
    ("hey chris how do i fold the boom", "how do i fold the boom"),
    ("Hey Chris, how are you?", "how are you?"),
    ("chris, what can you do", "what can you do"),
    ("hi chris", ""),
    ("hey chris", ""),
    ("how do i fold the boom", "how do i fold the boom"),
])
def test_the_wake_word_is_stripped_before_deciding(heard, expected):
    """Whisper transcribes the wake word along with the question, because the
    operator says it in one breath. Left in, it makes every question look like
    a greeting."""
    assert strip_wake_word(heard) == expected


def test_a_question_after_the_wake_word_still_routes_correctly():
    assert is_smalltalk("hey chris how do i fold the boom") is False
    assert is_smalltalk("hey chris how are you") is True


def test_the_wake_word_alone_is_conversation():
    """Someone said 'hey chris' and nothing else. Chris should answer, not the
    manual."""
    assert is_smalltalk("hey chris") is True
