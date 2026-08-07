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
               profiles_path=tmp_path / "profiles.json")


def test_ask_returns_a_serialisable_turn(api):
    result = api.ask("how do i fill the tank")
    assert result["ok"] is True
    assert result["turn"]["plan"]["kind"] == "cached"
    assert result["turn"]["answer"]["safety"][0]["level"] == "WARNING"


def test_ask_never_raises_into_js(tmp_path):
    api = Api(Config(devkit_url="http://127.0.0.1:9", timeout_s=1.0),
              emit=lambda n, p: None, log_path=tmp_path / "turns.jsonl",
              profiles_path=tmp_path / "profiles.json")
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
              profiles_path=tmp_path / "profiles.json")
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
              profiles_path=tmp_path / "profiles.json")
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
