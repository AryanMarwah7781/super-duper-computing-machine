"""Everyone who uses the machine, and everything they have done on it.

One SQLite file. It replaces the pair of JSON files this app started with —
`data/profiles.json` for the roster and `data/lesson_progress.json` for lesson
steps — because a trainer now has an admin who assigns lessons and reads
everybody's progress at once, and that is a set of joins, not a pair of blobs
each process rewrites whole.

Both legacy files are imported on first open and then left alone, so upgrading
loses nobody's history.

Three things worth knowing:

  Writes come from two threads. The lesson tailer records a step from its own
  polling thread while the UI thread is reading. One connection, one lock,
  `check_same_thread=False`.

  Deleting an operator deletes everything about them — history, lesson
  progress, assignments — through `ON DELETE CASCADE`, which SQLite only
  honours with `PRAGMA foreign_keys = ON` per connection.

  The file stays readable by anything that speaks SQL. That was the point of
  the JSON too: someone should be able to open the store and see what the app
  believes without running the app.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .logs import get as get_logger

log = get_logger("db")

# An operator's useful context is their recent questions, and an unbounded
# table eventually becomes a startup cost.
MAX_HISTORY = 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    -- Whether they have been shown how to start the simulator. A new operator
    -- is walked through it once; nobody sits through it twice.
    onboarded   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS history (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ts       TEXT NOT NULL,
    query    TEXT NOT NULL,
    kind     TEXT NOT NULL,
    source   TEXT NOT NULL DEFAULT 'typed',
    -- The whole turn, so re-opening a past question re-renders what was
    -- actually said rather than re-asking a corpus that may have moved.
    turn     TEXT
);
CREATE INDEX IF NOT EXISTS history_by_user ON history(user_id, id);

CREATE TABLE IF NOT EXISTS lesson_state (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id   TEXT NOT NULL,
    assigned    INTEGER NOT NULL DEFAULT 1,
    last_opened TEXT,
    PRIMARY KEY (user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id    TEXT NOT NULL,
    step_index   INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, lesson_id, step_index)
);

-- Answers already given, so a question asked twice is not searched twice. The
-- board takes 6 seconds on retrieval and 15-30 on synthesis; this is the same
-- answer in about a millisecond.
--
-- Keyed by the SERVICE as well as the question. The v3 and v4 pipelines answer
-- the same question differently, and an answer remembered from one must never
-- be served as if it came from the other.
CREATE TABLE IF NOT EXISTS answer_cache (
    key            TEXT PRIMARY KEY,
    query          TEXT NOT NULL,
    service        TEXT NOT NULL,
    render_version TEXT NOT NULL,
    kind           TEXT NOT NULL,
    turn           TEXT NOT NULL,
    took_ms        INTEGER NOT NULL DEFAULT 0,
    hits           INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    last_used      TEXT
);
CREATE INDEX IF NOT EXISTS answers_by_service ON answer_cache(service, render_version);
"""

# Dropped when matching a question to one already answered. Articles are the
# only words removed: the turn log has "how do i fill solution tank" and "how
# do i fill the solution tank?" as separate entries for the same question. No
# word that changes what is being asked is touched -- a wrong hit would serve
# the wrong procedure, which is the one failure this must not have.
_ARTICLES = {"the", "a", "an"}

# The many ways to ask for a procedure, and the many ways to ask what
# something is. Reduced to WHICH OF THE TWO is being asked, never removed:
# "how do i use the spray system master switch" and "what is the spray system
# master switch" share every remaining word and are different questions.
_OPENERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("how", "do", "i"), "howto"),
    (("how", "do", "you"), "howto"),
    (("how", "can", "i"), "howto"),
    (("how", "would", "i"), "howto"),
    (("how", "should", "i"), "howto"),
    (("how", "to"), "howto"),
    (("show", "me", "how", "to"), "howto"),
    (("tell", "me", "how", "to"), "howto"),
    (("walk", "me", "through"), "howto"),
    (("what", "are", "steps", "to"), "howto"),
    (("what", "is", "procedure", "for"), "howto"),
    (("steps", "to"), "howto"),
    (("procedure", "for"), "howto"),
    (("what", "is"), "whatis"),
    (("what", "are"), "whatis"),
    (("whats"), "whatis"),
    (("what", "does"), "whatis"),
    (("define"), "whatis"),
)

# A typo is repairable; a different word is a different question. These are
# never treated as misspellings of each other however close they look --
# "fold" and "unfold" differ by two characters and by everything that matters.
MIN_REPAIRABLE = 5      # shorter words are left exactly as typed
MAX_REPAIR_DISTANCE = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _distance(a: str, b: str, limit: int) -> int:
    """Levenshtein, given up on once it passes `limit`.

    Not difflib: "nossle" and "nozzle" score 0.67 there, below any cutoff worth
    using, while "fold" and "unfold" score 0.80. Ratios rank the dangerous pair
    above the harmless one; edit distance does not.
    """
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def repair_word(word: str, vocabulary: Iterable[str]) -> str:
    """The word that was meant, if it is obvious which one.

    Only words the vocabulary does not already contain are touched, so a real
    word is never "corrected" into a different real word — that is what keeps
    "fold" from becoming "unfold". A repair also has to be unambiguous: two
    candidates equally close means we do not know, and not knowing means
    leaving it alone and letting the question reach the board.
    """
    known = set(vocabulary)
    if word in known or len(word) < MIN_REPAIRABLE:
        return word
    best, runner_up, best_word = MAX_REPAIR_DISTANCE + 1, MAX_REPAIR_DISTANCE + 1, word
    for candidate in known:
        if abs(len(candidate) - len(word)) > MAX_REPAIR_DISTANCE:
            continue
        # One word inside the other is not a misspelling, it is a different
        # word: "unfold" is "fold" plus a prefix and two edits away from it.
        # With only "fold" cached, distance alone repaired "unfold" into it
        # and answered the opposite procedure.
        if word in candidate or candidate in word:
            continue
        d = _distance(word, candidate, MAX_REPAIR_DISTANCE)
        if d < best:
            best, runner_up, best_word = d, best, candidate
        elif d < runner_up:
            runner_up = d
    if best <= MAX_REPAIR_DISTANCE and best < runner_up:
        return best_word
    return word


def normalise_question(text: str) -> str:
    """The form two askings of the same question share.

    Lower case, no punctuation, single spaces, no articles. Deliberately
    nothing cleverer at this level: this is the exact key, and `loose_question`
    is where openers and typos are forgiven.
    """
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    words = [w for w in text.split() if w not in _ARTICLES]
    return " ".join(words)


def loose_question(text: str, vocabulary: Optional[Iterable[str]] = None) -> str:
    """The same question asked another way, reduced to one key.

    Two things are forgiven: the opener ("how to X" and "how do i X" are the
    same request) and a misspelling of a word the vocabulary knows ("nossle"
    for "nozzle"). What is NOT forgiven is any word that changes the request —
    fold and unfold, start and stop, left and right stay different questions,
    because serving the wrong procedure is worse than searching again.
    """
    words = normalise_question(text).split()
    kind = ""
    for opener, label in _OPENERS:
        opener = (opener,) if isinstance(opener, str) else opener
        if tuple(words[:len(opener)]) == opener:
            kind, words = label, words[len(opener):]
            break
    if vocabulary is not None:
        vocabulary = list(vocabulary)
        words = [repair_word(w, vocabulary) for w in words]
    return " ".join(([kind] if kind else []) + words)


def slugify(name: str) -> str:
    """A stable id from a display name. Two people called Sam collide, which is
    correct for a shop floor with one screen and no password."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "operator"


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


class Store:
    def __init__(self, path: Path, seed_mock: bool = True,
                 legacy_profiles: Optional[Path] = None,
                 legacy_progress: Optional[Path] = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        self._db.commit()

        if self._count("users") == 0:
            imported = self._import_legacy(legacy_profiles, legacy_progress)
            if not imported and seed_mock:
                self._seed()

    # -- plumbing ----------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _count(self, table: str) -> int:
        return self._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def _write(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, tuple(params))
            self._db.commit()
            return cur

    def _rows(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, tuple(params)).fetchall()

    # -- coming from the JSON era ------------------------------------------
    def _import_legacy(self, profiles: Optional[Path],
                       progress: Optional[Path]) -> bool:
        """Bring the old files across, once. Never raises: an unreadable
        legacy file is a lost history, not a dead app."""
        moved = False
        try:
            if profiles and Path(profiles).is_file():
                raw = json.loads(Path(profiles).read_text(encoding="utf-8"))
                for item in raw.get("profiles", []):
                    user = item["user"]
                    self._insert_user(user["id"], user["name"],
                                      user.get("created_at") or now(),
                                      user.get("last_seen") or now())
                    for entry in item.get("history", []):
                        self.record(user["id"], entry.get("query", ""),
                                    entry.get("kind", "cached"),
                                    entry.get("source", "typed"),
                                    turn=entry.get("turn"),
                                    ts=entry.get("ts"))
                    moved = True
        except (OSError, ValueError, KeyError) as e:
            log.warning("could not import %s (%s)", profiles, e)
        try:
            if progress and Path(progress).is_file():
                raw = json.loads(Path(progress).read_text(encoding="utf-8"))
                for user_id, lessons in raw.get("operators", {}).items():
                    if not self.get_user(user_id):
                        continue
                    for lesson_id, record in lessons.items():
                        for step in record.get("steps_done", []):
                            self.complete_step(user_id, lesson_id, int(step))
                        if record.get("last_opened"):
                            self.open_lesson(user_id, lesson_id,
                                             record["last_opened"])
                    moved = True
        except (OSError, ValueError, AttributeError) as e:
            log.warning("could not import %s (%s)", progress, e)
        if moved:
            log.info("imported the previous JSON store into %s", self.path)
        return moved

    def _seed(self) -> None:
        for name, turns in MOCK_USERS:
            user = self.create_user(name)
            for query, kind, source in turns:
                self.record(user["id"], query, kind, source)

    # -- the roster --------------------------------------------------------
    def _insert_user(self, user_id: str, name: str, created_at: str,
                     last_seen: str, onboarded: int = 1) -> None:
        # Anyone already in the store predates onboarding and has plainly been
        # using the machine; do not walk them through it now.
        self._write(
            "INSERT OR IGNORE INTO users (id, name, created_at, last_seen,"
            " onboarded) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, created_at, last_seen, onboarded))

    def _as_user(self, row: sqlite3.Row) -> dict:
        return {"id": row["id"], "name": row["name"],
                "created_at": row["created_at"], "last_seen": row["last_seen"],
                "onboarded": bool(row["onboarded"])}

    def get_user(self, user_id: str) -> Optional[dict]:
        rows = self._rows("SELECT * FROM users WHERE id = ?", (user_id,))
        return self._as_user(rows[0]) if rows else None

    def list_users(self) -> list[dict]:
        rows = self._rows(
            "SELECT u.*, (SELECT count(*) FROM history h WHERE h.user_id = u.id)"
            " AS turns FROM users u ORDER BY u.last_seen DESC")
        return [{**self._as_user(r), "turns": r["turns"]} for r in rows]

    def create_user(self, name: str) -> dict:
        """Add an operator. Raises ValueError on a blank or duplicate name —
        the admin screen shows the message, so it has to be readable."""
        name = (name or "").strip()
        if not name:
            raise ValueError("a name is required")
        user_id = slugify(name)
        if self.get_user(user_id):
            raise ValueError(f"{name} is already on the roster")
        # New operators start unonboarded: the first thing they see is how to
        # bring the simulator up.
        self._insert_user(user_id, name, now(), now(), onboarded=0)
        return self.get_user(user_id)  # type: ignore[return-value]

    def login(self, name: str) -> dict:
        """Sign in by name, creating the profile if this is a new person."""
        name = (name or "").strip()
        if not name:
            raise ValueError("a name is required")
        user_id = slugify(name)
        if not self.get_user(user_id):
            self._insert_user(user_id, name, now(), now(), onboarded=0)
        else:
            self._write("UPDATE users SET last_seen = ? WHERE id = ?",
                        (now(), user_id))
        return self.get_user(user_id)  # type: ignore[return-value]

    def delete_user(self, user_id: str) -> bool:
        """Remove an operator and everything recorded about them."""
        cur = self._write("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0

    def mark_onboarded(self, user_id: str) -> None:
        self._write("UPDATE users SET onboarded = 1 WHERE id = ?", (user_id,))

    # -- what they asked ---------------------------------------------------
    def history(self, user_id: str) -> list[dict]:
        rows = self._rows(
            "SELECT ts, query, kind, source, turn FROM history"
            " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, MAX_HISTORY))
        return [{"ts": r["ts"], "query": r["query"], "kind": r["kind"],
                 "source": r["source"],
                 "turn": json.loads(r["turn"]) if r["turn"] else None}
                for r in rows]

    def record(self, user_id: str, query: str, kind: str, source: str,
               turn: Optional[dict] = None, ts: Optional[str] = None) -> None:
        if not self.get_user(user_id):
            return
        self._write(
            "INSERT INTO history (user_id, ts, query, kind, source, turn)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, ts or now(), query, kind, source,
             json.dumps(turn) if turn else None))
        # Keep the newest MAX_HISTORY. Done on write so the table cannot grow
        # without bound between restarts.
        self._write(
            "DELETE FROM history WHERE user_id = ? AND id NOT IN ("
            "  SELECT id FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?)",
            (user_id, user_id, MAX_HISTORY))

    def clear_history(self, user_id: str) -> None:
        self._write("DELETE FROM history WHERE user_id = ?", (user_id,))

    # -- lessons -----------------------------------------------------------
    def open_lesson(self, user_id: str, lesson_id: str,
                    ts: Optional[str] = None) -> None:
        if not user_id or not self.get_user(user_id):
            return
        self._write(
            "INSERT INTO lesson_state (user_id, lesson_id, last_opened)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(user_id, lesson_id) DO UPDATE SET last_opened = ?",
            (user_id, lesson_id, ts or now(), ts or now()))

    def complete_step(self, user_id: str, lesson_id: str,
                      step_index: int) -> None:
        if not user_id or not self.get_user(user_id):
            return
        self._write(
            "INSERT OR IGNORE INTO lesson_progress"
            " (user_id, lesson_id, step_index, completed_at)"
            " VALUES (?, ?, ?, ?)",
            (user_id, lesson_id, int(step_index), now()))

    def steps_done(self, user_id: str, lesson_id: str) -> list[int]:
        return [r["step_index"] for r in self._rows(
            "SELECT step_index FROM lesson_progress WHERE user_id = ?"
            " AND lesson_id = ? ORDER BY step_index", (user_id, lesson_id))]

    def reset_lesson(self, user_id: str, lesson_id: str) -> None:
        """Start over. The visit stays on record — it happened, and erasing it
        would hide a lesson someone struggled with."""
        self._write("DELETE FROM lesson_progress WHERE user_id = ?"
                    " AND lesson_id = ?", (user_id, lesson_id))

    def lesson_summary(self, user_id: str) -> dict[str, dict]:
        """Every lesson this operator has touched or been assigned."""
        summary: dict[str, dict] = {}
        for row in self._rows(
                "SELECT lesson_id, assigned, last_opened FROM lesson_state"
                " WHERE user_id = ?", (user_id,)):
            summary[row["lesson_id"]] = {
                "steps_done": [], "last_opened": row["last_opened"],
                "assigned": bool(row["assigned"])}
        for row in self._rows(
                "SELECT lesson_id, step_index FROM lesson_progress"
                " WHERE user_id = ? ORDER BY step_index", (user_id,)):
            record = summary.setdefault(
                row["lesson_id"],
                {"steps_done": [], "last_opened": None, "assigned": True})
            record["steps_done"].append(row["step_index"])
        return summary

    # -- who learns what ---------------------------------------------------
    def assignments(self, user_id: str) -> set[str]:
        """The lessons explicitly withheld are the ones recorded as 0. A
        lesson nobody has touched has no row at all and counts as assigned:
        adding a lesson to the catalog must not silently hide it from
        everyone already on the roster."""
        return {r["lesson_id"] for r in self._rows(
            "SELECT lesson_id FROM lesson_state WHERE user_id = ?"
            " AND assigned = 0", (user_id,))}

    def is_assigned(self, user_id: str, lesson_id: str) -> bool:
        return lesson_id not in self.assignments(user_id)

    def set_assigned(self, user_id: str, lesson_id: str, assigned: bool) -> None:
        self._write(
            "INSERT INTO lesson_state (user_id, lesson_id, assigned)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(user_id, lesson_id) DO UPDATE SET assigned = ?",
            (user_id, lesson_id, int(assigned), int(assigned)))

    def set_assignments(self, user_id: str, lesson_ids: Iterable[str],
                        every_lesson: Iterable[str]) -> None:
        """Replace this operator's whole assignment set in one go."""
        keep = set(lesson_ids)
        for lesson_id in every_lesson:
            self.set_assigned(user_id, lesson_id, lesson_id in keep)

    # -- answers already given ---------------------------------------------
    @staticmethod
    def _answer_key(query: str, service: str, render_version: str) -> str:
        return f"{service}|{render_version}|{normalise_question(query)}"

    def recall(self, query: str, service: str, render_version: str) -> Optional[dict]:
        """The stored answer to this question from this service, or None.

        Two passes. The exact key first — same words, ignoring case,
        punctuation and articles. Then the loose key, which forgives the
        opener and a misspelling of a word already in the cache. The loose
        pass is a fallback and never overrules an exact hit.
        """
        key = self._answer_key(query, service, render_version)
        rows = self._rows("SELECT key, turn, took_ms FROM answer_cache"
                          " WHERE key = ?", (key,))
        if not rows:
            rows = self._loose_match(query, service, render_version)
        if not rows:
            return None
        self._write("UPDATE answer_cache SET hits = hits + 1, last_used = ?"
                    " WHERE key = ?", (now(), rows[0]["key"]))
        return {"turn": json.loads(rows[0]["turn"]),
                "took_ms": rows[0]["took_ms"]}

    def _loose_match(self, query: str, service: str, render_version: str) -> list:
        """Ask again with the opener normalised and obvious typos repaired.

        The vocabulary is the questions this service has already answered, so
        a repair can only ever move a word towards something already cached —
        it cannot invent a term the corpus has never seen.
        """
        stored = self._rows(
            "SELECT key, query, turn, took_ms FROM answer_cache"
            " WHERE service = ? AND render_version = ?", (service, render_version))
        if not stored:
            return []
        vocabulary = {w for row in stored
                      for w in normalise_question(row["query"]).split()}
        wanted = loose_question(query, vocabulary)
        if not wanted:
            return []
        for row in stored:
            if loose_question(row["query"]) == wanted:
                return [row]
        return []

    def remember(self, query: str, service: str, render_version: str,
                 kind: str, turn: dict, took_ms: int = 0) -> None:
        """Keep an answer for next time. Overwrites: a later answer from the
        same service is the better one to serve."""
        self._write(
            "INSERT INTO answer_cache (key, query, service, render_version,"
            " kind, turn, took_ms, hits, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)"
            " ON CONFLICT(key) DO UPDATE SET turn = ?, took_ms = ?,"
            " created_at = ?, kind = ?",
            (self._answer_key(query, service, render_version), query, service,
             render_version, kind, json.dumps(turn), int(took_ms), now(),
             json.dumps(turn), int(took_ms), now(), kind))

    def forget_answers(self, service: Optional[str] = None) -> int:
        """Empty the cache — for one service, or all of it. The way to make
        the app re-ask after the corpus on the board changes."""
        if service:
            cur = self._write("DELETE FROM answer_cache WHERE service = ?",
                              (service,))
        else:
            cur = self._write("DELETE FROM answer_cache")
        return cur.rowcount

    def cached_answers(self) -> list[dict]:
        return [dict(r) for r in self._rows(
            "SELECT query, service, render_version, kind, took_ms, hits,"
            " created_at, last_used FROM answer_cache"
            " ORDER BY hits DESC, created_at DESC")]

    # -- the admin's view --------------------------------------------------
    def all_progress(self) -> dict[str, dict[str, list[int]]]:
        """Every operator's completed steps, in one pass. The admin screen
        shows the whole roster at once; a query per user per lesson would be
        dozens of round trips for one refresh."""
        out: dict[str, dict[str, list[int]]] = {}
        for row in self._rows(
                "SELECT user_id, lesson_id, step_index FROM lesson_progress"
                " ORDER BY user_id, lesson_id, step_index"):
            out.setdefault(row["user_id"], {}).setdefault(
                row["lesson_id"], []).append(row["step_index"])
        return out

    def all_assignments(self) -> dict[str, set[str]]:
        """Per operator, the lessons withheld from them."""
        out: dict[str, set[str]] = {}
        for row in self._rows("SELECT user_id, lesson_id FROM lesson_state"
                              " WHERE assigned = 0"):
            out.setdefault(row["user_id"], set()).add(row["lesson_id"])
        return out
