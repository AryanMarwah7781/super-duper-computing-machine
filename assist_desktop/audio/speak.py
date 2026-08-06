"""Reading answers aloud, with Piper.

MEASURED: the first synthesis takes ~5.5s and every one after takes ~0.18s —
that is ONNX warming up, not the model being slow. Warm, it runs at about 18x
real time, so a twelve-second answer is synthesised in under a second. The voice
is therefore warmed at load with a throwaway phrase; without that, the first
answer of every session stalls for five seconds and feels broken.

Segments are spoken one at a time, synthesised just ahead of playback. Because
the answers already arrive pre-segmented, the first words start about a fifth of
a second after the answer does rather than after the whole thing is rendered.

Interruption is the other half. An operator who asks a new question mid-answer
wants the new answer, so speaking stops immediately rather than draining a
queue of stale audio.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from ..logs import get as get_logger

log = get_logger("speak")

DEFAULT_VOICE = Path(r"C:\Users\user\Desktop\piper\en_US-lessac-medium.onnx")

# Photo markers and JD part codes must never be read aloud — one cost ~4.6s of
# a voice spelling out a part number letter by letter. The devkit already
# strips them from spoken_segments; this is a belt-and-braces guard for text
# arriving from anywhere else.
_UNSPEAKABLE = ("[PHOTO:", "**", "_Manual page")


class Speaker:
    def __init__(self, voice_path: Path = DEFAULT_VOICE,
                 on_state: Optional[Callable[[str, dict], None]] = None) -> None:
        self.voice_path = Path(voice_path)
        self.on_state = on_state
        self.error: Optional[str] = None
        self._voice = None
        self._sample_rate = 22050
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._voice is not None

    @property
    def speaking(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def load(self) -> bool:
        if not self.voice_path.is_file():
            self.error = f"no voice at {self.voice_path}"
            return False
        try:
            from piper import PiperVoice
            self._voice = PiperVoice.load(str(self.voice_path))
            self._sample_rate = self._voice.config.sample_rate
            # Warm up: the first call pays ONNX initialisation, ~5.5s, and that
            # must not land on the operator's first answer.
            list(self._voice.synthesize("ready"))
            log.info("voice ready (%s, %d Hz)", self.voice_path.name,
                     self._sample_rate)
            self.error = None
            return True
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._voice = None
            log.error("voice failed to load: %s", self.error)
            return False

    # -- playback ----------------------------------------------------------
    def _render(self, text: str) -> np.ndarray:
        chunks = list(self._voice.synthesize(text))
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(
            [np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in chunks])

    def _run(self, segments: Sequence[str]) -> None:
        import sounddevice as sd

        speakable = [s.strip() for s in segments
                     if s.strip() and not s.strip().startswith(_UNSPEAKABLE)]
        if not speakable:
            return

        stream = None
        try:
            stream = sd.OutputStream(samplerate=self._sample_rate, channels=1,
                                     dtype="int16")
            stream.start()
            for i, segment in enumerate(speakable):
                if self._stop.is_set():
                    break
                audio = self._render(segment)
                if self._stop.is_set():
                    break
                if self.on_state:
                    self.on_state("speaking", {"index": i, "total": len(speakable)})
                # Written in slices so a stop lands within ~50ms instead of
                # after the current segment finishes.
                block = self._sample_rate // 20
                for start in range(0, len(audio), block):
                    if self._stop.is_set():
                        break
                    stream.write(audio[start:start + block])
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            log.warning("playback failed: %s", self.error)
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if self.on_state:
                self.on_state("spoken", {"interrupted": self._stop.is_set()})

    def speak(self, segments: Sequence[str]) -> bool:
        """Read these aloud, replacing anything currently being said."""
        if self._voice is None:
            return False
        with self._lock:
            self.stop()
            self._stop = threading.Event()
            log.info("speaking %d segment(s)", len(segments))
            self._thread = threading.Thread(target=self._run, args=(list(segments),),
                                            daemon=True)
            self._thread.start()
        return True

    def stop(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._stop.set()
            self._thread.join(timeout=1.5)
        self._thread = None
