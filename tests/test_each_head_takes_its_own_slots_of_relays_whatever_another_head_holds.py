"""Each head on a rig takes its own slots of relays, whatever another head holds.

A rig in several sessions at once may serve several heads, each started with
its own ``slots``. The agent takes at most ``slots`` relays at once for a
session's head and answers the next ``busy``; :data:`mcgyvr.rig.relay.MAX_ACTIVE`
is a safety net under each head's own bound, and under the rides to the
host's shared units together, never one bound for the whole rig: a head whose
slots are free is never refused because another head is full.
"""

from __future__ import annotations

import base64
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes


class _Head:
    """A head's API that holds every request until released."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.taken = 0
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                with outer.lock:
                    outer.taken += 1
                outer.release.wait(10.0)
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def wait_taken(self, count: int) -> None:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self.lock:
                if self.taken >= count:
                    return
            time.sleep(0.005)
        raise AssertionError(f"the head took {self.taken} of {count}")


class _Heads:
    """Two ready heads of this rig, by session id."""

    def __init__(self, heads: dict[str, tuple[_Head, int]]) -> None:
        self.heads = heads

    def head_port(self, session_id: str) -> int | None:
        found = self.heads.get(session_id)
        return found[0].port if found else None

    def head_slots(self, session_id: str) -> int:
        found = self.heads.get(session_id)
        return found[1] if found else 1

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return ("ready", "head") if session_id in self.heads else ("absent", None)


class _Rig:
    def __init__(self, slots: dict[str, int], max_active: int) -> None:
        from mcgyvr.rig import commands, relay

        self.heads = {sid: _Head() for sid in slots}
        self.box = fakes.Box()
        self.relays = relay.Relays(
            heads=_Heads({sid: (self.heads[sid], n) for sid, n in slots.items()}),
            send=self.box.put,
            max_active=max_active,
        )
        self.dispatcher = commands.Dispatcher()
        relay.register(self.dispatcher, self.relays)

    def ask(self, session_id: str, request_id: str) -> None:
        body = b"{}"
        for frame in (
            fakes.frame(
                "relay_request",
                f"r-{request_id}",
                session_id=session_id,
                request_id=request_id,
                endpoint="chat_completions",
                body_bytes=len(body),
                stream=False,
                timeout_s=10,
                max_response_bytes=1 << 20,
                window=8,
            ),
            fakes.frame(
                "relay_data",
                f"d-{request_id}",
                request_id=request_id,
                seq=0,
                data_b64=base64.b64encode(body).decode(),
            ),
        ):
            reply = self.dispatcher.dispatch(frame, fakes.Stub())
            if reply is not None:
                self.box.put(reply)

    def end(self, request_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            for frame in self.box.of_type("relay_end"):
                if frame["body"]["request_id"] == request_id:
                    body: dict[str, Any] = frame["body"]
                    return body
            time.sleep(0.005)
        raise AssertionError(f"no relay_end for {request_id} in {self.box.frames}")

    def close(self) -> None:
        for head in self.heads.values():
            head.release.set()
        self.relays.cancel_all()
        for head in self.heads.values():
            head.server.shutdown()


@pytest.fixture
def rig() -> Iterator[_Rig]:
    made = _Rig({"s1": 2, "s2": 2}, max_active=2)
    yield made
    made.close()


def test_a_head_with_free_slots_takes_a_relay_while_another_head_is_full(
    rig: _Rig,
) -> None:
    rig.ask("s1", "q1")
    rig.ask("s1", "q2")
    rig.heads["s1"].wait_taken(2)
    rig.ask("s2", "q3")
    rig.heads["s2"].wait_taken(1)
    rig.ask("s2", "q4")
    rig.heads["s2"].wait_taken(2)
    rig.heads["s2"].release.set()
    assert rig.end("q3")["outcome"] == "complete"
    assert rig.end("q4")["outcome"] == "complete"


def test_a_full_head_is_still_busy(rig: _Rig) -> None:
    rig.ask("s1", "q1")
    rig.ask("s1", "q2")
    rig.heads["s1"].wait_taken(2)
    rig.ask("s1", "q3")
    assert rig.end("q3") == {
        "request_id": "q3",
        "outcome": "error",
        "error_code": "busy",
    }


def test_the_safety_net_bounds_each_head_below_its_slots() -> None:
    made = _Rig({"s1": 4}, max_active=2)
    try:
        made.ask("s1", "q1")
        made.ask("s1", "q2")
        made.heads["s1"].wait_taken(2)
        made.ask("s1", "q3")
        assert made.end("q3")["error_code"] == "busy"
    finally:
        made.close()


def test_the_safety_net_is_never_below_a_heads_most_slots() -> None:
    from mcgyvr.rig import relay, sessionwire

    assert relay.MAX_ACTIVE >= sessionwire.MAX_SLOTS
