"""A head refuses a model file that is not the one its digest names.

When the hub's ``head_start`` names the model's ``digest``, the head hashes the
file this rig holds for that model before it starts anything: a file whose
sha256 is another fails the session as ``model_missing``, and no head container
is run; the file the digest names starts as any head does. The file is read in
chunks, and the session's lease is renewed between them, so hashing a large
model does not let the tunnel's lease lapse. A head the hub names no digest for
is not hashed.

The rig, its model file and its containers are the invented ones of
:mod:`tests.rig_pool_fakes`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool, prepared

CONTENT = b"an invented model file, a few chunks long" * 4
LOCAL_0 = {"kind": "local", "card_index": 0}


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    held = tmp_path / "dense" / fakes.MODEL
    held.parent.mkdir(parents=True)
    held.write_bytes(CONTENT)
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def head_start(pool: Pool, digest: str | None) -> Any:
    model: dict[str, Any] = {"name": fakes.MODEL}
    if digest is not None:
        model["digest"] = digest
    return pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model=model,
        ctx=4096,
        devices=[LOCAL_0],
        tensor_split=[1],
    )


def _head_runs(pool: Pool) -> int:
    from mcgyvr.rig import pooled

    return pool.docker.runs().count(pooled.container_name("s1", "head"))


def test_a_file_whose_digest_is_another_fails_the_head_as_model_missing(
    pool: Pool,
) -> None:
    prepared(pool, role="head")
    ack = head_start(pool, _sha256(b"another file altogether"))
    assert ack is not None and ack["type"] == "ack"

    pool.wait_for("session_status", "failed")
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "model_missing" and failed["role"] == "head"
    assert _head_runs(pool) == 0, "no head is started on a file the digest refuses"


def test_the_file_the_digest_names_starts_and_is_ready(pool: Pool) -> None:
    prepared(pool, role="head")
    ack = head_start(pool, _sha256(CONTENT))
    assert ack is not None and ack["type"] == "ack"

    pool.wait_for("session_status", "ready")
    assert _head_runs(pool) == 1


def test_the_file_is_hashed_in_chunks_with_the_lease_renewed_between_them(
    pool: Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import session as rs

    chunk = 16
    monkeypatch.setattr(rs, "DIGEST_CHUNK", chunk)
    sessions = pool.sessions
    hashing: list[bool] = []
    renewed_while_hashing: list[int] = []
    real_digest, real_renew = sessions._digest, sessions._renew

    def digest(session: Any, path: Path) -> str | None:
        hashing.append(True)
        try:
            found: str | None = real_digest(session, path)
            return found
        finally:
            hashing.pop()

    def renew(session: Any) -> None:
        if hashing:
            renewed_while_hashing.append(1)
        real_renew(session)

    monkeypatch.setattr(sessions, "_digest", digest)
    monkeypatch.setattr(sessions, "_renew", renew)

    prepared(pool, role="head")
    head_start(pool, _sha256(CONTENT))
    pool.wait_for("session_status", "ready")

    chunks = -(-len(CONTENT) // chunk)
    assert len(renewed_while_hashing) == chunks, "the lease is asked after every chunk"


def test_a_head_named_with_no_digest_is_not_hashed(
    pool: Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[Path] = []

    def digest(session: Any, path: Path) -> str | None:
        asked.append(path)
        return None

    monkeypatch.setattr(pool.sessions, "_digest", digest)
    prepared(pool, role="head")
    head_start(pool, None)
    pool.wait_for("session_status", "ready")
    assert asked == []
