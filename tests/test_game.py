"""Sizing and placing the simulator's own window.

The Win32 half cannot be tested without a running game, so the arithmetic is
kept separate from it and tested here. What matters: a bad size must still put
the game on the right monitor, and no size may ever spill onto a neighbouring
panel -- spilling is the entire problem this code exists to fix.
"""
from __future__ import annotations

from assist_desktop.game import parse_size, target_rect
from assist_desktop.screens import Panel

PANEL = Panel(1920, 1080, 0, 0)          # the simulator's monitor on the rig
LEFT = Panel(1920, 1080, -1920, 9)       # one with negative coordinates


class TestParseSize:
    def test_explicit_size(self):
        assert parse_size("1600x900", PANEL) == (1600, 900)

    def test_case_and_spacing(self):
        assert parse_size("  1600 X 900 ", PANEL) == (1600, 900)
        assert parse_size("1600*900", PANEL) == (1600, 900)

    def test_max_fills_the_panel(self):
        for spec in ["max", "MAX", "full", "fill", " max "]:
            assert parse_size(spec, PANEL) == (1920, 1080)

    def test_unset_fills_the_panel(self):
        assert parse_size(None, PANEL) == (1920, 1080)
        assert parse_size("", PANEL) == (1920, 1080)

    def test_rubbish_fills_the_panel_rather_than_refusing(self):
        assert parse_size("big", PANEL) == (1920, 1080)
        assert parse_size("1600", PANEL) == (1920, 1080)

    def test_never_larger_than_the_panel(self):
        # A window wider than its monitor is how the game ended up spanning
        # three of them in the first place.
        assert parse_size("5760x1080", PANEL) == (1920, 1080)
        assert parse_size("1600x4000", PANEL) == (1600, 1080)

    def test_zero_and_negative_fill_the_panel(self):
        assert parse_size("0x0", PANEL) == (1920, 1080)


class TestTargetRect:
    def test_max_covers_the_panel_exactly(self):
        assert target_rect(PANEL, "max") == (0, 0, 1920, 1080)

    def test_smaller_window_is_centred(self):
        x, y, w, h = target_rect(PANEL, "1600x900")
        assert (w, h) == (1600, 900)
        assert (x, y) == (160, 90)

    def test_stays_on_a_panel_with_negative_coordinates(self):
        x, y, w, h = target_rect(LEFT, "1600x900")
        assert (w, h) == (1600, 900)
        assert x == -1920 + 160
        assert y == 9 + 90

    def test_never_leaves_its_panel(self):
        for spec in ["max", "1600x900", "800x600", "5760x2000", "nonsense"]:
            x, y, w, h = target_rect(PANEL, spec)
            assert x >= PANEL.x
            assert y >= PANEL.y
            assert x + w <= PANEL.x + PANEL.width
            assert y + h <= PANEL.y + PANEL.height

    def test_odd_leftovers_do_not_overflow(self):
        # 1920-1599 is odd; integer division must not round the window off
        # the right-hand edge.
        x, y, w, h = target_rect(PANEL, "1599x1079")
        assert x + w <= PANEL.x + PANEL.width
        assert y + h <= PANEL.y + PANEL.height
