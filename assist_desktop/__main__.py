"""Entrypoint. Starts the bundle server, creates the window, wires the bridge.

`emit` needs the window, and the window needs the Api — so Api takes an emitter
that is pointed at the window once it exists.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import webview

from .api import Api
from .bundle_server import BundleServer
from .config import Config

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "ui" / "dist"
CACHE = ROOT / ".image_cache"
LOG = ROOT / "turns.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(prog="assist-desktop")
    parser.add_argument("--dev", action="store_true",
                        help="load the Vite dev server instead of ui/dist")
    parser.add_argument("--devkit", default=None, help="devkit base URL")
    args = parser.parse_args()

    config = Config.load()
    if args.devkit:
        config = Config(devkit_url=args.devkit, timeout_s=config.timeout_s,
                        top_k=config.top_k)

    if not args.dev and not (DIST / "index.html").is_file():
        raise SystemExit(
            f"no built UI at {DIST}. Run `npm run build` in ui/, or pass --dev."
        )

    server = BundleServer(DIST, config.devkit_url, CACHE)
    base_url = server.start()
    url = "http://localhost:5173" if args.dev else base_url

    window_ref: list = []

    def emit(name: str, data: dict) -> None:
        if not window_ref:
            return
        payload = json.dumps({"event": name, "data": data})
        try:
            window_ref[0].evaluate_js(
                f"window.assist && window.assist.emit({payload})")
        except Exception:
            # The window is closing; a dropped event is not worth a crash.
            pass

    api = Api(config, emit=emit, log_path=LOG)
    window = webview.create_window("DEERE ASSIST R4045", url, js_api=api,
                                   width=1280, height=860)
    window_ref.append(window)

    try:
        webview.start(api.start)
    finally:
        api.stop()
        server.stop()


if __name__ == "__main__":
    main()
