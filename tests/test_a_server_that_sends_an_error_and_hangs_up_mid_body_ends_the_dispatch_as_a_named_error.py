"""A server that sends an error and hangs up mid-body ends as a named error.

A model server that fails can fail twice in one reply: it sends an error
status, promises a body of some length, and closes the connection before the
body is all there. The dispatch must end as the runner's own error for an
error status, saying which status came back, that the server hung up before
its body was complete, and whatever part of the body did arrive. It must never
end as a raw exception from the HTTP library, which no caller up the ladder
knows to catch.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.runner import BackendError, Request, runner_for

#: What the server sends of its error body before it hangs up.
SENT = b'{"error": "the model ran out of'
#: What it says the error body will be; more than it sends.
PROMISED = len(SENT) + 64
STATUS = 500


class _ErrorThenHangUp(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(STATUS)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(PROMISED))
        self.end_headers()
        self.wfile.write(SENT)
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *_: Any) -> None:
        return


@contextlib.contextmanager
def error_then_hang_up() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _ErrorThenHangUp)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_an_error_status_cut_short_is_a_backend_error_that_says_what_happened() -> None:
    with error_then_hang_up() as base_url:
        endpoint = Endpoint(
            source="local",
            base_url=base_url,
            protocol=Protocol.OPENAI,
            max_parallel=1,
            credential_env=None,
        )
        with pytest.raises(BackendError) as raised:
            runner_for(endpoint).generate(
                "m", Request(prompt="hi", max_output_tokens=16)
            )

    message = str(raised.value)
    assert f"HTTP {STATUS}" in message
    assert "hung up" in message
    assert SENT.decode() in message
