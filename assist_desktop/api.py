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
from .logs import get as get_logger
from .client.transport import StaleResponse, Transport, TransportError
from .config import Config
from .models.wire import Turn
from .turnlog import TurnLog
from .users import UserStore

Emit = Callable[[str, dict], None]
log = get_logger("api")


def _turn_to_dict(turn: Turn) -> dict:
    return {
        "plan": asdict(turn.plan),
        "answer": asdict(turn.answer) if turn.answer else None,
        "candidates": [asdict(c) for c in turn.candidates],
        "timing": turn.timing,
    }


class Api:
    def __init__(self, config: Config, emit: Emit,
                 log_path: Optional[Path] = None,
                 profiles_path: Optional[Path] = None) -> None:
        self._config = config
        self._emit = emit
        self._transport = Transport(config.devkit_url, config.timeout_s)
        self._log = TurnLog(log_path or Path("turns.jsonl"))
        self._users = UserStore(profiles_path or Path("data/profiles.json"))
        self._monitor = HealthMonitor(self._transport, self._on_connection_change)
        # Voice asks originate in the audio thread, which has no idea who is
        # signed in — the UI tells us on sign-in and we remember.
        self._active_user = ""
        self._voice = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._monitor.start()

    def stop(self) -> None:
        self._monitor.stop()

    def _on_connection_change(self, state: ConnectionState, detail: str) -> None:
        log.info("devkit %s - %s", state.value, detail)
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

    def ask(self, query: str, source: str = "typed",
            user_id: str = "") -> dict:
        query = (query or "").strip()
        if not query:
            return {"ok": False, "turn": None, "error": "empty question"}
        log.info("ask (%s) %r", source, query)
        try:
            turn = self._transport.ask(query, top_k=self._config.top_k)
        except StaleResponse:
            log.info("  superseded, discarding")
            return {"ok": False, "turn": None, "error": None, "stale": True}
        except TransportError as e:
            self._log.append_error(query, e.detail, source=source)
            if user_id:
                self._users.record(user_id, query, "error", source)
            log.warning("  FAILED: %s", e.detail)
            self._emit("error", {"code": "transport", "message": e.detail})
            return {"ok": False, "turn": None, "error": e.detail}
        self._log.append(query, turn, source=source)
        top = turn.candidates[0].procedure_name if turn.candidates else "-"
        log.info("  %s in %sms - %s", turn.plan.kind,
                 turn.timing.get("total_ms", "?"), top or "-")
        payload = _turn_to_dict(turn)
        # The whole turn is stored, so re-opening a past question re-renders the
        # answer as it was given rather than re-asking a corpus that may differ.
        if user_id:
            self._users.record(user_id, query, turn.plan.kind, source,
                               turn=payload)
        return {"ok": True, "turn": payload, "error": None}

    # -- who is at the screen ---------------------------------------------
    def list_users(self) -> dict:
        return {"ok": True, "users": self._users.list_users()}

    def login(self, name: str) -> dict:
        try:
            user = self._users.login(name)
        except ValueError as e:
            return {"ok": False, "user": None, "error": str(e)}
        return {"ok": True, "user": user, "error": None}

    def history(self, user_id: str) -> dict:
        return {"ok": True, "entries": self._users.history(user_id)}

    def clear_history(self, user_id: str) -> dict:
        self._users.clear_history(user_id)
        return {"ok": True}

    # -- voice -------------------------------------------------------------
    def set_active_user(self, user_id: str) -> dict:
        """Who a spoken question belongs to. Called on sign-in and sign-out."""
        self._active_user = user_id or ""
        log.info("active user: %s", self._active_user or "(signed out)")
        return {"ok": True}

    def _ask_from_voice(self, text: str) -> None:
        """A spoken question takes the identical path to a typed one, then the
        answer is pushed as an event — nobody is awaiting a promise for it."""
        result = self.ask(text, source="voice", user_id=self._active_user)
        self._emit("answer", {"query": text, **result})

    def _voice_session(self):
        if self._voice is None:
            from .audio.session import VoiceSession
            self._voice = VoiceSession(emit=self._emit, ask=self._ask_from_voice)
        return self._voice

    def start_voice(self) -> dict:
        try:
            status = self._voice_session().start()
            log.info("voice start: %s", status)
            return {"ok": True, **status}
        except Exception as e:
            log.exception("voice failed to start")
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def stop_voice(self) -> dict:
        try:
            if self._voice is None:
                return {"ok": True, "state": "off"}
            return {"ok": True, **self._voice.stop()}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def audio_devices(self) -> dict:
        from .audio.mic import list_input_devices
        current = self._voice._mic.device if self._voice is not None else None
        return {"ok": True, "devices": list_input_devices(), "current": current}

    def set_audio_device(self, index) -> dict:
        try:
            value = None if index in (None, "", -1, "-1") else int(index)
            return {"ok": True, **self._voice_session().set_device(value)}
        except Exception as e:
            log.exception("could not switch microphone")
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def voice_status(self) -> dict:
        if self._voice is None:
            return {"ok": True, "state": "off", "wake_ready": False,
                    "stt_ready": False, "mic_running": False, "error": None}
        return {"ok": True, **self._voice.status()}
