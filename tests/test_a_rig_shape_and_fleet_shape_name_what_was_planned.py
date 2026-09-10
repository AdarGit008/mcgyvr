"""A rig shape names what is planned on one rig; a fleet shape is the set of them.

RED. ``mcgyvr.fleet.rig_shape`` and ``mcgyvr.fleet.fleet_shape`` do not exist.
The intent is ``records/plans/fleet-identity.md``, rules ID-1 to ID-3.

``records/plans/fleet-shape/formulas.md`` already calls the per-host set of
units a **shape** ``S(h)``, each unit in a lifecycle state, and the fleet the
tuple of them. These tests pin what goes into the two names:

* ID-1: lifecycle per unit, start order, the compose text's sha256, and the
  computed card and RAM totals in whole MiB.
* ID-2: a bound reaches a name only through a total. A bound change that moves
  a total moves the rig shape and its fleet shape; one that moves no total
  moves nothing.
* ID-3: a tolerance is not hashed. It lives in the approval record.
"""

from __future__ import annotations

import importlib
from typing import Any

from tests.red_port.conftest import required

RIG = "rig-" + "1" * 64
U3B = "unt-" + "3" * 64
U7B = "unt-" + "7" * 64
COMPOSE = "c" * 64


def _rig_shape_id() -> Any:
    return required(
        "name a rig shape by rig, unit lifecycles, start order, compose and totals",
        lambda: importlib.import_module("mcgyvr.fleet.rig_shape").rig_shape_id,
    )


def _fleet_shape() -> Any:
    return required(
        "name a fleet shape as the set of its rig shapes, and record its approval",
        lambda: importlib.import_module("mcgyvr.fleet.fleet_shape"),
    )


def _srv2(**overrides: Any) -> str:
    fields: dict[str, Any] = {
        "rig_id": RIG,
        "units": {U7B: "awake", U3B: "awake"},
        "start_order": [U7B, U3B],
        "compose_sha256": COMPOSE,
        "card_mib": 10587.0,
        "ram_mib": 6000.0,
    }
    fields.update(overrides)
    return str(_rig_shape_id()(**fields))


def test_lifecycle_start_order_and_compose_each_name_a_different_rig_shape() -> None:
    base = _srv2()
    assert base.startswith("rsh-")
    assert _srv2(units={U7B: "awake", U3B: "asleep-L2"}) != base
    assert _srv2(start_order=[U3B, U7B]) != base, (
        "which unit starts first decides the 3B's KV: 12,352 tokens second, "
        "42,608 started early (flexibility-2026-09-09, Q15)"
    )
    assert _srv2(compose_sha256="d" * 64) != base


def test_totals_are_hashed_in_whole_mib() -> None:
    """Float noise in a derived total must not rename a shape."""
    assert _srv2(card_mib=10587.2) == _srv2(card_mib=10587.4)
    assert _srv2(card_mib=10588.0) != _srv2(card_mib=10587.0)


def test_a_bound_that_moves_a_total_moves_the_rig_shape_and_its_fleet_shape() -> None:
    """qwen3next scratch 768 -> 829 adds 61 MiB to a card total that holds it."""
    fleet_shape = _fleet_shape()
    srv1 = "rsh-" + "a" * 64
    before = _srv2(card_mib=10587.0)
    after = _srv2(card_mib=10648.0)
    assert before != after
    assert fleet_shape.fleet_shape_id([srv1, before]) != fleet_shape.fleet_shape_id(
        [srv1, after]
    )


def test_a_bound_that_moves_no_total_keeps_both_names() -> None:
    fleet_shape = _fleet_shape()
    srv1 = "rsh-" + "a" * 64
    assert _srv2() == _srv2()
    assert fleet_shape.fleet_shape_id([srv1, _srv2()]) == fleet_shape.fleet_shape_id(
        [srv1, _srv2()]
    )


def test_a_fleet_shape_is_its_rig_shapes_in_any_order() -> None:
    fleet_shape = _fleet_shape()
    one, two = "rsh-" + "a" * 64, "rsh-" + "b" * 64
    named = fleet_shape.fleet_shape_id([one, two])
    assert named.startswith("fsh-")
    assert named == fleet_shape.fleet_shape_id([two, one])


def test_a_tolerance_change_keeps_the_fleet_shape_and_changes_its_record() -> None:
    fleet_shape = _fleet_shape()
    rsh = _srv2()
    fsh = fleet_shape.fleet_shape_id([rsh])
    passed = {rsh: {"passed": True, "envelope": "records/evidence/x/validation"}}
    loose = fleet_shape.approve(fsh, [rsh], passed, {"shmem_pct": 8.0})
    tight = fleet_shape.approve(fsh, [rsh], passed, {"shmem_pct": 5.0})
    assert loose["fleet_shape_id"] == tight["fleet_shape_id"] == fsh
    assert loose["tolerances"] != tight["tolerances"]
