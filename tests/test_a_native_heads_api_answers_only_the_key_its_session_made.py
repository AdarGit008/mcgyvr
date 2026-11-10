"""A native head's API answers only the key its session made; a container's asks none.

A Mac or Windows rig's pooled head listens on 127.0.0.1, which every local
process reaches, so each native session makes a key of its own (256 bits, as
a unit's key is made) and the head asks it of every request but ``/health``
(llama-server's ``--api-key``, read from ``LLAMA_API_KEY``). The key goes in
the head's environment, never its argv, which any local user may list, and
into no record, log or frame. The agent's own requests to the head (its
health, its warm-up, every relayed request and the ``/slots`` page) carry it
as a bearer token. A head is not started natively without one. A Linux rig's
head runs in a container on the tunnel's own network and is started, asked and
relayed to exactly as before: no key. (HELPER-SPEC.md, section 6.)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import unitkey
from mcgyvr.rig import pooled, session, userwg, wghelper
from mcgyvr.serving import llamacpp
from mcgyvr.serving.llamacpp import LOOPBACK
from tests import native_pool_fakes as native
from tests import rig_pool_fakes as fakes
from tests.native_pool_fakes import NativePool, make_native_pool

KEY = "k" * 43


def _spec(**changes: Any) -> pooled.HeadSpec:
    fields: dict[str, Any] = {
        "session_id": "s1",
        "image": llamacpp.RUNTIME,
        "binary": "/app/llama-server",
        "gpus": (0,),
        "models_dir": Path("/models"),
        "model": "m.gguf",
        "name": "m.gguf",
        "ctx": 4096,
        "n_gpu_layers": 99,
        "devices": ("CUDA0",),
        "tensor_split": (1,),
        "rpc": (),
        "bind": LOOPBACK,
        "memory_mb": 8192,
    }
    return pooled.HeadSpec(**{**fields, **changes})


def _wait_ready(pool: fakes.Pool) -> None:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if pool.sessions.state_of("s1")[0] == "ready":
            return
        time.sleep(0.01)
    raise AssertionError(f"s1 is {pool.sessions.state_of('s1')}: {pool.box.frames}")


# --- a native session -------------------------------------------------------


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[NativePool]:
    made = make_native_pool(tmp_path, monkeypatch)
    yield made
    made.pool.sessions.close()
    made.echo.close()


def _ready(rig: NativePool) -> str:
    """Bring s1's native head to ready; the key its head was started with."""
    pool = rig.pool
    assert pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
    pool.wait_for("session_prepared")
    pool.up("t1", **fakes.tunnel_up_body())
    rpc = {"kind": "rpc", "host": native.RPC_DEVICE[0], "port": native.RPC_DEVICE[1]}
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[rpc, {"kind": "local", "card_index": 0}],
        tensor_split=[1, 1],
    )
    assert ack is not None and ack["type"] == "ack", ack
    _wait_ready(pool)
    (spawn,) = [r for r in rig.requests() if r.get("verb") == "spawn"]
    key: str = spawn["env"][unitkey.LLAMA_ENV]
    return key


def test_a_native_head_is_started_with_a_key_of_its_sessions_own_in_its_env(
    rig: NativePool,
) -> None:
    key = _ready(rig)
    assert unitkey.KEY.fullmatch(key)
    said = rig.head_said()
    assert unitkey.LLAMA_ENV in said["env"]
    assert not any(key in arg for arg in said["argv"])
    assert "--api-key" not in said["argv"]


def test_the_agent_asks_a_native_head_with_its_key_and_says_it_nowhere(
    rig: NativePool,
) -> None:
    key = _ready(rig)
    # its health and its warm-up were asked with it, and the relay is given it
    assert rig.pool.keys and {got for _, got in rig.pool.keys} == {key}
    assert ("warm", key) in rig.pool.keys
    assert rig.pool.sessions.head_key("s1") == key
    assert rig.pool.sessions.head_key("s2") is None
    # no frame to the hub, no process record and no log the agent keeps holds it
    assert key not in repr(rig.pool.box.frames)
    assert key not in "\n".join(rig.pool.logged)
    for kept in (rig.tmp / "records", rig.tmp / "logs"):
        for path in kept.rglob("*"):
            if path.is_file():
                assert key not in path.read_text(errors="replace"), path


def test_each_native_session_makes_a_key_of_its_own(tmp_path: Path) -> None:
    host = userwg.NativeHost(
        agent_pid=1,
        helper=lambda: ["/x"],
        engine=lambda: userwg.Engine(tmp_path / "llama-server", llamacpp.CUDA),
        records=lambda: tmp_path / "records",
    )
    one, two = host.head_key(), host.head_key()
    assert one and two and one != two
    assert unitkey.KEY.fullmatch(one) and unitkey.KEY.fullmatch(two)


def test_a_native_head_with_no_key_is_never_started(tmp_path: Path) -> None:
    host = userwg.NativeHost(
        agent_pid=1,
        helper=lambda: ["/x"],
        engine=lambda: userwg.Engine(tmp_path / "llama-server", llamacpp.CUDA),
        records=lambda: tmp_path / "records",
    )
    host._runs["s1"] = userwg._Run(
        session_id="s1",
        helper=wghelper.Helper(["/x"], log=tmp_path / "h.log"),
        api_port=18080,
    )
    with pytest.raises(pooled.PoolError, match="only with its session's key"):
        host.start_head(_spec())


def test_a_heads_key_is_in_no_repr_of_its_spec() -> None:
    assert KEY not in repr(_spec(api_key=KEY))


# --- a Linux session --------------------------------------------------------


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[fakes.Pool]:
    made = fakes.make_pool(tmp_path)
    yield made
    made.sessions.close()


def test_a_containers_head_is_started_and_asked_with_no_key(pool: fakes.Pool) -> None:
    fakes.prepared(pool, role="head")
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    pool.up("t1", **body)
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[{"kind": "local", "card_index": 0}],
        tensor_split=[1],
    )
    assert ack is not None and ack["type"] == "ack"
    _wait_ready(pool)
    assert pool.keys and {got for _, got in pool.keys} == {None}
    assert pool.sessions.head_key("s1") is None
    (head,) = [
        c
        for c in pool.docker.containers_ever
        if c.labels.get("mcgyvr.pool.part") == "head"
    ]
    assert not any(
        unitkey.LLAMA_ENV in word or "--api-key" in word for word in head.argv
    )


def test_a_container_head_spec_with_a_key_is_refused() -> None:
    owner = pooled.Owner(uid=1000, gid=1000, agent_pid=1)
    with pytest.raises(pooled.PoolError, match="no API key"):
        pooled.head_argv(_spec(api_key=KEY, bind="10.0.0.2"), owner)


# --- the requests themselves ------------------------------------------------


@pytest.fixture
def head_api() -> Iterator[tuple[int, list[tuple[str, str | None]]]]:
    seen: list[tuple[str, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self) -> None:
            seen.append((self.path, self.headers.get("Authorization")))
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self.answer()

        def do_POST(self) -> None:
            self.answer()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield int(server.server_address[1]), seen
    server.shutdown()
    server.server_close()


def test_the_health_and_the_warm_up_carry_the_key_as_a_bearer_token(
    head_api: tuple[int, list[tuple[str, str | None]]],
) -> None:
    port, seen = head_api
    assert session.head_health(port, KEY) == "ok"
    assert session.warm_up(port, 4096, KEY, timeout=5.0)
    assert session.head_health(port) == "ok"
    assert session.warm_up(port, 4096, timeout=5.0)
    assert seen == [
        ("/health", f"Bearer {KEY}"),
        ("/v1/chat/completions", f"Bearer {KEY}"),
        ("/health", None),
        ("/v1/chat/completions", None),
    ]
