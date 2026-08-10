"""Answer the common questions once, before anyone asks them.

    .venv\\Scripts\\python tools\\warm_cache.py            # the curated list
    .venv\\Scripts\\python tools\\warm_cache.py --from-log # what people ask here
    .venv\\Scripts\\python tools\\warm_cache.py --list     # what is already cached
    .venv\\Scripts\\python tools\\warm_cache.py --clear    # forget it all

Retrieval on the board takes about six seconds and synthesis fifteen to
thirty. Both are one-off costs per question, and this pays them somewhere
other than in front of an operator.

Run it against the SAME devkit the app will use — an answer is stored per
service and per render version, so warming v3 does nothing for v4. It reads
.env for the address, exactly as the app does.

Nothing here invents an answer. Each question is asked through the ordinary
path and whatever the board says is what gets stored.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assist_desktop.api import Api            # noqa: E402
from assist_desktop.config import Config      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "data" / "common_questions.json"
TURNLOG = ROOT / "turns.jsonl"


def curated() -> list[str]:
    try:
        return json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    except (OSError, ValueError, KeyError):
        return []


def from_log(limit: int = 25) -> list[str]:
    """What has actually been asked on this machine, most-asked first. The
    curated list is a guess; this is evidence."""
    if not TURNLOG.is_file():
        return []
    counted: Counter[str] = Counter()
    for line in TURNLOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("kind") in ("cached", "synthesize") and row.get("query"):
            counted[row["query"].strip()] += 1
    return [q for q, _ in counted.most_common(limit)]


def main() -> int:
    ap = argparse.ArgumentParser(prog="warm_cache")
    ap.add_argument("--from-log", action="store_true",
                    help="use the questions people have actually asked here")
    ap.add_argument("--list", action="store_true", help="show what is cached")
    ap.add_argument("--clear", action="store_true", help="forget every answer")
    ap.add_argument("--all-services", action="store_true",
                    help="with --clear: every pipeline, not just this one")
    args = ap.parse_args()

    config = Config.load()
    api = Api(config, emit=lambda name, data: None)

    if args.list:
        answers = api.cached_answers()["answers"]
        if not answers:
            print("nothing cached yet")
            return 0
        print(f"{len(answers)} cached answer(s):\n")
        for a in answers:
            print(f"  {a['hits']:>3} hit(s)  {a['took_ms']:>6}ms first time  "
                  f"[{a['render_version']}] {a['query'][:56]}")
        return 0

    if args.clear:
        print(f"forgot {api.forget_answers(args.all_services)['removed']} answer(s)")
        return 0

    # The version is read from /health, and the cache keys on it, so a warm-up
    # started before the board answers would file everything under "?".
    api._monitor.poll_once()
    version = api._monitor.render_version
    if not version:
        print(f"the devkit at {config.devkit_url} is not answering — nothing warmed")
        return 1

    questions = from_log() if args.from_log else curated()
    if not questions:
        print("no questions to warm")
        return 1

    print(f"devkit {config.devkit_url}  ({version})")
    print(f"warming {len(questions)} question(s). Six seconds each, more when "
          f"the model writes prose.\n")

    hot = cold = failed = 0
    started = time.perf_counter()
    for i, question in enumerate(questions, start=1):
        was_cached = api._recall(question) is not None
        if was_cached:
            hot += 1
            print(f"  [{i:>2}/{len(questions)}] already cached  {question[:52]}")
            continue
        t = time.perf_counter()
        result = api.ask(question, source="warmup")
        took = (time.perf_counter() - t) * 1000
        if not result["ok"]:
            failed += 1
            print(f"  [{i:>2}/{len(questions)}] FAILED {result['error']}  {question[:40]}")
            continue
        kind = result["turn"]["plan"]["kind"]
        kept = kind in ("cached", "synthesize")
        cold += 1 if kept else 0
        mark = "cached" if kept else f"not kept ({kind})"
        print(f"  [{i:>2}/{len(questions)}] {took:>7.0f}ms  {mark:<16} {question[:44]}")

    print(f"\n{cold} newly cached, {hot} already there, {failed} failed, "
          f"in {time.perf_counter() - started:.0f}s")
    print("Those questions now answer in about a millisecond.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
