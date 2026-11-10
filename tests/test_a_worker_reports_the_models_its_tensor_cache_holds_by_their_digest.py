"""A worker reports the models its tensor cache holds, by the digest the hub names.

The hub plans a cheaper load on a worker whose cache already holds a model's
weights (``hello.weight_cache``), and names those weights by the sha256 of
the head's model file (``worker_start.model.digest``). The cache names its
files by the FNV-1a hash of each tensor, which says nothing of the model, so
the agent records it (:class:`mcgyvr.rig.tensorcache.Record`):

* when a worker session that was told its model's digest gives the cache
  back, each file the ledger vouches for that was not there when the session
  took the cache is recorded under that digest, beside the folder;
* a hello names a digest while the ledger vouches for every file recorded
  under it: a model one of whose files a trim or a check removed is
  forgotten, and a file under no digest is never reported;
* the record outlives the agent; the ledger it is read against does not
  outlive a boot, so after one nothing is named until the folder is checked;
* only a rig that lends the worker role and shares its cache names them, at
  most ``MAX_MODELS``, the newest.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.rig import protocol, session, tensorcache
from tests import rig_pool_fakes as fakes
from tests import rig_schema
from tests.caches import _cached, _put, _stop, _worker
from tests.rig_pool_fakes import Pool, hash_in_this_thread, make_pool

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


@pytest.fixture(autouse=True)
def _named_in_this_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each check names its files in this thread, so a wait bounds the agent
    alone (:func:`tests.rig_pool_fakes.hash_in_this_thread`)."""
    monkeypatch.setattr(tensorcache, "hash_files", hash_in_this_thread)


def _model(digest: str) -> dict[str, Any]:
    return {"model": {"name": fakes.MODEL, "digest": digest}}


def _session_storing(
    pool: Pool, session_id: str, *contents: bytes, **start: Any
) -> list[Path]:
    """A worker session holding the cache whose server stores ``contents``."""
    cache = pool.sessions.machine.cache_dir
    assert _cached(_worker(pool, session_id, 0, **start), cache)
    paths = [_put(cache, content) for content in contents]
    _stop(pool, session_id)
    return paths


def test_what_a_worker_stored_for_a_named_model_is_reported_by_that_digest(
    tmp_path: Path,
) -> None:
    pool = make_pool(tmp_path)
    try:
        assert pool.sessions.weight_cache() == ()
        paths = _session_storing(
            pool, "w1", os.urandom(4096), os.urandom(512), **_model(DIGEST)
        )
        assert pool.sessions.weight_cache() == (DIGEST,)
    finally:
        pool.sessions.close()
    saved = tensorcache.record_beside(tmp_path / "cache")
    assert saved.parent == tmp_path  # a worker mounts the folder, not this
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert json.loads(saved.read_text()) == {
        "v": tensorcache.RECORD_VERSION,
        "models": {DIGEST: sorted(path.name for path in paths)},
    }


def test_a_file_a_session_stored_with_no_digest_is_never_reported(
    tmp_path: Path,
) -> None:
    pool = make_pool(tmp_path)
    try:
        _session_storing(pool, "w1", os.urandom(4096))
        assert pool.sessions.weight_cache() == ()
        # a later session of a named model that stores nothing new names nothing
        _session_storing(pool, "w2", **_model(DIGEST))
        assert pool.sessions.weight_cache() == ()
    finally:
        pool.sessions.close()


def test_a_model_is_named_only_for_the_files_its_own_session_stored(
    tmp_path: Path,
) -> None:
    pool = make_pool(tmp_path)
    try:
        first = _session_storing(pool, "w1", os.urandom(4096), **_model(DIGEST))
        second = _session_storing(pool, "w2", os.urandom(4096), **_model(OTHER))
        assert pool.sessions.weight_cache() == (DIGEST, OTHER)
        # the first model loses a file: it is forgotten, the other one stays
        first[0].unlink()
        _session_storing(pool, "w3")
        assert pool.sessions.weight_cache() == (OTHER,)
        assert second[0].exists()
    finally:
        pool.sessions.close()


def test_a_model_trimmed_out_of_the_cache_is_forgotten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = make_pool(tmp_path)
    try:
        _session_storing(pool, "w1", os.urandom(4096), **_model(DIGEST))
        assert pool.sessions.weight_cache() == (DIGEST,)
        monkeypatch.setattr(
            session,
            "trim_cache",
            lambda folder, _mb: [p.unlink() for p in (folder / "rpc").iterdir()],
        )
        _session_storing(pool, "w2")
        assert pool.sessions.weight_cache() == ()
    finally:
        pool.sessions.close()
    saved = tensorcache.record_beside(tmp_path / "cache")
    assert json.loads(saved.read_text())["models"] == {}


def test_a_new_agent_reports_what_the_last_one_recorded(tmp_path: Path) -> None:
    first = make_pool(tmp_path)
    try:
        _session_storing(first, "w1", os.urandom(4096), **_model(DIGEST))
    finally:
        first.sessions.close()
    second = make_pool(tmp_path)
    try:
        assert second.sessions.weight_cache() == (DIGEST,)
    finally:
        second.sessions.close()


def test_after_a_reboot_nothing_is_named_until_the_folder_is_checked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = make_pool(tmp_path)
    try:
        _session_storing(first, "w1", os.urandom(4096), **_model(DIGEST))
    finally:
        first.sessions.close()
    monkeypatch.setattr(tensorcache, "boot_id", lambda: "another-boot")
    second = make_pool(tmp_path)
    try:
        assert second.sessions.weight_cache() == ()
        # the first worker after the reboot checks the folder, and runs without it
        assert not _cached(_worker(second, "b1", 0), tmp_path / "cache")
        _stop(second, "b1")
        assert second.sessions.weight_cache() == (DIGEST,)
    finally:
        second.sessions.close()


@pytest.mark.parametrize(
    "document",
    [
        "not json",
        json.dumps({"v": 2, "models": {}}),
        json.dumps({"v": 1, "models": {"sha256:short": ["0123456789abcdef"]}}),
        json.dumps({"v": 1, "models": {DIGEST: ["not-a-cache-name"]}}),
        json.dumps({"v": 1, "models": {DIGEST: "0123456789abcdef"}}),
    ],
)
def test_a_record_that_does_not_read_names_nothing(
    document: str, tmp_path: Path
) -> None:
    saved = tmp_path / "cache.models.json"
    saved.write_text(document)
    record = tensorcache.Record(saved)
    assert record.digests({"0123456789abcdef"}) == ()


def test_a_linked_record_is_not_read(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps({"v": 1, "models": {DIGEST: ["0123456789abcdef"]}}))
    (tmp_path / "cache.models.json").symlink_to(real)
    record = tensorcache.Record(tmp_path / "cache.models.json")
    assert record.digests({"0123456789abcdef"}) == ()


def _offer(tmp_path: Path, cached: tuple[str, ...], **share: Any) -> protocol.Offer:
    return session.offer(
        fakes.sharing(tmp_path, **share),
        fakes.inventory(tmp_path),
        (fakes.LAN_ADDRESS,),
        (),
        fakes.report(),
        cached=cached,
    )


def _hello(offer: protocol.Offer) -> dict[str, Any]:
    frame = json.loads(
        protocol.hello(
            "a" * 32,
            machine_id="rig-example",
            agent_version="0.0.0",
            ram_total_mb=65536,
            ram_free_mb=60000,
            cards=fakes.report().cards,
            offer=offer,
        )
    )
    rig_schema.validate(frame, rig_schema.load(), "#/$defs/AgentMessage")
    body: dict[str, Any] = frame["body"]
    return body


def test_a_worker_rig_names_its_cached_models_in_its_hello(tmp_path: Path) -> None:
    assert _hello(_offer(tmp_path, (DIGEST, OTHER)))["weight_cache"] == [
        DIGEST,
        OTHER,
    ]
    assert "weight_cache" not in _hello(_offer(tmp_path, ()))


def test_only_a_worker_sharing_its_cache_names_it(tmp_path: Path) -> None:
    assert _offer(tmp_path, (DIGEST,), roles=("head",)).weight_cache == ()
    assert _offer(tmp_path, (DIGEST,), cache=False).weight_cache == ()
    assert _offer(tmp_path, (DIGEST,), enabled=False).weight_cache == ()


def test_a_hello_names_at_most_the_newest_max_models(tmp_path: Path) -> None:
    many = tuple(f"sha256:{n:064x}" for n in range(protocol.MAX_MODELS + 3))
    offer = _offer(tmp_path, many)
    assert offer.weight_cache == many[3:]
    assert len(_hello(offer)["weight_cache"]) == protocol.MAX_MODELS


def test_a_hello_refuses_a_weight_cache_not_of_digests() -> None:
    for weight_cache in (("sha256:short",), (DIGEST, DIGEST)):
        offer = protocol.Offer(
            roles=("worker",),
            runtime=None,
            endpoints=(),
            models=(),
            sessions=(),
            weight_cache=weight_cache,
        )
        with pytest.raises(ValueError, match="weight_cache"):
            _hello(offer)


def test_a_worker_start_names_the_digest_of_the_heads_weights() -> None:
    from mcgyvr.rig import sessionwire

    def read(**body: Any) -> sessionwire.WorkerStart:
        envelope = protocol.decode(
            fakes.frame(
                "worker_start",
                session_id="s1",
                cards=[{"card_index": 0, "port": 50052}],
                **body,
            )
        )
        return sessionwire.read_worker_start(envelope)

    assert read().digest is None
    assert read(model={"name": fakes.MODEL}).digest is None
    assert read(**_model(DIGEST)).digest == DIGEST
    with pytest.raises(protocol.ProtocolError):
        read(model={"name": fakes.MODEL, "digest": "sha256:short"})
