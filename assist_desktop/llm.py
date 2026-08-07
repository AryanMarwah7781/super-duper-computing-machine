"""Chris, the conversational half — Gemma 4 E2B on llama.cpp on the board.

Only greetings and small talk arrive here; machine questions go to retrieval.
See smalltalk.py for the fork, and prompts/soul.md for who Chris is.

Why llama.cpp rather than the board's own LLiMa stack: LLiMa runs the model on
the accelerator and is genuinely faster, but its OpenAI-compatible front-end
could never be made to reach its own model server -- 404 on every inference
route -- and the accelerator leaks memory on each load cycle. llama.cpp gives a
real /v1/chat/completions, on the CPU, for a workload that is a few sentences
at a time.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .logs import get as get_logger

log = get_logger("llm")

DEFAULT_LLM_URL = "http://192.168.94.180:8091/v1/chat/completions"
SOUL_PATH = Path(__file__).resolve().parent / "prompts" / "soul.md"

# Chris answers in one to three sentences. This is a backstop against a model
# that decides to write an essay, not a target.
MAX_TOKENS = 160


def llm_url() -> str:
    """Read at call time, so .env and a restart-free change both work. The
    trigger URL taught this lesson: a module constant is captured before
    config has loaded .env, and silently ignores it."""
    return os.environ.get("ASSIST_LLM_URL", DEFAULT_LLM_URL)


def llm_timeout_s() -> float:
    # Six tokens a second on 16 small ARM cores, and the very first request
    # after a restart also pays for the system prompt. Generous on purpose.
    return float(os.environ.get("ASSIST_LLM_TIMEOUT_S", "60"))


def soul() -> str:
    try:
        return SOUL_PATH.read_text(encoding="utf-8")
    except OSError as e:
        # Without the prompt Chris is a generic assistant that will happily
        # invent a torque figure. Refusing is the safe failure.
        log.error("cannot read soul.md: %s", e)
        return ""


# Used only when retrieval found nothing for a machine question.
#
# The manual is a procedure corpus: it says how to fold a boom and never says
# what one is. "What is a boom?" therefore died as out-of-scope in 69 ms, which
# is a bad answer to a fair question. The line drawn here is between concepts
# and quantities -- explaining what a part is cannot hurt anyone, while an
# invented torque figure or step order can.
FALLBACK_NOTE = (
    "The manual search found nothing for this question.\n"
    "You MAY explain, in general terms, what a part or piece of terminology "
    "means, and what it is for.\n"
    "You MUST NOT give any procedure, sequence of steps, menu path, torque, "
    "pressure, capacity, interval, setting or any other number. If the "
    "question needs one of those, say it is not in the manual section you "
    "have and stop.\n"
    "Begin your reply with the exact sentence: This isn't from the manual.\n"
    "Then give at most two sentences."
)


def explain(text: str) -> tuple[bool, str]:
    """A general explanation for a machine question the manual could not
    answer. Concepts only -- see FALLBACK_NOTE."""
    return chat(text, system_extra=FALLBACK_NOTE)


def chat(text: str, history: Optional[list[dict]] = None,
         system_extra: str = "") -> tuple[bool, str]:
    """Ask Chris. Returns (ok, reply-or-reason) and never raises."""
    persona = soul()
    if not persona:
        return False, "Chris is unavailable: the personality file is missing."

    prompt = persona if not system_extra else persona + "\n\n" + system_extra
    messages = [{"role": "system", "content": prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": text})

    import httpx
    try:
        r = httpx.post(llm_url(), timeout=llm_timeout_s(), json={
            "messages": messages,
            "max_tokens": MAX_TOKENS,
            "temperature": 0.7,
        })
        r.raise_for_status()
        data = r.json()
        reply = (data["choices"][0]["message"].get("content") or "").strip()
    except Exception as e:
        log.warning("chris unreachable: %s: %s", type(e).__name__, e)
        return False, f"{type(e).__name__}: {e}"

    if not reply:
        # Gemma 4 E2B is a reasoning model. With thinking left on it spends the
        # whole budget deliberating and returns empty content, so the server is
        # started with --reasoning off. An empty reply means that regressed.
        log.warning("chris returned nothing (reasoning left on?)")
        return False, "empty reply"

    log.info("chris: %r", reply[:80])
    return True, reply
