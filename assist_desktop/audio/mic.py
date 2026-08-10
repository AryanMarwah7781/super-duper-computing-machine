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
    def __init__(self, device: Optional[int] = None,
                 device_name: Optional[str] = None) -> None:
        self.device = device
        # The name is the real identity. Indices shift the moment anything is
        # plugged in or out, so one captured at selection time can point at a
        # different microphone by the time the stream opens.
        self.device_name = device_name
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

    def resolved_device(self) -> Optional[int]:
        """The index to actually open, worked out now rather than at selection.

        Devices can be plugged in or out between choosing a microphone and
        opening it, and every index after the change shifts.
        """
        if self.device_name is None:
            return self.device
        return resolve_device(self.device_name, self.device)

    def start(self) -> bool:
        if self._stream is not None:
            return True
        # Held for the whole open, and by _refresh() for the whole re-init.
        # Opening a stream while another thread is between _terminate() and
        # _initialize() reads PortAudio state that has been freed: an access
        # violation inside libportaudio64bit.dll, which takes the process with
        # it and leaves nothing in the log.
        with _audio_lock:
            try:
                import sounddevice as sd
                self._stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    blocksize=FRAME_SAMPLES,
                    device=self.resolved_device(),
                    channels=1,
                    dtype="int16",
                    callback=self._on_frames,
                )
                self._stream.start()
                note_stream_opened()
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
                note_stream_closed()

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


def _sd():
    """sounddevice, or None where there is no audio stack at all."""
    try:
        import sounddevice as sd
    except Exception:
        return None
    return sd


_streams = 0
_streams_lock = threading.Lock()
# Serialises opening a stream against re-initialising PortAudio. Both are
# native calls into one global library; overlapping them crashes the process.
_audio_lock = threading.RLock()


def note_stream_opened() -> None:
    global _streams
    with _streams_lock:
        _streams += 1


def note_stream_closed() -> None:
    global _streams
    with _streams_lock:
        _streams = max(0, _streams - 1)


def _refresh(sd) -> None:
    """Ask Windows for the device list again.

    PortAudio enumerates devices once, when it initialises, and serves that
    snapshot for the life of the process. So a microphone plugged in while the
    app is running is invisible to it -- the picker keeps showing the world as
    it was at startup, and only a restart helps. Re-initialising is the only
    way to see current hardware.

    Two hard-won constraints, both from crashing the app on 2026-08-06:

    Never do this while a stream is open. Tearing PortAudio down underneath a
    live callback raised -10000 and killed the picker for the rest of the
    session. The caller stops the microphone first if it wants a rescan.

    Never leave it terminated. The two calls are caught separately, because
    one try/except around both meant a failed _initialize() after a successful
    _terminate() left the audio stack switched off permanently.

    Never overlap it with a stream being opened. The counter below says whether
    a stream IS open; it cannot say one is half-open. `_audio_lock` covers the
    window between "sd.InputStream(...)" being called and the counter going up
    — a window a device switch lands in every time, and where PortAudio died
    with 0xc0000005 on 2026-08-09.
    """
    with _audio_lock:
        with _streams_lock:
            if _streams:
                return
        try:
            sd._terminate()
        except Exception:
            # An old or unusual PortAudio build without these. A stale list is
            # still better than no list -- and nothing has been torn down.
            return
        try:
            sd._initialize()
        except Exception:
            pass


def list_input_devices() -> list[dict]:
    sd = _sd()
    if sd is None:
        return []
    _refresh(sd)
    try:
        devices = sd.query_devices()
    except Exception:
        # PortAudio can be left uninitialised by a failed refresh, or by
        # anything else in the process terminating it. Bring it back rather
        # than reporting no microphones for the rest of the session.
        try:
            sd._initialize()
            devices = sd.query_devices()
        except Exception:
            return []
    out = []
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            out.append({"index": i, "name": d["name"],
                        "default": i == sd.default.device[0]})
    return out


def resolve_device(name: Optional[str], index: Optional[int]) -> Optional[int]:
    """Find a microphone by name, falling back to its index, then the default.

    Names survive what indices do not: plugging a Yeti in pushed the built-in
    array from index 0 to 1, so a stored index quietly started selecting a
    different microphone. Returning None means the system default, which is a
    better answer than recording from whatever now occupies that slot.
    """
    if name is None:
        return index
    sd = _sd()
    if sd is None:
        return index
    try:
        listing = sd.query_devices()
    except Exception:
        return index
    devices = [d for d in enumerate(listing)
               if d[1].get("max_input_channels", 0) > 0]
    for i, d in devices:
        if d["name"] == name:
            return i
    # Some host APIs truncate names (MME caps at 31 characters), so the same
    # microphone can be listed under a shortened name.
    for i, d in devices:
        if d["name"].startswith(name[:31]) or name.startswith(d["name"][:31]):
            return i
    return None
