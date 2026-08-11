"""Chris asking a question and waiting for the answer.

The window races itself by design: a reply and a timeout can both arrive, and
the handler must run exactly once either way. These drive the session's frame
loop directly rather than through a microphone, so the races are reproducible.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from assist_desktop.audio.session import VoiceSession, VoiceState, _Prompt


class FakeWake:
    available, error = True, None

    def __init__(self):
        self.muted_for = None

    def mute(self, seconds=0.0):
        self.muted_for = seconds

    def unmute(self):
        self.muted_for = None

    def feed(self, _frame):
        pass


@pytest.fixture
def session(monkeypatch):
    """A session with the models and microphone stubbed out."""
    s = VoiceSession.__new__(VoiceSession)
    s._emit = lambda *_a, **_k: None
    s._ask = lambda _t: None
    s._wake = FakeWake()
    s._endpointer = None
    s._prompt = None
    s._state = VoiceState.IDLE
    s._lock = __import__("threading").Lock()
    s._last_level_sent = 0.0
    s._spoke_until = 0.0
    s.error = None
    return s


class TestPromptObject:
    def test_deadline_is_absolute(self):
        p = _Prompt("x", 0.05, lambda _t: None)
        assert not p.expired()
        time.sleep(0.06)
        assert p.expired()

    def test_expiry_can_be_asked_about_a_given_moment(self):
        p = _Prompt("x", 10.0, lambda _t: None)
        assert p.expired(time.time() + 11)
        assert not p.expired(time.time() + 9)


class TestListen:
    def test_opens_the_window_without_a_wake_word(self, session):
        assert session.listen(7.0, lambda _t: None) is True
        assert session.state is VoiceState.LISTENING
        assert session._endpointer is not None

    def test_mutes_the_wake_word_for_the_window(self, session):
        # Chris's own question is still in the room, and the gate would
        # otherwise fire on the answer it is already recording.
        session.listen(7.0, lambda _t: None)
        assert session._wake.muted_for is not None
        assert session._wake.muted_for >= 7.0

    def test_refused_when_the_voice_is_off(self, session):
        session._state = VoiceState.OFF
        assert session.listen(7.0, lambda _t: None) is False

    def test_refused_while_a_question_is_already_waiting(self, session):
        assert session.listen(7.0, lambda _t: None) is True
        # Two overlapping questions is a conversation nobody can follow.
        assert session.listen(7.0, lambda _t: None) is False

    def test_refused_while_busy_with_a_real_question(self, session):
        session._state = VoiceState.TRANSCRIBING
        assert session.listen(7.0, lambda _t: None) is False


class TestDelivery:
    def test_the_handler_runs_once(self, session):
        seen = []
        session.listen(7.0, seen.append)
        session._finish_prompt("lesson two")
        assert seen == ["lesson two"]

    def test_a_second_delivery_is_ignored(self, session):
        # The timeout and a real reply race each other; the loser must not
        # answer the same question twice.
        seen = []
        session.listen(7.0, seen.append)
        assert session._finish_prompt("lesson two") is True
        assert session._finish_prompt(None) is False
        assert seen == ["lesson two"]

    def test_delivering_with_nobody_waiting(self, session):
        assert session._finish_prompt("hello") is False

    def test_a_failing_handler_still_ends_the_prompt(self, session):
        def boom(_text):
            raise RuntimeError("the UI went away")

        session.listen(7.0, boom)
        session._finish_prompt("chatbot")      # must not raise
        assert session._prompt is None

    def test_cancelling_delivers_nothing_and_goes_idle(self, session):
        seen = []
        session.listen(7.0, seen.append)
        session.cancel_prompt()
        assert seen == [None]
        assert session._prompt is None
        assert session.state is VoiceState.IDLE

    def test_cancelling_when_nothing_is_waiting_is_safe(self, session):
        session.cancel_prompt()
        assert session._prompt is None


class TestTimeout:
    def test_the_window_closes_on_time(self, session):
        seen = []
        session.listen(0.01, seen.append)
        time.sleep(0.02)
        # A room with a running compressor never goes quiet enough for the
        # endpointer to finish, so the cap is what ends this.
        session._on_frame(np.zeros(320, dtype=np.int16))
        assert seen == [None]
        assert session.state is VoiceState.IDLE

    def test_frames_before_the_deadline_do_not_close_it(self, session):
        seen = []
        session.listen(5.0, seen.append)
        session._on_frame(np.zeros(320, dtype=np.int16))
        assert seen == []
        assert session.state is VoiceState.LISTENING
