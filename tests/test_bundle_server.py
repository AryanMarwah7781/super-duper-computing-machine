import socket
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


def test_jpeg_is_not_served_as_png(served):
    """The manual's images are .jpeg. An earlier version hardcoded image/png
    for every image, which browsers sniff around but is still wrong."""
    base, _ = served
    r = httpx.get(f"{base}/images/OMKK60066.pdf_p100_img0_d23880d0.jpeg")
    assert r.status_code == 200
    assert "png" not in r.headers["content-type"]


def test_cached_image_keeps_its_content_type(served):
    """Second fetch is served from disk and must not lose the type."""
    base, _ = served
    url = f"{base}/images/OMKK60066.pdf_p101_img0_c361b0ef.jpeg"
    first = httpx.get(url)
    second = httpx.get(url)
    assert second.status_code == 200
    assert second.headers["content-type"] == first.headers["content-type"]
    assert "png" not in second.headers["content-type"]


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


# -- the starter video -----------------------------------------------------

@pytest.fixture
def with_video(tmp_path, devkit_url):
    root = tmp_path / "dist3"
    root.mkdir()
    (root / "index.html").write_text("<h1>x</h1>", encoding="utf-8")
    video = tmp_path / "starter.mp4"
    video.write_bytes(bytes(range(256)) * 40)          # 10 240 bytes
    server = BundleServer(root, devkit_url, cache_dir=tmp_path / "c3",
                          media={"starter.mp4": video})
    base = server.start()
    yield base, video
    server.stop()


def test_serves_the_starter_video(with_video):
    base, video = with_video
    r = httpx.get(f"{base}/media/starter.mp4")
    assert r.status_code == 200
    assert r.content == video.read_bytes()
    assert r.headers["content-type"] == "video/mp4"
    assert r.headers["accept-ranges"] == "bytes"


def test_a_range_request_gets_exactly_that_range(with_video):
    """The recording is 220 MB with its moov atom at the end. Without 206s a
    player downloads the whole file before it can show a frame."""
    base, video = with_video
    r = httpx.get(f"{base}/media/starter.mp4", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 100-199/10240"
    assert r.content == video.read_bytes()[100:200]


def test_a_player_can_ask_for_the_tail(with_video):
    base, video = with_video
    r = httpx.get(f"{base}/media/starter.mp4", headers={"Range": "bytes=-64"})
    assert r.status_code == 206
    assert r.content == video.read_bytes()[-64:]


def test_an_open_ended_range_runs_to_the_end(with_video):
    base, video = with_video
    r = httpx.get(f"{base}/media/starter.mp4", headers={"Range": "bytes=10000-"})
    assert r.status_code == 206
    assert r.content == video.read_bytes()[10000:]


def test_the_url_cannot_reach_anything_that_was_not_registered(with_video):
    base, _ = with_video
    assert httpx.get(f"{base}/media/other.mp4").status_code == 404


def test_a_raw_request_cannot_climb_out_of_the_bundle(with_video, tmp_path):
    """httpx normalises "..", a hand-written request does not, and the file it
    would reach is real."""
    (tmp_path / "secret.txt").write_text("keep me", encoding="utf-8")
    base, _ = with_video
    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=5) as sock:
        sock.sendall(b"GET /dist3/../secret.txt HTTP/1.1\r\nHost: x\r\n"
                     b"Connection: close\r\n\r\n")
        body = b""
        while chunk := sock.recv(4096):
            body += chunk
    assert b"keep me" not in body


def test_a_missing_video_is_404_rather_than_a_broken_player(tmp_path, devkit_url):
    root = tmp_path / "dist4"
    root.mkdir()
    (root / "index.html").write_text("<h1>x</h1>", encoding="utf-8")
    server = BundleServer(root, devkit_url, cache_dir=tmp_path / "c4",
                          media={"starter.mp4": tmp_path / "absent.mp4"})
    base = server.start()
    try:
        assert httpx.get(f"{base}/media/starter.mp4").status_code == 404
    finally:
        server.stop()
