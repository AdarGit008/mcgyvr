"""A fleet that lacks the mcorch units awake is neither locked nor promoted.

Owner ruling: the check is per fleet. When a policy's orchestrator is
``type: mcorch``, the fleet being locked or promoted must hold both the
orchestrator's unit and the ``jev`` unit as slots, each ``awake``. An asleep
slot does not count: an mcorch conversation cannot wait for a wake. A policy
that names no ``jev`` unit cannot be held by any layout, and says so.

The one check is :func:`mcgyvr.fleet.layout.mcorch_units`, on the raw policy
and layout. ``mcgyvr fleet lock`` holds every fleet of the file to it, beside
the refusal of a ladder naming a unit the fleet lacks; ``mcgyvr fleet promote``
holds the fleet it promotes to it, and writes nothing when it refuses. A
``proposer`` orchestrator is untouched by both.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.fleet.promote import LOCK_DIR
from tests.test_dev_and_live_locks_flow_one_way import (
    SETUP_POLICY,
    dev_setup,
    home,
    listing,
    tree,
)
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import (
    EVIDENCE,
    FLEET,
    FLT02,
    POLICY,
    TOLERANCES,
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


# --- the one check ------------------------------------------------------------


def test_a_layout_holding_both_units_awake_passes() -> None:
    from mcgyvr.fleet.layout import mcorch_units

    mcorch_units(mcorch(), {"srv2": FLT02}, name="flt-02")


def test_an_asleep_slot_does_not_count() -> None:
    from mcgyvr.fleet.layout import FleetError, mcorch_units

    layout = {"srv2": [[AGENT, "awake"], [JEV, "asleep"]]}
    with pytest.raises(FleetError) as exc:
        mcorch_units(mcorch(), layout, name="flt-05")
    message = str(exc.value)
    assert "flt-05" in message and repr(JEV) in message and "awake" in message
    assert repr(AGENT) not in message, "the awake unit is not named as missing"


def test_every_missing_unit_is_named() -> None:
    from mcgyvr.fleet.layout import FleetError, mcorch_units

    with pytest.raises(FleetError) as exc:
        mcorch_units(mcorch(), {"srv1": [["other", "awake"], None]}, name="flt-09")
    message = str(exc.value)
    assert repr(AGENT) in message and repr(JEV) in message, message


def test_a_policy_naming_no_jev_unit_is_held_by_no_layout() -> None:
    from mcgyvr.fleet.layout import FleetError, mcorch_units

    with pytest.raises(FleetError, match=r"jev\.unit"):
        mcorch_units(mcorch(jev=None), {"srv2": FLT02}, name="flt-02")


def test_a_proposer_orchestrator_is_untouched() -> None:
    from mcgyvr.fleet.layout import mcorch_units

    proposer = {**POLICY, "orchestrator": {"type": "proposer", "unit": "ghost"}}
    mcorch_units(proposer, {}, name="flt-05")
    mcorch_units({**POLICY, "orchestrator": {"unit": "ghost"}}, {}, name="flt-05")
    mcorch_units(POLICY, {}, name="flt-05")


# --- mcgyvr fleet lock ----------------------------------------------------------


def test_lock_refuses_a_fleet_whose_jev_unit_is_asleep(tmp_path: Path) -> None:
    from mcgyvr.fleet import lock

    with pytest.raises(lock.LockRefusedError) as exc:
        lock.write(tmp_path, FLEET, EVIDENCE, policy=mcorch(), tolerances=TOLERANCES)
    message = str(exc.value)
    assert "flt-05" in message and repr(JEV) in message, message
    assert not (tmp_path / LOCK_DIR).exists(), "a refused lock wrote a record"


def test_lock_writes_a_fleet_holding_both_units_awake(tmp_path: Path) -> None:
    from mcgyvr.fleet import lock

    fleet = copy.deepcopy(FLEET)
    fleet["fleets"] = {"flt-02": {"layout": {"srv2": FLT02}, "next": []}}
    lock.write(tmp_path, fleet, EVIDENCE, policy=mcorch(), tolerances=TOLERANCES)
    assert (tmp_path / LOCK_DIR / "flt-02.json").is_file()


def test_lock_leaves_a_proposer_policy_as_it_was(tmp_path: Path) -> None:
    from mcgyvr.fleet import lock

    proposer = {**POLICY, "orchestrator": {"type": "proposer", "unit": JEV}}
    lock.write(tmp_path, FLEET, EVIDENCE, policy=proposer, tolerances=TOLERANCES)
    assert (tmp_path / LOCK_DIR / "flt-05.json").is_file()


# --- mcgyvr fleet promote -------------------------------------------------------


def test_promote_refuses_a_fleet_whose_agent_is_asleep_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet.promote import PromoteRefusedError, promote

    dev, setup = dev_setup(tmp_path, monkeypatch)
    # flt-05 holds the 3B asleep. The policy is written without a `jev`
    # block, which this build's policy reader does not know yet: the refusal
    # names the asleep agent, and the jev unit no policy names.
    policy = {**SETUP_POLICY, **mcorch(agent=JEV, jev=None)}
    (setup / "policy.yaml").write_text(
        yaml.safe_dump(policy, sort_keys=False), encoding="utf-8"
    )
    before = (listing(home()), tree(home()))

    with pytest.raises(PromoteRefusedError) as exc:
        promote(dev, setup, "flt-05")
    message = str(exc.value)
    assert "flt-05" in message and f"mcorch needs {JEV!r} awake" in message, message
    assert "jev.unit" in message, message
    assert (listing(home()), tree(home())) == before, "a refused promote wrote"
