"""Experiment: does giving Chris the manual's own text beat letting him recall?

v3 answers procedures only. "What is AutoTrac" has no procedure to match, so it
comes back out-of-scope and Chris answers from whatever a 2B model remembers
about John Deere guidance systems -- which is exactly the kind of plausible,
unverifiable answer this project exists to avoid.

But the chunks are there. 109 of them mention AutoTrac. They are simply never
rendered, because they are not procedures. This asks the same question twice --
once with nothing, once with those chunks pasted in -- and prints both so the
difference can be judged rather than assumed.

Deliberately does not touch the board's index: milvus-lite is single-process and
the service holds the lock. Retrieval here is plain keyword scoring over
chunks.json, which is enough to test the premise.

    python tools/grounded.py "what is autotrac"
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
CHUNKS = ROOT / "archive" / "jd-chatbot-v3" / "data" / "chunks.json"
FALLBACK_CHUNKS = ROOT / "rag-v4-min" / "chunks.json"
LLM = "http://192.168.94.180:8091/v1/chat/completions"
SOUL = (Path(__file__).resolve().parent.parent / "assist_desktop" / "prompts"
        / "soul.md")

STOP = {"what", "is", "a", "an", "the", "how", "do", "i", "of", "to", "on",
        "in", "for", "does", "it", "and", "my", "me", "with"}


def load_chunks() -> list[dict]:
    path = CHUNKS if CHUNKS.is_file() else FALLBACK_CHUNKS
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else list(data.values())
    print(f"corpus: {path.name}, {len(rows)} chunks\n")
    return rows


def find(rows: list[dict], query: str, k: int = 3) -> list[dict]:
    """Keyword scoring. Crude on purpose -- the point is to test what grounding
    does for the answer, not to reimplement the retriever."""
    terms = [t for t in re.findall(r"\w+", query.lower()) if t not in STOP]
    scored = []
    for c in rows:
        text = (str(c.get("procedure_name") or "") + " " +
                str(c.get("text") or "")).lower()
        score = sum(text.count(t) for t in terms)
        # A term in the title says far more than a mention buried in a step.
        title = str(c.get("procedure_name") or "").lower()
        score += 5 * sum(title.count(t) for t in terms)
        if score:
            scored.append((score, c))
    scored.sort(key=lambda p: -p[0])
    return [c for _, c in scored[:k]]


def ask(question: str, context: str = "") -> tuple[str, float]:
    persona = SOUL.read_text(encoding="utf-8")
    if context:
        persona += (
            "\n\nBelow are excerpts from the operator's manual. Answer using "
            "ONLY these excerpts. Explain in at most three sentences. If they "
            "do not contain the answer, say so.\n\n--- MANUAL EXCERPTS ---\n"
            + context)
    else:
        persona += ("\n\nThe manual search found nothing. You may explain what "
                    "a term means in general. Give no numbers or procedures.")
    t0 = time.time()
    r = httpx.post(LLM, timeout=300, json={
        "messages": [{"role": "system", "content": persona},
                     {"role": "user", "content": question}],
        "max_tokens": 200, "temperature": 0.3,
    })
    r.raise_for_status()
    reply = (r.json()["choices"][0]["message"].get("content") or "").strip()
    return reply, time.time() - t0


def main() -> None:
    question = " ".join(sys.argv[1:]) or "what is autotrac"
    rows = load_chunks()
    hits = find(rows, question)

    print(f'QUESTION: "{question}"')
    print("=" * 74)
    print(f"\nRetrieved {len(hits)} chunks by keyword:")
    for c in hits:
        print(f"  [{c.get('chunk_id')}] p{c.get('page')} "
              f"{c.get('content_type')} - {str(c.get('procedure_name'))[:60]}")

    context = "\n\n".join(
        f"[chunk {c.get('chunk_id')}, page {c.get('page')}] "
        f"{c.get('procedure_name')}\n{str(c.get('text'))[:1200]}" for c in hits)

    print("\n" + "-" * 74)
    print("A. WITHOUT the manual (what the app does today)")
    print("-" * 74)
    reply, secs = ask(question)
    print(f"{reply}\n   ({secs:.1f}s)")

    print("\n" + "-" * 74)
    print("B. WITH the manual excerpts")
    print("-" * 74)
    reply, secs = ask(question, context)
    print(f"{reply}\n   ({secs:.1f}s)")


if __name__ == "__main__":
    main()
