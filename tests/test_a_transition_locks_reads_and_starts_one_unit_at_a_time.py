"""A live change is one transition: lock, read, decide, act one unit at a time.

RED. ``mcgyvr.fleet.transition.apply`` does not exist. The intent is
``records/plans/fleet-identity.md``, "the live transition".

Owner's rulings: nothing changes on live except a move from one approved fleet
shape to another, sleep and wake included; the verdict is taken before anything
is touched, and a pre-check that fails refuses and keeps fleet A serving.

The order is the behaviour, so these tests read it off a fake rig port:

* the rig lease is held before the reading, because a reading acted on later
  is a race (``Capacity.drain``, ``src/mcgyvr/capacity.py:1266``: "The census
  decides *whether* to sleep; this is what makes acting on the decision safe");
* a unit is drained before it sleeps, so no admitted request is killed (D8);
* units start one at a time, each after the one before is healthy, because
  vLLM sizes its KV cache from what is on the card while it profiles, and a
  neighbour that starts early moves it by up to 616 MiB (Q15).
"""

from __future__ import annotations

import importlib
from typing import Any

from tests.red_port.conftest import required

U3B = "unt-" + "3" * 64
U7B = "unt-" + "7" * 64
FSH_A = "fsh-" + "a" * 64
FSH_B = "fsh-" + "b" * 64


class FakeRig:
    """Records every act; answers a reading it was built with."""

    def __init__(self, room_mib: int) -> None:
        self.log: list[str] = []
        self.room_mib = room_mib

    def take_lease(self) -> None:
        self.log.append("lease")

    def release_lease(self) -> None:
        self.log.append("release")

    def read(self) -> dict[str, Any]:
        self.log.append("read")
        return {
            "total_mib": self.room_mib + 380,
            "reserve_bound_mib": 380,
            "foreign_mib": 0,
            "staying_mib": [],
            "residual_mib": [],
            "mem_available_mib": 40000,
            "ram_floor_mib": 2048,
            "running_mapped": [],
            "swap_out_delta_pages": 0,
        }

    def drain(self, unit_id: str) -> None:
        self.log.append(f"drain {unit_id[:7]}")

    def sleep(self, unit_id: str) -> None:
        self.log.append(f"sleep {unit_id[:7]}")

    def down(self, unit_id: str) -> None:
        self.log.append(f"down {unit_id[:7]}")

    def start(self, unit_id: str) -> None:
        self.log.append(f"start {unit_id[:7]}")

    def wait_healthy(self, unit_id: str) -> None:
        self.log.append(f"healthy {unit_id[:7]}")

    def observe(self, unit_id: str) -> dict[str, Any]:
        self.log.append(f"observe {unit_id[:7]}")
        return {}


def plan(fsh: str, units: dict[str, str], order: list[str]) -> dict[str, Any]:
    return {
        "fleet_shape_id": fsh,
        "units": units,
        "start_order": order,
        "need": {
            U3B: {"card_need_mib": 3810, "ram_need_mib": 2950},
            U7B: {"card_need_mib": 7544, "ram_need_mib": 2950},
        },
    }


def _apply() -> Any:
    return required(
        "move the rig from one approved fleet shape to another under its lease",
        lambda: importlib.import_module("mcgyvr.fleet.transition").apply,
    )


def test_a_failed_pre_check_refuses_and_keeps_fleet_a() -> None:
    apply = _apply()
    rig = FakeRig(room_mib=4000)
    a = plan(FSH_A, {U3B: "awake", U7B: "asleep-L2"}, [U3B])
    b = plan(FSH_B, {U3B: "asleep-L2", U7B: "awake"}, [U7B])
    serving = apply(a, b, rig)
    assert serving == FSH_A
    acts = [line.split()[0] for line in rig.log]
    assert not {"drain", "sleep", "down", "start"} & set(acts), rig.log
    assert rig.log[-1] == "release"


def test_the_lease_is_taken_before_the_rig_is_read() -> None:
    apply = _apply()
    rig = FakeRig(room_mib=20000)
    apply(plan(FSH_A, {}, []), plan(FSH_B, {U3B: "awake"}, [U3B]), rig)
    assert rig.log[0] == "lease" and rig.log[1] == "read", rig.log
    assert rig.log[-1] == "release", rig.log


def test_a_unit_is_drained_before_it_sleeps() -> None:
    apply = _apply()
    rig = FakeRig(room_mib=20000)
    a = plan(FSH_A, {U3B: "awake", U7B: "awake"}, [U7B, U3B])
    b = plan(FSH_B, {U3B: "asleep-L2", U7B: "awake"}, [U7B])
    apply(a, b, rig)
    drain, sleep = f"drain {U3B[:7]}", f"sleep {U3B[:7]}"
    assert drain in rig.log and sleep in rig.log, rig.log
    assert rig.log.index(drain) < rig.log.index(sleep)


def test_units_start_one_at_a_time_in_order_each_after_healthy() -> None:
    apply = _apply()
    rig = FakeRig(room_mib=20000)
    b = plan(FSH_B, {U7B: "awake", U3B: "awake"}, [U7B, U3B])
    assert apply(plan(FSH_A, {}, []), b, rig) == FSH_B
    started = [line for line in rig.log if line.split()[0] in ("start", "healthy")]
    assert started == [
        f"start {U7B[:7]}",
        f"healthy {U7B[:7]}",
        f"start {U3B[:7]}",
        f"healthy {U3B[:7]}",
    ]
