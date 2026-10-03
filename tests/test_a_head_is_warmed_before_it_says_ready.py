"""A head is warmed with one request of its own before it says ``ready``.

The first request a freshly started engine answers pays for everything the
engine does once per process (kernels compiled for this card on first use
among them), and pays it in the user's wait. So once the head's API says it
is loaded, the agent sends it one small chat completion of its own — a
prompt that fits the session's context, a few tokens out, nothing of any
user's — and says ``ready`` only after it is answered. The warm-up is not a
judge: an answer that is an error, or none within its time, still lets the
session be ready, while a head that dies during it fails the session. The
warm-up goes to the head's loopback API only, and its prompt fits the
smallest context a session may have.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool, prepared


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _head(pool: Pool, ctx: int = 4096) -> None:
    prepared(pool, role="head")
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    pool.up("t1", **body)
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=ctx,
        devices=[{"kind": "local", "card_index": 0}],
        tensor_split=[1],
    )
    assert ack is not None and ack["type"] == "ack"


def test_the_head_is_warmed_once_before_ready_is_said(pool: Pool) -> None:
    _head(pool, ctx=8192)
    pool.wait_for("session_status", "ready")
    assert pool.warmed == [(18080, 8192)]
    states = [f["body"]["state"] for f in pool.box.of_type("session_status")]
    assert states == ["loading", "ready"]


def test_a_warm_up_that_fails_still_lets_the_session_be_ready(pool: Pool) -> None:
    pool.warm_answers[:] = [False]
    _head(pool)
    pool.wait_for("session_status", "ready")
    assert pool.sessions.head_port("s1") == 18080


def test_a_head_that_dies_while_warming_fails_the_session(pool: Pool) -> None:
    from mcgyvr.sandbox import pooled

    def die(port: int, ctx: int) -> bool:
        name = pooled.container_name("s1", "head")
        with pool.docker.lock:
            pool.docker.containers[name].state = "exited"
        threading.Event().wait(1.0)
        return False

    pool.warm_with = die
    _head(pool)
    pool.wait_for("session_status", "failed")
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "start_failed"
    assert not [
        f for f in pool.box.of_type("session_status") if f["body"]["state"] == "ready"
    ]
    assert pool.docker.of_session("s1") == []


@pytest.fixture
def head_api() -> Iterator[tuple[int, list[tuple[str, dict[str, Any]]]]]:
    seen: list[tuple[str, dict[str, Any]]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            seen.append((self.path, json.loads(self.rfile.read(length))))
            body = b'{"choices": []}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1]), seen
    server.shutdown()
    server.server_close()


def test_the_warm_up_is_one_small_completion_on_loopback_that_fits_the_context(
    head_api: tuple[int, list[tuple[str, dict[str, Any]]]],
) -> None:
    from mcgyvr.rig import session, sessionwire

    port, seen = head_api
    assert session.warm_up(port, sessionwire.MIN_CTX, timeout=5.0)
    assert session.warm_up(port, 1 << 20, timeout=5.0)
    small, large = (body for _, body in seen)
    assert [path for path, _ in seen] == ["/v1/chat/completions"] * 2
    for body in (small, large):
        assert body["stream"] is False and body["max_tokens"] == session.WARM_UP_TOKENS
        (message,) = body["messages"]
        assert message["role"] == "user"
    words = len(small["messages"][0]["content"].split())
    assert words + session.WARM_UP_TOKENS < sessionwire.MIN_CTX // 2
    assert len(large["messages"][0]["content"].split()) == session.WARM_UP_WORDS


def test_a_warm_up_with_no_head_listening_is_false_not_a_raise() -> None:
    from mcgyvr.rig import session

    assert session.warm_up(session.free_port(), 4096, timeout=0.5) is False
