"""A new agent mounts the tensor cache the last agent hashed.

A worker mounts the rig's cache folder only while every file in it is one
the agent hashed, unchanged since (:mod:`mcgyvr.rig.tensorcache`). What the
agent hashed was its memory alone, so after an agent restart the next worker
session ran without the cache — every tensor sent again — while the new
agent hashed the whole folder once more. The agent now writes what it hashed
beside the cache folder (never in it: a worker mounts the folder), and a new
agent reads it back:

* a file is trusted only as the same file the last agent hashed — its
  device, inode, size and times as they were then — so a file written to,
  cut short or replaced while no agent ran is hashed again before any worker
  mounts the folder, and a file the last agent never hashed is too;
* a file that is gone is forgotten, and the rest stay trusted;
* what was written in another boot of the machine is not read: a machine
  that went down may have lost a file's content and kept its size and times;
* a saved ledger that does not read (cut short, another shape, a link) is
  no ledger: the folder is hashed as before;
* nothing in the cache folder is removed because the agent started, and the
  trim to the owner's size still runs when a holder's session ends.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from tests.rig_pool_fakes import Pool, hash_in_this_thread, make_pool
from tests.test_no_worker_session_mounts_a_torn_tensor_cache_file import (
    _cached,
    _put,
    _stop,
    _worker,
)


@pytest.fixture(autouse=True)
def _named_in_this_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each check names its files in this thread, so a wait bounds the agent
    alone (:func:`tests.rig_pool_fakes.hash_in_this_thread`)."""
    from mcgyvr.rig import tensorcache

    monkeypatch.setattr(tensorcache, "hash_files", hash_in_this_thread)


def _hashed_by_an_agent_that_ended(tmp_path: Path, *contents: bytes) -> list[Path]:
    """A cache holding ``contents``, each hashed by an agent that then ended."""
    cache = tmp_path / "cache"
    paths = [_put(cache, content) for content in contents]
    first = make_pool(tmp_path)
    try:
        assert not _cached(_worker(first, "a1", 0), cache)
        _stop(first, "a1")
        assert _cached(_worker(first, "a2", 0), cache)
        _stop(first, "a2")
    finally:
        first.sessions.close()
    assert all(path.exists() for path in paths)
    return paths


def _new_agent(tmp_path: Path, **sharing: object) -> Pool:
    return make_pool(tmp_path, **sharing)


def test_the_first_worker_after_an_agent_restart_mounts_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import tensorcache

    paths = _hashed_by_an_agent_that_ended(tmp_path, os.urandom(4096), b"y" * 512)
    hashed: list[Path] = []
    real = tensorcache.hash_files

    def counted(found: list[Path], stop: threading.Event) -> dict[Path, str]:
        hashed.extend(found)
        return real(found, stop)

    monkeypatch.setattr(tensorcache, "hash_files", counted)
    second = _new_agent(tmp_path)
    try:
        assert _cached(_worker(second, "b1", 0), tmp_path / "cache")
        _stop(second, "b1")
    finally:
        second.sessions.close()
    assert hashed == []  # nothing is hashed twice
    assert all(path.exists() for path in paths)


def test_what_the_agent_hashed_is_kept_beside_the_cache_and_is_the_owners_alone(
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import tensorcache

    _hashed_by_an_agent_that_ended(tmp_path, os.urandom(4096))
    cache = tmp_path / "cache"
    saved = tensorcache.saved_beside(cache)
    assert saved.parent == cache.parent  # a worker mounts the folder, not this
    assert saved.is_file() and not saved.is_symlink()
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir() if "ledger" in p.name) == [
        saved.name
    ]


def test_a_file_cut_short_while_no_agent_ran_is_hashed_again_and_removed(
    tmp_path: Path,
) -> None:
    content = os.urandom(4096)
    whole, cut = _hashed_by_an_agent_that_ended(tmp_path, os.urandom(4096), content)
    cut.write_bytes(content[:1000])
    cache = tmp_path / "cache"
    second = _new_agent(tmp_path)
    try:
        assert not _cached(_worker(second, "b1", 0), cache)
        _stop(second, "b1")
        assert not cut.exists()
        assert whole.exists()
        assert _cached(_worker(second, "b2", 0), cache)
    finally:
        second.sessions.close()


def test_a_file_replaced_by_another_of_its_size_is_not_trusted(tmp_path: Path) -> None:
    content = os.urandom(4096)
    (path,) = _hashed_by_an_agent_that_ended(tmp_path, content)
    before = path.stat()
    other = path.with_name("moved-in")
    other.write_bytes(os.urandom(len(content)))
    os.utime(other, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(other, path)  # the name, the size and the written time are the same
    cache = tmp_path / "cache"
    second = _new_agent(tmp_path)
    try:
        assert not _cached(_worker(second, "b1", 0), cache)
        _stop(second, "b1")
        assert not path.exists()
    finally:
        second.sessions.close()


def test_a_file_no_agent_hashed_is_hashed_before_a_worker_mounts_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import tensorcache

    (known,) = _hashed_by_an_agent_that_ended(tmp_path, os.urandom(4096))
    cache = tmp_path / "cache"
    new = _put(cache, os.urandom(2048))
    torn = _put(cache, os.urandom(2048), torn=True)
    hashed: list[Path] = []
    real = tensorcache.hash_files

    def counted(found: list[Path], stop: threading.Event) -> dict[Path, str]:
        hashed.extend(found)
        return real(found, stop)

    monkeypatch.setattr(tensorcache, "hash_files", counted)
    second = _new_agent(tmp_path)
    try:
        assert not _cached(_worker(second, "b1", 0), cache)
        _stop(second, "b1")
        assert sorted(hashed) == sorted([new, torn])  # only what was not known
        assert known.exists() and new.exists() and not torn.exists()
        assert _cached(_worker(second, "b2", 0), cache)
    finally:
        second.sessions.close()


def test_a_file_that_is_gone_is_forgotten_and_the_rest_stay_trusted(
    tmp_path: Path,
) -> None:
    kept, gone = _hashed_by_an_agent_that_ended(
        tmp_path, os.urandom(4096), os.urandom(1024)
    )
    gone.unlink()
    second = _new_agent(tmp_path)
    try:
        assert _cached(_worker(second, "b1", 0), tmp_path / "cache")
    finally:
        second.sessions.close()
    assert kept.exists()


def test_a_ledger_written_in_another_boot_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import tensorcache

    (path,) = _hashed_by_an_agent_that_ended(tmp_path, os.urandom(4096))
    monkeypatch.setattr(tensorcache, "boot_id", lambda: "another-boot")
    cache = tmp_path / "cache"
    second = _new_agent(tmp_path)
    try:
        assert not _cached(_worker(second, "b1", 0), cache)
        _stop(second, "b1")
        assert path.exists()  # hashed again, whole, and kept
        assert _cached(_worker(second, "b2", 0), cache)
    finally:
        second.sessions.close()


def test_a_machine_that_cannot_say_its_boot_keeps_no_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import tensorcache

    monkeypatch.setattr(tensorcache, "boot_id", lambda: None)
    _hashed_by_an_agent_that_ended(tmp_path, os.urandom(4096))
    cache = tmp_path / "cache"
    assert not tensorcache.saved_beside(cache).exists()
    second = _new_agent(tmp_path)
    try:
        assert not _cached(_worker(second, "b1", 0), cache)
    finally:
        second.sessions.close()


@pytest.mark.parametrize(
    "spoil",
    ["cut", "list", "version", "identity", "name", "link", "relative"],
)
def test_a_saved_ledger_that_does_not_read_is_no_ledger(
    tmp_path: Path, spoil: str
) -> None:
    from mcgyvr.rig import tensorcache

    (path,) = _hashed_by_an_agent_that_ended(tmp_path, os.urandom(4096))
    cache = tmp_path / "cache"
    saved = tensorcache.saved_beside(cache)
    document = json.loads(saved.read_text())
    stray = cache / "rpc" / "notes.txt"
    if spoil == "cut":
        saved.write_text(saved.read_text()[:-20])
    elif spoil == "list":
        saved.write_text("[]")
    elif spoil == "version":
        document["v"] = 99
        saved.write_text(json.dumps(document))
    elif spoil == "identity":
        document["files"][str(path)] = [1, 2, True, "4", 5]
        saved.write_text(json.dumps(document))
    elif spoil == "name":
        # a ledger never makes a stray file one a worker may mount
        stray.write_bytes(b"x")
        found = stray.lstat()
        document["files"][str(stray)] = [
            found.st_dev,
            found.st_ino,
            found.st_size,
            found.st_mtime_ns,
            found.st_ctime_ns,
        ]
        saved.write_text(json.dumps(document))
    elif spoil == "relative":
        document["files"] = {
            os.path.relpath(name): identity
            for name, identity in document["files"].items()
        }
        saved.write_text(json.dumps(document))
    else:
        elsewhere = tmp_path / "elsewhere.json"
        saved.rename(elsewhere)
        saved.symlink_to(elsewhere)
    second = _new_agent(tmp_path)
    try:
        assert not _cached(_worker(second, "b1", 0), cache)
        _stop(second, "b1")
        assert path.exists()
        assert not stray.exists()
        assert _cached(_worker(second, "b2", 0), cache)
    finally:
        second.sessions.close()


def test_the_cache_is_still_trimmed_to_the_owners_size_after_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import tensorcache

    # both files are whole, and more than a mebibyte together: each is named
    # as itself here, since hashing them for real takes this test's seconds
    monkeypatch.setattr(
        tensorcache, "hash_files", lambda found, stop: {p: p.name for p in found}
    )
    old, new = _hashed_by_an_agent_that_ended(
        tmp_path, os.urandom(700 << 10), os.urandom(600 << 10)
    )
    os.utime(old, (1_000_000, 1_000_000))
    cache = tmp_path / "cache"
    second = _new_agent(tmp_path, cache_max_mb=1)
    try:
        # the start removed nothing; the old file's time changed, so it is
        # hashed again, and the trim after it keeps the folder to its size
        assert old.exists() and new.exists()
        assert not _cached(_worker(second, "b1", 0), cache)
        _stop(second, "b1")
        assert not old.exists() and new.exists()
        assert _cached(_worker(second, "b2", 0), cache)
    finally:
        second.sessions.close()


def test_a_ledger_reads_only_its_own_boots_files_as_they_were(tmp_path: Path) -> None:
    from mcgyvr.rig import tensorcache

    cache = tmp_path / "cache"
    path = _put(cache, os.urandom(4096))
    saved = tensorcache.saved_beside(cache)
    first = tensorcache.Ledger(saved)
    assert not first.trusted(cache)
    first.check(cache, threading.Event())
    assert first.trusted(cache)

    assert tensorcache.Ledger(saved).trusted(cache)
    assert not tensorcache.Ledger().trusted(cache)  # no file: memory alone
    os.utime(path, ns=(1, 1))
    assert not tensorcache.Ledger(saved).trusted(cache)
