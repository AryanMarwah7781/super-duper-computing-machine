"""Preflight: is everything this app needs present, and is anything holding it?

    python tools/preflight.py                 # check both sides
    python tools/preflight.py --local-only    # skip the board
    python tools/preflight.py --json          # machine-readable

Board access needs a password. Read from the environment so it never lands in
the repo:

    $env:ASSIST_BOARD_PASSWORD = "..."        # PowerShell
    export ASSIST_BOARD_PASSWORD=...          # bash

Every check reports one of:

    OK       present and free to use
    BUSY     present but something is holding it — names the holder
    MISSING  not there; the app cannot start
    WARN     works, but not how you probably want it

Exit code is 1 if anything is MISSING or BUSY, so this can gate a launch script.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

# --- what the app needs -------------------------------------------------------

BOARD_HOST = os.environ.get("ASSIST_BOARD_HOST", "192.168.94.180")
BOARD_USER = os.environ.get("ASSIST_BOARD_USER", "sima")
BOARD_HOSTKEY = os.environ.get(
    "ASSIST_BOARD_HOSTKEY",
    "SHA256:PgQIqx43Xlf1bLiYq7F9gp7YEx1afGr4TxH3vGzF66A")

REPO = Path(__file__).resolve().parent.parent
BUNDLE = "/media/nvme/ari_assist/rag-v4-min"
GEMMA = "/media/nvme/llima/models/gemma-4-E2B-it-GPTQ-a16w4"

OK, BUSY, MISSING, WARN = "OK", "BUSY", "MISSING", "WARN"
BLOCKING = {MISSING, BUSY}


@dataclass
class Check:
    group: str
    name: str
    status: str
    detail: str = ""


# --- plumbing -----------------------------------------------------------------

def _plink() -> Optional[str]:
    for c in (r"C:\Program Files\PuTTY\plink.exe",
              r"C:\Program Files (x86)\PuTTY\plink.exe"):
        if Path(c).is_file():
            return c
    return shutil.which("plink")


def remote(cmd: str, password: str, timeout: int = 60) -> tuple[int, str]:
    """Run a command on the board. plink, not ssh: ssh prompts interactively
    and there is no tty here."""
    exe = _plink()
    if not exe:
        return 127, "plink not found"
    try:
        p = subprocess.run(
            [exe, "-batch", "-ssh", "-hostkey", BOARD_HOSTKEY, "-pw", password,
             f"{BOARD_USER}@{BOARD_HOST}", cmd],
            capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --- local checks -------------------------------------------------------------

def check_local() -> list[Check]:
    out: list[Check] = []
    g = "windows client"

    venv = REPO / ".venv" / "Scripts" / "python.exe"
    out.append(Check(g, "python venv", OK if venv.is_file() else MISSING,
                     str(venv) if venv.is_file() else "run: python -m venv .venv"))

    dist = REPO / "ui" / "dist" / "index.html"
    out.append(Check(g, "ui build", OK if dist.is_file() else MISSING,
                     "ui/dist/index.html" if dist.is_file()
                     else "run: cd ui && npm run build"))

    # Wake word needs all three stages, not just the classifier — the mel and
    # embedding models are what actually make it runnable.
    wake = REPO.parent / "wakeword"
    need = ["hey_chris.onnx", "melspectrogram.onnx", "embedding_model.onnx"]
    have = [f for f in need if (wake / f).is_file()]
    if len(have) == len(need):
        out.append(Check(g, "wake word (hey_chris)", OK, f"{wake}"))
    elif have:
        out.append(Check(g, "wake word (hey_chris)", MISSING,
                         "missing: " + ", ".join(set(need) - set(have))))
    else:
        out.append(Check(g, "wake word (hey_chris)", MISSING, f"nothing in {wake}"))

    piper = Path(r"C:\Users\user\Desktop\piper\en_US-lessac-medium.onnx")
    out.append(Check(g, "piper voice (TTS)", OK if piper.is_file() else WARN,
                     str(piper) if piper.is_file() else "phase 2 only"))

    fixtures = REPO / "fixtures" / "procedure.json"
    out.append(Check(g, "fixtures / fake devkit", OK if fixtures.is_file() else MISSING,
                     "can run offline" if fixtures.is_file() else "fixtures/ missing"))
    return out


# --- board checks -------------------------------------------------------------

def check_board(password: str) -> list[Check]:
    out: list[Check] = []
    net, hw, models, svc = "network", "board hardware", "board models", "board services"

    if not port_open(BOARD_HOST, 22):
        out.append(Check(net, f"ssh {BOARD_HOST}:22", MISSING, "unreachable"))
        return out
    out.append(Check(net, f"ssh {BOARD_HOST}:22", OK, "reachable"))

    code, who = remote("id -un", password, timeout=30)
    if code != 0:
        out.append(Check(net, "ssh auth", MISSING, who or "auth failed"))
        return out
    out.append(Check(net, "ssh auth", OK, f"logged in as {who}"))

    # -- hardware
    _, mem = remote("free -m | awk '/^Mem:/{print $7\" \"$2}'", password)
    parts = mem.split()
    if len(parts) == 2:
        avail, total = int(parts[0]), int(parts[1])
        # Gemma 4 E2B is 8.7 GB on disk; it needs real headroom to load.
        status = OK if avail >= 6000 else WARN
        out.append(Check(hw, "memory", status,
                         f"{avail/1024:.1f} GB available of {total/1024:.1f} GB"))

    _, disk = remote("df -BG --output=avail /media/nvme | tail -1 | tr -d ' G'", password)
    if disk.isdigit():
        out.append(Check(hw, "disk /media/nvme", OK if int(disk) > 10 else WARN,
                         f"{disk} GB free"))

    # The MLA mailbox: mlashmcomplex holding it is normal and expected. The old
    # sima_lmm backend tries to open it directly and fails; the llima runtime
    # goes through the shared-memory complex and works.
    _, holder = remote(
        "sudo -n fuser -v /dev/m4_lp_mbox 2>&1 | tail -1 | awk '{print $NF}'", password)
    if "mlashmcomplex" in holder:
        out.append(Check(hw, "MLA mailbox", OK, "held by mlashmcomplex (expected)"))
    elif holder.strip():
        out.append(Check(hw, "MLA mailbox", BUSY, f"held by {holder.strip()}"))
    else:
        out.append(Check(hw, "MLA mailbox", WARN, "no holder — MLA may be uninitialised"))

    _, active = remote(
        "systemctl is-active simaai-appcomplex.service 2>/dev/null", password)
    out.append(Check(hw, "simaai-appcomplex", OK if active == "active" else MISSING,
                     active or "not running"))

    # MLA memory comes from the kernel CMA pool, and it is NOT freed when a
    # model process is killed rather than exited cleanly. Killing `llima run`
    # with pkill leaves its buffers allocated until reboot. Surfacing the pool
    # here makes that leak visible before it starves the next load.
    _, cma = remote(
        "awk '/CmaTotal|CmaFree/{print $2}' /proc/meminfo | tr '\\n' ' '", password)
    nums = [int(x) for x in cma.split() if x.isdigit()]
    if len(nums) == 2:
        total_mb, free_mb = nums[0] // 1024, nums[1] // 1024
        used_mb = total_mb - free_mb
        # Bracket trick: without it the pattern matches the shell wrapper whose
        # own command line contains the pattern, and every check self-reports.
        _, running = remote(
            "pgrep -af '[l]lima run|[d]evkit_demo' | head -1", password)
        # The driver reserves an unknown amount at boot, so "used" alone cannot
        # prove a leak. Compare against a baseline captured just after a reboot;
        # without one, report the number and say it is unverified rather than
        # guessing a threshold.
        baseline = REPO / "data" / "cma_baseline.txt"
        recorded = int(baseline.read_text().strip()) if baseline.is_file() else None
        if running:
            status, note = OK, f"{used_mb} MB in use by a running model"
        elif recorded is None:
            status, note = WARN, (f"{used_mb} MB held, no baseline recorded — run "
                                  f"--record-baseline just after a reboot")
        elif used_mb > recorded + 100:
            status, note = BUSY, (f"{used_mb} MB held vs {recorded} MB baseline — "
                                  f"{used_mb - recorded} MB orphaned; only a reboot "
                                  f"frees it")
        else:
            status, note = OK, f"{used_mb} MB, matches the {recorded} MB baseline"
        out.append(Check(hw, "MLA memory (CMA)", status,
                         f"{free_mb} MB free of {total_mb} MB — {note}"))

    # -- models
    _, gemma = remote(f"llima list 2>/dev/null | grep -c gemma-4-E2B", password)
    out.append(Check(models, "gemma-4-E2B (LLM)", OK if gemma == "1" else MISSING,
                     "registered with llima" if gemma == "1" else "not in llima list"))

    for label, path in [("whisper-small (STT)", "/media/nvme/llima/whisper-small-a16w8"),
                        ("supertonic (TTS)", "/media/nvme/supertonic/assets/onnx")]:
        _, ok = remote(f"[ -d {path} ] && echo yes || echo no", password)
        out.append(Check(models, label, OK if ok == "yes" else MISSING, path))

    # -- the RAG bundle
    for label, path in [("corpus chunks.json", f"{BUNDLE}/chunks.json"),
                        ("embedder bge-large", f"{BUNDLE}/bge-large-local"),
                        ("reranker cross-encoder", f"{BUNDLE}/cross-encoder-fast-local"),
                        ("bm25 index", f"{BUNDLE}/index/bm25")]:
        _, ok = remote(f"[ -e {path} ] && echo yes || echo no", password)
        out.append(Check(models, label, OK if ok == "yes" else MISSING, path))

    # Storage format matters: milvus-lite 2.5.1 wants a single SQLite FILE. The
    # index v4 shipped is a DIRECTORY and fails with "unable to open database
    # file" — rebuild it if this trips.
    _, kind = remote(
        f"if [ -f {BUNDLE}/index/jd_manuals_v4.db ]; then echo file; "
        f"elif [ -d {BUNDLE}/index/jd_manuals_v4.db ]; then echo dir; "
        f"else echo none; fi", password)
    if kind == "file":
        out.append(Check(models, "milvus index", OK, "single-file format (correct)"))
    elif kind == "dir":
        out.append(Check(models, "milvus index", MISSING,
                         "old DIRECTORY format — rebuild with rebuild_index.py"))
    else:
        out.append(Check(models, "milvus index", MISSING, "not found"))

    # milvus-lite is single-process. Ask who has the index file open rather than
    # pattern-matching process names — an earlier version grepped for
    # "service.py" and matched the unrelated mla_rt_service.py.
    _, lock = remote(
        f"sudo -n lsof -t {BUNDLE}/index/jd_manuals_v4.db 2>/dev/null "
        f"| head -3 | tr '\\n' ' '", password)
    lock = lock.strip()
    if lock:
        _, who = remote(f"ps -o comm= -p {lock.split()[0]} 2>/dev/null", password)
        out.append(Check(svc, "milvus index lock", BUSY,
                         f"pid {lock.split()[0]} ({who or '?'}) has it open"))
    else:
        out.append(Check(svc, "milvus index lock", OK, "free"))

    # -- ports
    for label, port, expect_used in [("LLiMa API", 5000, False),
                                     ("RAG service", 8090, False),
                                     ("mla_rt_service", 8000, True)]:
        used = port_open(BOARD_HOST, port, timeout=2)
        if expect_used:
            out.append(Check(svc, f"{label} :{port}", OK if used else WARN,
                             "running" if used else "not running"))
        else:
            out.append(Check(svc, f"{label} :{port}", WARN if used else OK,
                             "already in use" if used else "free to bind"))
    return out


# --- report -------------------------------------------------------------------

SYMBOL = {OK: "[ ok ]", BUSY: "[busy]", MISSING: "[MISS]", WARN: "[warn]"}


def report(checks: list[Check]) -> int:
    width = max(len(c.name) for c in checks) + 2
    group = None
    for c in checks:
        if c.group != group:
            group = c.group
            print(f"\n{group.upper()}")
        print(f"  {SYMBOL[c.status]}  {c.name:<{width}} {c.detail}")

    blockers = [c for c in checks if c.status in BLOCKING]
    warns = [c for c in checks if c.status == WARN]
    print()
    if blockers:
        print(f"{len(blockers)} blocker(s):")
        for c in blockers:
            print(f"   - {c.name}: {c.detail}")
    if warns:
        print(f"{len(warns)} warning(s) — not fatal.")
    if not blockers:
        print("All required resources present and free.")
    return 1 if blockers else 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="preflight")
    ap.add_argument("--local-only", action="store_true", help="skip board checks")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--record-baseline", action="store_true",
                    help="record MLA memory now as the clean baseline — only "
                         "meaningful straight after a reboot, before any model runs")
    args = ap.parse_args()

    if args.record_baseline:
        password = os.environ.get("ASSIST_BOARD_PASSWORD", "")
        if not password:
            print("set ASSIST_BOARD_PASSWORD first")
            return 1
        _, cma = remote(
            "awk '/CmaTotal|CmaFree/{print $2}' /proc/meminfo | tr '\\n' ' '", password)
        nums = [int(x) for x in cma.split() if x.isdigit()]
        if len(nums) != 2:
            print("could not read CMA from the board")
            return 1
        used = nums[0] // 1024 - nums[1] // 1024
        path = REPO / "data" / "cma_baseline.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(used))
        print(f"recorded MLA baseline: {used} MB used -> {path}")
        return 0

    checks = check_local()

    if not args.local_only:
        password = os.environ.get("ASSIST_BOARD_PASSWORD", "")
        if not password:
            checks.append(Check("network", "board password", WARN,
                                "set ASSIST_BOARD_PASSWORD to check the board"))
        else:
            checks += check_board(password)

    if args.json:
        print(json.dumps([asdict(c) for c in checks], indent=2))
        return 1 if any(c.status in BLOCKING for c in checks) else 0
    return report(checks)


if __name__ == "__main__":
    sys.exit(main())
