"""HTTP to the devkit. The only place that knows the devkit exists.

Cancellation is a generation counter, not a socket abort. A superseded request
is allowed to finish and its result is discarded — the devkit serialises queries
anyway, so aborting the socket would buy nothing, and the guarantee we actually
need is that a stale answer is never shown or spoken.
"""
from __future__ import annotations

import threading

import httpx

from ..models.wire import Turn


class TransportError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class StaleResponse(Exception):
    """Raised when the answer that arrived belongs to a superseded question."""


class Transport:
    def __init__(self, base_url: str, timeout_s: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._generation = 0
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._generation += 1

    def _current_generation(self) -> int:
        with self._lock:
            return self._generation

    def _check_generation(self, started_at: int) -> None:
        if started_at != self._current_generation():
            raise StaleResponse()

    def health(self) -> dict:
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{self.base_url}/health")
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as e:
            raise TransportError(str(e) or type(e).__name__) from e

    def ask(self, query: str, top_k: int = 5) -> Turn:
        generation = self._current_generation()
        try:
            with httpx.Client(timeout=self.timeout_s) as c:
                r = c.post(f"{self.base_url}/ask",
                           json={"query": query, "top_k": top_k})
                r.raise_for_status()
                payload = r.json()
        except httpx.ConnectError as e:
            # Checked before TimeoutException: ConnectTimeout subclasses it, and
            # "did not answer in 20s" is a lie when the port refused instantly.
            raise TransportError(f"cannot reach the devkit at {self.base_url}") from e
        except httpx.ConnectTimeout as e:
            raise TransportError(f"cannot reach the devkit at {self.base_url}") from e
        except httpx.TimeoutException as e:
            raise TransportError(f"the devkit did not answer within "
                                 f"{self.timeout_s:.0f}s") from e
        except httpx.HTTPError as e:
            raise TransportError(str(e) or type(e).__name__) from e
        self._check_generation(generation)
        return Turn.from_dict(payload)
