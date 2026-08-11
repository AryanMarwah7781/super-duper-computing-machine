"""Turning what somebody said into what they meant.

Everything here is a sentence a person might say to a microphone in a
workshop, including the ones Whisper mangles. The cases that matter most are
the refusals: an unclear reply must come back as None, because guessing puts
somebody in the wrong place with no idea why.
"""
from __future__ import annotations

import pytest

from assist_desktop.intents import (
    asks_about_lessons, choice, lesson, looks_like_a_question, normalise,
    spoken_number,
)

LESSONS = [
    {"id": "solution-pump", "title": "Turn On Solution Pump"},
    {"id": "unfold-boom", "title": "Unfold the Boom"},
    {"id": "fold-boom", "title": "Fold the Boom"},
    {"id": "parking-brake", "title": "Release the Parking Brake"},
    {"id": "engine-speed", "title": "Set Engine Speed"},
]

# The three actually installed, with the catalog's own numbering.
CATALOG = [
    {"id": "spray", "title": "Spray Lesson", "number": 1},
    {"id": "groups", "title": "Getting to Know CommandARM", "number": 2},
    {"id": "handle", "title": "Boom Lesson Plan", "number": 3},
]


class TestAsksAboutLessons:
    """The training is ours to answer; the machine is the board's.

    The manual is a procedure corpus for an R4045 and has never heard of a
    lesson plan, so these questions used to retrieve for ten seconds and
    answer "I don't know".
    """

    @pytest.mark.parametrize("said", [
        "what lesson plans are there",
        "what lessons do you have",
        "start lesson 2",
        "open the boom lesson plan",
        "show me my training plan",
        "what can i learn",
    ])
    def test_about_the_training(self, said):
        assert asks_about_lessons(said) is True

    @pytest.mark.parametrize("said", [
        "how do i fold the boom",
        "what is boomtrac pro",
        "how do i change the spray pressure",
        "fold the boom",
    ])
    def test_about_the_machine(self, said):
        # A machine question that happens to be the subject of a lesson still
        # wants the procedure, not a menu.
        assert asks_about_lessons(said) is False


class TestTheInstalledCatalog:
    """The three lessons that are really there, said the way people say them."""

    @pytest.mark.parametrize("said,want", [
        ("lesson 1", "spray"),
        ("lesson 2", "groups"),
        ("lesson 3", "handle"),
        ("number two", "groups"),
        ("the third one", "handle"),
    ])
    def test_by_number(self, said, want):
        assert lesson(said, CATALOG) == want

    @pytest.mark.parametrize("said,want", [
        ("spray lesson", "spray"),
        ("start the spray lesson", "spray"),
        ("getting to know commandarm", "groups"),
        ("boom lesson plan", "handle"),
        ("open the boom lesson plan", "handle"),
    ])
    def test_by_name(self, said, want):
        assert lesson(said, CATALOG) == want

    def test_the_catalog_numbering_survives_a_withheld_lesson(self):
        # The admin withheld the spray lesson. "Lesson two" must still be
        # Getting to Know CommandARM, not the first thing left on the screen.
        without_first = CATALOG[1:]
        assert lesson("lesson 2", without_first) == "groups"
        assert lesson("lesson 3", without_first) == "handle"

    def test_a_number_nobody_has_is_refused(self):
        assert lesson("lesson 9", CATALOG) is None


class TestNormalise:
    def test_strips_punctuation_and_case(self):
        assert normalise("Take me to the Chatbot!") == "take me to the chatbot"

    def test_empty(self):
        assert normalise("") == ""
        assert normalise(None) == ""


class TestChoice:
    @pytest.mark.parametrize("said", [
        "chatbot", "take me to the chatbot", "I want to ask a question",
        "let me talk to it", "open the chatbot",
        "I'd like to learn about the sprayer",
    ])
    def test_asking_for_the_chatbot(self, said):
        assert choice(said) == "chat"

    @pytest.mark.parametrize("said", [
        "lesson", "start lesson", "start my lesson plan",
        "continue my lessons", "take me to lessons", "training please",
        "carry on",
    ])
    def test_asking_for_lessons(self, said):
        assert choice(said) == "lesson"

    @pytest.mark.parametrize("said", [
        "nothing", "neither", "never mind", "no thanks", "not now",
    ])
    def test_declining(self, said):
        assert choice(said) == "cancel"

    def test_silence_and_noise_are_not_a_choice(self):
        for said in ["", "   ", "mm", "uh"]:
            assert choice(said) is None

    def test_something_unrelated_is_not_a_choice(self):
        assert choice("what is the weather") is None
        assert choice("hello there") is None

    def test_the_longest_phrase_wins_when_both_appear(self):
        # Contains "lesson" and "ask". The specific phrase is the intent --
        # the same rule the spoken commands learned the hard way.
        assert choice("start my lesson") == "lesson"
        assert choice("i want to ask a question") == "chat"

    def test_whole_words_only(self):
        # "chat" must not be found inside "chatter".
        assert choice("there was a lot of chatter") is None

    def test_mishearings_whisper_actually_produces(self):
        assert choice("listen plan") == "lesson"
        assert choice("chat bot") == "chat"


class TestSpokenNumber:
    @pytest.mark.parametrize("said,want", [
        ("lesson 3", 3), ("number 12", 12), ("start lesson 1", 1),
    ])
    def test_digits(self, said, want):
        assert spoken_number(said) == want

    @pytest.mark.parametrize("said,want", [
        ("lesson three", 3), ("the first one", 1), ("number five", 5),
        ("lesson twelve", 12), ("the third", 3),
    ])
    def test_words(self, said, want):
        assert spoken_number(said) == want

    def test_digits_beat_words(self):
        assert spoken_number("lesson 4 not two") == 4

    def test_homophones_are_a_last_resort(self):
        # "to" is a preposition far more often than it is the number two.
        assert spoken_number("take me to lesson five") == 5
        assert spoken_number("go to number three") == 3

    def test_a_bare_homophone_is_still_accepted(self):
        # Nothing else to go on, and "to" really is how Whisper writes "two".
        assert spoken_number("to") == 2

    def test_no_number(self):
        assert spoken_number("unfold the boom") is None
        assert spoken_number("") is None

    def test_absurd_numbers_are_ignored(self):
        assert spoken_number("lesson 2026") is None

    def test_a_homophone_inside_a_sentence_is_not_a_number(self):
        # Found the hard way: "start the solution pump lesson FOR me" was read
        # as "lesson four" and opened the parking brake instead -- a different
        # procedure on a real machine, chosen by a preposition.
        assert spoken_number("start the solution pump lesson for me") is None
        assert spoken_number("i want to do the boom one") is None


class TestLooksLikeAQuestion:
    """The guard that keeps the lesson list from swallowing questions.

    Standing at the list, "how do i fold the boom" and "fold the boom" are
    nearly the same words and want opposite things. Only the opening tells
    them apart -- the same rule the spoken commands learned when substring
    matching started the sprayer for somebody asking how to.
    """

    @pytest.mark.parametrize("said", [
        "how do i fold the boom",
        "what is boomtrac pro",
        "where is the solution pump",
        "can you tell me how to unfold the boom",
    ])
    def test_questions_are_left_for_the_manual(self, said):
        assert looks_like_a_question(said) is True

    @pytest.mark.parametrize("said", [
        "fold the boom",
        "lesson two",
        "solution pump",
        "start the parking brake lesson",
    ])
    def test_requests_are_not_questions(self, said):
        assert looks_like_a_question(said) is False

    def test_empty(self):
        assert looks_like_a_question("") is False


class TestLesson:
    def test_by_position_on_the_screen(self):
        assert lesson("lesson 2", LESSONS) == "unfold-boom"
        assert lesson("start the first one", LESSONS) == "solution-pump"

    def test_a_number_past_the_end_is_not_a_lesson(self):
        assert lesson("lesson 40", LESSONS) is None

    def test_by_name(self):
        assert lesson("turn on solution pump", LESSONS) == "solution-pump"
        assert lesson("release the parking brake", LESSONS) == "parking-brake"

    def test_by_partial_name(self):
        assert lesson("solution pump", LESSONS) == "solution-pump"
        assert lesson("engine speed please", LESSONS) == "engine-speed"

    def test_politeness_does_not_hurt_the_match(self):
        assert lesson("can you start the solution pump lesson for me",
                      LESSONS) == "solution-pump"

    def test_fold_and_unfold_are_kept_apart(self):
        # These differ by one word and do opposite things to the machine.
        assert lesson("unfold the boom", LESSONS) == "unfold-boom"
        assert lesson("fold the boom", LESSONS) == "fold-boom"

    def test_an_ambiguous_reply_is_refused_rather_than_guessed(self):
        # "the boom" matches Fold and Unfold equally. Starting the wrong one
        # on a real sprayer is worse than asking again.
        assert lesson("the boom", LESSONS) is None

    def test_nothing_recognisable(self):
        assert lesson("what is the weather", LESSONS) is None
        assert lesson("", LESSONS) is None

    def test_only_stopwords(self):
        assert lesson("the start please", LESSONS) is None

    def test_empty_catalog(self):
        assert lesson("lesson 1", []) is None

    def test_threshold_is_adjustable(self):
        # Half of "Turn On Solution Pump" is "solution pump".
        assert lesson("solution pump", LESSONS, threshold=0.99) is None
        assert lesson("solution pump", LESSONS, threshold=0.4) == "solution-pump"
