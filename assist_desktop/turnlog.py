"""Append-only record of every turn.

Retrieval accuracy is unmeasured and the known failure mode is a coin flip
between three chunks. This file is the evidence base for fixing that: the
question asked, which chunk won, why, and what else was in the running. A few
lines of code, no UI surface, and it turns "it felt wrong" into a measurement.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models.wire import Turn


class TurnLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _write(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def append(self, query: str, turn: Turn, source: str) -> None:
        self._write({
            "ts": self._now(),
            "query": query,
            "source": source,
            "kind": turn.plan.kind,
            "reason": turn.plan.reason,
            "chunk_ids": list(turn.plan.chunk_ids),
            "candidates": [asdict(c) for c in turn.candidates],
            "timing": turn.timing,
        })

    def append_error(self, query: str, detail: str, source: str) -> None:
        self._write({
            "ts": self._now(),
            "query": query,
            "source": source,
            "kind": "error",
            "reason": detail,
            "chunk_ids": [],
            "candidates": [],
            "timing": {},
        })
