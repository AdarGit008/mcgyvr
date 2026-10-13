"""No worker session ever mounts a torn tensor-cache file.

A worker's RPC server keeps a tensor its head sent in the rig's cache folder
under the tensor's hash, and loads it back by that name alone. In the pinned
engine (``llama.cpp`` b10644, ``ggml/src/ggml-rpc/ggml-rpc.cpp``):

* ``rpc_server::set_tensor`` writes ``<LLAMA_CACHE>/rpc/<hash>`` in place with
  a truncating ``std::ofstream`` (the engine's ``rpc-server.cpp``:
  ``fs_get_cache_directory() + "rpc"``), where ``<hash>`` is
  ``snprintf("%016" PRIx64, fnv_hash(data, size))``: the FNV-1a 64 of the
  whole tensor, sixteen lower-case hex digits;
* ``rpc_server::get_cached_file`` checks only that the name exists, and
  ``set_tensor_hash`` answers ``result = 1`` without hashing what it read.

A worker killed mid-write (its session torn down, the agent or the machine
gone) leaves the first part of a tensor under the whole tensor's name, and
the next session loads it as complete weights. So the agent hashes every
file in the folder before any worker mounts it:

* a file whose content hashes to its name is kept, and is not hashed again
  until it changes; any other file — torn, stray, or a link — is removed;
* a worker session started while the folder holds a file the agent has not
  hashed runs without the cache, and the agent hashes the folder meanwhile;
* the holder's teardown hands the folder to that check (then the trim), and
  no worker session mounts it until the check is done.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from tests import rig_pool_fakes as fakes
from tests.caches import _cached, _fnv1a_64, _put, _stop, _worker
from tests.rig_pool_fakes import Pool, make_pool


@pytest.fixture
def pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Pool]:
    from mcgyvr.rig import tensorcache

    # the check names each file in this thread, so a wait bounds the agent
    monkeypatch.setattr(tensorcache, "hash_files", fakes.hash_in_this_thread)
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def test_the_agent_names_a_file_as_the_engine_does(tmp_path: Path) -> None:
    from mcgyvr.rig import tensorcache

    # FNV-1a 64's published vectors, and the engine's "%016" PRIx64
    assert tensorcache.fnv1a_64(b"") == 0xCBF29CE484222325
    assert tensorcache.fnv1a_64(b"a") == 0xAF63DC4C8601EC8C
    assert tensorcache.fnv1a_64(b"foobar") == 0x85944171F73967E8
    content = os.urandom(3 * tensorcache.CHUNK // 2)
    path = _put(tmp_path, content)
    other = _put(tmp_path, b"x" * 100)

    assert tensorcache.hash_files([path, other], threading.Event()) == {
        path: path.name,
        other: other.name,
    }


def test_a_torn_file_left_from_before_is_removed_before_a_worker_mounts_the_cache(
    pool: Pool, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    whole = _put(cache, os.urandom(4096))
    torn = _put(cache, os.urandom(4096), torn=True)

    # the agent has hashed nothing of this folder: no worker mounts it yet
    assert not _cached(_worker(pool, "w1", 0), cache)
    pool.settle()

    assert not torn.exists()
    assert whole.exists()
    assert _cached(_worker(pool, "w2", 1), cache)


def test_a_file_torn_while_the_holder_held_the_cache_is_gone_before_the_next_mounts(
    pool: Pool, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    assert _cached(_worker(pool, "w1", 0), cache)
    # w1's engine writes one tensor whole, and is killed in the next
    whole = _put(cache, os.urandom(4096))
    torn = _put(cache, os.urandom(4096), torn=True)
    _stop(pool, "w1")

    assert not torn.exists()
    assert whole.exists()
    assert _cached(_worker(pool, "w2", 1), cache)


def test_no_worker_mounts_the_cache_while_the_agent_hashes_it(
    pool: Pool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import tensorcache

    cache = tmp_path / "cache"
    hashing = threading.Event()
    go = threading.Event()
    real = tensorcache.hash_files

    def held(paths: Sequence[Path], stop: threading.Event) -> dict[Path, str]:
        hashing.set()
        assert go.wait(5.0)
        return real(paths, stop)

    monkeypatch.setattr(tensorcache, "hash_files", held)
    assert _cached(_worker(pool, "w1", 0), cache)
    _put(cache, os.urandom(4096))
    ack = pool.ask("session_stop", "x-w1", session_id="w1", reason="done")
    assert ack is not None and ack["type"] == "ack", ack
    assert hashing.wait(5.0)
    try:
        assert not _cached(_worker(pool, "w2", 1), cache)
    finally:
        go.set()
    pool.settle()
    assert _cached(_worker(pool, "w3", 0), cache)


def test_a_link_or_a_stray_file_is_removed_and_a_links_target_is_untouched(
    pool: Pool, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    outside = tmp_path / "elsewhere"
    outside.write_bytes(b"not the agent's")
    engine = cache / "rpc"
    engine.mkdir(parents=True)
    link = engine / f"{_fnv1a_64(b'not the agents'):016x}"
    link.symlink_to(outside)
    stray = cache / "notes.txt"
    stray.write_bytes(b"x")

    assert not _cached(_worker(pool, "w1", 0), cache)
    pool.settle()

    assert not link.is_symlink() and not link.exists()
    assert not stray.exists()
    assert outside.read_bytes() == b"not the agent's"
    assert _cached(_worker(pool, "w2", 1), cache)


def test_a_hashed_file_that_changed_since_is_hashed_again(
    pool: Pool, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    content = os.urandom(4096)
    path = _put(cache, content)
    assert not _cached(_worker(pool, "w1", 0), cache)
    _stop(pool, "w1")
    assert path.exists()
    # the file is rewritten in place and cut short, after it was hashed
    path.write_bytes(content[:1000])

    assert not _cached(_worker(pool, "w2", 0), cache)
    _stop(pool, "w2")
    assert not path.exists()
    assert _cached(_worker(pool, "w3", 0), cache)
