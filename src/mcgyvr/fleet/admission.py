"""Live is admitted only by a read of its rigs, taken through the door.

Defect F2, "admit_live has no production caller" (owner, 2026-09-15). What
:func:`mcgyvr.fleet.admit.admit_live` is handed as ``observed`` is the door's
``read`` of each rig of the live fleet (:mod:`mcgyvr.fleet.read`), never a
guess, and the lock is read from the live fleet's own folder
(:func:`mcgyvr.fleet.roots.lock_root`), never the working directory.

:func:`admit` refuses (:class:`~mcgyvr.fleet.admit.LiveRefusedError`) when no
fleet is named or it has no lock, when its layout was edited after locking,
before any rig is read; and, once each rig is read, when a rig is not the rig
it was locked on or a process that is not ours holds its card, or when the door
could not read a rig at all. Otherwise it returns the plan: what would be
cleaned and restored, with the door commands that would do it. Carrying a plan
out stops and starts containers on a rig, and that is not decided (records the
owner's open ruling): the callers refuse a non-empty plan and print the
commands, and run none of them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.fleet.admit import LiveRefusedError, Plan, admit_live

#: A read of one rig through the door: ``(rig, run id, units to probe) -> exit``.
Reader = Callable[[str, str, Sequence[str]], int]


@dataclass(frozen=True)
class Admission:
    """What admission found: the live fleet, its plan, and the commands it names."""

    fleet: str
    plan: Plan
    commands: list[str]

    @property
    def admitted(self) -> bool:
        """Whether there is nothing to clean and nothing to restore."""
        return not self.plan.clean and not self.plan.restore


def admit(reader: Reader | None = None) -> Admission:
    """Read each rig of the live fleet through the door, and hold it to the lock."""
    from mcgyvr.fleet import read
    from mcgyvr.fleet.probe import journal_dir
    from mcgyvr.fleet.roots import LiveFleetError, live_fleet
    from mcgyvr.serving.run import mint_read_id

    try:
        named = live_fleet()
    except LiveFleetError as exc:
        raise LiveRefusedError(str(exc)) from exc
    if named is None:
        admit_live(Path(), {}, None, {})
    try:
        fleet = read.live()
    except read.ReadError as exc:
        raise LiveRefusedError(str(exc)) from exc
    # The lock and its pin first: a fleet that cannot be admitted costs no read.
    admit_live(fleet.folder, fleet.fleet, fleet.name, {})

    spawn = reader if reader is not None else read.spawn_read
    run_id = mint_read_id()
    rigs = sorted(fleet.fleet["fleets"][fleet.name].get("layout", {}))
    for rig in rigs:
        code = spawn(rig, run_id, ())
        if code != 0:
            raise LiveRefusedError(
                f"{rig}: the door could not read it (exit {code}), and live is "
                "admitted only by a read of its rigs"
            )
    filed = read.observations(journal_dir(fleet.folder), run_id)
    observed: dict[str, Any] = {}
    for rig in rigs:
        row = filed.get(rig)
        if row is None:
            raise LiveRefusedError(
                f"{rig}: the door's read filed no reading under {run_id}"
            )
        observed[rig] = {
            "rig_id": row.get("observed_rig_id"),
            "units": row.get("units") or {},
            "foreign": row.get("foreign") or [],
        }
    plan = admit_live(fleet.folder, fleet.fleet, fleet.name, observed)
    return Admission(fleet.name, plan, door_commands(fleet.fleet, fleet.name, plan))


def door_commands(fleet: Mapping[str, Any], name: str, plan: Plan) -> list[str]:
    """One line per step of ``plan``, naming the door command that would take it."""
    from mcgyvr.serving import spec_name
    from mcgyvr.serving.gatelib import DOOR_MODULE

    door = f"python -m {DOOR_MODULE}"
    units = fleet.get("units") or {}
    names = {str(unit.get("unit_id")): unit_name for unit_name, unit in units.items()}
    lines: list[str] = []
    for rig, key in plan.clean:
        compose = spec_name(rig, name)
        lines.append(
            f"clean {rig} {key}: {door} serve down --host {rig} --compose {compose} "
            f"stops every unit of ours on {rig}, this one included; {door} serve up "
            f"--host {rig} --compose {compose} brings {name}'s back"
        )
    for rig, unit_id, state in plan.restore:
        compose = spec_name(rig, name)
        lines.append(
            f"restore {rig} {unit_id} ({names.get(unit_id, 'no unit of this fleet')}) "
            f"{state}: `mcgyvr emit` writes {compose}; {door} serve up --host {rig} "
            f"--compose {compose} starts it"
        )
    return lines
