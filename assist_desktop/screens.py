"""Which physical panel each part of the experience opens on.

Three windows want fixed homes: the chatbot, the lesson plan, and the
simulator. Naming the panel is the whole problem -- pywebview indexes its
screens 0..n, Windows names the devices DISPLAY1/2/3/5 with no DISPLAY4, and
the Settings app shows a third set of numbers. None of them agree, and none of
them survive a cable moving.

So a panel is named by where it is:

    ASSIST_SCREEN_CHAT=1920x1080+1920+10

`tools/identify_screens.py` prints that token on each monitor. Coordinates only
change when somebody rearranges the desks, and when they do the app says so
rather than opening the lesson plan on top of the game.

Nothing here imports pywebview. It works on anything with .width/.height/.x/.y,
which is what makes it testable on a machine with one screen -- or none.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Imported for the side effect: config reads .env at import time, and the
# ASSIST_SCREEN_* keys live there. Without this the layout depends on whether
# something else happened to import config first -- which is how the trigger
# URL silently kept pointing at the old lab machine (c03e544). Resolving the
# layout is rare enough that eager loading costs nothing.
from . import config as _config       # noqa: F401

ROLES = ("chat", "lesson", "game")

# 1920x1080+1920+10, and the negative x of a monitor to the left of primary.
_TOKEN = re.compile(r"^\s*(\d+)x(\d+)([+-]\d+)([+-]\d+)\s*$")


@dataclass(frozen=True)
class Panel:
    width: int
    height: int
    x: int
    y: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height}{self.x:+d}{self.y:+d}"


def panel_of(screen) -> Panel:
    """A Panel from anything screen-shaped (pywebview's Screen, or a fake)."""
    return Panel(int(screen.width), int(screen.height),
                 int(screen.x), int(screen.y))


def parse(token: str | None) -> Panel | None:
    if not token:
        return None
    m = _TOKEN.match(token)
    if not m:
        return None
    w, h, x, y = m.groups()
    return Panel(int(w), int(h), int(x), int(y))


def match(wanted: Panel, screens: list) -> int | None:
    """Index of the screen `wanted` refers to, or None if it is not here.

    Position is what identifies a panel; resolution is allowed to differ. A
    monitor that changed mode is still the monitor on the left, and refusing
    to place a window because 1920x1080 became 1600x900 would be pedantry at
    the operator's expense.
    """
    panels = [panel_of(s) for s in screens]

    for i, p in enumerate(panels):
        if p == wanted:
            return i
    for i, p in enumerate(panels):
        if (p.x, p.y) == (wanted.x, wanted.y):
            return i
    return None


def defaults(screens: list) -> dict[str, int]:
    """Where things go when nobody has said. Left to right, primary first.

    The chatbot takes the primary panel because that is where somebody sitting
    down is already looking. The rest fill outward. With fewer panels than
    roles they double up rather than failing -- one screen showing everything
    is a working demo; a crash is not.
    """
    if not screens:
        return {}

    panels = [panel_of(s) for s in screens]
    primary = next((i for i, p in enumerate(panels) if (p.x, p.y) == (0, 0)), 0)
    rest = sorted((i for i in range(len(panels)) if i != primary),
                  key=lambda i: panels[i].x)
    order = [primary, *rest]
    return {role: order[i % len(order)] for i, role in enumerate(ROLES)}


def layout(screens: list, env: dict[str, str] | None = None
           ) -> tuple[dict[str, int], list[str]]:
    """Resolve every role to a screen index. Returns (layout, complaints).

    Complaints are returned rather than raised. A monitor that is off or
    unplugged should degrade to a sensible screen and a line in the log, not
    stop the app from starting in front of a room.
    """
    env = os.environ if env is None else env
    if not screens:
        return {}, ["no screens reported"]

    resolved = defaults(screens)
    notes: list[str] = []

    for role in ROLES:
        key = f"ASSIST_SCREEN_{role.upper()}"
        raw = env.get(key)
        if not raw:
            continue
        wanted = parse(raw)
        if wanted is None:
            notes.append(f"{key}={raw!r} is not a geometry like 1920x1080+0+0"
                         f"; using screen {resolved[role] + 1}")
            continue
        found = match(wanted, screens)
        if found is None:
            notes.append(f"{key}={raw} is not among the connected screens"
                         f"; using screen {resolved[role] + 1}")
            continue
        resolved[role] = found

    return resolved, notes


def describe(screens: list, resolved: dict[str, int]) -> list[str]:
    """One line per role, for the log. Says the panel, not the index."""
    out = []
    for role in ROLES:
        if role not in resolved:
            continue
        i = resolved[role]
        out.append(f"{role:<7} screen {i + 1}  {panel_of(screens[i])}")
    return out
