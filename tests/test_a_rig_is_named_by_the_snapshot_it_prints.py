"""A rig is named by the snapshot it prints, in the spelling the snapshot prints.

Owner, 2026-09-15 (D1): ``rig-`` = H{ host, hardware, system }
(``mcgyvr-lab/records/plans/fleet-identity.md`` §1) is hashed by one product function,
:func:`mcgyvr.fleet.ids.rig_id`, over the fields exactly as
``src/mcgyvr/serving/gate-scripts/rig-snapshot.sh`` prints them: tokenized,
every value a string. The lock and live admission both call it; there is no
second spelling.

Until now the two locked rig ids were hashed by hand scripts that disagree.
``fleet-setup/digests-srv2.json`` hashed the snapshot's own spelling and
``fleet-setup/digests-srv1.json`` hashed ``"Intel(R) Core(TM) i5-9600K CPU @
3.70GHz"`` with spaces and ``gpu_vram_mib`` as the integer 6144, which no rig
read ever prints. So srv2's locked id reproduces from a snapshot and srv1's does
not: srv1 gets a new id when it is re-locked, and until then live admission
cannot admit it.

* ``rig_id`` over srv2's snapshot is the id srv2 is locked under.
* A snapshot missing a field is refused by name, never hashed (§1 ID-1).
* ``rig-snapshot.sh`` prints ``os_machine_id``, derived as ``mcgyvr scan``
  derives its machine id: the first 16 hex of the sha256 of
  ``/etc/machine-id`` (``src/mcgyvr/scan.py``).
* The lock refuses a rig whose dev run's snapshot names another id than the
  one ``fleet.yaml`` pins.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import onedoor
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import (
    EVIDENCE,
    FLEET,
    POLICY,
    TOLERANCES,
)

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT_SH = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "rig-snapshot.sh"

#: What srv2's lock was hashed with beyond what hosts.json declares
#: (``fleet-setup/digests-srv2.json``): its machine id and kernel then.
SRV2_SYSTEM = {"os_machine_id": "6d5d8f1f2bfa5f96", "kernel": "7.0.0-31-generic"}


def srv2_snapshot(**override: str) -> dict[str, str]:
    """srv2's reading as ``rig-snapshot.sh`` prints it, parsed ``key=value``."""
    text = onedoor.snapshot_lines("srv2", **(SRV2_SYSTEM | override))
    return dict(line.split("=", 1) for line in text.splitlines() if line)


def locked_rig_id(host: str) -> str:
    fleet = yaml.safe_load((REPO / "fleet-setup" / "fleet.yaml").read_text("utf-8"))
    return str(fleet["rigs"][host]["rig_id"])


def test_srv2_is_locked_under_the_id_its_snapshot_names() -> None:
    from mcgyvr.fleet.ids import rig_id

    named = rig_id(srv2_snapshot())
    assert named == locked_rig_id("srv2")
    assert (REPO / "records" / "fleet" / "rigs" / named).is_dir()


def test_a_moved_rig_is_named_anew() -> None:
    from mcgyvr.fleet.ids import rig_id

    assert rig_id(srv2_snapshot(kernel="7.0.0-32-generic")) != locked_rig_id("srv2")
    assert rig_id(srv2_snapshot(pl1_uw="4095000000")) != locked_rig_id("srv2")


@pytest.mark.parametrize("missing", ["os_machine_id", "gpu_cc", "hostname", "kernel"])
def test_a_snapshot_missing_a_rig_field_is_refused_by_name(missing: str) -> None:
    from mcgyvr.fleet.ids import rig_id

    snapshot = srv2_snapshot()
    del snapshot[missing]
    with pytest.raises(ValueError, match=missing):
        rig_id(snapshot)


def test_the_snapshot_prints_os_machine_id_as_mcgyvr_scan_derives_it() -> None:
    """The reader's own function, run on this machine, against ``mcgyvr scan``'s."""
    from mcgyvr.scan import local_machine_id

    text = SNAPSHOT_SH.read_text(encoding="utf-8")
    assert re.search(r"^printf 'os_machine_id=%s\\n'", text, re.MULTILINE), (
        "rig-snapshot.sh prints no os_machine_id= line"
    )
    match = re.search(
        r"^os_machine_id\(\) \{\n.*?^\}\n", text, re.MULTILINE | re.DOTALL
    )
    assert match, "rig-snapshot.sh defines no os_machine_id() reader"
    reader = "set -u\n" + text.split("\nuptime_since()", 1)[0] + "\n" + match.group(0)
    done = subprocess.run(
        ["bash", "-c", reader + "os_machine_id\n"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == local_machine_id()


def _fleet_named_by(snapshot: dict[str, str], pinned: str) -> dict[str, Any]:
    fleet = copy.deepcopy(FLEET)
    fleet["rigs"]["srv2"]["rig_id"] = pinned
    return fleet


def test_the_lock_refuses_a_rig_id_its_dev_runs_snapshot_does_not_name(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import lock
    from mcgyvr.fleet.ids import rig_id

    snapshot = srv2_snapshot(hostname="srv2")
    evidence = copy.deepcopy(EVIDENCE)
    evidence["rigs"]["srv2"]["snapshot"] = snapshot
    named = rig_id(snapshot)

    stale = "rig-" + "2" * 64
    with pytest.raises(lock.LockRefusedError) as refused:
        lock.write(
            tmp_path / "stale",
            _fleet_named_by(snapshot, stale),
            evidence,
            policy=POLICY,
            tolerances=TOLERANCES,
        )
    said = str(refused.value)
    assert "srv2" in said and stale in said and named in said, said

    lock.write(
        tmp_path / "named",
        _fleet_named_by(snapshot, named),
        evidence,
        policy=POLICY,
        tolerances=TOLERANCES,
    )
    assert (tmp_path / "named" / "records" / "fleet" / "rigs" / named).is_dir()
    record = json.loads(
        (tmp_path / "named" / "records" / "fleet" / "flt-05.json").read_text("utf-8")
    )
    assert record["layout_sha256"]


def test_no_other_code_hashes_a_rig_id() -> None:
    """One spelling: ``ids.rig_id`` is the only ``digest("rig-", ...)`` shipped."""
    spelled = sorted(
        path.relative_to(REPO).as_posix()
        for top in ("src", "tools")
        for path in (REPO / top).rglob("*.py")
        if re.search(r"""digest\(\s*["']rig-["']""", path.read_text("utf-8"))
    )
    assert spelled == ["src/mcgyvr/fleet/ids.py"], spelled
