"""A host is locked by its own rig id's records, not by any record naming it.

Owner, 2026-09-16, on the orphaned records the rig-id re-lock left behind:
"fix and add to PR".

``mcgyvr fleet lock`` writes one directory per rig id and never prunes: when a
rig's id changes, the records of the id it had stay where they are. They still
carry ``"rig": "srv1"``, because that field is the rig's NAME, not its identity.
``admit.host_is_locked`` globbed ``*/cmb-*.json`` across every directory and
matched on that name, so the records of a machine that no longer exists answered
for the machine that does — a second source of truth, and the wrong one.

The lock pins the identity: ``rigs.<host>.rig_id`` in the ``fleet.yaml`` beside
the lock. ``mcgyvr fleet promote`` writes that file into the live fleet folder
(``promote.py:165``) and ``fleet use`` refuses a folder that does not load as a
setup, so for the live profile — the only profile that reaches this function
(``wake.py:464``) — it is there. So the answer is read from that rig id's
directory alone.

A root with no ``fleet.yaml`` beside its lock is left exactly as it was: this
narrows what can answer, and must never make something that is locked today
read as unlocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.fleet.admit import host_is_locked
from tests.test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock import (
    SRV1_EVIDENCE,
    SRV1_FLEET,
)
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import TOLERANCES

#: srv1's rig id as SRV1_FLEET pins it, and the id of a machine it is not.
PINNED = SRV1_FLEET["rigs"]["srv1"]["rig_id"]
STALE = "rig-" + "9" * 64

RIGS = ("records", "fleet", "rigs")


def _lock_root(tmp_path: Path) -> Path:
    """A lock root shaped like a promoted live fleet folder: the lock, and the
    ``fleet.yaml`` it was written from beside it."""
    from mcgyvr.fleet import lock

    root = tmp_path / "live-folder"
    root.mkdir()
    lock.write(root, SRV1_FLEET, SRV1_EVIDENCE, tolerances=TOLERANCES)
    (root / "fleet.yaml").write_text(
        yaml.safe_dump(SRV1_FLEET, sort_keys=False), encoding="utf-8"
    )
    return root


def _records_of(root: Path, rig_id: str) -> list[Path]:
    return sorted((root.joinpath(*RIGS) / rig_id).glob("cmb-*.json"))


def _plant_stale(root: Path, rig_id: str) -> Path:
    """A record under ``rig_id`` naming srv1, exactly as a rig id change leaves
    behind: the same shape the lock writes, under an id nothing pins."""
    written = _records_of(root, PINNED)
    assert written, "the fixture lock wrote no record to copy"
    body: dict[str, Any] = json.loads(written[0].read_text(encoding="utf-8"))
    assert body.get("rig") == "srv1", body
    target = root.joinpath(*RIGS) / rig_id / written[0].name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", "utf-8")
    return target


def test_the_pinned_rig_ids_records_answer_for_the_host(tmp_path: Path) -> None:
    root = _lock_root(tmp_path)
    assert host_is_locked(root, "srv1") is True
    assert host_is_locked(root, "srv2") is False, "a host the lock never names"


def test_a_stale_rig_ids_records_do_not_answer_for_the_host(tmp_path: Path) -> None:
    """The bug, as the rig-id re-lock produced it.

    srv1's id changed, so its pinned directory is the new one. The records of
    the old id remain and still say ``"rig": "srv1"``. With nothing under the
    pinned id, srv1 is not locked, whatever the old records say.
    """
    root = _lock_root(tmp_path)
    _plant_stale(root, STALE)

    for path in _records_of(root, PINNED):
        path.unlink()
    (root.joinpath(*RIGS) / PINNED).rmdir()

    assert _records_of(root, STALE), "the stale record is what the question is about"
    assert host_is_locked(root, "srv1") is False, (
        "a record under a rig id no fleet pins answered for srv1: the rig id is "
        "the identity, and the record's `rig` field is only the name"
    )


def test_a_stale_rig_id_beside_the_pinned_one_changes_no_answer(tmp_path: Path) -> None:
    """Both directories present, which is the state the re-lock actually left.

    The answer is the same either way; it must come from the pinned id.
    """
    root = _lock_root(tmp_path)
    _plant_stale(root, STALE)
    assert host_is_locked(root, "srv1") is True
    assert host_is_locked(root, "srv2") is False


def test_a_lock_with_no_fleet_beside_it_reads_as_it_did(tmp_path: Path) -> None:
    """No ``fleet.yaml`` is no pinned id, so nothing narrows and the lock reads
    as it always has. Narrowing must not turn a locked host into an unlocked
    one wherever the pin cannot be read."""
    root = _lock_root(tmp_path)
    (root / "fleet.yaml").unlink()
    assert host_is_locked(root, "srv1") is True

    root.joinpath(*RIGS, PINNED).rename(root.joinpath(*RIGS, STALE))
    assert host_is_locked(root, "srv1") is True, (
        "with no fleet.yaml to pin the rig id, every record still answers"
    )


def test_a_fleet_that_does_not_parse_reads_as_it_did(tmp_path: Path) -> None:
    """An unreadable pin is no pin: the same fallback, never a refusal."""
    root = _lock_root(tmp_path)
    (root / "fleet.yaml").write_text("rigs: [this is not a mapping\n", encoding="utf-8")
    assert host_is_locked(root, "srv1") is True


def test_a_fleet_that_pins_no_such_host_reads_as_it_did(tmp_path: Path) -> None:
    """A host the fleet.yaml does not name has no pinned id, so the lock reads
    as it always has rather than refusing a host it cannot pin."""
    root = _lock_root(tmp_path)
    fleet: dict[str, Any] = {**SRV1_FLEET, "rigs": {"srv9": {"rig_id": STALE}}}
    (root / "fleet.yaml").write_text(
        yaml.safe_dump(fleet, sort_keys=False), encoding="utf-8"
    )
    assert host_is_locked(root, "srv1") is True


def test_no_lock_tree_is_not_locked(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert host_is_locked(empty, "srv1") is False
