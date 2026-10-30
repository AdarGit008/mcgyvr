"""A release a test can fetch: archives served from this machine, pinned by sha256.

:func:`serving` answers ``GET /<name>`` for the files it is handed on a
loopback port, and :func:`release_of` pins them as a
:class:`mcgyvr.serving.release.Release` whose URLs point there.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import tarfile
import threading
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

import pytest

from mcgyvr.serving import release


def tar_gz(files: Mapping[str, bytes], *, top: str | None = "llama-b0") -> bytes:
    """A .tar.gz of `files`, under one `top` folder when given."""
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(body)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(body))
    return out.getvalue()


def zip_of(files: Mapping[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zipped:
        for name, body in files.items():
            zipped.writestr(name, body)
    return out.getvalue()


@contextmanager
def serving(files: Mapping[str, bytes]) -> Iterator[int]:
    """Serve `files` by name on a loopback port, for the block; yield the port."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = files.get(self.path.rsplit("/", 1)[-1])
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def release_of(
    monkeypatch: pytest.MonkeyPatch,
    port: int,
    files: Mapping[str, bytes],
    *,
    pinned: Mapping[str, str] | None = None,
) -> release.Release:
    """`files` pinned as a release served on `port`; `pinned` overrides a sha256."""
    monkeypatch.setattr(
        release, "DOWNLOAD_URL", f"http://127.0.0.1:{port}/{{repo}}/{{tag}}/{{name}}"
    )
    return release.Release(
        repo="example/tool",
        tag="v1",
        assets=tuple(
            release.Asset(
                name,
                len(body),
                (pinned or {}).get(name, hashlib.sha256(body).hexdigest()),
            )
            for name, body in files.items()
        ),
    )
