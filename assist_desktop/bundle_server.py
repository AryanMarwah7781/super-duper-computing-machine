"""Serves the built UI and proxies manual images.

The UI addresses only 127.0.0.1. Image URLs therefore stay stable when the
devkit address changes, photos survive a reconnect without re-fetching, and the
fake devkit serves images through the identical path with no UI change.
"""
from __future__ import annotations

import hashlib
import http.server
import socketserver
import threading
from pathlib import Path
from typing import Optional

import httpx

_IMAGE_PREFIX = "/images/"


class _Handler(http.server.SimpleHTTPRequestHandler):
    root: Path
    devkit_url: str
    cache_dir: Path

    def log_message(self, *args) -> None:  # quiet by default
        pass

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.startswith(_IMAGE_PREFIX):
            self._serve_image(self.path[len(_IMAGE_PREFIX):])
            return
        rel = self.path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if not rel or not (self.root / rel).is_file():
            self.path = "/index.html"
        super().do_GET()

    def _serve_image(self, rel: str) -> None:
        rel = rel.split("?", 1)[0]
        key = hashlib.sha1(rel.encode("utf-8")).hexdigest()
        cached = self.cache_dir / key
        if cached.is_file():
            self._send_bytes(cached.read_bytes())
            return
        try:
            r = httpx.get(f"{self.devkit_url}/images/{rel}", timeout=10.0)
            r.raise_for_status()
        except httpx.HTTPError:
            self.send_error(404, "image unavailable")
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(r.content)
        self._send_bytes(r.content)

    def _send_bytes(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path: str) -> str:
        rel = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        return str(self.root / rel)


class BundleServer:
    def __init__(self, root: Path, devkit_url: str, cache_dir: Path) -> None:
        self.root = Path(root)
        self.devkit_url = devkit_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self._httpd: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> str:
        handler = type("BoundHandler", (_Handler,),
                       {"root": self.root, "devkit_url": self.devkit_url,
                        "cache_dir": self.cache_dir})
        self._httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=2)
