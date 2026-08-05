"""A stand-in for the devkit service, replaying recorded fixtures.

Exists so the entire desktop host and UI can be built and tested on Windows
with the devkit switched off. Keyword routing is crude on purpose: the point is
to exercise every `plan.kind` and every line form of the display grammar, not to
imitate retrieval.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

# A 1x1 transparent PNG, so <img> tags resolve in tests without binary fixtures.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

_ROUTES = [("tire", "table"), ("pressure", "table"),
           ("oil", "passage"), ("weather", "oos")]


class AskRequest(BaseModel):
    query: str
    top_k: int = 5


def _pick(query: str) -> str:
    low = query.lower()
    for needle, name in _ROUTES:
        if needle in low:
            return name
    return "procedure"


def make_app(fixtures_dir: Path, ready: bool = True) -> FastAPI:
    cache = {p.stem: json.loads(p.read_text(encoding="utf-8"))
             for p in Path(fixtures_dir).glob("*.json")}
    app = FastAPI(title="fake-devkit")

    @app.get("/ready")
    def ready_probe() -> dict:
        return {"alive": True}

    @app.get("/health")
    def health() -> dict:
        return {**cache["health"], "ready": ready}

    @app.post("/ask")
    def ask(req: AskRequest) -> dict:
        return cache[_pick(req.query)]

    @app.get("/images/{path:path}")
    def images(path: str) -> Response:
        return Response(content=_PNG, media_type="image/png")

    return app


def run(port: int = 8100, ready: bool = True) -> None:
    import uvicorn
    fixtures = Path(__file__).resolve().parent.parent / "fixtures"
    uvicorn.run(make_app(fixtures, ready), host="127.0.0.1", port=port)


if __name__ == "__main__":
    run()
