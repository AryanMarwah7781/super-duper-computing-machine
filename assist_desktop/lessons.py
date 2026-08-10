"""Guided lessons, and the log that marks their steps complete.

A lesson is a short procedure on the real CommandARM: press this, then that.
Nothing here asks the operator to tell us they did it. The simulator's
Connections App already writes every signal that leaves the armrest to its
log.txt, so the step completes when the machine says it happened.

Three things carried over from the trainer spec (see data/lessons.json for the
content itself) and each one was paid for in a wrong answer:

  A received line can carry several signals in one array. Every pair on the
  line is matched, not just the first — a `search`-based reader silently drops
  the rest and makes indicator-driven steps look broken.

  One button can mean two things. The round centre-boom control sets frame
  height on its own and folds the booms when the reverse pedal was worked
  first, and sends the identical signal for both. The pedal never becomes a
  signal at all — it appears only as a raw `HID:` line — so a step that means
  "fold" has to be armed by one, or it fires on frame height instead.

  The hydro handle has no fixed neutral. Two sessions on the same physical
  handle rested at 174 and at 238, so "back to neutral" is a band around a
  value measured this session and deliberately never persisted.

  Reading the log is all we do. The Connections App is not touched, not
  launched, and not written to: it owns the hardware, and a trainer that
  interferes with it would be worse than no trainer.
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Callable, Iterable, Optional

from .logs import get as get_logger

log = get_logger("lessons")

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "data" / "lessons.json"

# {"signal":"PLT_AIC_SolutionPump","value":"1"} — one or many per line.
SIGNAL_RE = re.compile(r'"signal":"([^"]+)","value":"([^"]*)"')
# Cache chatter and restatements of data already handled above. Neither is an
# event; counting them completes steps nobody performed.
IGNORED_RE = re.compile(r"HasVioValueChanged\(\)|ProcessMessage\(\)")
SEND_RE = re.compile(r"SendVIOData\(\)")          # armrest -> cloud: a press
RECV_RE = re.compile(r"OnStompMessageReceived\(\)")  # cloud -> armrest: a light
# HID: ReversePedal(GenericDesktopY) pressed=True — pedals and levers the app
# reads straight off the device. These never become signals, so a control that
# only exists here is invisible unless we read the raw line.
HID_RE = re.compile(r"HID:\s*([A-Za-z0-9_]+)\([^)]*\)\s*pressed=(True|False)")
HID_PREFIX = "HID_"

BASELINE_CONDITIONS = ("off_baseline", "back_to_baseline")
# Samples taken before a resting value is trusted. Fewer and a handle still
# settling sets the neutral; many more and the operator waits on us.
BASELINE_SAMPLES = 10
DEFAULT_BAND = 12.0

POLL_INTERVAL_S = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- the catalog -----------------------------------------------------------

def load_catalog(path: Path = DEFAULT_CATALOG) -> dict:
    """Categories, lessons and steps. Never raises: a missing or broken
    catalog leaves an empty lesson list, which the UI can say plainly."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("no lesson catalog at %s (%s)", path, e)
        return {"log_path": "", "categories": []}


def find_lesson(catalog: dict, lesson_id: str) -> tuple[Optional[dict], str]:
    """The lesson and the category it sits in."""
    for category in catalog.get("categories", []):
        for lesson in category.get("lessons", []):
            if lesson.get("id") == lesson_id:
                return lesson, category.get("name", "")
    return None, ""


def triggers_for(lesson: dict) -> list["Trigger"]:
    """The sync rules of a lesson, in step order. Steps without one are still
    steps — they are performed in the game, where nothing reaches the log."""
    out = []
    for index, step in enumerate(lesson.get("steps", []), start=1):
        rule = step.get("sync")
        if rule:
            out.append(Trigger.from_dict(index, rule))
    return out


def sim_log_path(catalog: dict) -> str:
    """Where the Connections App writes. The environment wins, so moving the
    simulator does not mean editing the catalog."""
    return os.environ.get("ASSIST_SIM_LOG") or catalog.get("log_path", "")


# -- matching signals to steps --------------------------------------------

@dataclass(frozen=True)
class Trigger:
    step_index: int
    signals: tuple[str, ...]
    condition: str = "nonzero"
    value: Optional[str] = None
    requires_step: Optional[int] = None
    source: str = "sent"
    # A control that must be worked first for this press to mean what the step
    # says. The R4045 folds with the reverse pedal down and sets frame height
    # with the pedal up, and sends the identical signal for both.
    arm_signal: Optional[str] = None
    arm_value: str = "1"

    @classmethod
    def from_dict(cls, step_index: int, rule: dict) -> "Trigger":
        armed_by = rule.get("armed_by") or {}
        return cls(
            step_index=step_index,
            signals=tuple(rule.get("signals") or ()),
            condition=rule.get("condition") or "nonzero",
            value=rule.get("value"),
            requires_step=rule.get("requires_step"),
            source=rule.get("source") or "sent",
            arm_signal=armed_by.get("signal"),
            arm_value=str(armed_by.get("value", "1")),
        )


@dataclass
class StepWatcher:
    """Turns log lines into completed step indices.

    Pure: no files, no threads, no clock. Feed it lines and it hands back the
    steps that just completed, each one only the first time.
    """
    triggers: list[Trigger]
    done: set[int] = field(default_factory=set)
    _baselines: dict[str, float] = field(default_factory=dict)
    _samples: dict[str, list[float]] = field(default_factory=dict)
    _left_band: set[str] = field(default_factory=set)
    _armed: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._baseline_signals = {
            s for t in self.triggers if t.condition in BASELINE_CONDITIONS
            for s in t.signals
        }
        self._arm_signals = {t.arm_signal: t.arm_value
                             for t in self.triggers if t.arm_signal}

    def feed(self, lines: Iterable[str]) -> list[int]:
        completed: list[int] = []
        for line in lines:
            completed.extend(self.feed_line(line))
        return completed

    def feed_line(self, line: str) -> list[int]:
        if IGNORED_RE.search(line):
            return []
        hid = HID_RE.search(line)
        if hid:
            name, pressed = hid.groups()
            return self.feed_signal("hid", HID_PREFIX + name,
                                    "1" if pressed == "True" else "0")
        if SEND_RE.search(line):
            source = "sent"
        elif RECV_RE.search(line):
            source = "recv"
        else:
            return []
        completed: list[int] = []
        for signal, value in SIGNAL_RE.findall(line):
            completed.extend(self.feed_signal(source, signal, value))
        return completed

    def feed_signal(self, source: str, signal: str, value: str) -> list[int]:
        if source == "sent" and signal in self._baseline_signals:
            self._sample_baseline(signal, value)
        # Arming outlives the release. The pedal is worked and let go before
        # the button is reached, so disarming on release would arm nothing.
        if self._arm_signals.get(signal) == value:
            self._armed.add(signal)
        completed = []
        for trig in self.triggers:
            if trig.step_index in self.done:
                continue
            if trig.source != source or signal not in trig.signals:
                continue
            if trig.arm_signal is not None and trig.arm_signal not in self._armed:
                continue  # the same press, without the pedal, means something else
            # An ordered lesson: "move to Rate 2" means nothing until Rate 1
            # was selected, or the operator has learned no transition at all.
            if trig.requires_step is not None and trig.requires_step not in self.done:
                continue
            if self._met(trig, signal, value):
                self.done.add(trig.step_index)
                completed.append(trig.step_index)
                if trig.arm_signal is not None:
                    # One pedal press buys one fold, not every press after it.
                    self._armed.discard(trig.arm_signal)
        return completed

    # -- conditions --------------------------------------------------------
    def _met(self, trig: Trigger, signal: str, value: str) -> bool:
        if trig.condition == "equals":
            return value == trig.value
        if trig.condition == "nonzero":
            try:
                return abs(float(value)) > 0.01
            except ValueError:
                # Analog channels carry malformed literals — VIO_GPS_Speed
                # reports "0.3.2E05". A value we cannot read is not evidence
                # the operator did anything, so it completes nothing.
                return False
        if trig.condition in BASELINE_CONDITIONS:
            return self._band(trig, signal, value)
        return False

    def _sample_baseline(self, signal: str, value: str) -> None:
        """Measure this session's resting value. Not persisted — re-measured
        every time the lesson opens, because it genuinely changes."""
        if signal in self._baselines:
            return
        try:
            v = float(value)
        except ValueError:
            return
        samples = self._samples.setdefault(signal, [])
        samples.append(v)
        if len(samples) >= BASELINE_SAMPLES:
            self._baselines[signal] = median(samples)
            log.info("neutral for %s measured at %s", signal,
                     self._baselines[signal])

    def _band(self, trig: Trigger, signal: str, value: str) -> bool:
        base = self._baselines.get(signal)
        if base is None:
            return False  # still calibrating; nothing to compare against
        try:
            v = float(value)
        except ValueError:
            return False
        try:
            width = abs(float(trig.value)) if trig.value is not None else DEFAULT_BAND
        except (TypeError, ValueError):
            width = DEFAULT_BAND
        if abs(v - base) > width:
            self._left_band.add(signal)
            return trig.condition == "off_baseline"
        # "Return to neutral" only counts once it has actually left. Otherwise
        # a handle nobody touched satisfies the step on its first sample.
        return trig.condition == "back_to_baseline" and signal in self._left_band


# -- watching the file -----------------------------------------------------

class LogTailer:
    """Polls the Connections App's log for new lines and reports steps.

    Starts at the end of the file: the log accumulates across sessions, and
    replaying yesterday's presses would complete a lesson before the operator
    touched anything.
    """

    def __init__(self, path: str, watcher: StepWatcher,
                 on_step: Callable[[int], None],
                 interval: float = POLL_INTERVAL_S) -> None:
        self.path = str(path)
        self.watcher = watcher
        self._on_step = on_step
        self._interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        try:
            self._pos = os.path.getsize(self.path)
        except OSError:
            self._pos = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="lesson-tailer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.poll()
            except Exception:
                # A lesson that stops advancing is bad; a dead thread that
                # never advances again is worse.
                log.exception("lesson tailer poll failed")

    def poll(self) -> list[int]:
        """Read whatever has been appended and report the steps it completed.
        Public so a test can drive it without a thread."""
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size < self._pos:
            self._pos = 0  # the app restarted and truncated its log
        if size == self._pos:
            return []
        try:
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
        except OSError:
            return []
        completed = self.watcher.feed(chunk.splitlines())
        for index in completed:
            self._on_step(index)
        return completed


# -- what each operator has completed --------------------------------------

class ProgressStore:
    """Per-operator lesson progress, in one readable JSON file.

    Completed steps persist across sessions on purpose: an operator who did
    four of seven steps yesterday should see that, and the card on the lesson
    list is the only record anyone keeps of who has been trained on what.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, dict]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Same reasoning as the profile store: a corrupt record must not
            # stop the app from opening.
            return
        self._data = raw.get("operators", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"operators": self._data}, indent=2,
                                  ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def _record(self, user_id: str, lesson_id: str) -> dict:
        lessons = self._data.setdefault(user_id, {})
        return lessons.setdefault(lesson_id, {"steps_done": [],
                                              "last_opened": None})

    def summary(self, user_id: str) -> dict[str, dict]:
        """Every lesson this operator has touched, for the lesson list."""
        return {lesson_id: dict(record)
                for lesson_id, record in self._data.get(user_id, {}).items()}

    def steps_done(self, user_id: str, lesson_id: str) -> list[int]:
        return list(self._data.get(user_id, {})
                    .get(lesson_id, {}).get("steps_done", []))

    def opened(self, user_id: str, lesson_id: str) -> None:
        if not user_id:
            return
        with self._lock:
            self._record(user_id, lesson_id)["last_opened"] = _now()
            self._save()

    def complete(self, user_id: str, lesson_id: str, step_index: int) -> None:
        if not user_id:
            return
        with self._lock:
            record = self._record(user_id, lesson_id)
            if step_index not in record["steps_done"]:
                record["steps_done"] = sorted(record["steps_done"] + [step_index])
                self._save()

    def reset(self, user_id: str, lesson_id: str) -> None:
        """Start the lesson over. The record of having opened it stays — that
        happened, and erasing it would hide a lesson someone struggled with."""
        if not user_id:
            return
        with self._lock:
            record = self._record(user_id, lesson_id)
            record["steps_done"] = []
            self._save()
