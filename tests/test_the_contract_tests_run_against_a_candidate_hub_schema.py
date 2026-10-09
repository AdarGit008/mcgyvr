"""The contract tests run against a candidate hub schema, and the tripwire holds.

The hub's own CI validates the agent's code against a schema it is about to
publish before that schema is pinned here: ``MCGYVR_HUB_SCHEMA_UNDER_TEST``
names a directory holding ``protocol.schema.json`` and ``rider.schema.json``
(the hub's ``schemas/`` folder). ``rig_schema.load`` then reads the candidate
instead of the pinned copy and does not hold it to ``pinned_sha256``, so a
candidate that moved a value the agent reads fails the contract assertion
that reads it, not the digest tripwire.

The existing drift check is unchanged: ``MCGYVR_HUB_SCHEMA`` still names the
published file the copy was pinned from, and a file that moved from it still
fails the check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import rig_schema

CANDIDATE_GRACE = 30.0


def _protocol_with(**changed: object) -> dict[str, object]:
    protocol: dict[str, object] = json.loads(rig_schema.PROTOCOL.fixture.read_bytes())
    protocol.update(changed)
    return protocol


def _write(tmp_path: Path, name: str, schema: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def test_under_test_mode_reads_the_candidate_and_skips_the_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import session

    pinned = _protocol_with()
    candidate = dict(pinned)
    candidate["x-reconnect-grace-s"] = CANDIDATE_GRACE
    _write(tmp_path, rig_schema.PROTOCOL.hub_name, candidate)
    monkeypatch.setenv(rig_schema.UNDER_TEST_ENV, str(tmp_path))

    loaded = rig_schema.load()  # the pinned_sha256 tripwire must not fire

    # The candidate, not the pinned copy, is read: the copy's int and the
    # candidate's float are value-equal, so the type tells them apart.
    assert type(pinned["x-reconnect-grace-s"]) is int
    assert type(loaded["x-reconnect-grace-s"]) is float
    assert loaded["x-reconnect-grace-s"] == CANDIDATE_GRACE

    # A contract assertion, as the session tests write it, reads the candidate.
    assert session.Timing().grace_s == rig_schema.load()["x-reconnect-grace-s"]


def test_the_drift_check_still_fails_a_named_hub_file_that_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = _write(
        tmp_path,
        rig_schema.PROTOCOL.hub_name,
        _protocol_with(**{"x-reconnect-grace-s": 45}),
    )
    monkeypatch.setenv(rig_schema.PROTOCOL.env, str(moved))

    named = rig_schema.hub_file(rig_schema.PROTOCOL)
    assert named is not None
    assert named == moved
    with pytest.raises(AssertionError):
        assert rig_schema.sha256(named.read_bytes()) == rig_schema.PROTOCOL.hub_sha256
