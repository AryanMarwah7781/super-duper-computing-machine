"""Put the simulator on its own monitor, at a size somebody chose.

The game does not know about the other two panels and will happily stretch
across all of them -- it was found spanning 5776 pixels, from the lesson plan's
monitor to the chatbot's, with both of ours underneath it. So it gets moved.

    ASSIST_GAME_TITLE=Farming Simulator 25
    ASSIST_GAME_SIZE=1600x900      # or `max` to fill the panel

Two things are deliberate. The window is centred on its panel rather than
pinned to a corner, because a window the size of the panel and a window half
that size should both look placed rather than dropped. And it is never given
focus: moving the game must not pull the operator away from the screen they
are reading.

Exclusive fullscreen is the case this cannot help with. A game in true
fullscreen owns the display mode, and moving its window either does nothing or
drops the swap chain. Borderless windowed is the mode to run in, and the log
says so rather than pretending the move worked.
"""
from __future__ import annotations

import ctypes
import os
import re
import sys
from ctypes import wintypes
from typing import Optional

from .logs import get as get_logger
from .screens import Panel, panel_of

log = get_logger("game")

DEFAULT_TITLE = "Farming Simulator"
DEFAULT_SIZE = "max"

_SIZE = re.compile(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$")

# SetWindowPos: do not activate, do not reorder.
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SW_RESTORE = 9


def parse_size(spec: Optional[str], panel: Panel) -> tuple[int, int]:
    """How big the game window should be on `panel`.

    `max`, empty, or anything unreadable fills the panel. Falling back to the
    full panel rather than refusing is the right failure: a mistyped size
    should still put the game where it belongs.
    """
    if not spec or spec.strip().lower() in {"max", "full", "fill"}:
        return panel.width, panel.height

    m = _SIZE.match(spec)
    if not m:
        log.warning("ASSIST_GAME_SIZE=%r is not WxH or `max`; filling the panel",
                    spec)
        return panel.width, panel.height

    w, h = int(m.group(1)), int(m.group(2))
    if w <= 0 or h <= 0:
        return panel.width, panel.height
    # A window larger than the panel would spill onto the neighbours, which is
    # the exact problem this exists to fix.
    return min(w, panel.width), min(h, panel.height)


def target_rect(panel: Panel, spec: Optional[str]) -> tuple[int, int, int, int]:
    """(x, y, width, height) for the game, centred on its panel."""
    w, h = parse_size(spec, panel)
    x = panel.x + (panel.width - w) // 2
    y = panel.y + (panel.height - h) // 2
    return x, y, w, h


# -- the Windows half ------------------------------------------------------

def _user32():
    return ctypes.WinDLL("user32", use_last_error=True)


def find_window(title_contains: str) -> Optional[int]:
    """First visible top-level window whose title contains `title_contains`."""
    user32 = _user32()
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []
    needle = title_contains.casefold()

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if needle in buf.value.casefold():
                found.append(hwnd)
                return False
        return True

    cb = proc(visit)
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def place(screen, title: Optional[str] = None,
          size: Optional[str] = None) -> bool:
    """Move the game onto `screen`. True if a window was actually moved.

    Never raises. This runs during startup in front of a room, and a game that
    is not running yet is the ordinary case, not an error.
    """
    if sys.platform != "win32":
        return False

    title = title or os.environ.get("ASSIST_GAME_TITLE", DEFAULT_TITLE)
    size = size or os.environ.get("ASSIST_GAME_SIZE", DEFAULT_SIZE)

    try:
        hwnd = find_window(title)
    except Exception:
        log.exception("could not look for the game window")
        return False

    if hwnd is None:
        log.info("game      no window matching %r; nothing to place", title)
        return False

    panel = panel_of(screen)
    x, y, w, h = target_rect(panel, size)

    try:
        user32 = _user32()
        # A minimised window cannot be positioned meaningfully -- it reports
        # the restored rect but ignores the move until it comes back.
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        moved = user32.SetWindowPos(hwnd, 0, x, y, w, h,
                                    SWP_NOZORDER | SWP_NOACTIVATE)
    except Exception:
        log.exception("could not move the game window")
        return False

    if not moved:
        log.warning("game      the window refused to move; if it is in "
                    "exclusive fullscreen, set it to borderless windowed")
        return False

    log.info("game      placed at %dx%d+%d+%d", w, h, x, y)
    return True
