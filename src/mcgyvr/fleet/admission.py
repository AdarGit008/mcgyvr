"""Live is admitted only by a read of its rigs, taken through the door.

What :func:`mcgyvr.fleet.admit.admit_live` is handed as ``observed`` is the door's
``read`` of each rig of the live fleet (:mod:`mcgyvr.fleet.read`), never a
guess, and the lock is read from the live fleet's own folder
(:func:`mcgyvr.fleet.roots.lock_root`), never the working directory.

:func:`admit` refuses (:class:`~mcgyvr.fleet.admit.LiveRefusedError`) when no
fleet is named or it has no lock, when the config the command loaded holds a
unit on a rig that the live fleet does not lay out there (:func:`unapproved`:
that machine is not approved for live work yet), when its layout was edited
after locking,
or when the live folder's ``policy.yaml`` names an mcorch orchestrator whose
units the fleet does not hold awake, before any rig is read; and, once each rig
is read, when a rig is not the rig it was locked on or a process that is not
ours holds its card, or when the door could not read a rig at all. Otherwise it
returns the plan: what would be cleaned and restored, with the door commands
that would do it. Carrying a plan out stops and starts containers on a rig, and
the owner has not ruled that mcgyvr may do so: the callers refuse a non-empty
plan and print the commands, and run none of them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
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


def unapproved(
    units: Mapping[str, Mapping[str, Any]], fleet: Mapping[str, Any], name: str
) -> list[str]:
    """The units of ``units`` on a rig that live fleet ``name`` does not approve.

    ``units`` are the config a live command loaded, which need not be the live
    folder's: the working directory's comes first. A unit on a rig is approved
    only where the live fleet's layout places a unit of that name, on that rig
    and at that address, so a rig the layout does not name is never dispatched
    to unread. A unit on no rig is hosted and is not read by admission.
    """
    layout = fleet["fleets"][name].get("layout") or {}
    held = fleet.get("units") or {}
    placed = {
        (str(slot[0]), str(rig))
        for rig, slots in layout.items()
        for slot in slots
        if slot
    }
    out: list[str] = []
    for unit, body in sorted(units.items()):
        rig = body.get("rig")
        if not rig:
            continue
        live = held.get(unit) or {}
        if (unit, str(rig)) in placed and live.get("address") == body.get("address"):
            continue
        out.append(f"{unit} (on {rig})")
    return out


def admit(
    reader: Reader | None = None,
    *,
    units: Mapping[str, Mapping[str, Any]] | None = None,
) -> Admission:
    """Read each rig of the live fleet through the door, and hold it to the lock.

    ``units`` are the units of the config the command loaded, refused by
    :func:`unapproved` before any rig is read; ``None`` checks none.
    """
    from mcgyvr.fleet import read
    from mcgyvr.fleet.probe import ProbeError, folder_policy, journal_dir
    from mcgyvr.fleet.roots import LiveFleetError, live_file, live_fleet
    from mcgyvr.serving.run import mint_read_id

    try:
        named = live_fleet()
    except LiveFleetError as exc:
        raise LiveRefusedError(str(exc)) from exc
    if named is None:
        # The pointer looked for, by the path read: the config folder may have
        # been moved, and the default's pointer may name another fleet.
        raise LiveRefusedError(
            f"no fleet is live: {live_file()} names none (`mcgyvr fleet use`)"
        )
    try:
        fleet = read.live()
    except read.ReadError as exc:
        raise LiveRefusedError(str(exc)) from exc
    outside = unapproved(units or {}, fleet.fleet, fleet.name)
    if outside:
        raise LiveRefusedError(
            f"{', '.join(outside)}: the config loaded dispatches to a machine "
            f"the live fleet {named} does not lay out, and that machine is not "
            "approved for live work yet (a machine is approved by a read of it)"
        )
    # The live setup's own policy, beside its fleet.yaml: an mcorch
    # orchestrator holds the live fleet to its units.
    try:
        policy = folder_policy(fleet.folder)
    except ProbeError as exc:
        raise LiveRefusedError(str(exc)) from exc
    # The lock, its pin and the policy first: a fleet that cannot be admitted
    # costs no read.
    admit_live(fleet.folder, fleet.fleet, fleet.name, {}, policy=policy)

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
    plan = admit_live(fleet.folder, fleet.fleet, fleet.name, observed, policy=policy)
    return Admission(fleet.name, plan, door_commands(fleet.fleet, fleet.name, plan))


def door_commands(fleet: Mapping[str, Any], name: str, plan: Plan) -> list[str]:
    """One line per step of ``plan``, naming the door command that would take it."""
    from mcgyvr.serving import spec_name
    from mcgyvr.serving.gatelib import DOOR_MODULE
    from mcgyvr.serving.run import callers_mode

    door = f"python -m {DOOR_MODULE} serve"
    mode = callers_mode()
    units = fleet.get("units") or {}
    names = {str(unit.get("unit_id")): unit_name for unit_name, unit in units.items()}
    lines: list[str] = []
    for rig, key in plan.clean:
        compose = spec_name(rig, name)
        lines.append(
            f"clean {rig} {key}: {door} down --mode {mode} --host {rig} "
            f"--compose {compose} stops every unit of ours on {rig}, this one "
            f"included; {door} up --mode {mode} --host {rig} --compose "
            f"{compose} brings {name}'s back"
        )
    for rig, unit_id, state in plan.restore:
        compose = spec_name(rig, name)
        lines.append(
            f"restore {rig} {unit_id} ({names.get(unit_id, 'no unit of this fleet')}) "
            f"{state}: `mcgyvr emit` writes {compose}; {door} up --mode {mode} "
            f"--host {rig} --compose {compose} starts it"
        )
    return lines
