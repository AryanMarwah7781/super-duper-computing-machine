import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from assist_desktop.bundle_server import BundleServer
from tools.fake_devkit import make_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="module")
def devkit_url():
    config = uvicorn.Config(make_app(FIXTURES), host="127.0.0.1", port=8125,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "fake devkit failed to start"
    yield "http://127.0.0.1:8125"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def served(tmp_path, devkit_url):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("<h1>assist</h1>", encoding="utf-8")
    server = BundleServer(root, devkit_url, cache_dir=tmp_path / "cache")
    base = server.start()
    yield base, tmp_path / "cache"
    server.stop()


def test_serves_index(served):
    base, _ = served
    assert "assist" in httpx.get(f"{base}/index.html").text


def test_unknown_path_falls_back_to_index(served):
    base, _ = served
    assert httpx.get(f"{base}/some/spa/route").status_code == 200


def test_proxies_images_from_the_devkit(served):
    base, _ = served
    r = httpx.get(f"{base}/images/fill_cap.png")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_caches_images_to_disk(served):
    base, cache = served
    httpx.get(f"{base}/images/fill_cap.png")
    assert list(cache.rglob("*")), "expected the image to be cached"


def test_missing_image_is_404_not_a_crash(tmp_path):
    root = tmp_path / "dist2"
    root.mkdir()
    (root / "index.html").write_text("<h1>x</h1>", encoding="utf-8")
    server = BundleServer(root, "http://127.0.0.1:9", cache_dir=tmp_path / "c2")
    base = server.start()
    try:
        assert httpx.get(f"{base}/images/nope.png").status_code == 404
    finally:
        server.stop()
