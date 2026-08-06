"""Wake word gate for "hey chris".

MEASURED BEHAVIOUR — read before changing the thresholds.

Scored against Windows-synthesised speech (peak score per phrase):

    0.95  hey chris                       <- wake
    0.95  hey chris what is the tire...   <- wake
    0.93  hey chris                       <- wake
    0.93  the pressure is fine            <- NOT wake
    0.84  christmas is coming             <- NOT wake
    0.01  how do i fill the solution tank
    0.00  everything else tried

Peak score alone cannot separate these: the gap between the quietest wake and
the loudest impostor is 0.005. The confusables are the worst possible ones for
a sprayer — "pressure" is everyday vocabulary here, and "christmas" contains
the wake word.

What does separate them is how long the score stays high:

    frames above 0.8 -- wake: 6, 5, 3   impostors: 2, 2

So detection requires a sustained run, not a single spike. The margin is one
80 ms frame, which is thin, so every detection is logged with its score and
run length: tuning this on real speech needs data, not opinion.

The real fix is retraining the model with hard negatives ("pressure",
"christmas", and the rest of the sprayer vocabulary). This gate makes the model
usable meanwhile; it does not make it good.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..logs import get as get_logger

log = get_logger("wake")

# The three wake models ship in the repo — 3.7 MB total, and the application
# cannot listen without them, so a clone has to include them. Point
# ASSIST_WAKE_DIR at a different set to override.
DEFAULT_MODEL_DIR = Path(
    os.environ.get("ASSIST_WAKE_DIR")
    or Path(__file__).resolve().parent.parent.parent / "assets" / "wakeword"
)

# Tunable without editing code:
#   $env:ASSIST_WAKE_THRESHOLD = "0.5"
#   $env:ASSIST_WAKE_FRAMES    = "2"
# The measured values came from synthetic speech; a real voice in a real room
# will want different ones, and tools/voice_debug.py shows what yours scores.
SCORE_THRESHOLD = float(os.environ.get("ASSIST_WAKE_THRESHOLD", "0.6"))
REQUIRED_HOT_FRAMES = int(os.environ.get("ASSIST_WAKE_FRAMES", "3"))
REFRACTORY_S = 2.0            # ignore further detections for this long
# Report runs that got close but did not fire, so the log can answer "why did
# nothing happen" instead of staying silent.
NEAR_MISS_SCORE = 0.35


@dataclass(frozen=True)
class Detection:
    score: float
    hot_frames: int
    at: float


class WakeWord:
    """Scores each 80 ms frame and fires on a sustained run.

    `on_detect` is called from the audio thread — keep it short and hand off.
    """

    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR,
                 on_detect: Optional[Callable[[Detection], None]] = None,
                 threshold: float = SCORE_THRESHOLD,
                 required_hot_frames: int = REQUIRED_HOT_FRAMES) -> None:
        self.model_dir = Path(model_dir)
        self.on_detect = on_detect
        self.threshold = threshold
        self.required_hot_frames = required_hot_frames
        self.error: Optional[str] = None
        self.enabled = True
        self.last: Optional[Detection] = None

        self._model = None
        self._hot = 0
        self._peak = 0.0
        self._muted_until = 0.0
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._model is not None

    def load(self) -> bool:
        """Load the three-stage chain: mel -> embedding -> hey_chris."""
        needed = ["hey_chris.onnx", "melspectrogram.onnx", "embedding_model.onnx"]
        missing = [f for f in needed if not (self.model_dir / f).is_file()]
        if missing:
            self.error = f"missing wake models: {', '.join(missing)}"
            return False
        try:
            from openwakeword.model import Model
            self._model = Model(
                wakeword_models=[str(self.model_dir / "hey_chris.onnx")],
                melspec_model_path=str(self.model_dir / "melspectrogram.onnx"),
                embedding_model_path=str(self.model_dir / "embedding_model.onnx"),
                inference_framework="onnx",
            )
            self.error = None
            return True
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._model = None
            return False

    def mute(self, seconds: float) -> None:
        """Stop listening for the wake word — used while dictating, so the
        question itself cannot retrigger it (measured: "hey chris what is the
        tire pressure" scores 0.95 all the way through)."""
        with self._lock:
            self._muted_until = max(self._muted_until, time.time() + seconds)
            self._hot = 0
            self._peak = 0.0

    def unmute(self) -> None:
        with self._lock:
            self._muted_until = 0.0
            self._hot = 0
            self._peak = 0.0

    def feed(self, frame: np.ndarray) -> Optional[Detection]:
        if self._model is None or not self.enabled:
            return None
        now = time.time()
        with self._lock:
            if now < self._muted_until:
                return None
        try:
            score = float(self._model.predict(frame)["hey_chris"])
        except Exception:
            return None

        with self._lock:
            if score >= self.threshold:
                self._hot += 1
                self._peak = max(self._peak, score)
                if self._hot >= self.required_hot_frames:
                    hit = Detection(score=self._peak, hot_frames=self._hot, at=now)
                    self._hot = 0
                    self._peak = 0.0
                    self._muted_until = now + REFRACTORY_S
                    self.last = hit
                else:
                    return None
            else:
                # A run just ended. If it got anywhere near, say so — this is
                # the difference between "the microphone is dead" and "you were
                # one frame short of firing".
                if self._peak >= NEAR_MISS_SCORE:
                    log.info("near miss: peak=%.3f ran=%d (need %d frames above "
                             "%.2f)", self._peak, self._hot,
                             self.required_hot_frames, self.threshold)
                self._hot = 0
                self._peak = 0.0
                return None

        if self.on_detect:
            self.on_detect(hit)
        return hit
