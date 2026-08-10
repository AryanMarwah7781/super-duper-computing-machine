"""Prove service.py's logic and response shape without a devkit.

service.py is the one file that cannot be exercised on Windows: it imports v4,
whose vector half is milvus-lite, which has no Windows build. That is exactly
why retrieval lives on the devkit — but it also means the file would otherwise
ship having never run.

So the v4 modules are stubbed and the real service module is imported against
them. This does NOT prove retrieval works. It proves that given plausible v4
output, service.py routes it, renders it, serialises it, and produces something
the client's wire models accept — which is the part that is ours to get wrong.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import time
import types
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assist_desktop.models.wire import Turn

SERVICE_PY = Path(__file__).resolve().parent.parent / "service" / "service.py"


@dataclass(frozen=True)
class FakePlan:
    kind: str
    chunk_ids: tuple = ()
    reason: str = ""


@dataclass(frozen=True)
class FakeAnswer:
    display_text: str
    spoken_segments: tuple = ()
    safety: tuple = ()
    citations: tuple = ()
    images: tuple = ()
    render_version: str = "v4.0"
    source_hash: str = "deadbeef"


PROCEDURE_CHUNK = {
    "chunk_id": 412,
    "content_type": "procedure",
    "procedure_name": "Fill Solution Tank",
    "page": 472,
    "rerank_score": 8.14,
    "steps": [{"step_num": 1, "text": "Park the machine."}],
}
CAUTION_CHUNK = {
    "chunk_id": 88,
    "content_type": "caution",
    "procedure_name": "Fill Solution Tank",
    "page": 472,
    "rerank_score": 2.01,
}


def _install_fake_v4(hits: list[dict], plan: FakePlan,
                     load_error: str | None = None,
                     hang_load: bool = False) -> None:
    """Put fake v4 modules in sys.modules before service.py imports them."""
    def _load():
        if load_error:
            raise RuntimeError(load_error)
        if hang_load:
            # Stand in for the real ~26s cold load, so the not-ready window can
            # be asserted without racing the warm-up thread.
            threading.Event().wait()
        return {"by_id": {c["chunk_id"]: c for c in hits}}

    search_mod = types.ModuleType("assist.retrieve.search")
    search_mod.search = lambda query, top_k=5: hits  # type: ignore[attr-defined]
    search_mod._load = _load  # type: ignore[attr-defined]

    retrieve_pkg = types.ModuleType("assist.retrieve")
    retrieve_pkg.search = search_mod  # type: ignore[attr-defined]

    route_mod = types.ModuleType("assist.answer.route")
    route_mod.route = lambda hits: plan  # type: ignore[attr-defined]

    render_mod = types.ModuleType("assist.answer.render")
    render_mod.render = lambda chunk: FakeAnswer(  # type: ignore[attr-defined]
        display_text=f"Step 1: {chunk['steps'][0]['text']}\n\n_Manual page "
                     f"{chunk['page']}._",
        spoken_segments=("Step 1. Park the machine.",),
    )

    # Passage questions ("what is boomtrac pro") have no procedure to render,
    # so the service asks the model for prose. It may decline, and then the
    # passage is served verbatim -- the None return exercises that fallback.
    synth_mod = types.ModuleType("assist.answer.synthesize")
    synth_mod.synthesize = lambda q, chunks: FakeAnswer(  # type: ignore[attr-defined]
        display_text="The BoomTrac Pro system controls boom tilt.",
        spoken_segments=("The BoomTrac Pro system controls boom tilt.",),
    )

    answer_pkg = types.ModuleType("assist.answer")
    answer_pkg.route = route_mod  # type: ignore[attr-defined]
    answer_pkg.render = render_mod  # type: ignore[attr-defined]
    answer_pkg.synthesize = synth_mod  # type: ignore[attr-defined]

    assist_pkg = types.ModuleType("assist")
    assist_pkg.retrieve = retrieve_pkg  # type: ignore[attr-defined]
    assist_pkg.answer = answer_pkg  # type: ignore[attr-defined]

    sys.modules.update({
        "assist": assist_pkg,
        "assist.retrieve": retrieve_pkg,
        "assist.retrieve.search": search_mod,
        "assist.answer": answer_pkg,
        "assist.answer.route": route_mod,
        "assist.answer.render": render_mod,
        "assist.answer.synthesize": synth_mod,
    })


def _load_service(hits: list[dict], plan: FakePlan,
                  load_error: str | None = None, hang_load: bool = False):
    for name in list(sys.modules):
        if name == "assist" or name.startswith("assist."):
            del sys.modules[name]
    if "deere_service" in sys.modules:
        del sys.modules["deere_service"]
    _install_fake_v4(hits, plan, load_error, hang_load)

    spec = importlib.util.spec_from_file_location("deere_service", SERVICE_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deere_service"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture
def service_procedure():
    plan = FakePlan(kind="cached", chunk_ids=(412,), reason="top=procedure score=8.14")
    module = _load_service([PROCEDURE_CHUNK, CAUTION_CHUNK], plan)
    module._state.update(ready=True, corpus_hash="abc12345", chunk_count=2995)
    return module


def test_health_matches_what_the_client_expects(service_procedure):
    with TestClient(service_procedure.app) as client:
        health = client.get("/health").json()
    assert health["render_version"] == "v4.0"
    assert health["ready"] is True
    assert isinstance(health["chunk_count"], int)


def test_ask_response_deserialises_into_the_client_wire_models(service_procedure):
    with TestClient(service_procedure.app) as client:
        payload = client.post("/ask", json={"query": "how do i fill the tank"}).json()

    turn = Turn.from_dict(payload)
    assert turn.plan.kind == "cached"
    assert turn.plan.chunk_ids == (412,)
    assert turn.answer is not None
    assert turn.answer.render_version == "v4.0"
    assert "Step 1:" in turn.answer.display_text


def test_candidates_carry_the_rerank_scores(service_procedure):
    with TestClient(service_procedure.app) as client:
        payload = client.post("/ask", json={"query": "anything"}).json()

    turn = Turn.from_dict(payload)
    assert [c.chunk_id for c in turn.candidates] == [412, 88]
    assert turn.candidates[0].score == 8.14
    assert turn.candidates[0].content_type == "procedure"


def test_timing_keys_are_the_ones_the_client_reads(service_procedure):
    with TestClient(service_procedure.app) as client:
        payload = client.post("/ask", json={"query": "anything"}).json()
    assert set(payload["timing"]) == {"search_ms", "render_ms", "total_ms"}


def test_out_of_scope_returns_a_null_answer():
    plan = FakePlan(kind="oos", chunk_ids=(), reason="best of 5 candidates -3.63 < 0.0")
    module = _load_service([PROCEDURE_CHUNK], plan)
    module._state.update(ready=True)
    with TestClient(module.app) as client:
        payload = client.post("/ask", json={"query": "what is the weather"}).json()

    turn = Turn.from_dict(payload)
    assert turn.plan.kind == "oos"
    assert turn.answer is None, "oos must not invent an answer"


def test_asking_before_the_index_is_loaded_is_503_not_a_wrong_answer():
    plan = FakePlan(kind="cached", chunk_ids=(412,))
    module = _load_service([PROCEDURE_CHUNK], plan, hang_load=True)
    with TestClient(module.app) as client:
        assert client.get("/ready").status_code == 200, "port answers immediately"
        assert client.get("/health").json()["ready"] is False
        assert client.post("/ask", json={"query": "anything"}).status_code == 503


def test_a_warmup_failure_is_reported_rather_than_swallowed():
    """A held milvus lock is the failure most likely in practice — a stray
    ask.py. It must name itself, not present as a generic outage."""
    plan = FakePlan(kind="cached", chunk_ids=(412,))
    module = _load_service([PROCEDURE_CHUNK], plan,
                           load_error="DataDirLockedError: index is held")
    with TestClient(module.app) as client:
        for _ in range(50):
            if module._state["error"]:
                break
            time.sleep(0.02)
        assert "DataDirLockedError" in client.get("/health").json()["error"]
        assert client.get("/health").json()["ready"] is False
        assert "DataDirLockedError" in client.post(
            "/ask", json={"query": "x"}).json()["detail"]


def test_an_unreadable_chunks_file_does_not_brick_a_loaded_index():
    """The corpus hash is cosmetic. V4_ROOT does not exist on this machine, so
    reading it fails — the service must still come ready."""
    plan = FakePlan(kind="cached", chunk_ids=(412,))
    module = _load_service([PROCEDURE_CHUNK], plan)
    with TestClient(module.app) as client:
        for _ in range(100):
            if module._state["ready"]:
                break
            time.sleep(0.02)
        health = client.get("/health").json()
    assert health["ready"] is True, "a missing chunks.json must not block serving"
    assert health["corpus_hash"] == ""
    assert health["chunk_count"] == 1


def test_image_path_traversal_is_refused(service_procedure):
    with TestClient(service_procedure.app) as client:
        assert client.get("/images/../../etc/passwd").status_code == 404


# -- passage questions get prose, not a raw passage ------------------------

def test_a_synthesize_plan_synthesizes_rather_than_rendering():
    """v3 answered "what is boomtrac pro" with "I don't know" -- it has no
    procedure to render and the corpus has no glossary. v4 routes it to
    synthesize, and the service must honour that: rendering the passage chunk
    instead would serve raw manual text where prose was asked for."""
    plan = FakePlan(kind="synthesize", chunk_ids=(412,),
                    reason="prose synthesis from passage score=6.88")
    module = _load_service([PROCEDURE_CHUNK], plan)
    with TestClient(module.app) as client:
        payload = client.post("/ask", json={"query": "what is boomtrac pro"}).json()
    assert payload["plan"]["kind"] == "synthesize"
    assert "BoomTrac Pro system" in payload["answer"]["display_text"]
    assert "Step 1" not in payload["answer"]["display_text"], "not the renderer"


def test_a_declining_model_falls_back_to_the_passage(monkeypatch):
    """synthesize returns None when the model declines or is unreachable. The
    passage is then served verbatim: unhelpful, but never invented."""
    import sys
    plan = FakePlan(kind="synthesize", chunk_ids=(412,), reason="prose synthesis")
    module = _load_service([PROCEDURE_CHUNK], plan)
    sys.modules["assist.answer.synthesize"].synthesize = lambda q, chunks: None
    module.synthesize = lambda q, chunks: None
    with TestClient(module.app) as client:
        payload = client.post("/ask", json={"query": "what is boomtrac pro"}).json()
    assert payload["answer"] is not None, "must fall back, not fail"
    assert "Step 1" in payload["answer"]["display_text"], "the passage verbatim"


def test_a_bare_image_filename_is_served(tmp_path, monkeypatch):
    """`Image.image_path` is a bare filename, so IMAGES_ROOT must be the
    directory that holds the files. It was rooted one level up at .../static
    while the figures live in .../static/images, and every answer rendered
    with its text but no pictures."""
    plan = FakePlan(kind="cached", chunk_ids=(412,))
    module = _load_service([PROCEDURE_CHUNK], plan)
    (tmp_path / "fig.jpeg").write_bytes(b"\xff\xd8\xff\xe0jpeg")
    module.IMAGES_ROOT = tmp_path
    with TestClient(module.app) as client:
        assert client.get("/images/fig.jpeg").status_code == 200
