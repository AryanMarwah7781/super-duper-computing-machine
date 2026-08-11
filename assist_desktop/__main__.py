"""Entrypoint. Starts the bundle server, opens the windows, wires the bridge.

There is a window per panel now, not one window. The chatbot lives on one
monitor and the lesson plan on another, both black until somebody is greeted,
and the simulator gets a third that this app does not draw on at all.

Each window loads the same bundle with a different `?role=`, so there is one
UI, not three. Python decides which panel a role lands on; the UI decides what
a role shows. `emit` goes to every window: a turn that arrives while somebody
is reading the lesson plan still has to reach the lesson plan.

Fullscreen is deliberate and so is the escape hatch. `--windowed` opens
ordinary resizable windows for development, because a frameless fullscreen
window on the wrong monitor is genuinely hard to get rid of.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import webview

from . import commands, game, kiosk, screens
from .api import Api
from .bundle_server import BundleServer
from .config import Config
from .login_watch import LoginWatcher
from .logs import get as get_logger
from .logs import setup as setup_logging

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "ui" / "dist"
CACHE = ROOT / ".image_cache"
LOG = ROOT / "turns.jsonl"

# The panels this app draws on. The simulator's panel is resolved too -- the
# game is put there -- but no window of ours is opened over it.
WINDOWED_SIZE = (1100, 760)


def main() -> None:
    parser = argparse.ArgumentParser(prog="assist-desktop")
    parser.add_argument("--dev", action="store_true",
                        help="load the Vite dev server instead of ui/dist")
    parser.add_argument("--devkit", default=None, help="devkit base URL")
    parser.add_argument("--windowed", action="store_true",
                        help="ordinary windows instead of frameless fullscreen")
    parser.add_argument("--single", action="store_true",
                        help="one window with everything, as it was before")
    args = parser.parse_args()

    log_file = setup_logging()
    log = get_logger("main")
    log.info("=" * 62)

    config = Config.load()
    if args.devkit:
        config = Config(devkit_url=args.devkit, timeout_s=config.timeout_s,
                        top_k=config.top_k,
                        starter_video=config.starter_video)

    if not args.dev and not (DIST / "index.html").is_file():
        raise SystemExit(
            f"no built UI at {DIST}. Run `npm run build` in ui/, or pass --dev."
        )

    log.info("devkit    %s", config.devkit_url)
    route, where = commands.delivery()
    log.info("orders    %s (%s)", where,
             "written here, no listener needed" if route == "local"
             else "posted to the listener")
    log.info("log file  %s", log_file)
    starter = Path(config.starter_video)
    if not starter.is_file():
        log.warning("starter video missing: %s", starter)

    panels = list(webview.screens)
    layout, complaints = screens.layout(panels)
    for note in complaints:
        log.warning("screens   %s", note)
    for line in screens.describe(panels, layout):
        log.info("screens   %s", line)

    server = BundleServer(DIST, config.devkit_url, CACHE,
                          media={"starter.mp4": starter})
    base_url = server.start()
    log.info("ui served %s", base_url)
    base = "http://localhost:5173" if args.dev else base_url

    windows: dict[str, webview.Window] = {}

    def emit(name: str, data: dict) -> None:
        """Push an event to every open window.

        Broadcast rather than addressed: the lesson panel needs the same voice
        and connection events the chat panel does, and a role that turns out
        not to care ignores it for free.
        """
        payload = json.dumps({"event": name, "data": data})
        for window in list(windows.values()):
            try:
                window.evaluate_js(
                    f"window.assist && window.assist.emit({payload})")
            except Exception:
                # That window is closing. A dropped event is not worth taking
                # the other panels down for.
                pass

    api = Api(config, emit=emit, log_path=LOG)

    # Roles get a window each, unless two of them resolved onto the same panel
    # -- stacking two fullscreen windows on one monitor hides one of them for
    # good. One screen is a legitimate way to demo this, not a misconfiguration.
    wanted = ["chat", "lesson"]
    if args.single or layout.get("chat") == layout.get("lesson"):
        wanted = ["all"]

    for role in wanted:
        index = layout.get("chat" if role == "all" else role)
        screen = panels[index] if index is not None and panels else None
        title = {"chat": "DEERE ASSIST — CHATBOT",
                 "lesson": "DEERE ASSIST — LESSON PLAN",
                 "all": "DEERE ASSIST R4045"}[role]
        window = webview.create_window(
            title, f"{base}?role={role}", js_api=api,
            screen=screen,
            width=WINDOWED_SIZE[0], height=WINDOWED_SIZE[1],
            fullscreen=not args.windowed,
            frameless=not args.windowed,
            # Black from the first painted frame. Without this the window
            # flashes white while the bundle loads, which is the one thing
            # "keep the screens black" was asking us not to do.
            background_color="#000000",
            # A frameless window is draggable by its body by default, so any
            # stray drag on the chat panel slides the whole window off its
            # monitor with no title bar to put it back by. A panel that is
            # assigned to a screen has no business moving off it.
            easy_drag=False,
            # It covers the panel; it does not own it. Anything the operator
            # alt-tabs to has to be able to come to the front.
            on_top=False,
        )
        windows[role] = window
        log.info("window    %-6s screen %s", role,
                 (index + 1) if index is not None else "?")

    # There is no title bar, so the only way out is the one the UI draws.
    # Both panels move together: minimising one of two fullscreen windows
    # leaves the other covering its monitor, which reads as a half-crashed app.
    def minimize_all() -> None:
        for window in list(windows.values()):
            try:
                window.minimize()
            except Exception:
                log.exception("could not minimise a window")

    def close_all() -> None:
        for window in list(windows.values()):
            try:
                window.destroy()
            except Exception:
                log.exception("could not close a window")

    def raise_role(role: str) -> None:
        """Bring one panel forward without disturbing the others.

        `show()` restores it if it was minimised, which is the case that
        matters: the operator stepped away, minimised everything, and is now
        asking for the chatbot by voice from across the workshop.
        """
        window = windows.get(role) or windows.get("all")
        if window is None:
            return
        try:
            window.show()
        except Exception:
            log.exception("could not raise the %s panel", role)

    api.set_window_controls(minimize_all, close_all, raise_role)

    # The simulator gets its panel back. It is not ours to launch -- if it is
    # not running this says so and moves on -- but it will happily stretch
    # across every monitor, including the two this app just claimed.
    game_index = layout.get("game")
    if game_index is not None and panels:
        game.place(panels[game_index])

    # Two ways somebody can arrive already signed in, and neither is required.
    # The kiosk on the board POSTs the sign-in over the network; the older
    # arrangement writes the name to a file that is polled. Whichever is
    # absent simply never fires, and the app's own sign-in screen remains the
    # way in -- the demo does not wait on another machine being ready.
    listener = kiosk.LoginListener(api.external_login)
    listener.start()
    log.info("kiosk     %s (sign-outs are posted there)", kiosk.kiosk_url())

    watcher = LoginWatcher(api.external_login)
    if watcher.path.is_file():
        log.info("login     watching %s", watcher.path)
    else:
        log.info("login     %s does not exist yet; using the sign-in screen",
                 watcher.path)
    watcher.start()

    try:
        log.info("windows opening - close one to stop")
        webview.start(api.start)
    finally:
        log.info("shutting down")
        listener.stop()
        watcher.stop()
        api.stop()
        server.stop()
        log.info("stopped")


if __name__ == "__main__":
    main()
