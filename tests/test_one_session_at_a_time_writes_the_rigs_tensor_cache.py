"""One session at a time writes the rig's tensor cache, and it trims before letting go.

A worker's RPC server keeps the tensors its head sent in the rig's cache
folder, by their hash (``-c`` with ``LLAMA_CACHE``), so a reload sends only
what changed. The engine writes that file in place and reads it back without
checking it: in the pinned engine, ``rpc_server::set_tensor`` opens the file
with a truncating ``std::ofstream`` and writes the tensor into it, and
``rpc_server::get_cached_file`` takes whatever size it finds once the name
exists, so ``set_tensor_hash`` answers "set" with a file another process is
still writing. No lock, no temporary name, no rename. The agent cannot change
how the engine writes; it decides who mounts the folder.

With sessions on several cards of one rig at once, two sessions' workers of
the same model are sent the same tensors, under the same names. Were both
to mount the folder, one would load the other's half-written file as whole
weights, without an error. So:

* the first worker session to start its workers holds the rig's cache until
  its teardown ends; a worker session started while another holds it runs
  without one (no mount, no ``-c``): it is sent every tensor, and never
  reads a torn one;
* the holder trims the folder to the owner's size before it lets go, so no
  other session's worker is ever reading a file while it is removed;
* once the holder is gone, the next worker session takes the cache, and
  finds there what the earlier one kept.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _state(pool: Pool, session_id: str, state: str) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if pool.sessions.state_of(session_id)[0] == state:
            return
        time.sleep(0.005)
    raise AssertionError(f"{session_id} is {pool.sessions.state_of(session_id)}")


def _worker(pool: Pool, session_id: str, card: int) -> list[str]:
    """A worker session on ``card``, ready; its worker's ``docker run``."""
    from mcgyvr.sandbox import pooled

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
    from mcgyvr.sandbox import pooled

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


def test_two_worker_sessions_never_mount_the_rigs_cache_at_once(
    pool: Pool, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    first = _worker(pool, "w1", 0)
    second = _worker(pool, "w2", 1)

    assert _cached(first, cache)
    assert not _cached(second, cache)
    assert pool.sessions.state_of("w2") == ("ready", "worker")


def test_the_next_worker_session_takes_the_cache_once_the_holder_is_gone(
    pool: Pool, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    assert _cached(_worker(pool, "w1", 0), cache)
    assert not _cached(_worker(pool, "w2", 1), cache)
    _stop(pool, "w1")
    _state(pool, "w1", "stopped")
    pool.settle()

    assert _cached(_worker(pool, "w3", 0), cache)


def test_a_session_ending_without_the_cache_never_trims_it(
    pool: Pool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import session as rs

    trimmed: list[Path] = []
    monkeypatch.setattr(rs, "trim_cache", lambda folder, _mb: trimmed.append(folder))
    _worker(pool, "w1", 0)
    _worker(pool, "w2", 1)
    _stop(pool, "w2")
    _state(pool, "w2", "stopped")
    pool.settle()

    assert trimmed == []
    _stop(pool, "w1")
    _state(pool, "w1", "stopped")
    pool.settle()
    assert trimmed == [tmp_path / "cache"]


def test_the_holder_trims_before_another_session_can_take_the_cache(
    pool: Pool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import session as rs

    cache = tmp_path / "cache"
    trimming = threading.Event()
    go = threading.Event()
    trimmed: list[Path] = []

    def held_trim(folder: Path, _max_mb: int) -> None:
        trimming.set()
        assert go.wait(5.0)
        trimmed.append(folder)

    monkeypatch.setattr(rs, "trim_cache", held_trim)
    assert _cached(_worker(pool, "w1", 0), cache)
    _stop(pool, "w1")
    assert trimming.wait(5.0)
    try:
        # w1 is removing files from the folder: a worker started now must
        # not be reading from it
        assert not _cached(_worker(pool, "w2", 1), cache)
    finally:
        go.set()
    _state(pool, "w1", "stopped")
    pool.settle()
    assert trimmed == [cache]
