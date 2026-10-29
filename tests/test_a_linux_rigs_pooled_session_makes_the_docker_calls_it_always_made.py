"""A Linux rig's pooled session makes the docker calls it always made.

The session layer reaches its machine through one host seam, and a rig that
runs its sessions in containers (every Linux rig, and any rig lending with the
docker launcher) takes the docker host. That host must ask the daemon for
exactly what the session asked before the seam existed: the same ``docker
run`` argv for the tunnel, the workers and the head, the same scripts with the
same arguments in the same order, and the same STUN probe and keep-alive.

The calls are pinned in ``fixtures/pooled_docker_calls.json``, recorded from
the session code before the seam: a worker with a STUN traversal and a tunnel,
a head with a local card and a worker's rpc device, and a head alone on one
card, each run to ready and stopped. Polls that repeat while a session waits
(a listening check, a handshake read, a transfer read) are kept once, in the
order first made, so the record is the calls and not how often the machine
let the session's thread run.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool

GOLDEN = Path(__file__).parent / "fixtures" / "pooled_docker_calls.json"
TOKEN = "00112233445566778899aabbccddeeff"
STUN = "203.0.113.9"
#: The polls whose arguments say how often the thread ran, not what it asked.
POLLED = ("PEERS_SCRIPT", "TRANSFER_SCRIPT", "LISTENING_SCRIPT")


def _script_name(script: str) -> str:
    from mcgyvr.rig import pooled

    for name in dir(pooled):
        if name.endswith("_SCRIPT") and getattr(pooled, name) is script:
            return name
    return "<other>"


def _scrub(word: str, tmp_path: Path) -> str:
    from mcgyvr.rig import pooled

    return (
        word.replace(str(pooled.SECCOMP_PROFILE), "<seccomp>")
        .replace(str(tmp_path), "<tmp>")
        .replace(f"={os.getpid()}", "=<agent>")
    )


def _calls(pool: Pool, tmp_path: Path) -> dict[str, Any]:
    """The daemon's record of one scenario, scrubbed of this run's paths."""
    docker = pool.docker
    runs = [
        [_scrub(word, tmp_path) for word in container.argv]
        for container in docker.containers_ever
    ]
    seen: list[list[str]] = []
    for name, script, args in docker.scripts:
        which = _script_name(script)
        one = [name, which, *(list(args) if which not in POLLED else [])]
        if one not in seen:
            seen.append(one)
    python = [[name, how, *args] for name, how, args in docker.python]
    verbs: list[list[str]] = []
    for verb, args in docker.calls:
        one = [verb, *args]
        if not verbs or verbs[-1] != one:
            verbs.append(one)
    return {"runs": runs, "scripts": seen, "python": python, "calls": verbs}


def _state(pool: Pool, session_id: str, state: str) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if pool.sessions.state_of(session_id)[0] == state:
            return
        time.sleep(0.005)
    raise AssertionError(f"{session_id} is {pool.sessions.state_of(session_id)}")


def _stop(pool: Pool) -> None:
    assert pool.ask("session_stop", "x1", session_id="s1") is not None
    _state(pool, "s1", "stopped")
    pool.settle()


def _worker(pool: Pool) -> None:
    traversal = {"token": TOKEN, "stun": [{"host": STUN, "port": 3478, "kind": "stun"}]}
    assert (
        pool.ask(
            "session_prepare", "p1", session_id="s1", role="worker", traversal=traversal
        )
        is None
    )
    pool.wait_for("session_prepared")
    pool.up("t1", **fakes.tunnel_up_body())
    ack = pool.ask(
        "worker_start", "w1", session_id="s1", cards=[{"card_index": 1, "port": 50053}]
    )
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "s1", "ready")
    _stop(pool)


def _head_with_worker(pool: Pool) -> None:
    assert pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
    pool.wait_for("session_prepared")
    pool.up("t1", **fakes.tunnel_up_body())
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        slots=2,
        devices=[
            {"kind": "rpc", "host": fakes.PEER, "port": 50052},
            {"kind": "local", "card_index": 0},
        ],
        tensor_split=[1, 3],
    )
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "s1", "ready")
    _stop(pool)


def _head_alone(pool: Pool) -> None:
    assert pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
    pool.wait_for("session_prepared")
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=2048,
        devices=[{"kind": "local", "card_index": 1}],
        tensor_split=[1],
    )
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "s1", "ready")
    _stop(pool)


SCENARIOS: dict[str, Callable[[Pool], None]] = {
    "worker": _worker,
    "head_with_worker": _head_with_worker,
    "head_alone": _head_alone,
}


def record(name: str, tmp_path: Path) -> dict[str, Any]:
    """Run one scenario on a fresh invented rig and return its scrubbed calls."""
    pool = make_pool(tmp_path)
    try:
        SCENARIOS[name](pool)
    finally:
        pool.sessions.close()
    return _calls(pool, tmp_path)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_a_docker_rigs_session_asks_the_daemon_what_it_always_asked(
    name: str, tmp_path: Path
) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert record(name, tmp_path) == golden[name]
