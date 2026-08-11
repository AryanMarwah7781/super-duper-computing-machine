"""Which panel each window opens on.

The rig has four monitors and three numbering schemes that disagree, so the
mapping is held by geometry. These pin the behaviour that matters when the
geometry is wrong: a monitor that is off must not stop the app starting.
"""
from __future__ import annotations

from assist_desktop.screens import (
    Panel, defaults, describe, layout, match, panel_of, parse,
)


class FakeScreen:
    """Screen-shaped, the way pywebview's Screen is."""

    def __init__(self, width, height, x, y):
        self.width, self.height, self.x, self.y = width, height, x, y


# The real rig, in the order pywebview reports it.
RIG = [
    FakeScreen(2160, 1440, 3840, -353),
    FakeScreen(1920, 1080, -1920, 9),
    FakeScreen(1920, 1080, 0, 0),        # primary
    FakeScreen(1920, 1080, 1920, 10),
]


class TestParse:
    def test_reads_a_token(self):
        assert parse("1920x1080+1920+10") == Panel(1920, 1080, 1920, 10)

    def test_negative_x_for_a_monitor_left_of_primary(self):
        assert parse("1920x1080-1920+9") == Panel(1920, 1080, -1920, 9)

    def test_negative_y(self):
        assert parse("2160x1440+3840-353") == Panel(2160, 1440, 3840, -353)

    def test_tolerates_surrounding_space(self):
        assert parse("  1920x1080+0+0 ") == Panel(1920, 1080, 0, 0)

    def test_rubbish_is_none_not_an_exception(self):
        for bad in ["", None, "screen 3", "1920x1080", "x+y", "1920*1080+0+0"]:
            assert parse(bad) is None

    def test_str_round_trips(self):
        for token in ["1920x1080+1920+10", "1920x1080-1920+9",
                      "2160x1440+3840-353"]:
            assert str(parse(token)) == token


class TestMatch:
    def test_finds_the_panel(self):
        assert match(Panel(1920, 1080, 1920, 10), RIG) == 3

    def test_position_identifies_a_panel_even_at_a_new_resolution(self):
        # Somebody dropped that monitor to 1600x900. It is still the monitor
        # on the right, and the lesson plan still belongs on it.
        assert match(Panel(1600, 900, 1920, 10), RIG) == 3

    def test_absent_panel_is_none(self):
        assert match(Panel(1920, 1080, 9999, 9999), RIG) is None

    def test_exact_match_beats_a_position_only_match(self):
        screens = [FakeScreen(1600, 900, 0, 0), FakeScreen(1920, 1080, 0, 0)]
        assert match(Panel(1920, 1080, 0, 0), screens) == 1


class TestDefaults:
    def test_chat_lands_on_primary(self):
        assert defaults(RIG)["chat"] == 2

    def test_roles_get_different_panels_when_there_are_enough(self):
        got = defaults(RIG)
        assert len(set(got.values())) == 3

    def test_one_screen_doubles_up_rather_than_failing(self):
        got = defaults([FakeScreen(1920, 1080, 0, 0)])
        assert got == {"chat": 0, "lesson": 0, "game": 0}

    def test_two_screens_wrap(self):
        got = defaults([FakeScreen(1920, 1080, 0, 0),
                        FakeScreen(1920, 1080, 1920, 0)])
        assert got["chat"] == 0 and got["lesson"] == 1 and got["game"] == 0

    def test_no_screens_is_empty_not_a_crash(self):
        assert defaults([]) == {}


class TestLayout:
    def test_env_places_each_role(self):
        got, notes = layout(RIG, {
            "ASSIST_SCREEN_CHAT": "2160x1440+3840-353",
            "ASSIST_SCREEN_LESSON": "1920x1080-1920+9",
            "ASSIST_SCREEN_GAME": "1920x1080+1920+10",
        })
        assert got == {"chat": 0, "lesson": 1, "game": 3}
        assert notes == []

    def test_unset_roles_keep_their_default(self):
        got, notes = layout(RIG, {"ASSIST_SCREEN_GAME": "1920x1080-1920+9"})
        assert got["game"] == 1
        assert got["chat"] == defaults(RIG)["chat"]
        assert notes == []

    def test_a_monitor_that_is_not_there_falls_back_and_says_so(self):
        got, notes = layout(RIG, {"ASSIST_SCREEN_CHAT": "1920x1080+7777+0"})
        assert got["chat"] == defaults(RIG)["chat"]
        assert len(notes) == 1 and "not among the connected screens" in notes[0]

    def test_a_malformed_token_falls_back_and_says_so(self):
        got, notes = layout(RIG, {"ASSIST_SCREEN_LESSON": "screen 2"})
        assert got["lesson"] == defaults(RIG)["lesson"]
        assert len(notes) == 1 and "not a geometry" in notes[0]

    def test_no_screens_complains_rather_than_raising(self):
        got, notes = layout([], {})
        assert got == {} and notes == ["no screens reported"]

    def test_two_roles_may_share_a_panel_on_purpose(self):
        # Demoing on one monitor is legitimate, not a misconfiguration.
        got, notes = layout(RIG, {
            "ASSIST_SCREEN_CHAT": "1920x1080+0+0",
            "ASSIST_SCREEN_LESSON": "1920x1080+0+0",
        })
        assert got["chat"] == got["lesson"] == 2
        assert notes == []


class TestDescribe:
    def test_names_the_panel_not_the_index(self):
        lines = describe(RIG, layout(RIG, {})[0])
        assert len(lines) == 3
        assert "1920x1080+0+0" in " ".join(lines)


class TestPanelOf:
    def test_coerces_screen_shaped_things(self):
        assert panel_of(FakeScreen("1920", "1080", "0", "0")) == \
            Panel(1920, 1080, 0, 0)
