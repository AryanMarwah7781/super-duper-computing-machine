"""Serves the built UI, proxies manual images, and streams local video.

The UI addresses only 127.0.0.1. Image URLs therefore stay stable when the
devkit address changes, photos survive a reconnect without re-fetching, and the
fake devkit serves images through the identical path with no UI change.
"""
from __future__ import annotations

import hashlib
import http.server
import mimetypes
import os
import re
import socketserver
import threading
from pathlib import Path
from typing import Optional

import httpx

_IMAGE_PREFIX = "/images/"
_MEDIA_PREFIX = "/media/"
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
_CHUNK = 256 * 1024


def _content_type(name: str) -> str:
    """The manual's images are .jpeg; guess from the name as a fallback."""
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


class _Handler(http.server.SimpleHTTPRequestHandler):
    root: Path
    devkit_url: str
    cache_dir: Path
    media: dict

    def log_message(self, *args) -> None:  # quiet by default
        pass

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.startswith(_MEDIA_PREFIX):
            self._serve_media(self.path[len(_MEDIA_PREFIX):], body=False)
            return
        super().do_HEAD()

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.startswith(_IMAGE_PREFIX):
            self._serve_image(self.path[len(_IMAGE_PREFIX):])
            return
        if self.path.startswith(_MEDIA_PREFIX):
            self._serve_media(self.path[len(_MEDIA_PREFIX):])
            return
        rel = self.path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        # Browsers normalise ".." away; a hand-written request does not, and
        # `root / "../secrets"` is a real file. Anything that walks out of the
        # bundle gets the app, like any other unknown route.
        if not rel or ".." in rel.split("/") or not (self.root / rel).is_file():
            self.path = "/index.html"
        super().do_GET()

    # -- local video -------------------------------------------------------
    def _serve_media(self, name: str, body: bool = True) -> None:
        """Stream a registered local file, honouring Range.

        Range is not optional here. The starter recording is 220 MB with its
        `moov` atom at the end of the file, so a player has to fetch the tail
        before it can show a single frame; without 206 responses it downloads
        the whole thing first and seeking never works.

        Only files registered by name are reachable — the path never comes
        from the request, so nothing under the URL can escape into the disk.
        """
        path = self.media.get(name.split("?", 1)[0])
        if not path or not Path(path).is_file():
            self.send_error(404, "no such media")
            return
        size = os.path.getsize(path)
        content_type = _content_type(str(path))

        start, end = 0, size - 1
        match = _RANGE_RE.match(self.headers.get("Range") or "")
        partial = False
        if match:
            first, last = match.group(1), match.group(2)
            if first:
                start = min(int(first), size - 1)
                end = min(int(last), size - 1) if last else size - 1
            elif last:  # bytes=-500, the final 500 bytes
                start = max(size - int(last), 0)
            partial = True

        length = max(end - start + 1, 0)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not body:
            return
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # The player seeked, or the window closed mid-stream. Normal.
            pass

    def _serve_image(self, rel: str) -> None:
        rel = rel.split("?", 1)[0]
        key = hashlib.sha1(rel.encode("utf-8")).hexdigest()
        cached = self.cache_dir / key
        if cached.is_file():
            self._send_bytes(cached.read_bytes(), _content_type(rel))
            return
        try:
            r = httpx.get(f"{self.devkit_url}/images/{rel}", timeout=10.0)
            r.raise_for_status()
        except httpx.HTTPError:
            self.send_error(404, "image unavailable")
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(r.content)
        # Trust the devkit's content type when it gave one; the manual's images
        # are .jpeg, and an earlier version hardcoded image/png for everything.
        self._send_bytes(r.content,
                         r.headers.get("content-type") or _content_type(rel))

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path: str) -> str:
        rel = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        return str(self.root / rel)


class _ThreadingServer(socketserver.ThreadingTCPServer):
    daemon_threads = True   # a stalled stream must not hold up shutdown
    allow_reuse_address = True


class BundleServer:
    def __init__(self, root: Path, devkit_url: str, cache_dir: Path,
                 media: Optional[dict] = None) -> None:
        self.root = Path(root)
        self.devkit_url = devkit_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        # {url name: absolute path}. Videos live wherever they were recorded;
        # a 220 MB screen capture has no business inside the UI bundle.
        self.media = {name: Path(path) for name, path in (media or {}).items()}
        self._httpd: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> str:
        handler = type("BoundHandler", (_Handler,),
                       {"root": self.root, "devkit_url": self.devkit_url,
                        "cache_dir": self.cache_dir, "media": self.media})
        # Threaded, because a video stream holds its connection open for as
        # long as it plays and a single-threaded server would stall every
        # other request behind it.
        self._httpd = _ThreadingServer(("127.0.0.1", 0), handler)
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
