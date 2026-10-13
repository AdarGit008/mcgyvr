"""The tensor cache a worker session mounts."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool


def _fnv1a_64(data: bytes) -> int:
    """The engine's ``fnv_hash``, written out here as the test's own oracle."""
    value = 0xCBF29CE484222325
    for byte in data:
        value = ((value ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return value


def _put(folder: Path, content: bytes, *, torn: bool = False) -> Path:
    """A file as the engine writes it: named by the whole content's hash;
    ``torn`` keeps only its first part, as a worker killed mid-write does."""
    engine = folder / "rpc"
    engine.mkdir(parents=True, exist_ok=True)
    path = engine / f"{_fnv1a_64(content):016x}"
    path.write_bytes(content[: len(content) // 3] if torn else content)
    return path


def _state(pool: Pool, session_id: str, state: str) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if pool.sessions.state_of(session_id)[0] == state:
            return
        time.sleep(0.005)
    raise AssertionError(f"{session_id} is {pool.sessions.state_of(session_id)}")


def _worker(pool: Pool, session_id: str, card: int) -> list[str]:
    """A worker session on ``card``, ready; its worker's ``docker run``."""
    from mcgyvr.rig import pooled

    assert (
        pool.ask(
            "session_prepare", f"p-{session_id}", session_id=session_id, role="worker"
        )
        is None
    )
    deadline = time.monotonic() + 5.0
    prepared: Any = None
    while prepared is None and time.monotonic() < deadline:
        for frame in pool.box.of_type("session_prepared"):
            if frame.get("re") == f"p-{session_id}":
                prepared = frame
        time.sleep(0.005)
    assert prepared is not None, pool.box.frames
    pool.up(
        f"t-{session_id}",
        **fakes.tunnel_up_body(
            session_id=session_id, listen_port=prepared["body"]["listen_port"]
        ),
    )
    ack = pool.ask(
        "worker_start",
        f"w-{session_id}",
        session_id=session_id,
        cards=[{"card_index": card, "port": 50052 + card}],
    )
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, session_id, "ready")
    name = pooled.container_name(session_id, f"worker-{card}")
    return pool.docker.containers[name].argv


def _cached(argv: list[str], folder: Path) -> bool:
    """Whether this worker mounts ``folder`` and runs its server with ``-c``;
    a half of one without the other fails the test."""
    from mcgyvr.rig import pooled

    mounted = f"{folder}:{pooled.CACHE_MOUNT}:rw" in argv
    told = f"LLAMA_CACHE={pooled.CACHE_MOUNT}" in argv
    engine = argv[argv.index("mcgyvr-guard") + 1 :]
    asked = "-c" in engine
    assert mounted == told == asked, argv
    return mounted


def _stop(pool: Pool, session_id: str) -> None:
    ack = pool.ask(
        "session_stop", f"x-{session_id}", session_id=session_id, reason="done"
    )
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, session_id, "stopped")
    pool.settle()
