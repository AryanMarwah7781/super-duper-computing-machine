import pytest

from assist_desktop.models.wire import Turn

ALL = ["procedure", "table", "passage", "oos"]


@pytest.mark.parametrize("name", ALL)
def test_every_fixture_round_trips(load_fixture, name):
    turn = Turn.from_dict(load_fixture(name))
    assert turn.plan.kind in {"cached", "synthesize", "oos"}
    assert isinstance(turn.timing["total_ms"], int)


def test_procedure_parses_nested_structures(load_fixture):
    turn = Turn.from_dict(load_fixture("procedure"))
    assert turn.answer is not None
    assert turn.answer.render_version == "v4.0"
    assert turn.answer.safety[0].level == "WARNING"
    assert turn.answer.images[0].caption == "Fill cap location"
    assert turn.answer.citations[0].page == 472
    assert len(turn.answer.spoken_segments) == 6
    assert turn.candidates[0].score == 8.14


def test_oos_has_no_answer(load_fixture):
    turn = Turn.from_dict(load_fixture("oos"))
    assert turn.answer is None
    assert turn.plan.chunk_ids == ()


def test_unknown_fields_are_ignored(load_fixture):
    raw = load_fixture("table")
    raw["answer"]["future_field"] = "added by a newer service"
    turn = Turn.from_dict(raw)
    assert turn.answer is not None
