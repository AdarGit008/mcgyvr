"""A live ``serve up`` that displaced a dev run ends with its own ladder up.

Gate 2 lets a live run take a rig a dev run holds (ruling R1) and tears down
what the displaced run left: ``<displaced RUN_ID>-*`` and ``mcgyvr-*``
(``gate-scripts/02-rig.py:teardown_displaced``). Gate 7 repeats that teardown
for a displaced run's container that came back during the step. But every
serve unit is named ``mcgyvr-<host>-<service>`` (``mcgyvr emit``), so in a
``serve up`` the ``mcgyvr-*`` sweep at gate 7 removes exactly the units the
step just started — and the run then reports its own ladder as not up.

The units the door read from the compose file are this run's, not the
displaced run's, and gate 7 leaves them running.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from tests import onedoor
from tests.red_port.conftest import required
from tests.test_a_live_run_tears_down_the_serve_units_of_the_dev_run_it_displaced import (  # noqa: E501
    DEV_SERVE_LEASE,
)
from tests.test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock import (
    SRV1_EVIDENCE,
    SRV1_FLEET,
)
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file


def _live_lock() -> None:
    """The live fleet lock that admits the fixture's two units at gate 1."""
    lock = required(
        "write the fleet lock from passing dev runs, refusing what it cannot pin",
        lambda: importlib.import_module("mcgyvr.fleet.lock"),
    )
    live = Path.home() / ".mcgyvr"
    live.mkdir(parents=True, exist_ok=True)
    (live / "live.json").write_text('{"fleet": "flt-01"}', encoding="utf-8")
    lock.write(
        live / "fleets" / "flt-01",
        SRV1_FLEET,
        SRV1_EVIDENCE,
        policy={"ladder": ["a", "b"]},
        tolerances={"warm_decode_class_pct": {"llamacpp": 5.0}},
    )


def test_a_live_serve_up_that_displaced_a_dev_lease_leaves_its_units_running(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    _live_lock()
    # A dev serve's lease on an idle rig: gate 2 displaces it, and what it
    # left is already gone, so the only mcgyvr-* containers at gate 7 are the
    # ones this run's step brought up.
    onedoor.plant_lease(root, DEV_SERVE_LEASE)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", compose)

    removed = [
        line
        for line in onedoor.docker_log(root)
        if line.startswith("rm") and any(name in line for name in UNITS)
    ]
    assert removed == [], (
        "gate 7 removed the units this serve up had just started: "
        f"{removed}\nstderr: {result.stderr[-1500:]}"
    )
    assert result.returncode == 0, (result.returncode, result.stderr[-1500:])
    assert "the ladder is not up" not in result.stderr
