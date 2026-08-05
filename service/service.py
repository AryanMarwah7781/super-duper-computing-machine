"""HTTP front for the v4 pipeline. Deployed to /media/nvme/ari_jd/v4/service.py.

Deliberately separate from the historical server.py, which is wired to v2.2 and
v3 and carries face auth, wake word and PulseAudio playback. v4 needs four
endpoints; adding them there would re-couple v4 to the stack it stands apart
from.

Two constraints shape this file:

  Milvus-lite is single-process. This service holds an exclusive lock on the
  index for its lifetime — nothing else may search while it runs, including
  ask.py. Startup surfaces the failure through /health rather than degrading
  silently.

  Cold load is ~26s. It happens at startup, not on the first request, and
  /health reports ready=false until it finishes.
"""
from __future__ import annotations

import hashlib
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

V4_ROOT = Path("/media/nvme/ari_jd/v4")
IMAGES_ROOT = Path("/media/nvme/ari_jd/jd-chatbot-v3/static")
sys.path.insert(0, str(V4_ROOT))

from assist.answer.render import render          # noqa: E402
from assist.answer.route import route            # noqa: E402
from assist.retrieve import search as S          # noqa: E402

_state: dict = {"ready": False, "error": None, "started": time.time(),
                "corpus_hash": "", "chunk_count": 0}
_query_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_app: "FastAPI"):
    # Loading takes ~26s. Do it at startup on a background thread so the port
    # answers immediately and /health can report ready=false meanwhile.
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="deere-assist-v4", lifespan=lifespan)


class AskRequest(BaseModel):
    query: str
    top_k: int = 5


def _warm() -> None:
    try:
        loaded = S._load()
    except Exception as e:  # surfaced through /health, not swallowed
        _state["error"] = f"{type(e).__name__}: {e}"
        return

    # The corpus hash only identifies *which* corpus is loaded. Failing to read
    # it must not keep a perfectly good index from serving — an earlier version
    # computed it inside the same try, so a missing chunks.json bricked the
    # service with the index already loaded.
    try:
        digest = hashlib.sha1(
            (V4_ROOT / "data" / "chunks.json").read_bytes()).hexdigest()[:8]
    except OSError:
        digest = ""

    _state.update(ready=True, corpus_hash=digest,
                  chunk_count=len(loaded["by_id"]))


@app.get("/ready")
def ready() -> dict:
    return {"alive": True}


@app.get("/health")
def health() -> dict:
    return {
        "ready": bool(_state["ready"]),
        "error": _state["error"],
        "render_version": "v4.0",
        "corpus_hash": _state["corpus_hash"],
        "chunk_count": _state["chunk_count"],
        "uptime_s": int(time.time() - _state["started"]),
    }


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    if not _state["ready"]:
        detail = _state["error"] or "index is still loading"
        raise HTTPException(status_code=503, detail=detail)

    t0 = time.perf_counter()
    # Serialised: milvus-lite is single-process, and this is a one-operator
    # appliance. Concurrency would buy nothing and risk the store.
    with _query_lock:
        hits = S.search(req.query, top_k=req.top_k)
        t_search = time.perf_counter()
        plan = route(hits)

        answer = None
        if plan.kind != "oos" and plan.chunk_ids:
            chunk = S._load()["by_id"][plan.chunk_ids[0]]
            answer = asdict(render(chunk))
        t_render = time.perf_counter()

    return {
        "plan": {"kind": plan.kind, "chunk_ids": list(plan.chunk_ids),
                 "reason": plan.reason},
        "answer": answer,
        "candidates": [
            {"chunk_id": h["chunk_id"],
             "score": float(h.get("rerank_score", 0.0)),
             "content_type": h.get("content_type", ""),
             "procedure_name": h.get("procedure_name") or "",
             "page": h.get("page")}
            for h in hits
        ],
        "timing": {
            "search_ms": int((t_search - t0) * 1000),
            "render_ms": int((t_render - t_search) * 1000),
            "total_ms": int((time.perf_counter() - t0) * 1000),
        },
    }


@app.get("/images/{path:path}")
def images(path: str) -> FileResponse:
    target = (IMAGES_ROOT / path).resolve()
    if not str(target).startswith(str(IMAGES_ROOT.resolve())) or not target.is_file():
        raise HTTPException(status_code=404, detail="no such image")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=604800"})
