"""The voice loop: idle -> wake -> listening -> transcribing -> asking.

    "hey chris"          wake gate fires on a sustained run
    <question>           recording ends when the speaker stops, not on a timer
    -> transcript        faster-whisper, locally
    -> ask()             the same path a typed question takes

Three rules the states exist to enforce:

  The wake word is muted while dictating. "hey chris what is the tire pressure"
  scores 0.95 for its whole length, so an unmuted gate would retrigger on the
  question it is already listening to.

  The wake word is muted while the app is talking. Playback runs on its own
  thread, so `say()` returns the instant it starts and the old code unmuted
  immediately afterwards — with the answer still coming out of the speakers and
  into the microphone a foot away. The gate heard the app, fired, cut the answer
  off mid-sentence and recorded the room. That is the "it started listening
  again by itself" loop. See `_on_speech`.

  Only one utterance is in flight. A second wake during transcription is
  ignored rather than queued — an operator who repeats themselves wants the
  latest question answered once, not twice.
"""
from __future__ import annotations

import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..logs import get as get_logger
from .mic import Microphone, list_input_devices, rms_level
from .speak import Speaker
from .stt import Endpointer, Transcriber, Utterance
from .wake import Detection, WakeWord


class VoiceState(str, Enum):
    OFF = "off"                    # not started, or no microphone
    IDLE = "idle"                  # listening for the wake word
    LISTENING = "listening"        # recording a question
    TRANSCRIBING = "transcribing"  # turning it into text
    ASKING = "asking"              # waiting on the manual; wake stays muted


Emit = Callable[[str, dict], None]
AskFn = Callable[[str], None]
log = get_logger("audio")

# How long the gate stays shut after the last word of an answer. Room echo and
# the tail of a segment arrive slightly after playback reports finished.
ECHO_TAIL_S = float(os.environ.get("ASSIST_ECHO_TAIL_S", "0.6"))

# Set ASSIST_BARGE_IN=1 to keep the gate live while the app is talking, so
# "hey chris" can cut an answer short. Only sane on a headset or a directional
# microphone: on open speakers the app wakes itself. Off by default because
# that is what it did.
BARGE_IN = os.environ.get("ASSIST_BARGE_IN", "0").strip().lower() in ("1", "true", "yes")


class VoiceSession:
    def __init__(self, emit: Emit, ask: AskFn,
                 wake_model_dir: Optional[Path] = None,
                 device: Optional[int] = None) -> None:
        self._emit = emit
        self._ask = ask
        self._mic = Microphone(device=device)
        self._wake = WakeWord(model_dir=wake_model_dir or WakeWord.__init__.__defaults__[0],
                              on_detect=self._on_wake)
        self._stt = Transcriber()
        # Through the session, not straight to the UI: what the speaker is
        # doing decides whether the wake gate may listen.
        self._speaker = Speaker(on_state=self._on_speech)
        self._endpointer: Optional[Endpointer] = None
        self._state = VoiceState.OFF
        self._lock = threading.Lock()
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._last_level_sent = 0.0
        self._spoke_until = 0.0
        # The last listing handed to the picker, so a switch need not re-scan.
        self._devices: list[dict] = []
        self.error: Optional[str] = None

    # -- lifecycle ---------------------------------------------------------
    @property
    def state(self) -> VoiceState:
        return self._state

    def _set_state(self, state: VoiceState, **extra) -> None:
        self._state = state
        self._emit("voice", {"state": state.value, **extra})

    def start(self) -> dict:
        """Load models and open the microphone. Safe to call twice."""
        if self._mic.running:
            return self.status()

        if not self._wake.load():
            log.error("wake model failed to load: %s", self._wake.error)
            self.error = self._wake.error
            self._set_state(VoiceState.OFF, error=self.error)
            return self.status()

        # Whisper and the voice both load lazily: they are the slow parts and
        # the wake word should be live immediately.
        #
        # Only if they are not already loaded. Switching microphone comes
        # through here, and Whisper takes long enough that a switch a few
        # seconds after sign-in used to start a second load while the first
        # was still inside faster-whisper — with Piper reloading beside it and
        # PortAudio being re-initialised for the device scan. Three native
        # libraries reinitialising at once, and the process died without a
        # Python error: "select the AirPods, it loads for a second, it
        # crashes". The loads are individually guarded too; this keeps the
        # threads from being spawned at all.
        if not self._stt.available:
            threading.Thread(target=self._stt.load, daemon=True).start()
        if not self._speaker.available:
            threading.Thread(target=self._speaker.load, daemon=True).start()

        if not self._mic.start():
            log.error("microphone failed to open: %s", self._mic.error)
            self.error = self._mic.error
            self._set_state(VoiceState.OFF, error=self.error)
            return self.status()

        self._unsubscribe = self._mic.subscribe(self._on_frame)
        # The gate's settings decide whether ordinary speech wakes the app, so
        # a log that shows a session waking by itself must also show what it
        # was gating at.
        log.info('microphone open, listening for "hey chris" '
                 "(gate: %d frames above %.2f)",
                 self._wake.required_hot_frames, self._wake.threshold)
        self.error = None
        self._set_state(VoiceState.IDLE)
        return self.status()

    def stop(self) -> dict:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        self._mic.stop()
        self._set_state(VoiceState.OFF)
        return self.status()

    def devices(self) -> list[dict]:
        """The microphones Windows can see right now.

        The stream is closed around the scan and reopened after. PortAudio
        cannot be re-enumerated while a stream is open, and re-enumerating is
        the only way to notice a microphone plugged in since startup -- so the
        choice is a momentary gap in listening, or a permanently stale list.
        """
        was_running = self._mic.running
        if was_running:
            self._mic.stop()
        try:
            self._devices = list_input_devices()
            return self._devices
        finally:
            if was_running:
                self._mic.start()

    def set_device(self, index: Optional[int]) -> dict:
        """Switch microphone. Restarts the stream if it is already running,
        because a device cannot be changed underneath an open stream."""
        was_running = self._mic.running
        if was_running:
            self.stop()
        # Remember what was chosen, not just where it sat. The index is only
        # meaningful until the next device is plugged in or out.
        #
        # From the listing the picker was just shown, rather than a fresh scan:
        # scanning re-initialises PortAudio, and doing that in the middle of a
        # switch — with a Bluetooth headset changing profile at the same moment
        # — is how this crashed. The picker cannot offer a device it did not
        # list, so the cache is the same answer without the teardown.
        name = self._device_name(index)
        self._mic = Microphone(device=index, device_name=name)
        log.info("microphone set to %s (index %s)", name or "default",
                 index if index is not None else "-")
        if was_running:
            return self.start()
        return self.status()

    def _device_name(self, index: Optional[int]) -> Optional[str]:
        """The name behind an index, from the last listing the picker took."""
        if index is None:
            return None
        for device in self._devices or []:
            if device["index"] == index:
                return device["name"]
        # Nothing cached — the caller never opened the picker. Scanning is safe
        # here only because no switch is in flight.
        return next((d["name"] for d in list_input_devices()
                     if d["index"] == index), None)

    def status(self) -> dict:
        return {
            "state": self._state.value,
            "device": self._mic.device,
            "device_name": self._mic.device_name,
            "wake_ready": self._wake.available,
            "stt_ready": self._stt.available,
            "voice_ready": self._speaker.available,
            "speaking": self._speaker.speaking,
            "mic_running": self._mic.running,
            "error": self.error or self._wake.error or self._stt.error,
        }

    # -- the loop ----------------------------------------------------------
    def _on_frame(self, frame: np.ndarray) -> None:
        state = self._state

        if state is VoiceState.IDLE:
            self._wake.feed(frame)
            return

        if state is VoiceState.LISTENING:
            # A level meter, throttled: silence must look like silence so the
            # operator can see the microphone is live.
            now = time.time()
            if now - self._last_level_sent > 0.1:
                self._last_level_sent = now
                self._emit("voice_level", {"level": rms_level(frame)})

            endpointer = self._endpointer
            if endpointer is None:
                return
            utterance = endpointer.feed(frame)
            if utterance is not None:
                self._endpointer = None
                self._set_state(VoiceState.TRANSCRIBING)
                threading.Thread(target=self._transcribe, args=(utterance,),
                                 daemon=True).start()
            elif endpointer.done:
                # It ended but there was too little speech to transcribe. Say so
                # and go back to idle: without this the session sits in
                # LISTENING forever, because a finished endpointer returns
                # nothing on every later frame.
                log.info("nothing to transcribe, back to idle")
                self._endpointer = None
                self._wake.unmute()
                self._set_state(VoiceState.IDLE)

    def say(self, segments) -> bool:
        """Read an answer aloud.

        The gate is shut here, before playback starts, and not in the
        `speaking` callback alone. That callback only arrives once the first
        segment has been synthesised — about 200 ms later — and the session is
        already back in IDLE by then, feeding frames to a live gate. Observed:
        `WAKE score=0.807` in the same second as `speaking 1 segment(s)`, the
        app hearing its own first word.
        """
        if not BARGE_IN:
            self._wake.mute(seconds=120.0)
        return self._speaker.speak(segments)

    def hush(self) -> None:
        self._speaker.stop()

    # -- the app's own voice -----------------------------------------------
    def _on_speech(self, name: str, data: dict) -> None:
        """Playback started or finished. The UI wants to know either way; the
        wake gate has to."""
        if not BARGE_IN:
            if name == "speaking":
                # Long enough to cover any answer. `spoken` ends it — this is
                # only a backstop for a playback thread that dies without
                # reporting, which would otherwise deafen the app for good.
                self._wake.mute(seconds=120.0)
            elif name == "spoken":
                self._spoke_until = time.time()
                self._rearm_wake()
        elif name == "spoken":
            self._spoke_until = time.time()
        self._emit(name, data)

    def _rearm_wake(self, tail: Optional[float] = None) -> None:
        """Listen for "hey chris" again, after a short tail — the end of the
        answer is still crossing the room when playback reports finished."""
        tail = ECHO_TAIL_S if tail is None else tail
        self._wake.unmute()
        if tail > 0:
            self._wake.mute(seconds=tail)

    def _on_wake(self, hit: Detection) -> None:
        # Firing on the heels of the app's own voice is the signature of a
        # microphone hearing the speakers. It should be impossible now; say so
        # loudly if it happens anyway, rather than leaving it to be rediscovered
        # from a screenshot of nonsense transcripts.
        since = time.time() - self._spoke_until
        if since < 1.5:
            log.warning("wake fired %.1fs after the app stopped talking — if "
                        "this repeats, the microphone is hearing the speakers",
                        since)
        # A new question outranks the answer to the last one.
        self._speaker.stop()
        with self._lock:
            if self._state is not VoiceState.IDLE:
                return
            self._endpointer = Endpointer()
        # Mute for the whole utterance: the question would otherwise retrigger
        # the gate that is already listening to it.
        self._wake.mute(seconds=15.0)
        log.info("WAKE score=%.3f frames=%d", hit.score, hit.hot_frames)
        self._emit("wake", {"score": round(hit.score, 3),
                            "hot_frames": hit.hot_frames})
        self._set_state(VoiceState.LISTENING)

    def _transcribe(self, utterance: Utterance) -> None:
        text = ""
        try:
            text = self._stt.transcribe(utterance.audio)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"

        text = (text or "").strip()
        log.info("heard %.1fs (%s) -> %r", utterance.seconds,
                 utterance.ended_on, text)
        self._emit("transcript", {"text": text, "seconds": round(utterance.seconds, 2),
                                  "ended_on": utterance.ended_on})

        try:
            # Whisper hallucinates short filler on near-silence; do not ask it.
            if len(text) >= 3:
                self._set_state(VoiceState.ASKING)
                try:
                    self._ask(text)
                except Exception:
                    log.exception("asking failed")
            else:
                log.info("  too short to ask, ignoring")
        finally:
            # Unmute LAST. Answering takes about ten seconds, and the gate was
            # live throughout it — so a stray "hey chris" fired mid-answer and
            # left the session listening to nobody.
            #
            # And not at all while the answer is still being read out: `say()`
            # returns as soon as playback starts, so this runs with the app
            # still talking. `_on_speech` re-arms the gate when it stops.
            if BARGE_IN or not self._speaker.speaking:
                self._rearm_wake()
            self._set_state(VoiceState.IDLE)
