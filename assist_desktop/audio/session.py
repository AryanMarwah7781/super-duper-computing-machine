"""The voice loop: idle -> wake -> listening -> transcribing -> asking.

    "hey chris"          wake gate fires on a sustained run
    <question>           recording ends when the speaker stops, not on a timer
    -> transcript        faster-whisper, locally
    -> ask()             the same path a typed question takes

Two rules the states exist to enforce:

  The wake word is muted while dictating. "hey chris what is the tire pressure"
  scores 0.95 for its whole length, so an unmuted gate would retrigger on the
  question it is already listening to.

  Only one utterance is in flight. A second wake during transcription is
  ignored rather than queued — an operator who repeats themselves wants the
  latest question answered once, not twice.
"""
from __future__ import annotations

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
        self._speaker = Speaker(on_state=self._emit)
        self._endpointer: Optional[Endpointer] = None
        self._state = VoiceState.OFF
        self._lock = threading.Lock()
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._last_level_sent = 0.0
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
        threading.Thread(target=self._stt.load, daemon=True).start()
        threading.Thread(target=self._speaker.load, daemon=True).start()

        if not self._mic.start():
            log.error("microphone failed to open: %s", self._mic.error)
            self.error = self._mic.error
            self._set_state(VoiceState.OFF, error=self.error)
            return self.status()

        self._unsubscribe = self._mic.subscribe(self._on_frame)
        log.info('microphone open, listening for "hey chris"')
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
        return list_input_devices()

    def set_device(self, index: Optional[int]) -> dict:
        """Switch microphone. Restarts the stream if it is already running,
        because a device cannot be changed underneath an open stream."""
        was_running = self._mic.running
        if was_running:
            self.stop()
        self._mic = Microphone(device=index)
        log.info("microphone set to device %s", index if index is not None else "default")
        if was_running:
            return self.start()
        return self.status()

    def status(self) -> dict:
        return {
            "state": self._state.value,
            "device": self._mic.device,
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
        """Read an answer aloud."""
        return self._speaker.speak(segments)

    def hush(self) -> None:
        self._speaker.stop()

    def _on_wake(self, hit: Detection) -> None:
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
            self._wake.unmute()
            self._set_state(VoiceState.IDLE)
