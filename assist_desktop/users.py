"""Who is at the screen, and what they have asked before.

One JSON file holds both the roster and each person's history. That is enough
for a single-operator appliance and it keeps the whole thing inspectable — you
can open it in an editor and see exactly what the app believes.

History is deliberately capped per user. An operator's useful context is their
recent questions, and an unbounded file eventually becomes a startup cost.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MAX_HISTORY = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name: str) -> str:
    """A stable id from a display name. Two people called Sam collide, which is
    correct for a shop floor with one screen and no password."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "operator"


@dataclass(frozen=True)
class User:
    id: str
    name: str
    created_at: str
    last_seen: str


@dataclass(frozen=True)
class HistoryEntry:
    ts: str
    query: str
    kind: str
    source: str = "typed"
    # The full turn, so a past answer re-renders exactly as it first appeared
    # rather than being re-asked against a corpus that may have moved.
    turn: Optional[dict] = None


@dataclass
class _Profile:
    user: User
    history: list[HistoryEntry] = field(default_factory=list)


MOCK_USERS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Priya Sharma", [
        ("how do i fill the solution tank", "cached", "typed"),
        ("what is the tire inflation pressure", "cached", "voice"),
        ("what engine oil should i use", "synthesize", "typed"),
    ]),
    ("Marcus Chen", [
        ("how do i start spraying the field", "cached", "voice"),
        ("how do i fold the boom", "cached", "voice"),
    ]),
    ("Dan Whitfield", [
        ("what is the weather tomorrow", "oos", "typed"),
        ("how do i clean the nozzles", "cached", "typed"),
        ("where is the battery disconnect", "cached", "voice"),
    ]),
]


class UserStore:
    def __init__(self, path: Path, seed_mock: bool = True) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._profiles: dict[str, _Profile] = {}
        self._load()
        if seed_mock and not self._profiles:
            self._seed()

    # -- persistence -------------------------------------------------------
    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt profile file must not stop the app from starting; a
            # missing history is recoverable, a dead window is not.
            return
        for item in raw.get("profiles", []):
            user = User(**item["user"])
            history = [HistoryEntry(**e) for e in item.get("history", [])]
            self._profiles[user.id] = _Profile(user=user, history=history)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profiles": [
                {"user": asdict(p.user),
                 "history": [asdict(e) for e in p.history]}
                for p in self._profiles.values()
            ]
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.path)

    def _seed(self) -> None:
        for name, turns in MOCK_USERS:
            user = self._create(name)
            for query, kind, source in turns:
                self._profiles[user.id].history.append(
                    HistoryEntry(ts=_now(), query=query, kind=kind,
                                 source=source, turn=None))
        self._save()

    # -- api ---------------------------------------------------------------
    def _create(self, name: str) -> User:
        user = User(id=slugify(name), name=name.strip(),
                    created_at=_now(), last_seen=_now())
        self._profiles[user.id] = _Profile(user=user)
        return user

    def list_users(self) -> list[dict]:
        return [
            {**asdict(p.user), "turns": len(p.history)}
            for p in sorted(self._profiles.values(),
                            key=lambda p: p.user.last_seen, reverse=True)
        ]

    def login(self, name: str) -> dict:
        """Sign in by name, creating the profile if this is a new person."""
        name = (name or "").strip()
        if not name:
            raise ValueError("a name is required")
        with self._lock:
            user_id = slugify(name)
            profile = self._profiles.get(user_id)
            if profile is None:
                user = self._create(name)
            else:
                user = User(id=profile.user.id, name=profile.user.name,
                            created_at=profile.user.created_at, last_seen=_now())
                self._profiles[user_id] = _Profile(user=user,
                                                   history=profile.history)
            self._save()
            return asdict(self._profiles[user_id].user)

    def history(self, user_id: str) -> list[dict]:
        profile = self._profiles.get(user_id)
        if profile is None:
            return []
        return [asdict(e) for e in reversed(profile.history)]

    def record(self, user_id: str, query: str, kind: str, source: str,
               turn: Optional[dict] = None) -> None:
        with self._lock:
            profile = self._profiles.get(user_id)
            if profile is None:
                return
            profile.history.append(HistoryEntry(ts=_now(), query=query,
                                                kind=kind, source=source,
                                                turn=turn))
            del profile.history[:-MAX_HISTORY]
            self._save()

    def clear_history(self, user_id: str) -> None:
        with self._lock:
            profile = self._profiles.get(user_id)
            if profile is not None:
                profile.history.clear()
                self._save()
