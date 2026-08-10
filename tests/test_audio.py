"""Tests for the voice loop that need no microphone and no models.

The wake gate's thresholds came out of measurement, so the tests pin the
behaviour those measurements justified rather than the numbers themselves.
"""
from __future__ import annotations

import sys
import types

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
    """A gate at the documented values, stated rather than inherited.

    WakeWord's defaults come from the environment, and `.env` is loaded by
    whichever test imports config first — so a local ASSIST_WAKE_FRAMES=2 used
    to change what these tests were testing, depending on collection order.
    """
    kw.setdefault("threshold", 0.8)
    kw.setdefault("required_hot_frames", 3)
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


# -- the session state machine ---------------------------------------------

def test_an_endpointer_reports_done_even_when_it_discards_the_audio():
    """A too-short utterance returns nothing. Without `done`, the session
    cannot tell that apart from 'still recording' and waits forever — which is
    exactly how it hung after a cough."""
    ep = Endpointer()
    for _ in range(6):
        ep.feed(frame(30))
    ep.feed(frame(4000))
    result = None
    for _ in range(14):
        result = ep.feed(frame(30)) or result
    assert result is None, "too short to be a question"
    assert ep.done is True, "the session must be able to see that it ended"


def test_an_endpointer_is_not_done_while_still_recording():
    ep = Endpointer()
    for _ in range(6):
        ep.feed(frame(30))
    for _ in range(4):
        ep.feed(frame(2500))
    assert ep.done is False


# -- the app must not wake itself ------------------------------------------
#
# Found on 2026-08-09 from a session full of transcripts nobody spoke: "Okay.",
# "Next.", "I think you have to stay a little loudly." Playback runs on its own
# thread, so say() returned the instant it started and the gate was unmuted
# with the answer still coming out of the speakers into a microphone a foot
# away. It heard the app, fired, cut the answer off and recorded the room.

import time

from assist_desktop.audio import session as sessionmod
from assist_desktop.audio.session import VoiceSession, VoiceState
from assist_desktop.audio.stt import Utterance


class FakeSpeaker:
    """The real Speaker's surface, with playback under the test's control."""

    def __init__(self, on_state):
        self.on_state = on_state
        self.speaking = False
        self.said: list[list[str]] = []
        self.available = True

    def load(self):
        return True

    def speak(self, segments):
        self.said.append(list(segments))
        self.speaking = True
        self.on_state("speaking", {"index": 0, "total": 1})
        return True

    def finished(self):
        self.speaking = False
        self.on_state("spoken", {"interrupted": False})

    def stop(self):
        if self.speaking:
            self.finished()


@pytest.fixture
def session(monkeypatch):
    events: list[tuple[str, dict]] = []
    s = VoiceSession(emit=lambda n, d: events.append((n, d)), ask=lambda t: None)
    s._speaker = FakeSpeaker(s._on_speech)
    s._wake._model = FakeModel([])
    s.events = events
    return s


def gate_open(s: VoiceSession) -> bool:
    """Would "hey chris" be heard right now? Asked without the side effects of
    a real detection."""
    detector, s._wake.on_detect = s._wake.on_detect, None
    s._wake._model = FakeModel([0.95, 0.95, 0.95])
    try:
        return any(s._wake.feed(frame(500)) is not None for _ in range(3))
    finally:
        s._wake.on_detect = detector
        s._wake._hot = 0
        s._wake._peak = 0.0


def test_the_gate_is_open_when_nothing_is_happening(session):
    assert gate_open(session) is True


def test_the_gate_shuts_while_the_app_is_talking(session):
    session.say(["Sprayer system deactivated."])
    assert gate_open(session) is False


def test_the_gate_reopens_once_the_answer_has_been_read(session):
    session.say(["Sprayer system deactivated."])
    session._speaker.finished()
    session._rearm_wake(tail=0)      # skip the echo tail for the assertion
    assert gate_open(session) is True


def test_a_short_tail_covers_the_room_echo(session):
    session.say(["Sprayer system deactivated."])
    session._speaker.finished()
    assert gate_open(session) is False, "the last words are still in the room"
    assert session._wake._muted_until <= time.time() + sessionmod.ECHO_TAIL_S + 0.5


def test_finishing_a_turn_does_not_open_the_gate_mid_answer(session, monkeypatch):
    """The exact bug: _transcribe's finally ran while playback was still going."""
    monkeypatch.setattr(session._stt, "transcribe", lambda audio: "stop spraying")
    session._ask = lambda text: session.say(["Sprayer system deactivated."])
    session._transcribe(Utterance(audio=np.zeros(1600, dtype=np.int16),
                                  seconds=1.0, speech_seconds=0.8,
                                  ended_on="silence"))
    assert session.state is VoiceState.IDLE
    assert session._speaker.said == [["Sprayer system deactivated."]]
    assert gate_open(session) is False, "it would hear itself and wake again"

    session._speaker.finished()
    session._rearm_wake(tail=0)
    assert gate_open(session) is True


def test_a_silent_answer_reopens_the_gate_immediately(session, monkeypatch):
    """Nothing is spoken — a command with no voice, or Piper missing. There is
    no playback to wait for, so waiting would deafen the app."""
    monkeypatch.setattr(session._stt, "transcribe", lambda audio: "stop spraying")
    session._ask = lambda text: None
    session._transcribe(Utterance(audio=np.zeros(1600, dtype=np.int16),
                                  seconds=1.0, speech_seconds=0.8,
                                  ended_on="silence"))
    session._rearm_wake(tail=0)
    assert gate_open(session) is True


def test_playback_ending_badly_still_reopens_the_gate(session):
    """The speaker reports `spoken` from a finally, including when playback
    failed. If it did not, the app would never listen again."""
    session.say(["something"])
    session._speaker.stop()          # what hush() and a failed stream both do
    session._rearm_wake(tail=0)
    assert gate_open(session) is True


def test_the_ui_still_hears_about_speech(session):
    session.say(["Sprayer system deactivated."])
    session._speaker.finished()
    assert [name for name, _ in session.events] == ["speaking", "spoken"]


def test_barge_in_can_be_turned_back_on(session, monkeypatch):
    """A headset has no feedback path, and interrupting an answer is useful."""
    monkeypatch.setattr(sessionmod, "BARGE_IN", True)
    session.say(["Sprayer system deactivated."])
    assert gate_open(session) is True


# -- the gate must count frames where the measurement counted them ---------
#
# Reported on 2026-08-09: one "hey chris", then it kept waking on the commands
# themselves — "start spraying", "stop spraying" — for four turns with no wake
# word spoken. The module's own measurement separates a wake from an impostor
# by FRAMES ABOVE 0.8, but frames were being counted above 0.6. An impostor
# holding two frames above 0.8 holds five or six above 0.6, clears the required
# three, and fires.

from assist_desktop.audio import wake as wakemod


def test_the_shipped_gate_counts_frames_where_the_measurement_did():
    """Guard against quietly lowering this again: the docstring's separation
    is 'frames above 0.8', so that is what the default has to be."""
    assert wakemod.SCORE_THRESHOLD >= 0.8


def test_an_impostor_does_not_fire_at_the_shipped_default():
    """'the pressure is fine': peaks at 0.93 but holds it for two frames, then
    sits in the 0.6s. Three frames above 0.6 — and it used to wake the app."""
    w, fired = gate([0.93, 0.90, 0.72, 0.68, 0.65, 0.1])
    for _ in range(6):
        w.feed(frame(500))
    assert fired == []


def test_a_real_wake_still_fires_at_the_shipped_default():
    """Measured wake runs above 0.8: 6, 5 and 3 frames."""
    w, fired = gate([0.95, 0.92, 0.88, 0.1])
    for _ in range(4):
        w.feed(frame(500))
    assert len(fired) == 1


def test_lowering_the_threshold_is_what_makes_ordinary_speech_wake_it():
    """The same impostor, gated the way it used to be. This is not a rule the
    app should follow — it is the evidence for why the default moved."""
    w, fired = gate([0.93, 0.90, 0.72, 0.68, 0.65, 0.1], threshold=0.6)
    for _ in range(6):
        w.feed(frame(500))
    assert len(fired) == 1, "0.6 fires on speech that is not the wake word"


def test_the_gate_shuts_before_the_first_word_not_after(session):
    """Observed 17:03:25: `WAKE score=0.807` in the same second as `speaking 1
    segment(s)`. Playback reports `speaking` only after the first segment has
    been synthesised, ~200ms in, and the session is back in IDLE by then — so
    the gate has to be shut by say() itself, before anything is rendered."""
    class SilentSpeaker(FakeSpeaker):
        def speak(self, segments):          # never reports `speaking`
            self.said.append(list(segments))
            self.speaking = True
            return True

    session._speaker = SilentSpeaker(session._on_speech)
    session.say(["Sprayer system activated."])
    assert gate_open(session) is False


def test_a_slow_answer_does_not_outlive_the_mute(session, monkeypatch):
    """Chris took 27 seconds to answer once, and the wake mute set at the wake
    word is 15. The gate must still be shut when the answer finally speaks."""
    monkeypatch.setattr(session._stt, "transcribe", lambda audio: "hey chris")
    session._wake.mute(seconds=15.0)
    session._wake.unmute()                  # as if those 15 seconds had passed
    session._ask = lambda text: session.say(["What can I do for you?"])
    session._transcribe(Utterance(audio=np.zeros(1600, dtype=np.int16),
                                  seconds=1.0, speech_seconds=0.8,
                                  ended_on="silence"))
    assert gate_open(session) is False


# -- switching microphone must not reload the models -----------------------
#
# Reported 2026-08-09: "every time I select AirPods mic it loads for a second
# and crashes". No traceback, no error line — the log just stops and the app
# restarts, which is what a native crash looks like. set_device() restarts the
# session, and start() was reloading openwakeword, faster-whisper and Piper
# every time. Whisper had not finished its FIRST load eight seconds earlier
# (`stt_ready: False` in the log), so the second one began while the first was
# still running, with PortAudio being terminated and re-initialised for the
# device scan at the same moment.

def test_a_model_loads_once_however_many_times_it_is_asked():
    from assist_desktop.audio.stt import Transcriber

    t = Transcriber()
    loads = []
    t._load = lambda: (loads.append(1), t.__setattr__("_model", object()), True)[-1]
    assert t.load() is True
    assert t.load() is True
    assert loads == [1], "a second load would run beside the first, in C"


def test_the_voice_loads_once_however_many_times_it_is_asked():
    from assist_desktop.audio.speak import Speaker

    s = Speaker()
    loads = []
    s._load = lambda: (loads.append(1), s.__setattr__("_voice", object()), True)[-1]
    s.load()
    s.load()
    assert loads == [1]


def test_the_wake_model_loads_once_however_many_times_it_is_asked():
    w = WakeWord()
    loads = []
    w._load = lambda: (loads.append(1), w.__setattr__("_model", FakeModel([])), True)[-1]
    w.load()
    w.load()
    assert loads == [1]


def test_switching_microphone_does_not_reload_anything(session, monkeypatch):
    """The crash, from the top: start(), then start() again as set_device does."""
    started = []
    monkeypatch.setattr(session._mic, "start", lambda: (started.append(1), True)[-1])
    monkeypatch.setattr(session._mic, "subscribe", lambda fn: (lambda: None))
    monkeypatch.setattr(type(session._mic), "running", property(lambda self: False))

    wake_loads, stt_loads, voice_loads = [], [], []
    monkeypatch.setattr(session._wake, "load",
                        lambda: (wake_loads.append(1), True)[-1])
    monkeypatch.setattr(session._stt, "load", lambda: stt_loads.append(1))
    monkeypatch.setattr(type(session._stt), "available",
                        property(lambda self: bool(stt_loads)))
    session._speaker.load = lambda: voice_loads.append(1)

    session.start()
    session.start()          # what picking another microphone does

    assert started == [1, 1], "the audio stream is what reopens"
    assert len(stt_loads) <= 1, "Whisper must not load twice"
    assert len(voice_loads) == 0, "the voice was already loaded"


# -- PortAudio must never be re-initialised under a live stream -------------
#
# Windows Event Log, 2026-08-09, from selecting the AirPods in the picker:
#   19:12:43  faulting module libportaudio64bit.dll  exception 0xc0000005
#   19:13:35  faulting module ntdll.dll              exception 0xc0000374
# An access violation and then heap corruption: PortAudio state being used
# after it was freed. Nothing reaches the Python log, because nothing raises.

def test_playback_counts_as_a_live_stream(monkeypatch):
    """Only microphone streams were counted. An output stream was invisible to
    the guard, so the picker would re-initialise PortAudio while the app was
    speaking through it."""
    import assist_desktop.audio.mic as micmod
    from assist_desktop.audio.speak import Speaker

    seen = []
    monkeypatch.setattr(micmod, "note_stream_opened",
                        lambda: seen.append("open"))
    monkeypatch.setattr(micmod, "note_stream_closed",
                        lambda: seen.append("close"))
    import assist_desktop.audio.speak as speakmod
    monkeypatch.setattr(speakmod, "note_stream_opened", lambda: seen.append("open"))
    monkeypatch.setattr(speakmod, "note_stream_closed", lambda: seen.append("close"))

    class FakeStream:
        def start(self): pass
        def write(self, _): pass
        def stop(self): pass
        def close(self): pass

    fake_sd = types.SimpleNamespace(OutputStream=lambda **kw: FakeStream())
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    s = Speaker()
    s._voice = object()
    monkeypatch.setattr(s, "_render", lambda text: np.zeros(100, dtype=np.int16))
    s._run(["anything"])
    assert seen == ["open", "close"], "playback must be visible to the guard"


def test_switching_device_does_not_rescan_portaudio(session, monkeypatch):
    """A scan re-initialises PortAudio. Doing that mid-switch, while a
    Bluetooth headset is changing profile, is the crash."""
    import assist_desktop.audio.session as sess

    scans = []
    monkeypatch.setattr(sess, "list_input_devices",
                        lambda: (scans.append(1), [{"index": 2,
                                                    "name": "Headset (AirPods Pro - Find My)",
                                                    "default": False}])[-1])
    monkeypatch.setattr(type(session._mic), "running", property(lambda self: False))

    session.devices()                     # the picker opens: one scan
    assert len(scans) == 1
    session.set_device(2)                 # the operator picks: no further scan
    assert len(scans) == 1, "the switch must use the listing already taken"
    assert session._mic.device_name == "Headset (AirPods Pro - Find My)"


def test_a_switch_without_the_picker_still_finds_the_name(session, monkeypatch):
    """Nothing cached — nobody opened the picker. Scanning is safe here."""
    import assist_desktop.audio.session as sess
    monkeypatch.setattr(sess, "list_input_devices",
                        lambda: [{"index": 2, "name": "Headset (AirPods Pro - Find My)",
                                  "default": False}])
    monkeypatch.setattr(type(session._mic), "running", property(lambda self: False))
    session.set_device(2)
    assert session._mic.device_name == "Headset (AirPods Pro - Find My)"
