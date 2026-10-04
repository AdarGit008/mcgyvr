"""A pooled head serves as many requests at once as the hub gives it slots.

``head_start`` may carry ``slots``: how many requests the session's head
serves at once, a whole number of 1 to :data:`~mcgyvr.rig.sessionwire.MAX_SLOTS`,
1 when it is left out. ``ctx`` stays the context of *one* slot, so the head
is launched with ``-np <slots>`` and ``-c <slots * ctx>``, and each slot
gets its own share of the cache: never ``-kvu`` (a cache shared by every
slot fails each running request once it is full), and ``-np`` is always
given, since the engine unifies the cache when it picks the slot count
itself. The warm-up is one request, so it is sized to one slot's context.

The agent says it speaks this with the ``head_slots`` feature; the hub
sends more than one slot only to an agent that says so. The agent then
takes at most ``slots`` relays at once for the session's head, and answers
the next ``busy``. The hub orders ``devices`` so the head's own card comes
last (the last device holds the output layer), and the agent keeps that
order exactly: in ``-dev`` and in ``-ts``.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests import rig_schema
from tests.rig_pool_fakes import Pool, make_pool, prepared

BRIDGE_IP = fakes.BRIDGE.split("/")[0]


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _with_tunnel(pool: Pool) -> None:
    prepared(pool, role="head")
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    pool.up("t1", **body)


def _head_start(pool: Pool, **changes: Any) -> dict[str, Any] | None:
    body: dict[str, Any] = {
        "session_id": "s1",
        "model": {"name": fakes.MODEL},
        "ctx": 4096,
        "devices": [{"kind": "local", "card_index": 0}],
        "tensor_split": [1],
    }
    body.update(changes)
    return pool.ask("head_start", "h1", **body)


def _engine(pool: Pool) -> list[str]:
    """The model server's own argv: everything from its binary on."""
    from mcgyvr.rig import sharing
    from mcgyvr.sandbox import pooled

    argv = pool.docker.containers[pooled.container_name("s1", "head")].argv
    return argv[argv.index(sharing.DEFAULT_HEAD_BINARY) :]


def _expected(slots: int, ctx: int, dev: str = "CUDA0", ts: str = "1") -> list[str]:
    from mcgyvr.rig import sharing

    return [
        sharing.DEFAULT_HEAD_BINARY,
        "-m",
        f"/models/dense/{fakes.MODEL}",
        "-ngl",
        "999",
        "-sm",
        "layer",
        "-np",
        str(slots),
        "-c",
        str(slots * ctx),
        "-fa",
        "on",
        "-ctk",
        "q8_0",
        "-ctv",
        "q8_0",
        "--host",
        BRIDGE_IP,
        "--port",
        "8080",
        "-dev",
        dev,
        "-ts",
        ts,
    ]


# --- the field --------------------------------------------------------------------


def test_slots_is_one_when_the_hub_leaves_it_out(pool: Pool) -> None:
    prepared(pool, role="head")
    ack = _head_start(pool, ctx=8192)
    assert ack is not None and ack["type"] == "ack", ack
    pool.wait_for("session_status", "ready")
    assert _engine(pool) == _expected(1, 8192)
    assert pool.sessions.head_slots("s1") == 1


@pytest.mark.parametrize("slots", [1, 2, 16])
def test_slots_of_one_to_the_most_are_read(slots: int) -> None:
    from mcgyvr.rig import protocol, sessionwire

    assert sessionwire.MAX_SLOTS == 16
    envelope = protocol.decode(
        fakes.frame(
            "head_start",
            "h1",
            session_id="s1",
            model={"name": fakes.MODEL},
            ctx=4096,
            devices=[{"kind": "local", "card_index": 0}],
            tensor_split=[1],
            slots=slots,
        )
    )
    assert sessionwire.read_head_start(envelope).slots == slots


@pytest.mark.parametrize("bad", [0, -1, 17, 1 << 20, True, "2", 2.0, [2]])
def test_slots_out_of_bounds_or_not_a_whole_number_is_refused_and_starts_nothing(
    pool: Pool, bad: Any
) -> None:
    prepared(pool, role="head")
    answer = _head_start(pool, slots=bad)
    assert answer is not None and answer["type"] == "error", answer
    assert answer["body"]["code"] == "bad_message"
    assert "slots" in answer["body"]["message"]
    pool.settle()
    assert len(pool.docker.runs()) == 1  # the tunnel alone


# --- the launch -------------------------------------------------------------------


def _spec(slots: int, ctx: int) -> Any:
    from mcgyvr.sandbox import pooled

    return pooled.HeadSpec(
        session_id="s",
        image="engine:rpc",
        binary="/app/llama-server",
        gpus=(0,),
        models_dir=Path("/srv/models"),
        model="dense/model-q5.gguf",
        ctx=ctx,
        slots=slots,
        n_gpu_layers=99,
        devices=("RPC0", "CUDA0"),
        tensor_split=(5, 10),
        rpc=("198.51.100.1:50052",),
        bind="203.0.113.2",
        memory_mb=16384,
    )


@pytest.mark.parametrize("slots", [1, 2, 4])
def test_head_argv_gives_each_slot_its_own_context_and_never_a_shared_cache(
    slots: int,
) -> None:
    from mcgyvr.sandbox import pooled

    owner = pooled.Owner(uid=1000, gid=1000, agent_pid=4242)
    argv = pooled.head_argv(_spec(slots, 6144), owner)
    assert argv[argv.index("/app/llama-server") :] == [
        "/app/llama-server",
        "-m",
        "/models/dense/model-q5.gguf",
        "-ngl",
        "99",
        "-sm",
        "layer",
        "-np",
        str(slots),
        "-c",
        str(slots * 6144),
        "-fa",
        "on",
        "-ctk",
        "q8_0",
        "-ctv",
        "q8_0",
        "--host",
        "203.0.113.2",
        "--port",
        "8080",
        "--rpc",
        "198.51.100.1:50052",
        "-dev",
        "RPC0,CUDA0",
        "-ts",
        "5,10",
    ]
    for unified in ("-kvu", "--kv-unified", "-no-kvu", "--no-kv-unified"):
        assert unified not in argv


@pytest.mark.parametrize("slots", [1, 2, 4])
def test_a_head_started_with_slots_launches_that_many_and_warms_one_slots_context(
    pool: Pool, slots: int
) -> None:
    prepared(pool, role="head")
    ack = _head_start(pool, ctx=8192, slots=slots)
    assert ack is not None and ack["type"] == "ack", ack
    pool.wait_for("session_status", "ready")
    assert _engine(pool) == _expected(slots, 8192)
    assert pool.warmed == [(18080, 8192)]
    assert pool.sessions.head_slots("s1") == slots


def test_the_same_head_start_with_other_slots_is_refused(pool: Pool) -> None:
    prepared(pool, role="head")
    first = _head_start(pool, slots=2)
    assert first is not None and first["type"] == "ack"
    again = _head_start(pool, slots=2)
    assert again is not None and again["type"] == "ack"
    other = _head_start(pool, slots=3)
    assert other is not None and other["type"] == "error"
    assert other["body"]["code"] == "bad_message"
    pool.settle()


# --- the hub's device order -------------------------------------------------------


@pytest.mark.parametrize(
    ("devices", "dev", "ts"),
    [
        # the hub puts the head's own card last: it holds the output layer
        (
            [
                {"kind": "rpc", "host": fakes.SELF, "port": 50052},
                {"kind": "local", "card_index": 0},
            ],
            "RPC0,CUDA0",
            "7,3",
        ),
        (
            [
                {"kind": "local", "card_index": 1},
                {"kind": "rpc", "host": fakes.SELF, "port": 50052},
                {"kind": "local", "card_index": 0},
            ],
            "CUDA1,RPC0,CUDA0",
            "7,3,2",
        ),
    ],
)
def test_the_hubs_device_order_is_kept_exactly(
    pool: Pool, devices: list[dict[str, Any]], dev: str, ts: str
) -> None:
    from mcgyvr.sandbox import pooled

    _with_tunnel(pool)
    shares = [int(share) for share in ts.split(",")]
    ack = _head_start(pool, devices=devices, tensor_split=shares, slots=2)
    assert ack is not None and ack["type"] == "ack", ack
    pool.settle()
    argv = pool.docker.containers[pooled.container_name("s1", "head")].argv
    assert argv[argv.index("-dev") + 1] == dev
    assert argv[argv.index("-ts") + 1] == ts
    assert argv[argv.index("-np") + 1] == "2"


# --- the feature ------------------------------------------------------------------


def test_the_agent_says_it_speaks_head_slots(tmp_path: Path) -> None:
    from mcgyvr.rig import protocol, session

    assert "head_slots" in session.FEATURES
    on = session.offer(
        fakes.sharing(tmp_path), fakes.inventory(tmp_path), (fakes.LAN_ADDRESS,), ()
    )
    assert on is not None
    hello = json.loads(
        protocol.hello(
            "h",
            machine_id="m",
            agent_version="1",
            ram_total_mb=1,
            ram_free_mb=None,
            cards=(),
            offer=on,
        )
    )
    rig_schema.validate(hello, rig_schema.load(), "#/$defs/Hello")
    assert "head_slots" in hello["body"]["capabilities"]["features"]


# --- the relays -------------------------------------------------------------------


class _HeldHead:
    """A head's loopback API that holds every answer open until released."""

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
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                outer.release.wait(10.0)
                body = b'{"ok": true}'
                self.wfile.write(f"{len(body):x}\r\n".encode() + body + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])


class _Heads:
    def __init__(self, port: int, slots: int) -> None:
        self.port = port
        self.slots = slots

    def head_port(self, session_id: str) -> int | None:
        return self.port if session_id == "s1" else None

    def head_slots(self, session_id: str) -> int:
        return self.slots if session_id == "s1" else 1

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return ("ready", "head") if session_id == "s1" else ("absent", None)


def _ask(dispatcher: Any, box: fakes.Box, request_id: str) -> None:
    body = b"{}"
    reply = dispatcher.dispatch(
        fakes.frame(
            "relay_request",
            f"r-{request_id}",
            session_id="s1",
            request_id=request_id,
            endpoint="chat_completions",
            body_bytes=len(body),
            stream=False,
            timeout_s=10,
            max_response_bytes=1 << 20,
            window=8,
        ),
        fakes.Stub(),
    )
    if reply is not None:
        box.put(reply)
    reply = dispatcher.dispatch(
        fakes.frame(
            "relay_data",
            f"d-{request_id}",
            request_id=request_id,
            seq=0,
            data_b64=base64.b64encode(body).decode(),
        ),
        fakes.Stub(),
    )
    if reply is not None:
        box.put(reply)


def _end(box: fakes.Box, request_id: str, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in box.of_type("relay_end"):
            if frame["body"]["request_id"] == request_id:
                body: dict[str, Any] = frame["body"]
                return body
        time.sleep(0.005)
    raise AssertionError(f"no relay_end for {request_id} in {box.frames}")


def _wait_taken(head: _HeldHead, count: int) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with head.lock:
            if head.taken >= count:
                return
        time.sleep(0.005)
    raise AssertionError(f"the head took {head.taken} of {count}")


def test_a_head_of_two_slots_takes_two_relays_and_the_third_is_busy() -> None:
    from mcgyvr.rig import commands, relay

    head = _HeldHead()
    box = fakes.Box()
    relays = relay.Relays(heads=_Heads(head.port, slots=2), send=box.put)
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, relays)
    try:
        _ask(dispatcher, box, "q1")
        _ask(dispatcher, box, "q2")
        _wait_taken(head, 2)
        _ask(dispatcher, box, "q3")
        assert _end(box, "q3") == {
            "request_id": "q3",
            "outcome": "error",
            "error_code": "busy",
        }
        head.release.set()
        assert _end(box, "q1")["outcome"] == "complete"
        assert _end(box, "q2")["outcome"] == "complete"
        _ask(dispatcher, box, "q4")  # a slot is free again
        assert _end(box, "q4")["outcome"] == "complete"
        assert head.taken == 3
    finally:
        head.release.set()
        relays.cancel_all()
        head.server.shutdown()


def test_a_head_of_one_slot_takes_one_relay_at_a_time() -> None:
    from mcgyvr.rig import commands, relay

    head = _HeldHead()
    box = fakes.Box()
    relays = relay.Relays(heads=_Heads(head.port, slots=1), send=box.put)
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, relays)
    try:
        _ask(dispatcher, box, "q1")
        _wait_taken(head, 1)
        _ask(dispatcher, box, "q2")
        assert _end(box, "q2")["error_code"] == "busy"
        head.release.set()
        assert _end(box, "q1")["outcome"] == "complete"
    finally:
        head.release.set()
        relays.cancel_all()
        head.server.shutdown()


def test_the_rigs_own_bound_never_refuses_a_slot_the_head_has() -> None:
    from mcgyvr.rig import relay, sessionwire

    # The bound is each head's, so it never refuses a slot a head may have.
    assert relay.MAX_ACTIVE >= sessionwire.MAX_SLOTS
