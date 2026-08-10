import json
import sqlite3

import pytest

from assist_desktop.db import MAX_HISTORY, Store, slugify


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "assist.db")


# -- the roster ------------------------------------------------------------

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
    first = Store(tmp_path / "assist.db")
    first.login("Aryan")
    first.record("aryan", "how do i fold the boom", "cached", "voice")
    first.close()

    second = Store(tmp_path / "assist.db")
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


def test_unknown_user_has_no_history(store):
    assert store.history("nobody") == []


def test_history_is_not_recorded_for_someone_who_is_not_on_the_roster(store):
    store.record("ghost", "q", "cached", "typed")
    assert store.history("ghost") == []


@pytest.mark.parametrize("name,expected", [
    ("Aryan", "aryan"),
    ("Priya Sharma", "priya-sharma"),
    ("  Dan  W  ", "dan-w"),
    ("!!!", "operator"),
])
def test_slugify(name, expected):
    assert slugify(name) == expected


def test_the_store_is_readable_by_anything_that_speaks_sql(store, tmp_path):
    store.login("Aryan")
    db = sqlite3.connect(tmp_path / "assist.db")
    assert db.execute("SELECT count(*) FROM users").fetchone()[0] > 0
    db.close()


# -- the admin adds and removes people -------------------------------------

def test_a_created_operator_appears_on_the_roster(store):
    user = store.create_user("Sam Patel")
    assert user["id"] == "sam-patel"
    assert any(u["id"] == "sam-patel" for u in store.list_users())


def test_a_created_operator_has_not_been_shown_the_simulator_yet(store):
    assert store.create_user("Sam Patel")["onboarded"] is False
    store.mark_onboarded("sam-patel")
    assert store.get_user("sam-patel")["onboarded"] is True


def test_two_people_cannot_share_a_name(store):
    store.create_user("Sam Patel")
    with pytest.raises(ValueError):
        store.create_user("sam patel")


def test_creating_without_a_name_is_refused(store):
    with pytest.raises(ValueError):
        store.create_user("  ")


def test_deleting_an_operator_takes_everything_with_them(store):
    store.create_user("Sam Patel")
    store.record("sam-patel", "q", "cached", "typed")
    store.complete_step("sam-patel", "spray", 1)
    store.set_assigned("sam-patel", "booms", False)

    assert store.delete_user("sam-patel") is True
    assert store.get_user("sam-patel") is None
    assert store.history("sam-patel") == []
    assert store.steps_done("sam-patel", "spray") == []
    assert store.assignments("sam-patel") == set()


def test_deleting_someone_who_is_not_there_says_so(store):
    assert store.delete_user("nobody") is False


# -- lesson progress -------------------------------------------------------

@pytest.fixture
def learner(store):
    store.create_user("Sam Patel")
    return "sam-patel"


def test_progress_survives_a_restart(tmp_path):
    first = Store(tmp_path / "assist.db")
    first.create_user("Sam Patel")
    first.complete_step("sam-patel", "spray", 2)
    first.complete_step("sam-patel", "spray", 1)
    first.close()
    assert Store(tmp_path / "assist.db").steps_done("sam-patel", "spray") == [1, 2]


def test_progress_is_per_operator(store, learner):
    store.complete_step(learner, "spray", 1)
    store.login("Aryan")
    assert store.steps_done("aryan", "spray") == []


def test_a_step_is_recorded_once(store, learner):
    store.complete_step(learner, "spray", 1)
    store.complete_step(learner, "spray", 1)
    assert store.steps_done(learner, "spray") == [1]


def test_reset_clears_the_steps_but_keeps_the_visit(store, learner):
    store.open_lesson(learner, "spray")
    store.complete_step(learner, "spray", 1)
    store.reset_lesson(learner, "spray")
    assert store.steps_done(learner, "spray") == []
    assert store.lesson_summary(learner)["spray"]["last_opened"]


def test_a_signed_out_screen_records_nothing(store):
    store.complete_step("", "spray", 1)
    assert store.all_progress() == {}


def test_every_operators_progress_comes_back_in_one_call(store, learner):
    store.create_user("Ari")
    store.complete_step(learner, "spray", 1)
    store.complete_step("ari", "spray", 1)
    store.complete_step("ari", "groups", 3)
    assert store.all_progress() == {
        learner: {"spray": [1]},
        "ari": {"spray": [1], "groups": [3]},
    }


# -- who learns what -------------------------------------------------------

def test_every_lesson_is_assigned_until_the_admin_says_otherwise(store, learner):
    # A lesson added to the catalog tomorrow must not be invisible to
    # everybody already on the roster.
    assert store.is_assigned(learner, "spray") is True


def test_withholding_a_lesson_is_remembered(store, learner):
    store.set_assigned(learner, "spray", False)
    assert store.is_assigned(learner, "spray") is False
    assert store.assignments(learner) == {"spray"}


def test_setting_the_whole_assignment_list_replaces_it(store, learner):
    every = ["spray", "booms", "groups"]
    store.set_assignments(learner, ["spray"], every)
    assert store.assignments(learner) == {"booms", "groups"}
    store.set_assignments(learner, every, every)
    assert store.assignments(learner) == set()


def test_withholding_a_lesson_keeps_the_progress_already_made(store, learner):
    store.complete_step(learner, "spray", 1)
    store.set_assigned(learner, "spray", False)
    assert store.steps_done(learner, "spray") == [1]


# -- coming from the JSON era ----------------------------------------------

def test_the_old_json_files_are_imported_once(tmp_path):
    (tmp_path / "profiles.json").write_text(json.dumps({"profiles": [{
        "user": {"id": "ari", "name": "Ari", "created_at": "2026-08-01T09:00:00+00:00",
                 "last_seen": "2026-08-06T09:00:00+00:00"},
        "history": [{"ts": "2026-08-06T09:00:00+00:00", "query": "how do i spray",
                     "kind": "cached", "source": "voice", "turn": None}],
    }]}), encoding="utf-8")
    (tmp_path / "lesson_progress.json").write_text(json.dumps({"operators": {
        "ari": {"spray": {"steps_done": [1, 2], "last_opened": "2026-08-06T09:00:00+00:00"}},
    }}), encoding="utf-8")

    store = Store(tmp_path / "assist.db",
                  legacy_profiles=tmp_path / "profiles.json",
                  legacy_progress=tmp_path / "lesson_progress.json")

    assert [u["name"] for u in store.list_users()] == ["Ari"], "no mock seeding over real people"
    assert store.history("ari")[0]["query"] == "how do i spray"
    assert store.steps_done("ari", "spray") == [1, 2]
    assert store.get_user("ari")["onboarded"] is True, "they have plainly used it"


def test_an_unreadable_legacy_file_does_not_stop_startup(tmp_path):
    (tmp_path / "profiles.json").write_text("{ not json", encoding="utf-8")
    store = Store(tmp_path / "assist.db",
                  legacy_profiles=tmp_path / "profiles.json")
    assert store.list_users(), "expected the mock roster to seed instead"


# -- answers already given -------------------------------------------------

V4 = ("http://192.168.94.180:8092", "v4.0")


def turn_for(text: str) -> dict:
    return {"plan": {"kind": "cached", "chunk_ids": [7], "reason": "top=x"},
            "answer": {"display_text": text, "spoken_segments": [text],
                       "safety": [], "citations": [], "images": [],
                       "render_version": "v4.0", "source_hash": "h"},
            "candidates": [], "timing": {"total_ms": 6500}}


def test_an_answer_comes_back_for_the_same_question(store):
    store.remember("how do i fill the solution tank", *V4, "cached",
                   turn_for("Step 1: Park."), took_ms=6500)
    found = store.recall("how do i fill the solution tank", *V4)
    assert found["turn"]["answer"]["display_text"] == "Step 1: Park."
    assert found["took_ms"] == 6500


def test_the_same_question_asked_differently_still_hits(store):
    # Both of these are in the real turn log, as separate entries.
    store.remember("how do i fill the solution tank?", *V4, "cached",
                   turn_for("Step 1: Park."))
    assert store.recall("how do i fill solution tank", *V4) is not None


def test_a_different_question_misses(store):
    store.remember("how do i fold the boom", *V4, "cached", turn_for("Fold."))
    assert store.recall("how do i unfold the boom", *V4) is None


def test_an_answer_from_another_pipeline_is_never_served(store):
    """v3 and v4 answer the same question differently. Serving one as the
    other would be quietly wrong, and the switch between them is a one-line
    edit in .env."""
    store.remember("what is boomtrac pro", "http://board:8090", "v3",
                   "cached", turn_for("v3 said this"))
    assert store.recall("what is boomtrac pro", *V4) is None


def test_re_answering_replaces_the_older_answer(store):
    store.remember("how do i fold the boom", *V4, "cached", turn_for("old"))
    store.remember("how do i fold the boom", *V4, "cached", turn_for("new"))
    found = store.recall("how do i fold the boom", *V4)
    assert found["turn"]["answer"]["display_text"] == "new"


def test_hits_are_counted(store):
    store.remember("how do i fold the boom", *V4, "cached", turn_for("Fold."))
    for _ in range(3):
        store.recall("how do i fold the boom", *V4)
    assert store.cached_answers()[0]["hits"] == 3


def test_the_cache_can_be_emptied_for_one_pipeline(store):
    store.remember("q1", *V4, "cached", turn_for("a"))
    store.remember("q2", "http://board:8090", "v3", "cached", turn_for("b"))
    assert store.forget_answers(V4[0]) == 1
    assert store.recall("q1", *V4) is None
    assert store.recall("q2", "http://board:8090", "v3") is not None


def test_the_cache_survives_a_restart(tmp_path):
    first = Store(tmp_path / "assist.db")
    first.remember("how do i fold the boom", *V4, "cached", turn_for("Fold."))
    first.close()
    assert Store(tmp_path / "assist.db").recall("how do i fold the boom", *V4)


@pytest.mark.parametrize("asked,same", [
    ("How do I fill the solution tank?", "how do i fill solution tank"),
    ("  how   do i FOLD the boom  ", "how do i fold a boom"),
    ("what is the tire pressure", "what is tire pressure"),
])
def test_questions_that_should_share_an_answer(asked, same):
    from assist_desktop.db import normalise_question
    assert normalise_question(asked) == normalise_question(same)


@pytest.mark.parametrize("one,other", [
    ("how do i fold the boom", "how do i unfold the boom"),
    ("how do i start spraying", "how do i stop spraying"),
    ("what is the tire pressure", "what is the oil pressure"),
    ("how to start spraying", "how do i start spraying"),
])
def test_questions_that_must_not_share_an_answer(one, other):
    """A wrong hit serves the wrong procedure. Only articles are dropped."""
    from assist_desktop.db import normalise_question
    assert normalise_question(one) != normalise_question(other)


# -- the same question, asked another way ----------------------------------

@pytest.fixture
def warmed(store):
    """A cache holding the questions the rig was warmed with."""
    for q in ("how do i check the nozzle flow", "how do i fold the boom",
              "how do i unfold the boom", "how do i clean the strainers",
              "what is boomtrac pro", "how do i start spraying"):
        store.remember(q, *V4, "cached", turn_for(f"answer to {q}"))
    return store


def answer_for(store, question):
    found = store.recall(question, *V4)
    return found["turn"]["answer"]["display_text"] if found else None


@pytest.mark.parametrize("asked,expected", [
    ("how to check nozzle flow", "how do i check the nozzle flow"),
    ("how can i check the nozzle flow", "how do i check the nozzle flow"),
    ("show me how to check the nozzle flow", "how do i check the nozzle flow"),
    ("steps to clean the strainers", "how do i clean the strainers"),
    ("whats boomtrac pro", "what is boomtrac pro"),
    ("what is the boomtrac pro?", "what is boomtrac pro"),
])
def test_the_opener_does_not_have_to_match(warmed, asked, expected):
    assert answer_for(warmed, asked) == f"answer to {expected}"


@pytest.mark.parametrize("typo,expected", [
    ("how do i check the nossle flow", "how do i check the nozzle flow"),
    ("how do i check the nozzel flow", "how do i check the nozzle flow"),
    ("how do i clean the strainrs", "how do i clean the strainers"),
    ("how to check the nossle flow", "how do i check the nozzle flow"),
])
def test_an_obvious_typo_still_finds_the_answer(warmed, typo, expected):
    assert answer_for(warmed, typo) == f"answer to {expected}"


@pytest.mark.parametrize("asked", [
    "how do i unfold the boom",
    "how to unfold the boom",
    "how do i unfold boom",
])
def test_fold_never_answers_an_unfold_question(warmed, asked):
    """Two characters apart, and the opposite procedure. A cache that gets
    this wrong tells someone to fold a boom they are standing under."""
    assert answer_for(warmed, asked) == "answer to how do i unfold the boom"


def test_a_procedure_never_answers_a_definition(warmed):
    """Stripping the opener entirely would collapse these into one key."""
    warmed.remember("how do i use boomtrac pro", *V4, "cached",
                    turn_for("the procedure"))
    assert answer_for(warmed, "what is boomtrac pro") == "answer to what is boomtrac pro"
    assert answer_for(warmed, "how to use boomtrac pro") == "the procedure"


@pytest.mark.parametrize("asked", [
    "how do i stop spraying",          # start/stop
    "how do i check the boom flow",    # a different thing entirely
    "how do i clean the nozzles",      # strainers are not nozzles
    "what is boom air purge",          # never cached
])
def test_a_different_question_still_reaches_the_board(warmed, asked):
    assert answer_for(warmed, asked) is None


def test_a_short_word_is_never_repaired():
    """"fold" is four letters from "hold", "cold" and "gold". Words this short
    are taken exactly as typed."""
    from assist_desktop.db import repair_word
    assert repair_word("fold", ["fold", "unfold", "hold"]) == "fold"
    assert repair_word("gold", ["fold", "unfold"]) == "gold"


def test_a_real_word_is_never_repaired_into_another_real_word():
    from assist_desktop.db import repair_word
    assert repair_word("fold", ["unfold", "fold"]) == "fold"
    assert repair_word("spraying", ["spraying", "praying"]) == "spraying"


def test_an_ambiguous_typo_is_left_alone():
    """Equally close to two known words means we do not know which, and not
    knowing means letting the question reach the board."""
    from assist_desktop.db import repair_word
    assert repair_word("arain", ["drain", "brain"]) == "arain"


def test_a_word_is_never_repaired_into_one_that_contains_it():
    """The failure this was found by: with only "fold" cached, "unfold" is two
    edits away and was repaired into it — answering the opposite procedure."""
    from assist_desktop.db import repair_word
    assert repair_word("unfold", ["fold", "boom"]) == "unfold"
    assert repair_word("prefill", ["fill"]) == "prefill"


def test_repairs_only_reach_words_the_cache_already_knows():
    from assist_desktop.db import repair_word
    assert repair_word("nossle", ["boom", "spraying"]) == "nossle"
