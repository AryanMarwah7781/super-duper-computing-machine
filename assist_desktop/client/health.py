"""Connection state. The transition rule is a pure function so it can be
tested without a network, a clock or a thread."""
from __future__ import annotations

import threading
from enum import Enum
from typing import Callable, Optional

from .transport import Transport, TransportError

# Both pipelines emit the same display grammar, so the client renders either.
# v3 is the one currently deployed: it retrieves "how do i start spraying"
# correctly, which v4 regressed. v4 has the better safety attachment.
SUPPORTED_RENDER_VERSIONS = ("v4.0", "v3")
EXPECTED_RENDER_VERSION = "v4.0"


class ConnectionState(str, Enum):
    CONNECTING = "connecting"
    READY = "ready"
    WARMING = "warming"
    OFFLINE = "offline"


def next_state(current: ConnectionState, health: Optional[dict],
               error: Optional[str]) -> tuple[ConnectionState, str]:
    if error is not None or health is None:
        return (ConnectionState.OFFLINE,
                f"devkit unreachable: {error or 'no response'}")
    if not health.get("ready", False):
        return ConnectionState.WARMING, "devkit is warming up — loading the index"
    version = health.get("render_version", "")
    if version and version not in SUPPORTED_RENDER_VERSIONS:
        return (ConnectionState.READY,
                f"connected, but the service renders {version} and this client "
                f"supports {', '.join(SUPPORTED_RENDER_VERSIONS)}")
    if version and version != EXPECTED_RENDER_VERSION:
        return ConnectionState.READY, f"connected — {version} pipeline"
    return ConnectionState.READY, "connected"


class HealthMonitor:
    """Polls /health on a background thread, reporting only real changes."""

    def __init__(self, transport: Transport,
                 on_change: Callable[[ConnectionState, str], None],
                 interval_s: float = 3.0) -> None:
        self._transport = transport
        self._on_change = on_change
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.state = ConnectionState.CONNECTING
        self.detail = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def poll_once(self) -> None:
        try:
            health, error = self._transport.health(), None
        except TransportError as e:
            health, error = None, e.detail
        state, detail = next_state(self.state, health, error)
        if state is not self.state or detail != self.detail:
            self.state, self.detail = state, detail
            self._on_change(state, detail)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._interval_s)
