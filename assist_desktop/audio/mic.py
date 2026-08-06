"""One microphone, one stream, many listeners.

The wake gate and the recorder both need the same audio, and two processes
cannot open one microphone on Windows. So a single stream runs and fans frames
out to whoever is subscribed.

Everything downstream expects 16 kHz mono int16 in 80 ms frames (1280 samples),
because that is what openwakeword's melspectrogram model was built for.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280          # 80 ms — openwakeword's frame size
Listener = Callable[[np.ndarray], None]


class Microphone:
    def __init__(self, device: Optional[int] = None) -> None:
        self.device = device
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()
        self._stream = None
        self.error: Optional[str] = None

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)
        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)
        return unsubscribe

    def _on_frames(self, indata, _frames, _time, status) -> None:
        if status:
            # Overflows are expected under load and are not worth tearing the
            # stream down for; a dropped 80 ms frame costs one wake sample.
            pass
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(mono)
            except Exception:
                # One bad listener must not kill the audio thread.
                pass

    def start(self) -> bool:
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=FRAME_SAMPLES,
                device=self.device,
                channels=1,
                dtype="int16",
                callback=self._on_frames,
            )
            self._stream.start()
            self.error = None
            return True
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._stream = None
            return False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    @property
    def running(self) -> bool:
        return self._stream is not None


def rms_level(frame: np.ndarray) -> float:
    """0..1 loudness, for a level meter. Silence must read as silence, so the
    operator can see the microphone is live before speaking."""
    if frame.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))))
    return min(1.0, rms / 3000.0)


def list_input_devices() -> list[dict]:
    try:
        import sounddevice as sd
    except Exception:
        return []
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            out.append({"index": i, "name": d["name"],
                        "default": i == sd.default.device[0]})
    return out
