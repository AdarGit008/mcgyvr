"""Live refuses an mcorch setup whose fleet lacks its units awake.

Owner ruling: the check is per fleet, and the live fleet is the fleet being
admitted. ``admit_live`` takes the live policy as ``policy``; when its
orchestrator is ``type: mcorch``, the fleet's layout must hold the
orchestrator's unit and the ``jev`` unit, each ``awake``, or the run is
refused naming what is missing. The lock and its pin are checked first, so an
edited layout still says to re-lock.

``admission.admit`` hands ``admit_live`` the policy in the live fleet's own
folder (``policy.yaml`` beside its ``fleet.yaml``), read the way the probe reads
its journal setting, and a refused setup costs no read of a rig. A ``proposer``
orchestrator is untouched: it is admitted exactly as before.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.test_a_live_run_is_admitted_only_by_a_read_of_its_rigs import (
    FIRST,
    FakeDoor,
    go_live,
)
from tests.test_live_runs_only_a_locked_fleet_and_cleans_what_is_not_in_it import (
    locked,
    observed,
)
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import (
    FLEET,
    POLICY,
    U3B,
    U7B,
)

AGENT, JEV = "srv2_7b", "srv2_3b"


def mcorch(agent: str | None = AGENT, jev: str | None = JEV) -> dict[str, Any]:
    """A policy whose orchestrator is mcorch over ``agent``, judged by ``jev``."""
    policy: dict[str, Any] = {
        **copy.deepcopy(POLICY),
        "deployment": "local-only",
        "orchestrator": {"type": "mcorch", "unit": agent, "authoring": "direct"},
    }
    if jev is not None:
        policy["jev"] = {"unit": jev}
    return policy


# --- admit_live ---------------------------------------------------------------


def test_a_fleet_holding_the_jev_unit_asleep_is_refused(tmp_path: Path) -> None:
    from mcgyvr.fleet.admit import LiveRefusedError, admit_live

    root = locked(tmp_path)
    with pytest.raises(LiveRefusedError) as exc:
        admit_live(root, FLEET, "flt-05", observed(), policy=mcorch())
    message = str(exc.value)
    assert "flt-05" in message and repr(JEV) in message and "awake" in message


def test_a_fleet_holding_both_units_awake_is_admitted(tmp_path: Path) -> None:
    from mcgyvr.fleet.admit import admit_live

    root = locked(tmp_path)
    both = observed({U7B: "awake", U3B: "awake"})
    plan = admit_live(root, FLEET, "flt-02", both, policy=mcorch())
    assert plan.clean == [] and plan.restore == []


def test_the_pin_is_checked_before_the_mcorch_units(tmp_path: Path) -> None:
    from mcgyvr.fleet.admit import LiveRefusedError, admit_live

    root = locked(tmp_path)
    edited = copy.deepcopy(FLEET)
    slots = edited["fleets"]["flt-05"]["layout"]["srv2"]
    edited["fleets"]["flt-05"]["layout"]["srv2"] = list(reversed(slots))
    with pytest.raises(LiveRefusedError, match="re-lock"):
        admit_live(root, edited, "flt-05", observed(), policy=mcorch())


def test_a_proposer_policy_is_admitted_as_before(tmp_path: Path) -> None:
    from mcgyvr.fleet.admit import admit_live

    root = locked(tmp_path)
    proposer = {**POLICY, "orchestrator": {"type": "proposer", "unit": "ghost"}}
    plan = admit_live(root, FLEET, "flt-05", observed(), policy=proposer)
    assert plan.clean == [] and plan.restore == []


# --- admission.admit hands it the live policy ----------------------------------


def live_policy(folder: Path, orchestrator: dict[str, Any]) -> None:
    """Rewrite the live folder's policy, keeping the journal the door files to."""
    path = folder / "policy.yaml"
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    policy["orchestrator"] = orchestrator
    policy["deployment"] = "local-only"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")


def test_admission_refuses_a_live_mcorch_setup_before_reading_a_rig(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet.admission import admit
    from mcgyvr.fleet.admit import LiveRefusedError

    folder = go_live(tmp_path)
    # The agent is awake in the live fleet; no `jev` block is written, since
    # this build's policy reader does not know one yet.
    live_policy(folder, {"type": "mcorch", "unit": FIRST, "authoring": "direct"})
    door = FakeDoor([])

    with pytest.raises(LiveRefusedError) as exc:
        admit(door.spawn)
    message = str(exc.value)
    assert "jev.unit" in message and repr(FIRST) not in message, message
    assert door.calls == [], "a setup the policy refuses cost a read of a rig"


def test_admission_names_an_agent_the_live_fleet_does_not_hold(tmp_path: Path) -> None:
    from mcgyvr.fleet.admission import admit
    from mcgyvr.fleet.admit import LiveRefusedError

    folder = go_live(tmp_path)
    live_policy(folder, {"type": "mcorch", "unit": "srv9_absent"})

    with pytest.raises(LiveRefusedError, match="mcorch needs 'srv9_absent' awake"):
        admit(FakeDoor([]).spawn)


def test_admission_admits_a_live_proposer_setup_as_before(tmp_path: Path) -> None:
    from mcgyvr.fleet.admission import admit

    folder = go_live(tmp_path)
    live_policy(folder, {"type": "proposer", "unit": "srv9_absent"})
    door = FakeDoor([])

    admission = admit(door.spawn)
    assert admission.admitted, admission.commands
    assert sorted(host for host, _ in door.calls) == ["srv1", "srv2"]
