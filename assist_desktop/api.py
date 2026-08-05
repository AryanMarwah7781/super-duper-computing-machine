"""The pywebview bridge — everything the UI is allowed to do.

`emit` is injected rather than reaching for a window, so the whole bridge is
ordinary Python and tests need no browser. Methods never raise: an exception
crossing into JavaScript surfaces as an unhandled promise rejection, which is
invisible. Every method returns a result envelope instead.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from .client.health import ConnectionState, HealthMonitor
from .client.transport import StaleResponse, Transport, TransportError
from .config import Config
from .models.wire import Turn
from .turnlog import TurnLog

Emit = Callable[[str, dict], None]


def _turn_to_dict(turn: Turn) -> dict:
    return {
        "plan": asdict(turn.plan),
        "answer": asdict(turn.answer) if turn.answer else None,
        "candidates": [asdict(c) for c in turn.candidates],
        "timing": turn.timing,
    }


class Api:
    def __init__(self, config: Config, emit: Emit,
                 log_path: Optional[Path] = None) -> None:
        self._config = config
        self._emit = emit
        self._transport = Transport(config.devkit_url, config.timeout_s)
        self._log = TurnLog(log_path or Path("turns.jsonl"))
        self._monitor = HealthMonitor(self._transport, self._on_connection_change)

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._monitor.start()

    def stop(self) -> None:
        self._monitor.stop()

    def _on_connection_change(self, state: ConnectionState, detail: str) -> None:
        self._emit("connection", {"state": state.value, "detail": detail})

    # -- bridge methods ----------------------------------------------------
    def health(self) -> dict:
        try:
            return {"ok": True, "health": self._transport.health(), "error": None}
        except TransportError as e:
            return {"ok": False, "health": None, "error": e.detail}

    def cancel(self) -> dict:
        self._transport.cancel()
        return {"ok": True}

    def ask(self, query: str, source: str = "typed") -> dict:
        query = (query or "").strip()
        if not query:
            return {"ok": False, "turn": None, "error": "empty question"}
        try:
            turn = self._transport.ask(query, top_k=self._config.top_k)
        except StaleResponse:
            return {"ok": False, "turn": None, "error": None, "stale": True}
        except TransportError as e:
            self._log.append_error(query, e.detail, source=source)
            self._emit("error", {"code": "transport", "message": e.detail})
            return {"ok": False, "turn": None, "error": e.detail}
        self._log.append(query, turn, source=source)
        return {"ok": True, "turn": _turn_to_dict(turn), "error": None}
