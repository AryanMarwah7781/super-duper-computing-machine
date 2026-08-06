"""HTTP front for the v3 pipeline, speaking the same contract as the v4 one.

Deployed to /media/nvme/ari_assist/service_v3.py and run with cwd
/media/nvme/ari_assist/v3, because v3's config.py uses relative paths
(./data, ./bge-large-local, ./static/images).

Why v3 rather than v4: v4's own handoff records that it dropped v3's 14
corrective retrieval regexes and never replaced them, and the regression is
real. Measured on this board — "how do i start spraying":

    v3  ->  Field Operation                              correct
    v4  ->  Example 1: Activate a Section  (8.14)        wrong
            Example 3: Activate All Nozzles (8.00)       wrong
            Field Operation                 (4.28)

The trade is safety attachment: v4's repair passes reattached 64 detached
CAUTION blocks and recovered 60 warnings that were in no chunk at all, and v3
has none of that. See §Known gaps below.

Differences from the v4 service, all handled here so the client is unchanged:

  answer      v3 returns one rendered string; it already uses the same line
              grammar ("Here's how:", "Step N:", "[PHOTO: ...]").
  images      v3's caption IS the JD id code, and that is what the [PHOTO:]
              marker carries, so caption-matching in the client works as-is.
  page        v3 emits no "_Manual page N._" footer, so citations are empty.
  scores      v3's Source carries no rerank score, so candidates are reported
              without one. The turn log loses its score evidence under v3.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import difflib
import json
import math
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

V3_ROOT = Path("/media/nvme/ari_assist/v3")
IMAGES_ROOT = Path("/media/nvme/ari_assist/static/images")
os.chdir(V3_ROOT)          # v3's config.py is all relative paths
sys.path.insert(0, str(V3_ROOT))

from chatbot import JDChatbot          # noqa: E402

RENDER_VERSION = "v3"

_state: dict = {"ready": False, "error": None, "started": time.time(),
                "chunk_count": 0}
# Vocabulary of the manual, for repairing misheard words. Speech-to-text turns
# "spraying" into "spinning" and "speaking" — words that are perfectly ordinary
# English but appear nowhere in this manual, so retrieval correctly finds
# nothing and the operator gets "I don't know" for a question they asked right.
_vocab: dict[str, int] = {}
_WORD = re.compile(r"[a-z]{4,}")
STOPWORDS = {"what", "when", "where", "which", "with", "that", "this", "have",
             "does", "should", "would", "could", "from", "into", "your", "then",
             "them", "they", "there", "here", "about", "after", "before"}
_bot: JDChatbot | None = None
_query_lock = threading.Lock()


class AskRequest(BaseModel):
    query: str
    top_k: int = 5


def _build_vocab() -> None:
    """Every word the manual uses, WITH how often — frequency is the signal.

    Counting matters. "spinning" appears 10 times in this manual and "spraying"
    176, so when speech-to-text produces one of them the common word is far
    more likely to be what was said. Edit distance alone got this wrong: it
    offered "spreading" (12 uses) over "spraying" for "speaking".
    """
    try:
        chunks = json.load(open(V3_ROOT / "data" / "chunks.json", encoding="utf-8"))
    except Exception:
        return
    for c in chunks:
        # A word in a procedure NAME is what operators ask about; a word in body
        # text may be incidental. "spraying" titles procedures, "spring" only
        # ever describes a part — so names count for far more.
        for word in _WORD.findall((c.get("procedure_name") or "").lower()):
            _vocab[word] = _vocab.get(word, 0) + NAME_WEIGHT
        parts = [c.get("text") or ""]
        parts += [s.get("text", "") for s in (c.get("steps") or [])]
        for part in parts:
            for word in _WORD.findall(part.lower()):
                _vocab[word] = _vocab.get(word, 0) + 1


# A word this rare in the manual is a plausible mishearing even though it does
# appear — "spinning" (10 uses) next to "spraying" (176) is exactly that case.
NAME_WEIGHT = 12
RARE = 25
# How much more common a candidate must be before overriding a word that is
# genuinely in the manual.
DOMINANCE = 6


def _repair_word(bare: str) -> str | None:
    """The manual's word most likely to have been misheard as this one.

    Scored on similarity AND frequency: an edit-distance-only match offered
    "spreading" for "speaking" when "spraying" is fifteen times more common.
    """
    here = _vocab.get(bare, 0)
    if here and here > RARE:
        return None                      # common in the manual: trust it

    near = difflib.get_close_matches(bare, _vocab.keys(), n=8, cutoff=0.6)
    best, best_score = None, 0.0
    for candidate in near:
        if candidate == bare:
            continue
        count = _vocab.get(candidate, 0)
        if here and count < here * DOMINANCE:
            continue                     # not clearly more likely: leave it
        ratio = difflib.SequenceMatcher(None, bare, candidate).ratio()
        score = ratio * math.log1p(count)
        if score > best_score:
            best, best_score = candidate, score
    return best


def _suggest(query: str) -> str:
    """Repair a query that the manual cannot answer as heard.

    Returns "" when nothing looked misheard, so a correctly heard question is
    never rewritten.
    """
    if not _vocab:
        return ""
    fixed, changed = [], False
    for word in query.split():
        bare = re.sub(r"[^a-z]", "", word.lower())
        if len(bare) < 4 or bare in STOPWORDS:
            fixed.append(word)
            continue
        repaired = _repair_word(bare)
        if repaired:
            fixed.append(repaired)
            changed = True
        else:
            fixed.append(word)
    return " ".join(fixed) if changed else ""


def _warm() -> None:
    global _bot
    try:
        bot = JDChatbot()
        count = bot.chunk_count()
        _bot = bot
        _build_vocab()
        _state.update(ready=True, chunk_count=count)
    except Exception as e:  # surfaced through /health, not swallowed
        _state["error"] = f"{type(e).__name__}: {e}"


def _lifespan_factory():
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        threading.Thread(target=_warm, daemon=True).start()
        yield

    return lifespan


app = FastAPI(title="deere-assist-v3", lifespan=_lifespan_factory())


def _image_dicts(response) -> list[dict]:
    """Collapse response-level and per-source images into the wire shape.

    v3 gives {url, fname, caption} where caption is the JD id code. The client
    matches a [PHOTO: X] marker on caption first and id_code second, and X *is*
    that code — so both fields carry it and either match works.
    """
    seen: set[str] = set()
    out: list[dict] = []
    pools = [response.images or []]
    pools += [s.images or [] for s in (response.sources or [])]
    for pool in pools:
        for img in pool:
            code = (img.get("caption") or "").strip()
            fname = img.get("fname") or os.path.basename(img.get("url") or "")
            if not fname or fname in seen:
                continue
            seen.add(fname)
            out.append({"id_code": code, "image_path": fname,
                        "caption": code, "step_num": None})
    return out


@app.get("/ready")
def ready() -> dict:
    return {"alive": True}


@app.get("/health")
def health() -> dict:
    return {
        "ready": bool(_state["ready"]),
        "error": _state["error"],
        "render_version": RENDER_VERSION,
        "corpus_hash": "",
        "chunk_count": _state["chunk_count"],
        "uptime_s": int(time.time() - _state["started"]),
    }


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    if not _state["ready"] or _bot is None:
        raise HTTPException(status_code=503,
                            detail=_state["error"] or "pipeline is still loading")

    t0 = time.perf_counter()
    # v3's milvus handle and its chatbot session are not concurrency-safe, and
    # this is a one-operator appliance.
    with _query_lock:
        try:
            r = _bot.ask(req.query, render_mode="deterministic")
        except Exception as e:
            raise HTTPException(status_code=502,
                                detail=f"{type(e).__name__}: {e}") from e
    elapsed = int((time.perf_counter() - t0) * 1000)

    suggestion = ""
    if r.clarification_needed or not r.sources:
        kind, answer = "oos", None
        # Nothing matched. Before giving up, check whether a word was misheard.
        suggestion = _suggest(req.query)
    else:
        kind = "cached" if r.is_procedural else "synthesize"
        images = _image_dicts(r)
        answer = {
            "display_text": r.answer,
            # v3 has no separate spoken form; the renderer's own lines are the
            # closest thing, minus the photo markers which must never be read
            # aloud (a JD part code spoken letter by letter cost ~4.6s each).
            "spoken_segments": [ln.strip() for ln in r.answer.split("\n")
                                if ln.strip() and not ln.strip().startswith("[PHOTO:")],
            "safety": [],
            "citations": [],
            "images": images,
            "render_version": RENDER_VERSION,
            "source_hash": "",
        }

    return {
        "plan": {"kind": kind,
                 "chunk_ids": [s.chunk_id for s in (r.sources or [])],
                 "reason": f"v3 is_procedural={r.is_procedural} "
                           f"sources={len(r.sources or [])}"},
        "answer": answer,
        "candidates": [{"chunk_id": s.chunk_id, "score": 0.0,
                        "content_type": s.content_type,
                        "procedure_name": s.procedure_name, "page": None}
                       for s in (r.sources or [])],
        "suggestion": suggestion,
        "timing": {"search_ms": elapsed, "render_ms": 0, "total_ms": elapsed},
    }


@app.get("/images/{path:path}")
def images(path: str) -> FileResponse:
    target = (IMAGES_ROOT / path).resolve()
    if not str(target).startswith(str(IMAGES_ROOT.resolve())) or not target.is_file():
        raise HTTPException(status_code=404, detail="no such image")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=604800"})
