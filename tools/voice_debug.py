"""Live view of the voice path, for when "hey chris" does nothing.

    .venv\\Scripts\\python tools\\voice_debug.py

Shows, in real time:

    input device      which microphone is actually open
    level             is audio arriving at all
    wake score        what the model thinks, every 80 ms
    hot frames        how close a run got to firing
    detections        what fired, with score and run length

The thresholds are live sliders on purpose. Detection needs a sustained run
because peak score alone cannot separate "hey chris" (0.95) from "the pressure
is fine" (0.93) — see assist_desktop/audio/wake.py. The usable margin is one
80 ms frame, so the right values are the ones your voice and your room produce,
not the ones a synthetic test produced.

Standalone: it opens its own microphone, so close the main app first or pick a
different device — Windows will not hand the same one to both.
"""
from __future__ import annotations

import queue
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from assist_desktop.audio.mic import (  # noqa: E402
    Microphone,
    list_input_devices,
    rms_level,
)
from assist_desktop.audio.wake import DEFAULT_MODEL_DIR, WakeWord  # noqa: E402

BG = "#0b0b0d"
FG = "#e7e7ea"
DIM = "#8b8b94"
BRAND = "#4A93D9"
GOOD = "#3ddc84"
HOT = "#ffb020"
FIRE = "#ff5c5c"


class Meter(tk.Canvas):
    """A horizontal bar with an optional peak-hold marker and threshold line."""

    def __init__(self, parent, width=440, height=22, colour=BRAND):
        super().__init__(parent, width=width, height=height, bg="#1b1b20",
                         highlightthickness=0)
        # NOT _w/_h: Tkinter stores the widget's own path name in self._w, and
        # shadowing it makes every later canvas call fail with
        # 'invalid command name'.
        self._width, self._height, self._colour = width, height, colour
        self._bar = self.create_rectangle(0, 0, 0, height, fill=colour, width=0)
        self._mark = self.create_line(0, 0, 0, height, fill="#ffffff", width=2,
                                      state="hidden")
        self._thresh = self.create_line(0, 0, 0, height, fill=FIRE, width=1,
                                        state="hidden")

    def set(self, value: float, peak: float | None = None,
            threshold: float | None = None, colour: str | None = None):
        value = max(0.0, min(1.0, value))
        self.coords(self._bar, 0, 0, self._width * value, self._height)
        if colour:
            self.itemconfig(self._bar, fill=colour)
        if peak is None:
            self.itemconfig(self._mark, state="hidden")
        else:
            x = self._width * max(0.0, min(1.0, peak))
            self.coords(self._mark, x, 0, x, self._height)
            self.itemconfig(self._mark, state="normal")
        if threshold is None:
            self.itemconfig(self._thresh, state="hidden")
        else:
            x = self._width * threshold
            self.coords(self._thresh, x, 0, x, self._height)
            self.itemconfig(self._thresh, state="normal")


class VoiceDebug:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Voice debug — hey chris")
        root.configure(bg=BG)
        root.geometry("560x520")
        root.attributes("-topmost", True)

        self.q: queue.Queue = queue.Queue()
        self.mic: Microphone | None = None
        self.wake: WakeWord | None = None
        self.devices = list_input_devices()
        self.level_peak = 0.0
        self.score_peak = 0.0
        self.peak_decay = time.time()
        self.frames = 0
        self.hot_run = 0

        pad = {"padx": 14}
        tk.Label(root, text="INPUT DEVICE", bg=BG, fg=DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(14, 2), **pad)
        names = [f"[{d['index']}] {d['name'][:46]}" + ("  (default)" if d["default"] else "")
                 for d in self.devices]
        self.device_box = ttk.Combobox(root, values=names, state="readonly", width=62)
        if names:
            default = next((i for i, d in enumerate(self.devices) if d["default"]), 0)
            self.device_box.current(default)
        self.device_box.pack(anchor="w", **pad)

        row = tk.Frame(root, bg=BG)
        row.pack(anchor="w", pady=10, **pad)
        self.button = tk.Button(row, text="Start listening", command=self.toggle,
                                bg=BRAND, fg="#08121c", relief="flat",
                                font=("Segoe UI", 10, "bold"), padx=16, pady=6)
        self.button.pack(side="left")
        self.status = tk.Label(row, text="stopped", bg=BG, fg=DIM,
                               font=("Segoe UI", 9))
        self.status.pack(side="left", padx=12)

        tk.Label(root, text="MICROPHONE LEVEL  — moves when sound reaches the app",
                 bg=BG, fg=DIM, font=("Segoe UI", 8, "bold")).pack(anchor="w",
                                                                   pady=(8, 2), **pad)
        self.level_meter = Meter(root, colour=GOOD)
        self.level_meter.pack(anchor="w", **pad)
        self.level_text = tk.Label(root, text="0.000", bg=BG, fg=FG,
                                   font=("Consolas", 9))
        self.level_text.pack(anchor="w", **pad)

        tk.Label(root, text='WAKE SCORE  — say "hey chris"', bg=BG, fg=DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(10, 2), **pad)
        self.score_meter = Meter(root, colour=BRAND)
        self.score_meter.pack(anchor="w", **pad)
        self.score_text = tk.Label(root, text="0.000   peak 0.000   hot 0",
                                   bg=BG, fg=FG, font=("Consolas", 9))
        self.score_text.pack(anchor="w", **pad)

        tune = tk.Frame(root, bg=BG)
        tune.pack(anchor="w", pady=(12, 0), **pad)
        tk.Label(tune, text="threshold", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w")
        self.threshold = tk.DoubleVar(value=0.8)
        tk.Scale(tune, from_=0.1, to=0.99, resolution=0.01, orient="horizontal",
                 variable=self.threshold, length=180, bg=BG, fg=FG,
                 troughcolor="#1b1b20", highlightthickness=0,
                 command=self._retune).grid(row=1, column=0)
        tk.Label(tune, text="frames needed", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).grid(row=0, column=1, sticky="w", padx=(24, 0))
        self.needed = tk.IntVar(value=3)
        tk.Scale(tune, from_=1, to=8, orient="horizontal", variable=self.needed,
                 length=140, bg=BG, fg=FG, troughcolor="#1b1b20",
                 highlightthickness=0, command=self._retune).grid(row=1, column=1,
                                                                  padx=(24, 0))

        tk.Label(root, text="DETECTIONS", bg=BG, fg=DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(12, 2), **pad)
        self.log = tk.Listbox(root, height=6, bg="#141418", fg=FG, relief="flat",
                              font=("Consolas", 9), highlightthickness=0)
        self.log.pack(fill="x", **pad)

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self.tick)

    # -- audio thread ------------------------------------------------------
    def _on_frame(self, frame: np.ndarray) -> None:
        level = rms_level(frame)
        score = 0.0
        if self.wake is not None and self.wake._model is not None:
            try:
                score = float(self.wake._model.predict(frame)["hey_chris"])
            except Exception:
                score = 0.0
            self.wake.feed(frame)
        self.q.put((level, score))

    def _on_detect(self, hit) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.q.put(("FIRED", f"{stamp}  score={hit.score:.3f}  frames={hit.hot_frames}"))

    def _retune(self, _=None) -> None:
        if self.wake is not None:
            self.wake.threshold = float(self.threshold.get())
            self.wake.required_hot_frames = int(self.needed.get())

    # -- control -----------------------------------------------------------
    def toggle(self) -> None:
        if self.mic is not None:
            self.close_stream()
            return

        self.wake = WakeWord(model_dir=DEFAULT_MODEL_DIR, on_detect=self._on_detect,
                             threshold=float(self.threshold.get()),
                             required_hot_frames=int(self.needed.get()))
        if not self.wake.load():
            self.status.config(text=self.wake.error or "wake model failed", fg=FIRE)
            self.wake = None
            return

        index = self.device_box.current()
        device = self.devices[index]["index"] if 0 <= index < len(self.devices) else None
        self.mic = Microphone(device=device)
        self.mic.subscribe(self._on_frame)
        if not self.mic.start():
            self.status.config(text=self.mic.error or "microphone failed", fg=FIRE)
            self.mic = None
            return

        self.frames = 0
        self.status.config(text="listening", fg=GOOD)
        self.button.config(text="Stop")

    def close_stream(self) -> None:
        if self.mic is not None:
            self.mic.stop()
            self.mic = None
        self.wake = None
        self.status.config(text="stopped", fg=DIM)
        self.button.config(text="Start listening")

    def close(self) -> None:
        self.close_stream()
        self.root.destroy()

    # -- ui thread ---------------------------------------------------------
    def tick(self) -> None:
        level = score = None
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item[0], str):
                self.log.insert(0, item[1])
                self.score_meter.set(1.0, colour=FIRE)
                continue
            level, score = item
            self.frames += 1

        now = time.time()
        if now - self.peak_decay > 1.5:
            self.peak_decay = now
            self.level_peak *= 0.6
            self.score_peak *= 0.6

        if level is not None:
            self.level_peak = max(self.level_peak, level)
            self.level_meter.set(level, peak=self.level_peak)
            silent = self.frames > 25 and self.level_peak < 0.005
            self.level_text.config(
                text=f"{level:.3f}   peak {self.level_peak:.3f}   frames {self.frames}"
                     + ("   << SILENT: no sound reaching the app" if silent else ""),
                fg=FIRE if silent else FG)

        if score is not None:
            self.score_peak = max(self.score_peak, score)
            threshold = float(self.threshold.get())
            hot = score >= threshold
            self.hot_run = self.hot_run + 1 if hot else 0
            self.score_meter.set(score, peak=self.score_peak, threshold=threshold,
                                 colour=HOT if hot else BRAND)
            self.score_text.config(
                text=f"{score:.3f}   peak {self.score_peak:.3f}   "
                     f"hot {self.hot_run}/{int(self.needed.get())}")

        self.root.after(50, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    VoiceDebug(root)
    root.mainloop()
