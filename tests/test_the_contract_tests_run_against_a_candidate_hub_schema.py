"""The contract tests run against a candidate hub schema, and the drift check holds.

A hub's CI validates the agent's code against a schema it is about to
publish: ``MCGYVR_HUB_SCHEMA_UNDER_TEST`` names a directory holding
``protocol.schema.json`` and ``rider.schema.json`` (the hub's ``schemas/``
folder). ``rig_schema.load`` then reads the candidate instead of the schema
the product ships, so a candidate that moved a value the agent reads fails
the contract assertion that reads it.

The drift check is apart from it: ``MCGYVR_HUB_SCHEMA`` names a hub's
published file, and a file that is not the shipped one byte for byte fails
the check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import rig_schema

CANDIDATE_GRACE = 30.0


def _protocol_with(**changed: object) -> dict[str, object]:
    protocol: dict[str, object] = json.loads(rig_schema.PROTOCOL.shipped())
    protocol.update(changed)
    return protocol


def _write(tmp_path: Path, name: str, schema: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def test_under_test_mode_reads_the_candidate_and_not_the_shipped_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import session

    shipped = _protocol_with()
    candidate = dict(shipped)
    candidate["x-reconnect-grace-s"] = CANDIDATE_GRACE
    _write(tmp_path, rig_schema.PROTOCOL.hub_name, candidate)
    monkeypatch.setenv(rig_schema.UNDER_TEST_ENV, str(tmp_path))

    loaded = rig_schema.load()

    # The candidate, not the shipped schema, is read: the shipped int and the
    # candidate's float are value-equal, so the type tells them apart.
    assert type(shipped["x-reconnect-grace-s"]) is int
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
        assert named.read_bytes() == rig_schema.PROTOCOL.shipped()
