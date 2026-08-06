"""Tests for the voice loop that need no microphone and no models.

The wake gate's thresholds came out of measurement, so the tests pin the
behaviour those measurements justified rather than the numbers themselves.
"""
from __future__ import annotations

import numpy as np
import pytest

from assist_desktop.audio.mic import rms_level
from assist_desktop.audio.stt import Endpointer
from assist_desktop.audio.wake import Detection, WakeWord

FRAME = 1280


def frame(amplitude: float) -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.normal(0, amplitude, FRAME)).astype(np.int16)


class FakeModel:
    """Stands in for openwakeword, returning a scripted score sequence."""

    def __init__(self, scores):
        self.scores = list(scores)

    def predict(self, _frame):
        return {"hey_chris": self.scores.pop(0) if self.scores else 0.0}


def gate(scores, **kw) -> tuple[WakeWord, list[Detection]]:
    fired: list[Detection] = []
    w = WakeWord(on_detect=fired.append, **kw)
    w._model = FakeModel(scores)
    return w, fired


# -- the wake gate ---------------------------------------------------------

def test_a_single_high_frame_does_not_fire():
    """A lone spike is what 'the pressure is fine' looks like."""
    w, fired = gate([0.95, 0.1, 0.1, 0.1])
    for _ in range(4):
        w.feed(frame(500))
    assert fired == []


def test_two_high_frames_do_not_fire():
    """Measured: the loudest impostors held above 0.8 for two frames."""
    w, fired = gate([0.95, 0.92, 0.1, 0.1])
    for _ in range(4):
        w.feed(frame(500))
    assert fired == []


def test_three_sustained_frames_fire():
    """Measured: real wake utterances held for three frames or more."""
    w, fired = gate([0.95, 0.92, 0.91, 0.1])
    for _ in range(4):
        w.feed(frame(500))
    assert len(fired) == 1
    assert fired[0].hot_frames == 3
    assert fired[0].score == pytest.approx(0.95)


def test_the_run_must_be_consecutive():
    """High, low, high, high is not a sustained utterance."""
    w, fired = gate([0.95, 0.2, 0.93, 0.94, 0.1])
    for _ in range(5):
        w.feed(frame(500))
    assert fired == []


def test_quiet_speech_never_fires():
    w, fired = gate([0.4] * 10)
    for _ in range(10):
        w.feed(frame(500))
    assert fired == []


def test_refractory_stops_an_immediate_second_trigger():
    w, fired = gate([0.9] * 12)
    for _ in range(12):
        w.feed(frame(500))
    assert len(fired) == 1, "one utterance must not fire twice"


def test_muting_suppresses_detection():
    """The question itself scores as high as the wake word, so the gate is
    muted while dictating."""
    w, fired = gate([0.95, 0.95, 0.95, 0.95])
    w.mute(seconds=60)
    for _ in range(4):
        w.feed(frame(500))
    assert fired == []


def test_unmute_restores_detection():
    w, fired = gate([0.95, 0.95, 0.95])
    w.mute(seconds=60)
    w.unmute()
    for _ in range(3):
        w.feed(frame(500))
    assert len(fired) == 1


def test_threshold_is_tunable():
    w, fired = gate([0.6, 0.6, 0.6], threshold=0.5)
    for _ in range(3):
        w.feed(frame(500))
    assert len(fired) == 1


def test_missing_models_reports_rather_than_raises(tmp_path):
    w = WakeWord(model_dir=tmp_path)
    assert w.load() is False
    assert "missing wake models" in (w.error or "")
    assert w.available is False


# -- endpointing -----------------------------------------------------------

def test_recording_ends_after_the_speaker_stops():
    ep = Endpointer()
    result = None
    for _ in range(6):          # ~0.5s calibrating on quiet room
        result = ep.feed(frame(30)) or result
    for _ in range(12):         # ~1s of speech
        result = ep.feed(frame(2500)) or result
    assert result is None, "must not end while they are still talking"
    for _ in range(14):         # ~1.1s of silence
        result = ep.feed(frame(30)) or result
    assert result is not None
    assert result.ended_on == "silence"


def test_a_long_utterance_is_cut_off_rather_than_recorded_forever():
    ep = Endpointer()
    result = None
    for _ in range(200):        # 16s of continuous speech
        result = ep.feed(frame(2500))
        if result:
            break
    assert result is not None
    assert result.ended_on == "max-length"
    assert result.seconds <= 12.5


def test_a_cough_is_not_an_utterance():
    """One blip in a quiet room still produces ~1.4s of recording. Gating on
    the recording length let that through; the gate measures speech."""
    ep = Endpointer()
    result = None
    for _ in range(6):
        result = ep.feed(frame(30)) or result
    result = ep.feed(frame(4000)) or result    # one loud blip
    for _ in range(14):
        result = ep.feed(frame(30)) or result
    assert result is None, "too short to be a question"


def speak_then_stop(ep: Endpointer, loud_frames=12, quiet_frames=14):
    """Calibrate on a quiet room, talk, then stop — returns the utterance."""
    for _ in range(6):
        ep.feed(frame(30))
    for _ in range(loud_frames):
        if (u := ep.feed(frame(2500))) is not None:
            return u
    for _ in range(quiet_frames):
        if (u := ep.feed(frame(30))) is not None:
            return u
    return None


def test_speech_time_is_measured_separately_from_recording_time():
    result = speak_then_stop(Endpointer())
    assert result is not None
    assert result.speech_seconds < result.seconds
    assert result.speech_seconds >= 0.4


def test_the_endpointer_is_single_use():
    """session.py drops it after each utterance; feeding it again must not
    manufacture a second one carrying the first one's speech total."""
    ep = Endpointer()
    first = speak_then_stop(ep)
    assert first is not None
    for _ in range(40):
        assert ep.feed(frame(2500)) is None


def test_silence_alone_never_completes():
    ep = Endpointer()
    for _ in range(60):
        assert ep.feed(frame(20)) is None


def test_speaking_immediately_after_the_wake_word_still_records():
    """The calibration window can contain speech, because operators answer the
    wake word at once. An uncapped noise floor would then sit above their voice
    and the whole question would be discarded as silence."""
    ep = Endpointer()
    result = None
    for _ in range(30):                    # talking from the very first frame
        if (result := ep.feed(frame(2500))) is not None:
            break
    for _ in range(14):
        if result is None:
            result = ep.feed(frame(30))
    assert result is not None, "speech during calibration must not blind the gate"
    assert result.speech_seconds > 0.4


# -- level meter -----------------------------------------------------------

def test_silence_reads_as_silence():
    assert rms_level(np.zeros(FRAME, dtype=np.int16)) == 0.0


def test_loud_audio_reads_high_and_is_clamped():
    assert rms_level(frame(9000)) == 1.0


def test_level_rises_with_volume():
    assert rms_level(frame(300)) < rms_level(frame(1500))
