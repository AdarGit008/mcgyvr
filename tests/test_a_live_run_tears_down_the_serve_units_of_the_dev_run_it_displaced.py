"""A live run that displaces a dev serve tears the dev run's units down.

RED, against code that exists. P0 of ``records/plans/fleet-identity.md`` §11,
and a prerequisite of live's auto-clean (§6).

Gate 2 lets a live run take a rig a dev run holds (ruling R1) and tears down
what it displaced by name: every container whose name starts with the
displaced run's id (``src/mcgyvr/serving/gate-scripts/02-rig.py:108``,
``prefix = f"{displaced.run_id}-"``). That matches a campaign step's
containers (``<RUN_ID>-<role>``) and never a serve unit's, which ``mcgyvr emit``
names ``mcgyvr-<host>-<service>`` (``src/mcgyvr/emit.py:505``). So a dev
``serve up`` displaced by live stays up on the rig live just took.

Driven with a live ``serve down``, which gate 1 always admits (§6), so this
stays a pure gate-2 test once the fleet lock is enforced.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file

#: A dev serve, on another machine, holding srv1 (the lease format of
#: ``tests/red_port/test_dod_rig_lease.py``).
DEV_SERVE_LEASE = (
    "lease_id=deadbeefdeadbeef profile=dev holder=someone@elsewhere "
    "machine=elsewhere0000 pid=1 started_at=2026-09-06T01:02:03Z "
    "campaign=live-srv1 step=serve-up run_id=2026-09-06-live-srv1-serve-up"
)


def test_a_live_run_removes_the_serve_units_of_the_dev_run_it_displaced(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.plant_lease(root, DEV_SERVE_LEASE)
    onedoor.containers_up(root, *UNITS)

    result = onedoor.serve_door(root, "down", compose)

    removed_at_gate_2 = [
        name
        for name in UNITS
        if any(
            line.startswith("rm") and name in line for line in onedoor.docker_log(root)
        )
    ]
    assert removed_at_gate_2 == list(UNITS), (
        "gate 2 must tear down the serve units of the dev run it displaced; "
        f"removed {removed_at_gate_2}.\nstderr: {result.stderr[-1500:]}"
    )
