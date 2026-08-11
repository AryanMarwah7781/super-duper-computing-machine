"""Reading the signed-in operator out of a file another process writes.

The shape of that file was undecided, so the reader accepts several. What
matters most here is the failure behaviour: a half-written file, a locked
file, or rubbish must all come back as "nobody", never as a crash and never
as a person called `{"name": "Pri`.
"""
from __future__ import annotations

import json

import pytest

from assist_desktop.login_watch import LoginWatcher, parse, read


class TestParse:
    def test_preferred_shape(self):
        assert parse('{"name": "Priya Sharma"}') == "Priya Sharma"

    @pytest.mark.parametrize("key", [
        "username", "user", "operator", "displayName", "display_name",
        "full_name", "fullName",
    ])
    def test_the_other_spellings_of_name(self, key):
        assert parse(json.dumps({key: "Marcus Chen"})) == "Marcus Chen"

    def test_name_wins_when_several_are_present(self):
        assert parse('{"user": "wrong", "name": "Priya Sharma"}') \
            == "Priya Sharma"

    def test_a_bare_line_of_text(self):
        assert parse("Priya Sharma") == "Priya Sharma"

    def test_a_bare_json_string(self):
        assert parse('"Priya Sharma"') == "Priya Sharma"

    def test_a_log_takes_the_last_entry(self):
        text = json.dumps([{"name": "Marcus Chen"}, {"name": "Dan Whitfield"}])
        assert parse(text) == "Dan Whitfield"

    def test_last_line_of_a_plain_text_log(self):
        assert parse("Marcus Chen\nDan Whitfield\n") == "Dan Whitfield"

    def test_surrounding_whitespace_and_bom(self):
        assert parse('﻿  {"name": "  Priya Sharma  "}  ') == "Priya Sharma"

    def test_empty_is_nobody(self):
        for text in ["", "   ", "\n", "﻿"]:
            assert parse(text) is None

    def test_half_written_json_is_nobody_not_a_name(self):
        # The writer is another process and there is no lock. This is the
        # case that would otherwise greet the room with a fragment of JSON.
        assert parse('{"name": "Priya') is None
        assert parse('[{"name":') is None

    def test_json_without_any_name_key(self):
        assert parse('{"id": 7, "shift": "morning"}') is None

    def test_empty_containers(self):
        assert parse("{}") is None
        assert parse("[]") is None

    def test_a_name_that_is_really_a_log_line_is_rejected(self):
        assert parse("x" * 200) is None

    def test_non_string_values_are_ignored(self):
        assert parse('{"name": 42}') is None
        assert parse('{"name": null, "user": "Priya Sharma"}') == "Priya Sharma"


class TestRead:
    def test_reads_a_file(self, tmp_path):
        f = tmp_path / "current_user.json"
        f.write_text('{"name": "Priya Sharma"}', encoding="utf-8")
        assert read(f) == "Priya Sharma"

    def test_missing_file_is_nobody(self, tmp_path):
        assert read(tmp_path / "not-there.json") is None

    def test_a_directory_where_a_file_was_expected_does_not_raise(self, tmp_path):
        assert read(tmp_path) is None

    def test_utf8_bom_from_powershell_out_file(self, tmp_path):
        # Set-Content and Out-File write a BOM by default on this rig.
        f = tmp_path / "u.json"
        f.write_text('{"name": "Priya Sharma"}', encoding="utf-8-sig")
        assert read(f) == "Priya Sharma"


class TestWatcher:
    def test_fires_once_for_a_login(self, tmp_path):
        f = tmp_path / "u.json"
        f.write_text('{"name": "Priya Sharma"}', encoding="utf-8")
        seen = []
        w = LoginWatcher(seen.append, path=f)

        assert w.poll_once() == "Priya Sharma"
        w.poll_once()
        w.poll_once()
        assert seen == ["Priya Sharma"]

    def test_fires_again_when_a_different_person_logs_in(self, tmp_path):
        f = tmp_path / "u.json"
        f.write_text('{"name": "Priya Sharma"}', encoding="utf-8")
        seen = []
        w = LoginWatcher(seen.append, path=f)
        w.poll_once()

        f.write_text('{"name": "Marcus Chen"}', encoding="utf-8")
        w.poll_once()
        assert seen == ["Priya Sharma", "Marcus Chen"]

    def test_clearing_the_file_lets_the_same_person_be_greeted_again(self, tmp_path):
        f = tmp_path / "u.json"
        f.write_text('{"name": "Priya Sharma"}', encoding="utf-8")
        seen = []
        w = LoginWatcher(seen.append, path=f)
        w.poll_once()

        f.write_text("", encoding="utf-8")       # signed out
        w.poll_once()
        f.write_text('{"name": "Priya Sharma"}', encoding="utf-8")
        w.poll_once()
        assert seen == ["Priya Sharma", "Priya Sharma"]

    def test_a_failing_callback_does_not_kill_the_watcher(self, tmp_path):
        f = tmp_path / "u.json"
        f.write_text('{"name": "Priya Sharma"}', encoding="utf-8")

        def boom(_name):
            raise RuntimeError("the UI was not ready")

        w = LoginWatcher(boom, path=f)
        w.poll_once()                            # must not raise

        seen = []
        w2 = LoginWatcher(seen.append, path=f)
        assert w2.poll_once() == "Priya Sharma"

    def test_missing_file_polls_quietly(self, tmp_path):
        seen = []
        w = LoginWatcher(seen.append, path=tmp_path / "later.json")
        assert w.poll_once() is None
        assert seen == []

    def test_start_and_stop_are_safe_without_a_file(self, tmp_path):
        w = LoginWatcher(lambda _n: None, path=tmp_path / "never.json",
                         poll_s=0.01)
        w.start()
        w.start()          # second start is a no-op, not a second thread
        w.stop()
        w.stop()           # stopping twice is safe
