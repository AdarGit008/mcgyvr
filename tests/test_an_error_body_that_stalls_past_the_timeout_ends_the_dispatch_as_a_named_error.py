"""An error body that stalls past the timeout ends the dispatch as a named error.

A model server can send an error status and its headers, start its body, and
then send nothing more while keeping the connection open. The read of that
body times out. The dispatch must end as the runner's own error for an error
status, saying which status came back and that its body could not be read,
and why. It must not claim the body was empty, since part of it may have
arrived. It must never end as a raw timeout from the socket: the callers that
catch the runner's errors would miss it, and the failure would not be recorded
as a runner failure.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import BackendError, Request, runner_for

STATUS = 503
#: What the server sends of its error body before it stalls.
SENT = b'{"error": "busy'


@contextlib.contextmanager
def stalling() -> Iterator[str]:
    """A loopback server that sends part of an error body, then holds the rest.

    It holds until the test releases it, and the release is in ``finally``, so
    the server's thread ends whether the test's assertions pass or not.
    """
    release = threading.Event()

    class _Stall(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(STATUS)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(SENT) + 64))
            self.end_headers()
            self.wfile.write(SENT)
            self.wfile.flush()
            release.wait()
            self.close_connection = True

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Stall)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_an_error_body_that_stalls_is_a_backend_error_that_says_why() -> None:
    with stalling() as base_url:
        endpoint = Endpoint(
            source="local",
            base_url=base_url,
            protocol=Protocol.OPENAI,
            max_parallel=1,
            credential_env=None,
        )
        with pytest.raises(BackendError) as raised:
            runner_for(endpoint).generate(
                "m", Request(prompt="hi", max_output_tokens=16, timeout_s=0.5)
            )

    message = str(raised.value)
    assert f"HTTP {STATUS}" in message
    assert "its body could not be read" in message
    assert "TimeoutError" in message
    assert "empty body" not in message
