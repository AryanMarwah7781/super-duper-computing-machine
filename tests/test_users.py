import json

import pytest

from assist_desktop.users import MAX_HISTORY, UserStore, slugify


@pytest.fixture
def store(tmp_path):
    return UserStore(tmp_path / "profiles.json")


def test_seeds_mock_users_on_first_run(store):
    names = [u["name"] for u in store.list_users()]
    assert "Priya Sharma" in names
    assert "Marcus Chen" in names
    assert "Dan Whitfield" in names


def test_mock_users_have_history(store):
    priya = store.login("Priya Sharma")
    history = store.history(priya["id"])
    assert len(history) == 3
    assert history[0]["query"]
    assert history[0]["kind"] in {"cached", "synthesize", "oos"}


def test_login_creates_a_new_person(store):
    user = store.login("Aryan")
    assert user["id"] == "aryan"
    assert user["name"] == "Aryan"
    assert store.history("aryan") == []


def test_login_twice_keeps_the_same_history(store):
    user = store.login("Aryan")
    store.record(user["id"], "how do i fill the tank", "cached", "typed")
    again = store.login("Aryan")
    assert again["id"] == user["id"]
    assert len(store.history("aryan")) == 1


def test_history_is_newest_first(store):
    store.login("Aryan")
    store.record("aryan", "first", "cached", "typed")
    store.record("aryan", "second", "cached", "typed")
    assert [e["query"] for e in store.history("aryan")] == ["second", "first"]


def test_history_survives_a_restart(tmp_path):
    first = UserStore(tmp_path / "profiles.json")
    first.login("Aryan")
    first.record("aryan", "how do i fold the boom", "cached", "voice")

    second = UserStore(tmp_path / "profiles.json")
    history = second.history("aryan")
    assert len(history) == 1
    assert history[0]["query"] == "how do i fold the boom"
    assert history[0]["source"] == "voice"


def test_history_is_capped(store):
    store.login("Aryan")
    for i in range(MAX_HISTORY + 25):
        store.record("aryan", f"question {i}", "cached", "typed")
    history = store.history("aryan")
    assert len(history) == MAX_HISTORY
    assert history[0]["query"] == f"question {MAX_HISTORY + 24}"


def test_a_stored_turn_is_returned_for_re_render(store):
    store.login("Aryan")
    turn = {"plan": {"kind": "cached"}, "answer": {"display_text": "Step 1: Go."}}
    store.record("aryan", "q", "cached", "typed", turn=turn)
    assert store.history("aryan")[0]["turn"]["answer"]["display_text"] == "Step 1: Go."


def test_empty_name_is_rejected(store):
    with pytest.raises(ValueError):
        store.login("   ")


def test_clear_history_keeps_the_user(store):
    store.login("Aryan")
    store.record("aryan", "q", "cached", "typed")
    store.clear_history("aryan")
    assert store.history("aryan") == []
    assert any(u["id"] == "aryan" for u in store.list_users())


def test_a_corrupt_profile_file_does_not_stop_startup(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{ this is not json", encoding="utf-8")
    store = UserStore(path)
    assert store.list_users(), "expected mock users to seed over the corrupt file"


def test_unknown_user_has_no_history(store):
    assert store.history("nobody") == []


@pytest.mark.parametrize("name,expected", [
    ("Aryan", "aryan"),
    ("Priya Sharma", "priya-sharma"),
    ("  Dan  W  ", "dan-w"),
    ("!!!", "operator"),
])
def test_slugify(name, expected):
    assert slugify(name) == expected


def test_file_is_human_readable(store, tmp_path):
    store.login("Aryan")
    raw = json.loads((tmp_path / "profiles.json").read_text(encoding="utf-8"))
    assert "profiles" in raw
