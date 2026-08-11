"""Put a big number on every monitor, so a role can be pinned to a panel.

    .venv\\Scripts\\python tools\\identify_screens.py
    .venv\\Scripts\\python tools\\identify_screens.py --seconds 20

There are three numbering schemes on this rig and no two agree. pywebview
indexes its own list 0..n, Windows names the devices DISPLAY1/2/3/5 with no
DISPLAY4 at all, and the Settings app shows a fourth set of numbers. Asking
somebody which monitor is "screen 3" cannot be answered from any of them.

So this asks the panels directly. Each one shows the token that identifies it,
and that token -- a geometry, not an index -- is what goes in .env:

    ASSIST_SCREEN_CHAT=1920x1080+1920+10

Geometry is used deliberately. An index reshuffles the moment a cable moves or
a monitor sleeps, and a layout pinned to indices then opens the lesson screen
on top of the game. Coordinates only change when somebody actually rearranges
the desks, and when they do the app says so instead of guessing.
"""
from __future__ import annotations

import argparse
import sys
import tkinter as tk

import webview

# The panels are told apart by colour as well as number, because "the blue one"
# survives being read out across a workshop and "the second one" does not.
COLOURS = ["#004884", "#8a1c1c", "#1b5e20", "#5c2d91", "#a15c00", "#00595c"]


def token(screen) -> str:
    """The stable name for a panel: what goes in .env."""
    return f"{screen.width}x{screen.height}+{screen.x}+{screen.y}"


def show(seconds: float) -> int:
    screens = list(webview.screens)
    if not screens:
        print("no screens reported.")
        return 1

    root = tk.Tk()
    root.withdraw()
    panels = []

    for i, screen in enumerate(screens):
        w = tk.Toplevel(root)
        w.overrideredirect(True)          # no title bar to shift the position
        w.geometry(f"{screen.width}x{screen.height}+{screen.x}+{screen.y}")
        w.configure(bg=COLOURS[i % len(COLOURS)])
        w.attributes("-topmost", True)

        bg = COLOURS[i % len(COLOURS)]
        tk.Label(w, text=str(i + 1), fg="white", bg=bg,
                 font=("Segoe UI", 260, "bold")).pack(pady=(screen.height // 8, 0))
        tk.Label(w, text=token(screen), fg="white", bg=bg,
                 font=("Consolas", 30)).pack()
        tk.Label(w, text="primary" if (screen.x, screen.y) == (0, 0) else "",
                 fg="white", bg=bg, font=("Segoe UI", 20)).pack(pady=8)
        tk.Label(w, text="click or press a key to close all",
                 fg="white", bg=bg, font=("Segoe UI", 16)).pack(pady=40)

        w.bind("<Button-1>", lambda _e: root.destroy())
        w.bind("<Key>", lambda _e: root.destroy())
        w.focus_force()
        panels.append(w)

    print(f"{len(screens)} screens. Each is showing its number and its token:\n")
    for i, screen in enumerate(screens):
        primary = "  (primary)" if (screen.x, screen.y) == (0, 0) else ""
        print(f"  {i + 1}   {token(screen)}{primary}")
    print("\nPut the tokens of the panels you want in .env:\n")
    print("  ASSIST_SCREEN_CHAT=<token of the chatbot panel>")
    print("  ASSIST_SCREEN_LESSON=<token of the lesson panel>")
    print("  ASSIST_SCREEN_GAME=<token of the simulator panel>")

    root.after(int(seconds * 1000), root.destroy)
    try:
        root.mainloop()
    except tk.TclError:
        pass       # destroyed from a binding while mainloop was unwinding
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="identify_screens")
    parser.add_argument("--seconds", type=float, default=15.0,
                        help="how long to leave the numbers up (default 15)")
    args = parser.parse_args()
    return show(args.seconds)


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("Windows only.")
    raise SystemExit(main())
