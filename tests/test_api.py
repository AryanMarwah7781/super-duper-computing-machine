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


def test_oos_is_ok_but_has_no_answer(api):
    result = api.ask("what is the weather")
    assert result["ok"] is True
    assert result["turn"]["plan"]["kind"] == "oos"
    assert result["turn"]["answer"] is None
