"""A Mac or Windows rig runs a pooled head through its helper, on the loopback alone.

A rig lending with ``launcher: native`` on macOS or Windows runs its sessions
through the ``mcgyvr-wg`` helper (here ``tests/fake_wg_helper.py``, which
speaks the helper's grammar): the helper prepares the session's key and
socket, brings the tunnel up, opens one forward per rpc device and starts the
pinned llama-server as its own child. The head listens on 127.0.0.1 alone
(pin K13) — an operator's ``LLAMA_ARG_HOST`` is not handed down — and reaches
each worker only through a forward that accepts the head's own pid and nothing
else. A worker is refused before anything starts: the helper serves no rpc
server yet. Stopping the session ends the head and the helper. Every frame is
checked against the hub's published schema.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import native_pool_fakes as native
from tests import rig_pool_fakes as fakes
from tests.native_pool_fakes import NativePool, make_native_pool


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[NativePool]:
    made = make_native_pool(tmp_path, monkeypatch)
    yield made
    made.pool.sessions.close()
    made.echo.close()


def _state(rig: NativePool, state: str, session_id: str = "s1") -> None:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if rig.pool.sessions.state_of(session_id)[0] == state:
            return
        time.sleep(0.01)
    found = rig.pool.sessions.state_of(session_id)
    raise AssertionError(f"{session_id} is {found}: {rig.pool.box.frames}")


def _prepare(rig: NativePool, role: str = "head") -> Any:
    return rig.pool.ask("session_prepare", "p1", session_id="s1", role=role)


def _head(rig: NativePool, *devices: dict[str, Any]) -> Any:
    return rig.pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        slots=2,
        devices=list(devices),
        tensor_split=[1] * len(devices),
    )


RPC = {"kind": "rpc", "host": native.RPC_DEVICE[0], "port": native.RPC_DEVICE[1]}
LOCAL_0 = {"kind": "local", "card_index": 0}


def _ready_with_worker(rig: NativePool) -> dict[str, Any]:
    assert _prepare(rig) is None
    rig.pool.wait_for("session_prepared")
    rig.pool.up("t1", **fakes.tunnel_up_body())
    ack = _head(rig, RPC, LOCAL_0)
    assert ack is not None and ack["type"] == "ack", ack
    _state(rig, "ready")
    return rig.head_said()


def test_a_prepared_native_head_says_the_helpers_key_and_the_sessions_port(
    rig: NativePool,
) -> None:
    assert _prepare(rig) is None
    rig.pool.wait_for("session_prepared")
    body = rig.pool.box.of_type("session_prepared")[0]["body"]
    assert body["public_key"] == "C" * 42 + "w="
    assert body["listen_port"] == 51820
    prepare = [r for r in rig.requests() if r.get("verb") == "prepare"]
    assert prepare == [
        {
            "id": 1,
            "verb": "prepare",
            "listen_port": 51820,
            "hosts": [fakes.LAN_ADDRESS],
            "lease_s": 60,
        }
    ]
    assert rig.pool.docker.calls == []  # no daemon is asked anything


def test_a_native_head_listens_on_the_loopback_and_reaches_its_worker_by_forward(
    rig: NativePool,
) -> None:
    said = _ready_with_worker(rig)
    argv = said["argv"]
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv.count("--host") == 1
    assert argv[argv.index("--port") + 1] == "18080"
    assert argv[argv.index("-m") + 1] == str(rig.tmp / "dense" / fakes.MODEL)
    assert argv[argv.index("-dev") + 1] == "RPC0,CUDA0"
    assert argv[argv.index("-np") + 1] == "2"
    assert argv[argv.index("-c") + 1] == "8192"
    (local,) = argv[argv.index("--rpc") + 1].split(",")
    assert local.startswith("127.0.0.1:")
    # the head reached the worker through the forward, and the forward through
    # the tunnel address the hub named
    assert said["rpc"] == {local: "echo:ping"}
    assert rig.echo.heard == [b"ping"]
    events = [r for r in rig.requests() if "event" in r]
    assert [e["event"] for e in events] == ["accepted"]
    forward = [r for r in rig.requests() if r.get("verb") == "forward"]
    assert [(f["part"], f["to"]) for f in forward] == [
        ("head", f"{native.RPC_DEVICE[0]}:{native.RPC_DEVICE[1]}")
    ]
    # the head's cards and its runtime's settings, and nothing of the agent's
    # own: no listening address of the operator's, no token
    assert "CUDA_VISIBLE_DEVICES" in said["env"]
    assert "GGML_SCHED_MAX_COPIES" in said["env"]
    assert "LLAMA_ARG_HOST" not in said["env"]
    assert "HF_TOKEN" not in said["env"]
    assert rig.pool.sessions.head_port("s1") == 18080
    verbs = rig.verbs()
    assert verbs[:2] == ["prepare", "up"]
    assert verbs.index("forward") < verbs.index("spawn")


def test_a_forward_refuses_a_process_that_is_not_the_head(rig: NativePool) -> None:
    said = _ready_with_worker(rig)
    local = said["argv"][said["argv"].index("--rpc") + 1]
    host, _, port = local.rpartition(":")
    with socket.create_connection((host, int(port)), timeout=5) as intruder:
        try:
            intruder.sendall(b"steal")
            intruder.shutdown(socket.SHUT_WR)
            answered = intruder.recv(64)
        except OSError:
            answered = b""
        assert answered == b""  # closed unanswered
    deadline = time.monotonic() + 5.0
    while not any(r.get("event") == "refused" for r in rig.requests()):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert rig.echo.heard == [b"ping"]  # only the head's own connection got through


def test_stopping_a_native_session_ends_its_head_and_its_helper(
    rig: NativePool,
) -> None:
    _ready_with_worker(rig)
    helper = rig.host._runs["s1"].helper
    assert rig.pool.ask("session_stop", "x1", session_id="s1") is not None
    _state(rig, "stopped")
    rig.pool.settle()
    assert not helper.alive()
    assert rig.verbs()[-2:] == ["kill", "teardown"]
    assert rig.host.owned() == []


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    with open(f"/proc/{pid}/stat", encoding="ascii") as stat:
        return stat.read().split(") ")[-1][0] != "Z"


def _recorded_pid(rig: NativePool, part: str) -> int:
    from mcgyvr.rig import pooled

    record = rig.tmp / "records" / f"{pooled.container_name('s1', part)}.json"
    pid: int = json.loads(record.read_text())["pid"]
    return pid


def test_a_head_outliving_a_helper_killed_outright_is_ended_by_its_record(
    rig: NativePool,
) -> None:
    _ready_with_worker(rig)
    head, helper = _recorded_pid(rig, "head"), _recorded_pid(rig, "tunnel")
    assert _alive(head)
    os.kill(helper, signal.SIGKILL)  # no teardown: the head is left behind
    rig.pool.wait_for("session_status", "failed")
    rig.pool.settle()
    deadline = time.monotonic() + 5.0
    while _alive(head):
        assert time.monotonic() < deadline, "the head outlived its session"
        time.sleep(0.01)
    assert list((rig.tmp / "records").glob("*.json")) == []


def test_a_sweep_ends_what_an_agent_that_died_left_recorded(
    rig: NativePool,
) -> None:
    import subprocess
    import sys

    from mcgyvr import hostos

    left = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
    )
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()  # an agent pid that is no more
    folder = rig.tmp / "records"
    folder.mkdir(mode=0o700, exist_ok=True)
    (folder / "mcgyvr-pool-000000000000-head.json").write_text(
        json.dumps(
            {
                "name": "mcgyvr-pool-000000000000-head",
                "session_id": "old",
                "agent_pid": gone.pid,
                "pid": left.pid,
                "start": hostos.process_start_time(left.pid),
                "program": sys.executable,
            }
        )
    )
    try:
        assert rig.pool.sessions.sweep() == ["mcgyvr-pool-000000000000-head"]
        assert left.wait(timeout=5) != 0
        assert list(folder.glob("*.json")) == []
    finally:
        if left.poll() is None:
            left.kill()
            left.wait()


def test_a_native_head_alone_needs_no_tunnel_and_no_forward(rig: NativePool) -> None:
    assert _prepare(rig) is None
    rig.pool.wait_for("session_prepared")
    ack = _head(rig, LOCAL_0)
    assert ack is not None and ack["type"] == "ack", ack
    _state(rig, "ready")
    said = rig.head_said()
    assert "--rpc" not in said["argv"]
    assert said["argv"][said["argv"].index("-dev") + 1] == "CUDA0"
    assert "up" not in rig.verbs() and "forward" not in rig.verbs()


@pytest.mark.parametrize("role", ["worker"])
def test_a_native_rig_refuses_a_worker_before_anything_starts(
    rig: NativePool, role: str
) -> None:
    refused = _prepare(rig, role)
    assert refused is not None and refused["type"] == "error"
    assert refused["body"]["code"] == "not_capable"
    assert "head role alone" in refused["body"]["message"]
    assert rig.requests() == []
    started = rig.pool.ask(
        "worker_start", "w1", session_id="s1", cards=[{"card_index": 0, "port": 50052}]
    )
    assert started is not None and started["body"]["code"] == "unknown_session"


def test_a_native_build_that_cannot_name_its_cards_refuses_a_local_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_native_pool(tmp_path, monkeypatch, backend="vulkan")
    try:
        assert _prepare(rig) is None
        rig.pool.wait_for("session_prepared")
        refused = _head(rig, LOCAL_0)
        assert refused is not None and refused["body"]["code"] == "not_capable"
        assert "spawn" not in rig.verbs()
    finally:
        rig.pool.sessions.close()
        rig.echo.close()


def test_a_helper_that_ends_fails_the_session_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_native_pool(tmp_path, monkeypatch, config={"faults": {"lease": "die"}})
    try:
        assert _prepare(rig) is None
        rig.pool.wait_for("session_prepared")
        rig.pool.wait_for("session_status", "failed")
        status = rig.pool.box.of_type("session_status")[-1]["body"]
        assert status["error_code"] == "tunnel_failed"
        assert "tunnel ended" in status["log_excerpt"]
    finally:
        rig.pool.sessions.close()
        rig.echo.close()


@pytest.mark.parametrize(
    ("config", "said"),
    [
        ({"version": "v9.9.9"}, "pins v0.1.0"),
        ({"proto": 2}, "proto 2"),
        ({"faults": {"prepare": "extra_key"}}, "does not read"),
        ({"faults": {"prepare": "wrong_id"}}, "another request"),
        ({"faults": {"prepare": "garbage"}}, "not JSON"),
    ],
)
def test_a_helper_not_speaking_the_pinned_grammar_fails_the_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: dict[str, Any],
    said: str,
) -> None:
    rig = make_native_pool(tmp_path, monkeypatch, config=config)
    try:
        assert _prepare(rig) is None
        rig.pool.wait_for("session_status", "failed")
        status = rig.pool.box.of_type("session_status")[-1]["body"]
        assert status["error_code"] == "tunnel_failed"
        assert said in status["log_excerpt"]
        rig.pool.settle()
        assert rig.host.owned() == []
    finally:
        rig.pool.sessions.close()
        rig.echo.close()


def test_a_linux_rig_lending_native_still_runs_its_sessions_in_containers(
    tmp_path: Path,
) -> None:
    pool = fakes.make_pool(tmp_path, launcher="native")
    try:
        assert pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
        pool.wait_for("session_prepared")
        assert pool.docker.runs() != []
    finally:
        pool.sessions.close()


def test_the_requests_the_agent_sends_are_the_helpers_grammar(rig: NativePool) -> None:
    """The fake refuses any request that is not exactly its verb's fields, or
    that comes out of order, so a session that reaches ready and stops sent
    nothing outside the grammar, with ids one greater each time."""
    _ready_with_worker(rig)
    assert rig.pool.ask("session_stop", "x1", session_id="s1") is not None
    _state(rig, "stopped")
    assert [r for r in rig.requests() if r.get("event") == "refusal"] == []
    ids = [r["id"] for r in rig.requests() if "verb" in r]
    assert ids == list(range(1, len(ids) + 1))


def test_a_native_rig_with_no_helper_pinned_for_it_refuses_a_head_unstarted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import wgpin

    rig = make_native_pool(tmp_path, monkeypatch)
    monkeypatch.setattr(wgpin, "pinned_here", lambda: False)
    try:
        refused = _prepare(rig, "head")
        assert refused is not None and refused["body"]["code"] == "not_capable"
        assert rig.requests() == []
        assert rig.pool.docker.calls == []
    finally:
        rig.pool.sessions.close()
        rig.echo.close()


def test_an_agent_with_no_native_host_refuses_a_native_rigs_head_unstarted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_native_pool(tmp_path, monkeypatch, with_host=False)
    try:
        refused = _prepare(rig, "head")
        assert refused is not None and refused["body"]["code"] == "not_capable"
        assert "no native sessions" in refused["body"]["message"]
        assert rig.requests() == []
        assert rig.pool.docker.calls == []
    finally:
        rig.pool.sessions.close()
        rig.echo.close()
