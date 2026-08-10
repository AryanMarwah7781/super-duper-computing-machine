import json
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from assist_desktop.api import Api
from assist_desktop.config import Config
from tools.fake_devkit import make_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="module")
def devkit_url():
    config = uvicorn.Config(make_app(FIXTURES), host="127.0.0.1", port=8124,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "fake devkit failed to start"
    yield "http://127.0.0.1:8124"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def api(devkit_url, tmp_path):
    return Api(Config(devkit_url=devkit_url), emit=lambda n, p: None,
               log_path=tmp_path / "turns.jsonl",
               db_path=tmp_path / "assist.db")


def test_ask_returns_a_serialisable_turn(api):
    result = api.ask("how do i fill the tank")
    assert result["ok"] is True
    assert result["turn"]["plan"]["kind"] == "cached"
    assert result["turn"]["answer"]["safety"][0]["level"] == "WARNING"


def test_ask_never_raises_into_js(tmp_path):
    api = Api(Config(devkit_url="http://127.0.0.1:9", timeout_s=1.0),
              emit=lambda n, p: None, log_path=tmp_path / "turns.jsonl",
              db_path=tmp_path / "assist.db")
    result = api.ask("anything")
    assert result["ok"] is False
    assert result["turn"] is None
    assert result["error"]


def test_ask_logs_the_turn(api, tmp_path):
    api.ask("what tire pressure")
    assert (tmp_path / "turns.jsonl").read_text(encoding="utf-8").strip()


def test_ask_emits_an_error_event_on_failure(tmp_path):
    events: list[tuple[str, dict]] = []
    api = Api(Config(devkit_url="http://127.0.0.1:9", timeout_s=1.0),
              emit=lambda n, p: events.append((n, p)),
              log_path=tmp_path / "turns.jsonl",
              db_path=tmp_path / "assist.db")
    api.ask("anything")
    assert any(name == "error" for name, _ in events)


def test_lists_the_mock_users(api):
    names = [u["name"] for u in api.list_users()["users"]]
    assert "Priya Sharma" in names


def test_login_returns_a_user(api):
    result = api.login("Aryan")
    assert result["ok"] is True
    assert result["user"]["id"] == "aryan"


def test_login_rejects_an_empty_name(api):
    assert api.login("  ")["ok"] is False


def test_asking_as_a_user_records_history(api):
    api.login("Aryan")
    api.ask("how do i fill the solution tank", user_id="aryan")
    entries = api.history("aryan")["entries"]
    assert len(entries) == 1
    assert entries[0]["query"] == "how do i fill the solution tank"
    assert entries[0]["turn"]["answer"]["display_text"]


def test_asking_without_a_user_records_nothing(api):
    api.ask("how do i fill the solution tank")
    assert api.history("aryan")["entries"] == []


def test_a_failed_ask_is_still_recorded_for_the_user(tmp_path):
    api = Api(Config(devkit_url="http://127.0.0.1:9", timeout_s=1.0),
              emit=lambda n, p: None, log_path=tmp_path / "turns.jsonl",
              db_path=tmp_path / "assist.db")
    api.login("Aryan")
    api.ask("anything", user_id="aryan")
    assert api.history("aryan")["entries"][0]["kind"] == "error"


def test_empty_question_is_rejected(api):
    assert api.ask("   ")["ok"] is False


def test_oos_never_comes_back_looking_like_the_manual(api, monkeypatch):
    """Out-of-scope may now be explained by Chris, but it must never be dressed
    as a manual answer: no citations, no page, no chunk ids, nothing implying
    the manual backed it.

    This replaces an earlier test asserting `answer is None`. The rule that was
    protecting -- never present a guess as the manual -- is unchanged; a null
    answer was one way to keep it and a clearly marked chat turn is another.
    With Chris down it still falls back to null, which
    test_chris_failing_on_a_fallback_leaves_the_honest_i_dont_know pins.
    """
    monkeypatch.setattr("assist_desktop.llm.explain",
                        lambda t: (True, "This isn't from the manual. A boom is "
                                         "the folding spray arm."))
    result = api.ask("what is the weather")
    turn = result["turn"]
    assert result["ok"] is True
    assert turn["plan"]["kind"] == "chat", "marked as conversation, not retrieval"
    assert turn["answer"]["citations"] == []
    assert turn["plan"]["chunk_ids"] == []
    assert turn["candidates"] == []


# -- commands act instead of searching ------------------------------------

def test_an_order_runs_the_command_and_never_reaches_the_manual(api, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr("assist_desktop.commands._send",
                        lambda p: (sent.append(p) or (True, "")))
    result = api.ask("fold the boom")
    assert result["ok"] is True
    assert result["turn"]["plan"]["kind"] == "command"
    assert sent == ["Fold the Boom"]
    assert result["turn"]["timing"]["total_ms"] == 0, "no retrieval happened"


def test_asking_how_still_searches_the_manual(api, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr("assist_desktop.commands._send",
                        lambda p: (sent.append(p) or (True, "")))
    result = api.ask("how do i fold the boom")
    assert result["turn"]["plan"]["kind"] != "command"
    assert sent == [], "a question must not touch the machine"


def test_a_command_is_spoken_and_recorded(api, monkeypatch):
    monkeypatch.setattr("assist_desktop.commands._send", lambda p: (True, ""))
    api.login("Aryan")
    api.ask("start spraying", user_id="aryan")
    entries = api.history("aryan")["entries"]
    assert entries[0]["kind"] == "command"
    assert entries[0]["turn"]["answer"]["spoken_segments"]


def test_an_unreachable_simulator_is_reported_not_claimed(api, monkeypatch):
    monkeypatch.setattr("assist_desktop.commands._send",
                        lambda p: (False, "ConnectError: refused"))
    result = api.ask("unfold the boom")
    text = result["turn"]["answer"]["display_text"].lower()
    assert "not" in text, "must not claim the boom moved"


def test_every_command_is_logged_whether_or_not_it_worked(api, tmp_path,
                                                          monkeypatch):
    """The one thing this app does that moves machinery. Whether it fired has
    to be answerable afterwards, not only when it raised."""
    import json
    monkeypatch.setattr("assist_desktop.commands._send", lambda p: (True, ""))
    api.ask("fold the boom")
    monkeypatch.setattr("assist_desktop.commands._send",
                        lambda p: (False, "ConnectError: refused"))
    api.ask("unfold the boom")
    lines = [json.loads(l) for l in
             (tmp_path / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    commands = [l for l in lines if l["kind"] == "command"]
    assert [(c["command"], c["ok"]) for c in commands] == [
        ("fold_boom", True), ("unfold_boom", False)]


# -- greetings go to Chris, machine questions go to the manual -------------

def test_a_greeting_reaches_chris_and_never_the_manual(api, monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr("assist_desktop.llm.chat",
                        lambda t, history=None: (asked.append(t) or (True, "I'm here.")))
    result = api.ask("how are you")
    assert result["turn"]["plan"]["kind"] == "chat"
    assert result["turn"]["answer"]["display_text"] == "I'm here."
    assert asked == ["how are you"]
    assert result["turn"]["answer"]["citations"] == [], "Chris cites nothing"


def test_a_machine_question_never_reaches_chris(api, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr("assist_desktop.llm.chat",
                        lambda t, history=None: (called.append(t) or (True, "nope")))
    result = api.ask("how do i fill the tank")
    assert result["turn"]["plan"]["kind"] != "chat"
    assert called == [], "the manual answers machine questions, not the model"


def test_the_wake_word_is_stripped_before_retrieval(api, monkeypatch):
    seen: list[str] = []
    real = api._transport.ask
    monkeypatch.setattr(api._transport, "ask",
                        lambda q, top_k=5: (seen.append(q) or real(q, top_k=top_k)))
    api.ask("hey chris how do i fill the tank")
    assert seen == ["how do i fill the tank"]


def test_chris_being_down_does_not_send_a_greeting_to_the_manual(api, monkeypatch):
    monkeypatch.setattr("assist_desktop.llm.chat",
                        lambda t, history=None: (False, "ConnectError"))
    result = api.ask("hello")
    assert result["ok"] is True
    assert result["turn"]["plan"]["kind"] == "chat"
    assert "machine" in result["turn"]["answer"]["display_text"].lower()


def test_a_question_the_manual_cannot_answer_reaches_chris_for_a_concept(api,
                                                                monkeypatch):
    """The manual says how to fold a boom and never what one is, so "what is a
    boom" came back out-of-scope in 69ms. A definition is safe to give."""
    seen: list[str] = []
    monkeypatch.setattr("assist_desktop.llm.explain",
                        lambda t: (seen.append(t) or
                                   (True, "This isn't from the manual. The boom is the "
                                          "folding arm carrying the nozzles.")))
    result = api.ask("what is the weather")      # fixture returns oos
    assert result["turn"]["plan"]["kind"] == "chat"
    assert "boom" in result["turn"]["answer"]["display_text"]
    assert seen == ["what is the weather"]


def test_the_oos_fallback_is_told_to_refuse_numbers_and_procedures():
    """The whole safety of the fallback rests on this instruction."""
    from assist_desktop.llm import FALLBACK_NOTE
    lowered = FALLBACK_NOTE.lower()
    for forbidden in ("torque", "pressure", "procedure", "menu path", "number"):
        assert forbidden in lowered, forbidden
    assert "must not" in lowered


def test_an_oos_question_still_reaches_the_manual_first(api, monkeypatch):
    """Chris is the fallback, not the front door. Retrieval runs first."""
    asked: list[str] = []
    real = api._transport.ask
    monkeypatch.setattr(api._transport, "ask",
                        lambda q, top_k=5: (asked.append(q) or real(q, top_k=top_k)))
    monkeypatch.setattr("assist_desktop.llm.explain", lambda t: (True, "x"))
    api.ask("what is the weather")
    assert asked == ["what is the weather"]


def test_chris_failing_on_a_fallback_leaves_the_honest_i_dont_know(api,
                                                                   monkeypatch):
    monkeypatch.setattr("assist_desktop.llm.explain", lambda t: (False, "down"))
    result = api.ask("what is the weather")
    assert result["turn"]["plan"]["kind"] == "oos"
    assert result["turn"]["answer"] is None, "no invented answer when Chris is down"


def test_the_board_is_given_time_to_answer(api):
    """A fixed 20s deadline was cutting off real answers once Chris started
    sharing the board's CPU. A slow question is slow, not broken."""
    from assist_desktop.config import Config
    assert Config().timeout_s >= 120, "must not cut the board off mid-answer"
    assert Config.load().timeout_s >= 120


# -- lessons ---------------------------------------------------------------

def lesson_api(tmp_path, catalog: dict, emit=None):
    catalog_path = tmp_path / "lessons.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    return Api(Config(devkit_url="http://127.0.0.1:9"),
               emit=emit or (lambda n, p: None),
               log_path=tmp_path / "turns.jsonl",
               db_path=tmp_path / "assist.db",
               catalog_path=catalog_path)


def one_lesson_catalog(log_path: str) -> dict:
    return {
        "log_path": log_path,
        "categories": [{
            "name": "CommandARM Lessons",
            "lessons": [{
                "id": "pump", "name": "Solution Pump", "summary": "",
                "steps": [
                    {"header": "Pump on", "body": "Press it.",
                     "sync": {"signals": ["PLT_AIC_SolutionPump"],
                              "condition": "equals", "value": "1"}},
                    {"header": "Walk away", "body": "No signal for this one."},
                ],
            }],
        }],
    }


def press(signal: str, value: str) -> str:
    return ('2026-08-07 12:00:15,432 DEBUG - MsgQueueDataHandler.SendVIOData():'
            f' Data: {{"signal":"{signal}","value":"{value}"}}\n')


def test_the_shipped_catalog_reaches_the_ui(tmp_path):
    api = Api(Config(devkit_url="http://127.0.0.1:9"), emit=lambda n, p: None,
              log_path=tmp_path / "turns.jsonl",
              db_path=tmp_path / "assist.db")
    result = api.lessons("ari")
    assert result["ok"] is True
    assert result["categories"], "the lesson catalog ships with the app"
    assert result["progress"] == {}


def test_a_press_completes_a_step_and_is_pushed_to_the_ui(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    events: list[tuple[str, dict]] = []
    api = lesson_api(tmp_path, one_lesson_catalog(str(log)),
                     emit=lambda name, data: events.append((name, data)))
    api.login("Ari")

    opened = api.open_lesson("ari", "pump")
    assert opened["sync"] is True
    log.write_text(press("PLT_AIC_SolutionPump", "1"), encoding="utf-8")
    api._tailer.poll()
    api.close_lesson()

    assert events == [("lesson_step", {"lesson_id": "pump", "step_index": 1,
                                       "source": "machine"})]
    assert api.lessons("ari")["progress"]["pump"]["steps_done"] == [1]


def test_a_lesson_reopens_where_the_operator_left_it(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    api = lesson_api(tmp_path, one_lesson_catalog(str(log)))
    api.login("Ari")
    api.complete_step("ari", "pump", 1)
    assert api.open_lesson("ari", "pump")["steps_done"] == [1]
    api.close_lesson()


def test_a_lesson_with_no_log_to_watch_says_so_rather_than_stalling(tmp_path):
    api = lesson_api(tmp_path, one_lesson_catalog(str(tmp_path / "absent.txt")))
    opened = api.open_lesson("ari", "pump")
    assert opened["ok"] is True
    assert opened["sync"] is False
    assert "simulator log" in opened["detail"]


def test_starting_over_forgets_the_steps(tmp_path):
    api = lesson_api(tmp_path, one_lesson_catalog(str(tmp_path / "absent.txt")))
    api.login("Ari")
    api.open_lesson("ari", "pump")
    api.complete_step("ari", "pump", 1)
    assert api.reset_lesson("ari", "pump")["steps_done"] == []
    assert api.lessons("ari")["progress"]["pump"]["steps_done"] == []


def test_an_unknown_lesson_is_an_error_not_a_crash(tmp_path):
    api = lesson_api(tmp_path, one_lesson_catalog(str(tmp_path / "absent.txt")))
    assert api.open_lesson("ari", "nope")["ok"] is False


def test_shutting_down_stops_watching_the_log(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    api = lesson_api(tmp_path, one_lesson_catalog(str(log)))
    api.open_lesson("ari", "pump")
    assert api._tailer.running
    api.stop()
    assert api._tailer is None


# -- the admin -------------------------------------------------------------

def admin_api(tmp_path):
    api = lesson_api(tmp_path, one_lesson_catalog(str(tmp_path / "absent.txt")))
    assert api.admin_login("admin", "admin")["ok"] is True
    return api


def test_the_admin_password_is_checked_in_python(tmp_path):
    api = lesson_api(tmp_path, one_lesson_catalog(str(tmp_path / "absent.txt")))
    assert api.admin_login("admin", "wrong")["ok"] is False
    assert api.admin_login("someone", "admin")["ok"] is False
    assert api.admin_login("admin", "admin")["ok"] is True


def test_nothing_admin_works_before_signing_in(tmp_path):
    api = lesson_api(tmp_path, one_lesson_catalog(str(tmp_path / "absent.txt")))
    for result in (api.admin_overview(),
                   api.admin_create_user("Sam"),
                   api.admin_delete_user("ari"),
                   api.admin_set_assignments("ari", [])):
        assert result["ok"] is False


def test_signing_out_closes_the_admin_screen(tmp_path):
    api = admin_api(tmp_path)
    api.admin_logout()
    assert api.admin_overview()["ok"] is False


def test_the_overview_carries_every_operator_and_every_lesson(tmp_path):
    api = admin_api(tmp_path)
    api.admin_create_user("Sam Patel")
    api.open_lesson("sam-patel", "pump")
    api.complete_step("sam-patel", "pump", 1)

    overview = api.admin_overview()
    assert [lesson["id"] for lesson in overview["lessons"]] == ["pump"]
    sam = next(o for o in overview["operators"] if o["id"] == "sam-patel")
    assert sam["lessons"]["pump"]["done"] == 1
    assert sam["steps_done"] == 1
    assert sam["steps_total"] == 2, "the lesson has two steps"
    assert sam["lessons"]["pump"]["last_opened"]
    assert overview["refreshed_at"], "the refresh button shows when it last ran"


def test_a_withheld_lesson_does_not_count_against_an_operator(tmp_path):
    api = admin_api(tmp_path)
    api.admin_create_user("Sam Patel")
    api.admin_set_assignments("sam-patel", [])
    sam = next(o for o in api.admin_overview()["operators"]
               if o["id"] == "sam-patel")
    assert sam["lessons"]["pump"]["assigned"] is False
    assert sam["steps_total"] == 0, "not 50% behind on a lesson nobody gave them"


def test_an_operator_only_sees_the_lessons_they_were_given(tmp_path):
    api = admin_api(tmp_path)
    api.admin_create_user("Sam Patel")
    assert api.lessons("sam-patel")["categories"], "assigned by default"
    api.admin_set_assignments("sam-patel", [])
    assert api.lessons("sam-patel")["categories"] == []


def test_creating_a_duplicate_operator_is_a_message_not_a_crash(tmp_path):
    api = admin_api(tmp_path)
    api.admin_create_user("Sam Patel")
    again = api.admin_create_user("Sam Patel")
    assert again["ok"] is False
    assert "already" in again["error"]


def test_deleting_the_operator_at_the_screen_signs_them_out(tmp_path):
    api = admin_api(tmp_path)
    api.admin_create_user("Sam Patel")
    api.set_active_user("sam-patel")
    api.admin_delete_user("sam-patel")
    assert api._active_user == "", "a deleted operator must not keep recording"


def test_a_new_operator_is_shown_the_simulator_first(tmp_path):
    api = admin_api(tmp_path)
    created = api.admin_create_user("Sam Patel")
    assert created["user"]["onboarded"] is False
    assert api.login("Sam Patel")["user"]["onboarded"] is False
    api.mark_onboarded("sam-patel")
    assert api.login("Sam Patel")["user"]["onboarded"] is True


def test_the_starter_video_is_reported_missing_rather_than_shown_broken(tmp_path):
    api = Api(Config(devkit_url="http://127.0.0.1:9",
                     starter_video=str(tmp_path / "nope.mp4")),
              emit=lambda n, p: None, log_path=tmp_path / "turns.jsonl",
              db_path=tmp_path / "assist.db")
    result = api.starter_video()
    assert result["available"] is False
    assert result["url"] == "/media/starter.mp4"


# -- answers already given -------------------------------------------------
#
# The board takes ~6s to retrieve and 15-30s to synthesise. A question asked
# twice should not be searched twice.

def counting_api(devkit_url, tmp_path, monkeypatch):
    """An Api whose transport counts how often the board is actually asked."""
    api = Api(Config(devkit_url=devkit_url), emit=lambda n, p: None,
              log_path=tmp_path / "turns.jsonl",
              db_path=tmp_path / "assist.db")
    api._monitor.poll_once()          # learn the render version, as the app does
    asked: list[str] = []
    real = api._transport.ask
    monkeypatch.setattr(api._transport, "ask",
                        lambda q, top_k=5: (asked.append(q) or real(q, top_k=top_k)))
    return api, asked


def test_the_same_question_is_only_asked_of_the_board_once(devkit_url, tmp_path,
                                                            monkeypatch):
    api, asked = counting_api(devkit_url, tmp_path, monkeypatch)
    first = api.ask("how do i fill the solution tank")
    second = api.ask("how do i fill the solution tank")

    assert asked == ["how do i fill the solution tank"], "asked the board twice"
    assert second["recalled"] is True
    assert (second["turn"]["answer"]["display_text"]
            == first["turn"]["answer"]["display_text"])


def test_a_recalled_answer_does_not_claim_the_time_it_first_took(devkit_url,
                                                                  tmp_path,
                                                                  monkeypatch):
    monkeypatch.setenv("ASSIST_RECALL_DELAY_S", "0")
    api, _ = counting_api(devkit_url, tmp_path, monkeypatch)
    first = api.ask("how do i fill the solution tank")
    again = api.ask("how do i fill the solution tank")
    assert again["turn"]["timing"]["total_ms"] < first["turn"]["timing"]["total_ms"]
    assert again["turn"]["timing"]["first_answered_ms"] >= 0
    assert "recalled" in again["turn"]["plan"]["reason"]


def test_the_same_question_phrased_differently_is_recalled(devkit_url, tmp_path,
                                                            monkeypatch):
    api, asked = counting_api(devkit_url, tmp_path, monkeypatch)
    api.ask("how do i fill the solution tank")
    api.ask("How do I fill the solution tank?")
    assert len(asked) == 1


def test_a_different_question_still_reaches_the_board(devkit_url, tmp_path,
                                                       monkeypatch):
    api, asked = counting_api(devkit_url, tmp_path, monkeypatch)
    api.ask("how do i fill the solution tank")
    api.ask("what tire pressure")
    assert len(asked) == 2


def test_an_out_of_scope_answer_is_not_kept(devkit_url, tmp_path, monkeypatch):
    """A miss is the corpus failing to match today. Keeping it would make
    tomorrow's answer impossible."""
    api, asked = counting_api(devkit_url, tmp_path, monkeypatch)
    monkeypatch.setattr("assist_desktop.llm.explain", lambda t: (False, "down"))
    api.ask("what is the weather")
    api.ask("what is the weather")
    assert len(asked) == 2, "an oos must be re-asked"


def test_a_command_is_never_answered_from_the_cache(devkit_url, tmp_path,
                                                     monkeypatch):
    """It has to act on the machine every single time."""
    api, _ = counting_api(devkit_url, tmp_path, monkeypatch)
    fired: list[str] = []
    monkeypatch.setattr("assist_desktop.commands._send",
                        lambda p: (fired.append(p) or (True, "")))
    api.ask("fold the boom")
    api.ask("fold the boom")
    assert fired == ["Fold the Boom", "Fold the Boom"]


def test_chris_is_not_answered_from_the_cache(devkit_url, tmp_path, monkeypatch):
    """A conversation that repeats itself word for word is not a conversation."""
    api, _ = counting_api(devkit_url, tmp_path, monkeypatch)
    replies = iter(["I'm here.", "Still here."])
    monkeypatch.setattr("assist_desktop.llm.chat",
                        lambda t, history=None: (True, next(replies)))
    first = api.ask("hello")
    second = api.ask("hello")
    assert first["turn"]["answer"]["display_text"] != \
        second["turn"]["answer"]["display_text"]


def test_switching_pipeline_does_not_serve_the_old_answer(devkit_url, tmp_path,
                                                           monkeypatch):
    """.env changing from v3 to v4 is a one-line edit, and the two answer the
    same question differently."""
    api, asked = counting_api(devkit_url, tmp_path, monkeypatch)
    api.ask("how do i fill the solution tank")
    api._monitor.render_version = "v3"        # as if pointed at the other one
    api.ask("how do i fill the solution tank")
    assert len(asked) == 2


def test_clearing_the_cache_makes_it_ask_again(devkit_url, tmp_path, monkeypatch):
    api, asked = counting_api(devkit_url, tmp_path, monkeypatch)
    api.ask("how do i fill the solution tank")
    assert api.forget_answers()["removed"] == 1
    api.ask("how do i fill the solution tank")
    assert len(asked) == 2


def test_a_recalled_answer_is_still_recorded_for_the_operator(devkit_url,
                                                               tmp_path,
                                                               monkeypatch):
    api, _ = counting_api(devkit_url, tmp_path, monkeypatch)
    api.login("Ari")
    api.ask("how do i fill the solution tank", user_id="ari")
    api.ask("how do i fill the solution tank", user_id="ari")
    entries = api.history("ari")["entries"]
    assert len(entries) == 2, "history is what they asked, not what we searched"
    assert entries[0]["turn"]["answer"]["display_text"]


def test_a_recalled_answer_is_held_back_to_a_believable_pace(devkit_url,
                                                              tmp_path,
                                                              monkeypatch):
    """Six milliseconds reads as though nothing happened. The wait is the only
    part of the original answer worth keeping."""
    monkeypatch.setenv("ASSIST_RECALL_DELAY_S", "0.4")
    api, _ = counting_api(devkit_url, tmp_path, monkeypatch)
    api.ask("how do i fill the solution tank")

    started = time.perf_counter()
    again = api.ask("how do i fill the solution tank")
    elapsed = time.perf_counter() - started

    assert again["recalled"] is True
    assert elapsed >= 0.4, "handed back instantly"
    assert elapsed < 1.5, "held longer than it was told to"


def test_the_reported_time_is_the_wait_that_happened(devkit_url, tmp_path,
                                                      monkeypatch):
    """Not padded to look like the original search: what is reported is what
    the operator actually waited, and the real first answer is kept beside
    it."""
    monkeypatch.setenv("ASSIST_RECALL_DELAY_S", "0.4")
    api, _ = counting_api(devkit_url, tmp_path, monkeypatch)
    first = api.ask("how do i fill the solution tank")
    again = api.ask("how do i fill the solution tank")

    reported = again["turn"]["timing"]["total_ms"]
    assert 400 <= reported < 1500
    assert reported < first["turn"]["timing"]["total_ms"], "not claiming a search"
    assert again["turn"]["timing"]["first_answered_ms"] > 0


def test_the_pacing_can_be_turned_off(devkit_url, tmp_path, monkeypatch):
    monkeypatch.setenv("ASSIST_RECALL_DELAY_S", "0")
    api, _ = counting_api(devkit_url, tmp_path, monkeypatch)
    api.ask("how do i fill the solution tank")
    started = time.perf_counter()
    api.ask("how do i fill the solution tank")
    assert (time.perf_counter() - started) < 0.3


def test_a_live_answer_is_never_delayed(devkit_url, tmp_path, monkeypatch):
    """The pacing exists to slow a cache hit to the speed of a real answer,
    never to slow a real one down."""
    monkeypatch.setenv("ASSIST_RECALL_DELAY_S", "5")
    api, asked = counting_api(devkit_url, tmp_path, monkeypatch)
    started = time.perf_counter()
    api.ask("how do i fill the solution tank")
    assert (time.perf_counter() - started) < 5, "the board's own answer was held up"
    assert asked, "this one went to the board"
