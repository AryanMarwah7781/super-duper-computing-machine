"""Logging, so the application can be watched instead of guessed at.

Two destinations on purpose:

    console   what you see while it runs, one line per event
    file      logs/app.log, kept across restarts, so a problem that happened
              five minutes ago is still there when you go looking

The interesting events are deliberately noisy — every question asked, every
wake-word detection with its score, every connection change. When voice does
nothing, the log should say whether the microphone opened, whether the model
scored anything, and what the transcript was. Silence in a log is the worst
possible answer to "why did nothing happen".
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

_CONSOLE = "%(asctime)s  %(levelname)-5s  %(name)-14s  %(message)s"
_FILE = "%(asctime)s  %(levelname)-5s  %(name)-18s  %(message)s"


class _Brief(logging.Formatter):
    """Short module names: assist_desktop.audio.session -> audio.session."""

    def format(self, record: logging.LogRecord) -> str:
        record.name = record.name.replace("assist_desktop.", "")
        return super().format(record)


def setup(level: int = logging.INFO, quiet_libraries: bool = True) -> Path:
    root = logging.getLogger()
    if root.handlers:
        return LOG_FILE

    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_Brief(_CONSOLE, datefmt="%H:%M:%S"))
    root.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rotating = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3,
                                   encoding="utf-8")
    rotating.setFormatter(_Brief(_FILE, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(rotating)

    if quiet_libraries:
        # These are chatty at INFO and drown out anything of ours.
        for noisy in ("httpx", "httpcore", "faster_whisper", "urllib3",
                      "openwakeword", "numba", "matplotlib"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    return LOG_FILE


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
