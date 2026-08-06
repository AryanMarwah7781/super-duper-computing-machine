"""Speech to text, and knowing when the operator stopped talking.

Endpointing is the part that makes this feel seamless. The old stack recorded
for a fixed 7 seconds every time, so a three-word question still cost seven
seconds before anything else could start. Here the recording ends when speech
ends: energy-based, with a floor calibrated from the room's own noise in the
first moments of capture.

Transcription is local. faster-whisper's base.en runs on the CPU here in about
a second for a short utterance, which beats a round trip to the devkit — and
the devkit's Whisper lives inside LLiMa, which has been unreliable.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .mic import SAMPLE_RATE

MODEL_SIZE = "base.en"

# Whisper decodes toward ordinary English, which is wrong here: it produced
# "start spinning" and "start speaking" for "start spraying", and "feel the
# solution back" for "fill the solution tank". Those are all common words, so
# no amount of after-the-fact repair recovers them — the fix has to happen
# while it is still deciding. This primes the decoder with the machine's own
# vocabulary, which is what initial_prompt is for.
VOCABULARY_PROMPT = (
    "John Deere R4045 self-propelled sprayer. Spraying the field, solution "
    "tank, fill the solution tank, boom, fold the boom, unfold, nozzle, "
    "nozzles, ExactApply, spray system master switch, rate control, "
    "raise lower switch, rinse tank, product pump, agitation, transport "
    "position, engine oil, tire inflation pressure, hydraulic, PTO, "
    "operator station, CommandArm, display, calibration."
)
MAX_UTTERANCE_S = 12.0        # hard stop, so a stuck stream cannot record forever
MIN_UTTERANCE_S = 0.4         # shorter than this is a cough, not a question
SILENCE_TO_END_S = 0.8        # quiet for this long means they finished
LEAD_IN_S = 0.3               # window used to measure the room's noise
NOISE_FLOOR_MIN = 180.0       # below this, a quiet room reads as speech
NOISE_FLOOR_MAX = 600.0       # above this, ordinary speech would read as silence


@dataclass(frozen=True)
class Utterance:
    audio: np.ndarray
    seconds: float            # length of the recording
    speech_seconds: float     # how much of it was above the noise floor
    ended_on: str             # "silence" | "max-length"


class Endpointer:
    """Collects frames until the speaker stops.

    The threshold adapts: the first few frames measure the room, and speech has
    to clear that floor by a margin. A fixed threshold either misses a quiet
    operator or never ends in a loud cab.
    """

    def __init__(self) -> None:
        self._frames: list[np.ndarray] = []
        self._noise: list[float] = []
        self._floor: Optional[float] = None
        self._silent_run = 0.0
        self._spoke = False
        self._elapsed = 0.0
        self._speech = 0.0
        # One Endpointer per utterance. After it completes, further frames
        # belong to the next one — accumulating them produced a second, tiny
        # "utterance" carrying the previous one's speech total.
        self._done = False

    @property
    def done(self) -> bool:
        """True once this utterance has ended — including when it was too short
        to return. The caller must know either way, or it waits forever for an
        utterance that will never arrive."""
        return self._done

    @staticmethod
    def _energy(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))))

    def feed(self, frame: np.ndarray) -> Optional[Utterance]:
        if self._done:
            return None
        seconds = len(frame) / SAMPLE_RATE
        self._elapsed += seconds
        self._frames.append(frame)
        energy = self._energy(frame)

        # First ~300 ms: listen to the room rather than judge it.
        if self._floor is None:
            self._noise.append(energy)
            if self._elapsed >= LEAD_IN_S:
                base = float(np.median(self._noise)) if self._noise else 0.0
                # Clamped at both ends. The ceiling matters: an operator who
                # starts talking the instant the wake word fires puts speech
                # inside the calibration window, and an uncapped floor would
                # then sit above their voice — the recording would never see
                # speech at all and would end as a discarded silence.
                self._floor = min(max(base * 2.5, NOISE_FLOOR_MIN),
                                  NOISE_FLOOR_MAX)
            return None

        if energy > self._floor:
            self._spoke = True
            self._silent_run = 0.0
            self._speech += seconds
        elif self._spoke:
            self._silent_run += seconds

        if self._spoke and self._silent_run >= SILENCE_TO_END_S:
            return self._finish("silence")
        if self._elapsed >= MAX_UTTERANCE_S:
            return self._finish("max-length")
        return None

    def _finish(self, reason: str) -> Optional[Utterance]:
        self._done = True
        audio = np.concatenate(self._frames) if self._frames else np.zeros(0, np.int16)
        seconds = len(audio) / SAMPLE_RATE
        speech = self._speech
        self._frames = []
        # Measure the SPEECH, not the recording. A cough in a quiet room yields
        # a second and a half of audio containing 80 ms of sound; gating on the
        # recording length let that through as a question.
        if speech < MIN_UTTERANCE_S:
            return None
        return Utterance(audio=audio, seconds=seconds, speech_seconds=speech,
                         ended_on=reason)


class Transcriber:
    """faster-whisper, loaded once and reused."""

    def __init__(self, model_size: str = MODEL_SIZE) -> None:
        self.model_size = model_size
        self.error: Optional[str] = None
        self._model = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._model is not None

    def load(self) -> bool:
        try:
            from faster_whisper import WhisperModel
            # int8 on CPU: the accuracy cost is negligible for short commands
            # and it roughly halves the time to a transcript.
            self._model = WhisperModel(self.model_size, device="cpu",
                                       compute_type="int8")
            self.error = None
            return True
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._model = None
            return False

    def transcribe(self, audio: np.ndarray) -> str:
        if self._model is None:
            return ""
        samples = audio.astype(np.float32) / 32768.0
        with self._lock:
            segments, _ = self._model.transcribe(
                samples, language="en", beam_size=1,
                condition_on_previous_text=False,
                initial_prompt=VOCABULARY_PROMPT,
            )
            return " ".join(s.text.strip() for s in segments).strip()
