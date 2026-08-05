from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tools.fake_devkit import make_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def client():
    return TestClient(make_app(FIXTURES))


def test_health_reports_ready(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ready"] is True
    assert r.json()["render_version"] == "v4.0"


def test_health_can_report_warming():
    c = TestClient(make_app(FIXTURES, ready=False))
    assert c.get("/health").json()["ready"] is False


@pytest.mark.parametrize("query,expected_kind", [
    ("how do i fill the tank", "cached"),
    ("what tire pressure", "cached"),
    ("what engine oil", "synthesize"),
    ("what is the weather", "oos"),
])
def test_ask_routes_by_keyword(client, query, expected_kind):
    r = client.post("/ask", json={"query": query})
    assert r.status_code == 200
    assert r.json()["plan"]["kind"] == expected_kind


def test_oos_returns_null_answer(client):
    r = client.post("/ask", json={"query": "what is the weather"})
    assert r.json()["answer"] is None


def test_images_return_a_png(client):
    r = client.get("/images/fill_cap.png")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")
