import json

from assist_desktop.models.wire import Turn
from assist_desktop.turnlog import TurnLog


def test_appends_one_record_per_turn(tmp_path, load_fixture):
    log = TurnLog(tmp_path / "turns.jsonl")
    log.append("how do i fill the tank",
               Turn.from_dict(load_fixture("procedure")), source="typed")
    log.append("what tire pressure",
               Turn.from_dict(load_fixture("table")), source="typed")

    lines = (tmp_path / "turns.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["query"] == "how do i fill the tank"
    assert first["kind"] == "cached"
    assert first["reason"] == "top=procedure score=8.14"
    assert first["candidates"][0]["score"] == 8.14
    assert first["timing"]["total_ms"] == 4520
    assert first["source"] == "typed"
    assert first["ts"]


def test_records_failures_too(tmp_path):
    log = TurnLog(tmp_path / "turns.jsonl")
    log.append_error("anything", "devkit unreachable", source="typed")
    record = json.loads((tmp_path / "turns.jsonl").read_text(encoding="utf-8"))
    assert record["kind"] == "error"
    assert record["reason"] == "devkit unreachable"


def test_creates_parent_directory(tmp_path, load_fixture):
    log = TurnLog(tmp_path / "nested" / "deep" / "turns.jsonl")
    log.append("q", Turn.from_dict(load_fixture("oos")), source="typed")
    assert (tmp_path / "nested" / "deep" / "turns.jsonl").exists()
