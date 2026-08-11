"""The pywebview bridge — everything the UI is allowed to do.

`emit` is injected rather than reaching for a window, so the whole bridge is
ordinary Python and tests need no browser. Methods never raise: an exception
crossing into JavaScript surfaces as an unhandled promise rejection, which is
invisible. Every method returns a result envelope instead.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from . import commands, intents, lessons, llm, smalltalk
from .client.health import ConnectionState, HealthMonitor
from .db import Store, now as db_now, slugify
from .logs import get as get_logger
from .client.transport import StaleResponse, Transport, TransportError
from .config import Config
from .models.wire import Turn
from .turnlog import TurnLog

Emit = Callable[[str, dict], None]
log = get_logger("api")

# The trainer's own login, which is not an operator badge. There are no roles
# and no second admin: one shop floor, one person who sets up the training.
# Both are overridable, so a site that cares can change them without a build.
ADMIN_USER = os.environ.get("ASSIST_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ASSIST_ADMIN_PASSWORD", "admin")


def recall_delay_s() -> float:
    """How long a remembered answer should take to come back.

    A cache hit is ready in about six milliseconds, and an answer that appears
    the instant the question lands reads as though nothing happened — no
    search, no thinking, possibly no answer to the question actually asked.
    Holding it for a couple of seconds is not a fake search; the wait is the
    only part of the original that was worth keeping.

    Read per call so it can be tuned without a restart, and set to 0 to hand
    answers back as fast as they are found.
    """
    try:
        return max(0.0, float(os.environ.get("ASSIST_RECALL_DELAY_S", "2.5")))
    except ValueError:
        return 2.5


def _command_turn(result: "commands.CommandResult") -> dict:
    """Dress a command result as a turn, so it flows through history, the
    conversation and speech exactly like an answer does."""
    return {
        "plan": {"kind": "command", "chunk_ids": [],
                 "reason": f"{result.name} {'ok' if result.ok else 'FAILED'}"},
        "answer": {
            "display_text": result.spoken,
            "spoken_segments": [result.spoken],
            "safety": [], "citations": [], "images": [],
            "render_version": "command", "source_hash": "",
        },
        "candidates": [],
        "timing": {"search_ms": 0, "render_ms": 0, "total_ms": 0},
    }


def _chat_turn(reply: str, ok: bool = True) -> dict:
    """Dress a reply from Chris as a turn, so it flows through history, the
    conversation and speech like any other answer. No citations and no
    candidates: nothing here came from the manual, and pretending otherwise
    would put a page number under something Chris said."""
    return {
        "plan": {"kind": "chat", "chunk_ids": [],
                 "reason": "smalltalk" if ok else "chat failed"},
        "answer": {
            "display_text": reply,
            "spoken_segments": [reply],
            "safety": [], "citations": [], "images": [],
            "render_version": "chat", "source_hash": "",
        },
        "candidates": [],
        "timing": {"search_ms": 0, "render_ms": 0, "total_ms": 0},
    }


def _turn_to_dict(turn: Turn) -> dict:
    return {
        "plan": asdict(turn.plan),
        "answer": asdict(turn.answer) if turn.answer else None,
        "candidates": [asdict(c) for c in turn.candidates],
        "timing": turn.timing,
    }


# Which panel owns which screen. Only these two are on monitors of their own;
# everything else is drawn wherever it was asked for.
_PANEL_FOR = {"chat": "chat", "lesson": "lesson"}

# How long Chris waits for an answer. Long enough to think and speak a short
# reply, short enough that somebody who has walked away is not held up by a
# screen counting down at them. Overridable for a slow room.
PROMPT_SECONDS = float(os.environ.get("ASSIST_PROMPT_SECONDS", "7"))


class Api:
    def __init__(self, config: Config, emit: Emit,
                 log_path: Optional[Path] = None,
                 db_path: Optional[Path] = None,
                 catalog_path: Optional[Path] = None) -> None:
        self._config = config
        self._emit = emit
        self._transport = Transport(config.devkit_url, config.timeout_s)
        self._log = TurnLog(log_path or Path("turns.jsonl"))
        db_path = Path(db_path or "data/assist.db")
        # Whatever the JSON era left behind, imported once. See db.py.
        self._users = Store(db_path,
                            legacy_profiles=db_path.parent / "profiles.json",
                            legacy_progress=db_path.parent / "lesson_progress.json")
        self._monitor = HealthMonitor(self._transport, self._on_connection_change)
        # Voice asks originate in the audio thread, which has no idea who is
        # signed in — the UI tells us on sign-in and we remember.
        self._active_user = ""
        # Replaced by __main__ once the windows exist. No-ops until then, so
        # a UI that asks to minimise during startup is ignored rather than
        # raising at somebody mid-demo.
        self._minimize_windows = lambda: None
        self._close_windows = lambda: None
        self._raise_window = lambda _role: None
        # What is on screen, so "hey chris" can mean something local. Empty
        # means everything spoken goes to the manual, as it always did.
        self._voice_context = ""
        self._voice_context_user = ""
        self._voice = None
        self._catalog = lessons.load_catalog(catalog_path
                                             or lessons.DEFAULT_CATALOG)
        self._tailer: Optional[lessons.LogTailer] = None
        self._open_lesson = ""
        self._admin = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._monitor.start()

    def stop(self) -> None:
        self._monitor.stop()
        self.close_lesson()

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

        # Commands act; questions get answered. "fold the boom" folds it,
        # "how do i fold the boom" explains it. See commands.py for how the
        # two are told apart.
        done = commands.match_and_execute(query)
        if done is not None:
            payload = _command_turn(done)
            self._log.append_command(query, done.name, done.ok, done.detail,
                                     source=source)
            if user_id:
                self._users.record(user_id, query, "command", source, turn=payload)
            return {"ok": True, "turn": payload, "error": None}

        # The training is ours to answer, not the board's. The manual is a
        # procedure corpus for an R4045 and has never heard of a lesson plan,
        # so "what lesson plans are there" retrieved for ten seconds and
        # answered "I don't know". Chris knows, because Chris is holding the
        # catalog.
        taught = self._answer_about_lessons(query, user_id, source)
        if taught is not None:
            return taught

        # Greetings go to Chris; anything about the machine goes to the
        # manual. The default is the manual -- see smalltalk.py for why that
        # direction is the safe one.
        if smalltalk.is_smalltalk(query):
            ok, reply = llm.chat(query)
            if ok:
                payload = _chat_turn(reply)
                if user_id:
                    self._users.record(user_id, query, "chat", source,
                                       turn=payload)
                return {"ok": True, "turn": payload, "error": None}
            # Chris is down. Say so rather than silently searching the manual
            # for "how are you" and answering "I don't know".
            log.warning("  chris failed: %s", reply)
            payload = _chat_turn("I can't reach my conversation model right "
                                 "now, but I can still answer questions about "
                                 "the machine.", ok=False)
            if user_id:
                self._users.record(user_id, query, "chat", source, turn=payload)
            return {"ok": True, "turn": payload, "error": None}

        # The wake word rides along in voice transcripts; retrieval should not
        # have to match against it.
        query = smalltalk.strip_wake_word(query) or query

        # Asked before, on this pipeline? Then it is already answered. The
        # board takes six seconds to retrieve and up to thirty to synthesise;
        # this is the same answer, from this machine, in about a millisecond.
        asked_at = time.perf_counter()
        recalled = self._recall(query)
        if recalled is not None:
            waited = self._pace(asked_at)
            recalled["timing"] = {**recalled["timing"], "total_ms": waited}
            self._log.append_recall(query, recalled, source=source)
            if user_id:
                self._users.record(user_id, query,
                                   recalled["plan"]["kind"], source,
                                   turn=recalled)
            return {"ok": True, "turn": recalled, "error": None,
                    "recalled": True}

        started = time.perf_counter()
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
        # The manual is a procedure corpus and has no glossary, so a fair
        # question like "what is a boom" comes back out-of-scope. Let Chris
        # explain the concept -- never the numbers or the steps.
        if turn.plan.kind == "oos":
            ok, reply = llm.explain(query)
            if ok:
                self._log.append(query, turn, source=source)
                payload = _chat_turn(reply)
                payload["plan"]["reason"] = "oos -> chris explained"
                if user_id:
                    self._users.record(user_id, query, "chat", source,
                                       turn=payload)
                return {"ok": True, "turn": payload, "error": None}

        self._log.append(query, turn, source=source)
        top = turn.candidates[0].procedure_name if turn.candidates else "-"
        log.info("  %s in %sms - %s", turn.plan.kind,
                 turn.timing.get("total_ms", "?"), top or "-")
        payload = _turn_to_dict(turn)
        self._remember(query, turn, payload,
                       took_ms=int((time.perf_counter() - started) * 1000))
        # The whole turn is stored, so re-opening a past question re-renders the
        # answer as it was given rather than re-asking a corpus that may differ.
        if user_id:
            self._users.record(user_id, query, turn.plan.kind, source,
                               turn=payload)
        return {"ok": True, "turn": payload, "error": None}

    # -- answers already given ---------------------------------------------
    def _service_identity(self) -> tuple[str, str]:
        """Which pipeline answered. An answer from v3 must never be served as
        though it came from v4, so both halves are part of the cache key."""
        return self._config.devkit_url, self._monitor.render_version or "?"

    def _pace(self, asked_at: float) -> int:
        """Hold a remembered answer back to the pace of a real one, and report
        how long it actually took. The timing is not padded to look like the
        original search — six seconds is claimed nowhere; what is reported is
        the wait that happened."""
        target = recall_delay_s()
        elapsed = time.perf_counter() - asked_at
        if elapsed < target:
            time.sleep(target - elapsed)
        return int((time.perf_counter() - asked_at) * 1000)

    def _recall(self, query: str) -> Optional[dict]:
        service, version = self._service_identity()
        found = self._users.recall(query, service, version)
        if found is None:
            return None
        turn = found["turn"]
        # Say where it came from, and how long it took the first time. Timing
        # must not claim six seconds for something that took no time at all.
        turn["plan"] = {**turn["plan"],
                        "reason": f"{turn['plan']['reason']} · recalled"}
        turn["timing"] = {**turn.get("timing", {}),
                          "first_answered_ms": found["took_ms"]}
        turn["recalled"] = True
        log.info("  recalled (first answer took %sms)", found["took_ms"])
        return turn

    def _remember(self, query: str, turn: Turn, payload: dict,
                  took_ms: int) -> None:
        """Keep answers, not verdicts. An `oos` is the corpus failing to match
        today and may match tomorrow; storing it would make a miss permanent.
        Errors are not answers at all."""
        if turn.plan.kind not in ("cached", "synthesize") or not turn.answer:
            return
        service, version = self._service_identity()
        self._users.remember(query, service, version, turn.plan.kind,
                             payload, took_ms=took_ms)

    def forget_answers(self, all_services: bool = False) -> dict:
        """Empty the cache. Use after the corpus on the board changes — the
        client cannot see that happen."""
        service, _ = self._service_identity()
        removed = self._users.forget_answers(None if all_services else service)
        log.info("cache cleared: %d answer(s)", removed)
        return {"ok": True, "removed": removed}

    def cached_answers(self) -> dict:
        return {"ok": True, "answers": self._users.cached_answers()}

    # -- who is at the screen ---------------------------------------------
    def list_users(self) -> dict:
        return {"ok": True, "users": self._users.list_users()}

    def login(self, name: str) -> dict:
        # Asked before the write, because login() creates the profile when it
        # is missing -- afterwards everybody looks like a returning operator.
        # This is the whole difference between "Welcome" and "Welcome back".
        returning = self._users.get_user(slugify(name or "")) is not None
        try:
            user = self._users.login(name)
        except ValueError as e:
            return {"ok": False, "user": None, "error": str(e),
                    "returning": False}
        return {"ok": True, "user": user, "error": None,
                "returning": returning}

    def history(self, user_id: str) -> dict:
        return {"ok": True, "entries": self._users.history(user_id)}

    def clear_history(self, user_id: str) -> dict:
        self._users.clear_history(user_id)
        return {"ok": True}

    def mark_onboarded(self, user_id: str) -> dict:
        """They have been shown how to bring the simulator up. Once is enough."""
        self._users.mark_onboarded(user_id)
        return {"ok": True}

    # -- lessons -----------------------------------------------------------
    def lessons(self, user_id: str = "") -> dict:
        """The catalog this operator has been assigned, plus their record of
        it. A lesson the admin withheld is not listed — an operator should not
        see a locked door, only the lessons that are theirs."""
        withheld = self._users.assignments(user_id) if user_id else set()
        categories = []
        for category in self._catalog.get("categories", []):
            allowed = [lesson for lesson in category.get("lessons", [])
                       if lesson.get("id") not in withheld]
            if allowed:
                categories.append({**category, "lessons": allowed})
        return {"ok": True, "categories": categories,
                "progress": self._users.lesson_summary(user_id)}

    def _answer_about_lessons(self, query: str, user_id: str,
                              source: str) -> Optional[dict]:
        """Answer a question about the training, or None to carry on.

        Two shapes. "What lessons are there" is answered with the list, read
        out with its numbers so the numbers can then be said back. "Start the
        boom lesson plan" opens it.

        A question about the machine that merely mentions a lesson is left
        alone -- see `looks_like_a_question`. Somebody asking how to fold the
        boom wants the procedure, not a menu.
        """
        if not intents.asks_about_lessons(query):
            return None

        try:
            visible = self._visible_lessons(user_id)
        except Exception:
            log.exception("could not read the lesson list")
            return None
        if not visible:
            return None

        wanted = intents.lesson(query, visible)
        if wanted and not intents.looks_like_a_question(query):
            name = next((l["title"] for l in visible if l["id"] == wanted),
                        "that lesson")
            log.info("  lesson request -> %s", wanted)
            # The lesson list lives on its own panel, so this has to travel.
            self._emit("lesson_heard", {"text": query, "lesson_id": wanted})
            self.navigate("lesson")
            return self._lesson_reply(f"Opening {name}.", query, user_id, source)

        listed = ", ".join(f"{l.get('number') or i + 1}, {l['title']}"
                           for i, l in enumerate(visible))
        reply = (f"There {'is' if len(visible) == 1 else 'are'} "
                 f"{len(visible)} lesson{'' if len(visible) == 1 else 's'}: "
                 f"{listed}. Say the number or the name to start one.")
        log.info("  lesson list (%d)", len(visible))
        self.navigate("lesson")
        return self._lesson_reply(reply, query, user_id, source)

    def _lesson_reply(self, reply: str, query: str, user_id: str,
                      source: str) -> dict:
        payload = _chat_turn(reply)
        payload["plan"]["reason"] = "lessons"
        if user_id:
            self._users.record(user_id, query, "chat", source, turn=payload)
        return {"ok": True, "turn": payload, "error": None}

    def open_lesson(self, user_id: str, lesson_id: str) -> dict:
        """Open a lesson and, where its steps are wired to signals, start
        watching the simulator's log so they complete on their own."""
        lesson, category = lessons.find_lesson(self._catalog, lesson_id)
        if lesson is None:
            return {"ok": False, "error": f"no lesson called {lesson_id!r}"}

        self.close_lesson()
        self._users.open_lesson(user_id, lesson_id)
        self._open_lesson = lesson_id
        done = self._users.steps_done(user_id, lesson_id)
        result = {"ok": True, "lesson": lesson, "category": category,
                  "steps_done": done, "sync": False, "detail": ""}

        triggers = lessons.triggers_for(lesson)
        if not triggers:
            result["detail"] = ("This lesson is performed in Farming "
                                "Simulator, which does not report back. "
                                "Tick each step off as you go.")
            return result

        path = lessons.sim_log_path(self._catalog)
        if not path or not Path(path).is_file():
            result["detail"] = (f"The simulator log is not at {path or '(unset)'}"
                                " — steps will not complete on their own. "
                                "Start the Connections App, or tick them off "
                                "by hand.")
            log.warning("lesson %s opened without a log at %s", lesson_id, path)
            return result

        watcher = lessons.StepWatcher(triggers)
        # Resume rather than restart: a step done in an earlier session stays
        # done, and ordered steps that wait on it can fire again.
        watcher.done.update(done)
        self._tailer = lessons.LogTailer(
            path, watcher,
            on_step=lambda index: self._on_lesson_step(user_id, lesson_id, index))
        self._tailer.start()
        log.info("lesson %s open, watching %s", lesson_id, path)
        result["sync"] = True
        result["detail"] = ("Watching the CommandARM. Steps complete as you "
                            "operate the console.")
        return result

    def _on_lesson_step(self, user_id: str, lesson_id: str, index: int) -> None:
        """Called from the tailer thread. Nobody is awaiting a promise for
        this, so it goes out as an event."""
        self._users.complete_step(user_id, lesson_id, index)
        log.info("lesson %s step %d complete", lesson_id, index)
        self._emit("lesson_step", {"lesson_id": lesson_id, "step_index": index,
                                   "source": "machine"})

    def close_lesson(self) -> dict:
        if self._tailer is not None:
            self._tailer.stop()
            self._tailer = None
        self._open_lesson = ""
        return {"ok": True}

    def complete_step(self, user_id: str, lesson_id: str,
                      step_index: int) -> dict:
        """Tick a step off by hand — for lessons played in the simulator,
        where nothing reaches the log, and for a signal the log missed."""
        self._users.complete_step(user_id, lesson_id, int(step_index))
        return {"ok": True,
                "steps_done": self._users.steps_done(user_id, lesson_id)}

    def reset_lesson(self, user_id: str, lesson_id: str) -> dict:
        self._users.reset_lesson(user_id, lesson_id)
        # A lesson being watched has its own idea of what is done. Reopen it
        # so the log starts marking steps from the beginning again.
        if self._open_lesson == lesson_id and self._tailer is not None:
            self.open_lesson(user_id, lesson_id)
        return {"ok": True, "steps_done": []}

    # -- getting started ----------------------------------------------------
    def starter_video(self) -> dict:
        """The recording that shows how to bring the simulator up. Served
        from where it was recorded, over 127.0.0.1 — see bundle_server."""
        path = Path(self._config.starter_video)
        available = path.is_file()
        if not available:
            log.warning("starter video missing: %s", path)
        return {"ok": True, "url": "/media/starter.mp4",
                "available": available, "path": str(path)}

    # -- the admin -----------------------------------------------------------
    def admin_login(self, username: str, password: str) -> dict:
        """One shared trainer login. The password is checked here and never
        travels to the UI, which only ever learns yes or no."""
        ok = ((username or "").strip().lower() == ADMIN_USER.lower()
              and (password or "") == ADMIN_PASSWORD)
        self._admin = ok
        log.info("admin sign-in %s", "accepted" if ok else "REFUSED")
        return {"ok": ok, "error": None if ok else "Wrong username or password."}

    def admin_logout(self) -> dict:
        self._admin = False
        return {"ok": True}

    def _refuse(self) -> dict:
        return {"ok": False, "error": "not signed in as admin"}

    def _lesson_index(self) -> list[dict]:
        """The catalog flattened to what the admin screen needs: one row per
        lesson, with the category it belongs to and how many steps it has."""
        out = []
        for category in self._catalog.get("categories", []):
            for lesson in category.get("lessons", []):
                out.append({
                    "id": lesson["id"],
                    "name": lesson["name"],
                    "category": category.get("name", ""),
                    "steps": len(lesson.get("steps", [])),
                    "live": any(step.get("sync")
                                for step in lesson.get("steps", [])),
                })
        return out

    def admin_overview(self) -> dict:
        """Everyone, everything, in one call — this is what the refresh button
        re-reads. Two queries for the whole roster rather than two per
        operator, because the screen shows them all at once."""
        if not self._admin:
            return self._refuse()
        index = self._lesson_index()
        progress = self._users.all_progress()
        withheld = self._users.all_assignments()

        operators = []
        for user in self._users.list_users():
            done_by_lesson = progress.get(user["id"], {})
            not_theirs = withheld.get(user["id"], set())
            summary = self._users.lesson_summary(user["id"])
            rows = {}
            done_total = 0
            steps_total = 0
            for lesson in index:
                assigned = lesson["id"] not in not_theirs
                done = len(done_by_lesson.get(lesson["id"], []))
                rows[lesson["id"]] = {
                    "done": done,
                    "assigned": assigned,
                    "last_opened": summary.get(lesson["id"], {}).get("last_opened"),
                }
                # Only assigned lessons count towards someone's progress. A
                # trainee held back from five lessons is not 30% behind.
                if assigned:
                    done_total += done
                    steps_total += lesson["steps"]
            operators.append({**user, "lessons": rows,
                              "steps_done": done_total,
                              "steps_total": steps_total})

        return {"ok": True, "lessons": index, "operators": operators,
                "refreshed_at": db_now()}

    def admin_create_user(self, name: str) -> dict:
        if not self._admin:
            return self._refuse()
        try:
            user = self._users.create_user(name)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        log.info("admin created operator %s", user["id"])
        return {"ok": True, "user": user, "error": None}

    def admin_delete_user(self, user_id: str) -> dict:
        """Remove an operator and everything recorded about them. If they are
        the one signed in at the machine, sign them out too — a deleted
        operator must not keep answering questions into a profile that is
        gone."""
        if not self._admin:
            return self._refuse()
        removed = self._users.delete_user(user_id)
        if removed and self._active_user == user_id:
            self._active_user = ""
        log.info("admin deleted operator %s (%s)", user_id,
                 "gone" if removed else "no such operator")
        return {"ok": removed,
                "error": None if removed else "no such operator"}

    def admin_set_assignments(self, user_id: str, lesson_ids) -> dict:
        """Which lessons this operator is meant to work through."""
        if not self._admin:
            return self._refuse()
        every = [lesson["id"] for lesson in self._lesson_index()]
        self._users.set_assignments(user_id, list(lesson_ids or []), every)
        return {"ok": True, "assigned": sorted(
            set(every) - self._users.assignments(user_id))}

    # -- Chris asking a question -------------------------------------------
    def ask_choice(self, seconds: float = PROMPT_SECONDS) -> dict:
        """Say the two options aloud, then listen for which one.

        Fire and forget: the answer arrives as a `choice_heard` event rather
        than as a return value, because the UI has a countdown to run in the
        meantime and cannot sit on a promise for seven seconds.
        """
        def heard(text):
            picked = intents.choice(text or "")
            log.info("choice heard %r -> %s", text, picked or "unclear")
            self._emit("choice_heard", {"text": text or "",
                                        "choice": picked})
            if picked in ("chat", "lesson"):
                self.navigate(picked)

        return self._listen("choice", seconds, heard)

    def ask_which_lesson(self, user_id: str = "",
                         seconds: float = PROMPT_SECONDS) -> dict:
        """"Which lesson?" -- answered by number or by name.

        The numbering is the one on the screen. An operator can only say "the
        third one" about the list in front of them, so the catalog is read in
        display order and filtered to what they were actually assigned.
        """
        try:
            visible = self._visible_lessons(user_id)
        except Exception:
            log.exception("could not read the lesson list")
            visible = []

        def heard(text):
            picked = intents.lesson(text or "", visible)
            log.info("lesson heard %r -> %s", text, picked or "unclear")
            self._emit("lesson_heard", {"text": text or "",
                                        "lesson_id": picked})

        return self._listen("lesson", seconds, heard)

    def _visible_lessons(self, user_id: str) -> list[dict]:
        """The lessons this operator can see, in the order they are shown.

        `name` is the field the catalog actually uses; reading `title` here
        handed the matcher a list of empty strings, so a lesson could only
        ever be picked by number and never by name.
        """
        catalog = self.lessons(user_id)
        out: list[dict] = []
        for category in catalog.get("categories", []):
            for item in category.get("lessons", []):
                out.append({"id": item.get("id"),
                            "title": item.get("name") or item.get("title", ""),
                            "number": item.get("number")})
        return out

    def _listen(self, name: str, seconds: float, handler) -> dict:
        try:
            session = self._voice_session()
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        started = session.listen(seconds, handler, name=name)
        # Not an error. The microphone may be busy, or off entirely, and the
        # screen still works by touch -- the point of asking aloud is that it
        # is an addition to the buttons, never the only way through.
        return {"ok": True, "listening": bool(started)}

    def cancel_listening(self) -> dict:
        """They tapped instead of answering."""
        if self._voice is not None:
            self._voice.cancel_prompt()
        return {"ok": True}

    def set_voice_context(self, context: str = "", user_id: str = "") -> dict:
        """What is on screen, so "hey chris" can mean something local.

        The seven second window closes, and the operator still wants lesson
        two. Saying "hey chris, lesson two" has to work — but the wake word
        feeds the manual, and "lesson two" is not in the manual.

        So while the lesson list is up, a spoken line is offered to the list
        first. Only what the list cannot use goes on to the board.
        """
        self._voice_context = context or ""
        self._voice_context_user = user_id or ""
        return {"ok": True}

    def _handled_by_context(self, text: str) -> bool:
        """True if the screen took this line, so the manual should not see it."""
        if self._voice_context != "lesson":
            return False
        # "how do i fold the boom" is a question for the manual, even standing
        # in front of a lesson called Fold the Boom. Only the opening words
        # tell those two apart.
        if intents.looks_like_a_question(text):
            return False
        try:
            visible = self._visible_lessons(self._voice_context_user)
        except Exception:
            log.exception("could not read the lesson list")
            return False
        picked = intents.lesson(text, visible)
        if not picked:
            return False
        log.info("context lesson %r -> %s", text, picked)
        self._emit("lesson_heard", {"text": text, "lesson_id": picked})
        return True

    # -- moving between panels ---------------------------------------------
    def navigate(self, screen: str) -> dict:
        """Ask for a screen, from any panel.

        A tile is tapped on whichever monitor the operator is standing at, but
        the chatbot only exists on the chatbot's panel. So the request is
        broadcast and the panel that owns that screen answers it; the others
        leave themselves alone. Without this, tapping "chatbot" on the lesson
        monitor either does nothing or draws a second chatbot in the wrong
        place.
        """
        self._emit("navigate", {"screen": screen})
        self._raise_role(_PANEL_FOR.get(screen, ""))
        return {"ok": True}

    def _raise_role(self, role: str) -> None:
        """Bring a panel forward, if something else is covering it."""
        if not role:
            return
        try:
            self._raise_window(role)
        except Exception:
            log.exception("could not raise the %s panel", role)

    # -- the windows themselves --------------------------------------------
    def set_window_controls(self, minimize, close, raise_window=None) -> None:
        """Hand the UI a way to minimise, close, and bring a panel forward.

        The windows are frameless, so there is no title bar and no X. Without
        this there is no way out of a fullscreen window that covers the panel
        it is on — which is a demo nobody can end.
        """
        self._minimize_windows = minimize
        self._close_windows = close
        if raise_window is not None:
            self._raise_window = raise_window

    def minimize_window(self) -> dict:
        """Get out of the way without ending the session.

        Every panel goes down together. Minimising one of two fullscreen
        windows leaves the other covering its monitor, which looks like a
        half-crashed app rather than an app that stepped aside.
        """
        try:
            self._minimize_windows()
            return {"ok": True}
        except Exception as e:
            log.exception("could not minimise")
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def close_window(self) -> dict:
        try:
            self._close_windows()
            return {"ok": True}
        except Exception as e:
            log.exception("could not close")
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # -- voice -------------------------------------------------------------
    def set_active_user(self, user_id: str) -> dict:
        """Who a spoken question belongs to. Called on sign-in and sign-out.

        Also the moment the other panels find out. Sign-in happens in one
        window; the lesson plan is on a different monitor in a different
        window and would otherwise sit black through the whole session,
        waiting for somebody who, as far as it knows, never arrived.
        """
        self._active_user = user_id or ""
        log.info("active user: %s", self._active_user or "(signed out)")
        user = self._users.get_user(self._active_user) if self._active_user \
            else None
        self._emit("active_user", {"user": user})
        return {"ok": True}

    def _ask_from_voice(self, text: str) -> None:
        """A spoken question takes the identical path to a typed one, then the
        answer is pushed as an event — nobody is awaiting a promise for it."""
        # The screen gets first refusal. Standing at the lesson list, "hey
        # chris, lesson two" is a lesson, and searching the manual for it
        # would spend ten seconds arriving at "I don't know".
        if self._handled_by_context(text):
            return
        result = self.ask(text, source="voice", user_id=self._active_user)
        self._emit("answer", {"query": text, **result})
        # Asked by voice, answered by voice.
        turn = result.get("turn") or {}
        answer = turn.get("answer") or {}
        segments = answer.get("spoken_segments") or []
        if segments and self._voice is not None:
            self._voice.say(segments)
        elif turn.get("plan", {}).get("kind") == "oos" and self._voice is not None:
            self._voice.say(["I don't know. Nothing in the manual matched that."])

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
        # Through the session when there is one: it knows to close the stream
        # around the scan. Enumerating underneath a live stream crashed the
        # picker with PortAudio -10000.
        if self._voice is not None:
            return {"ok": True, "devices": self._voice.devices(),
                    "current": self._voice._mic.device}
        return {"ok": True, "devices": list_input_devices(), "current": None}

    def set_audio_device(self, index) -> dict:
        try:
            value = None if index in (None, "", -1, "-1") else int(index)
            return {"ok": True, **self._voice_session().set_device(value)}
        except Exception as e:
            log.exception("could not switch microphone")
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def speak(self, segments) -> dict:
        try:
            ok = self._voice_session().say(list(segments or []))
            return {"ok": bool(ok)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def stop_speaking(self) -> dict:
        if self._voice is not None:
            self._voice.hush()
        return {"ok": True}

    def voice_status(self) -> dict:
        if self._voice is None:
            return {"ok": True, "state": "off", "wake_ready": False,
                    "stt_ready": False, "mic_running": False, "error": None}
        return {"ok": True, **self._voice.status()}
