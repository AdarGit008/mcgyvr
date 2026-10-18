"""Admit live work on the live fleet, or refuse it before any rig is touched.

The live fleet's name comes from the live file and its folder is loaded. The
units of the config being loaded are checked against that fleet's layout, so a
unit that would dispatch to a machine the live fleet does not hold is refused.
The fleet folder's policy is loaded and the layout is checked against its lock
with no readings at all, so a layout that no longer matches its pin is refused
before any rig is read. Each rig of the layout is then read through the door
under one minted run id, the readings the read filed are collected, and
``admit_live`` turns them into a ``Plan``, returned as an ``Admission`` with the
door commands that would carry it out.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr.fleet.admit import LiveRefusedError, Plan, admit_live
from mcgyvr.fleet.promote import on_a_users_machine

#: Runs one rig's read: rig name, run id, and any probe arguments; returns the
#: door's exit code, 0 when the read went through. `read.spawn_read` in practice.
Reader = Callable[[str, str, Sequence[str]], int]


@dataclass(frozen=True)
class Admission:
    """What live work on the live fleet came to, or what stands in its way.

    `fleet` is the live fleet's name, `plan` is what `admit_live` found between
    the readings and the locked layout, and `commands` are the door commands
    that would close that gap.
    """

    fleet: str
    plan: Plan
    commands: list[str]

    @property
    def admitted(self) -> bool:
        """Whether the rigs already read as the locked layout: nothing to clean
        and nothing to restore."""
        return not self.plan.clean and not self.plan.restore


def unapproved(
    units: Mapping[str, Mapping[str, Any]], fleet: Mapping[str, Any], name: str
) -> list[str]:
    """Return a line for each unit of `units` the live fleet `name` does not
    already hold as laid out.

    A unit that names a rig is held when the fleet's layout places it on that
    rig and the fleet holds it at the same address; otherwise it is reported
    as `unit (on rig)`. A unit that names no rig is reported only when its
    address is one a user's machine answers to, as `unit (why)`, with `why`
    saying why that address is not a public one.
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
            why = on_a_users_machine(str(body.get("address") or ""))
            if why is not None:
                out.append(f"{unit} ({why})")
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
    """Admit live work on the live fleet and return what it would change.

    `units` is the loaded config's units, checked against the live fleet's
    layout; `reader` stands in for `read.spawn_read` so a test can read without
    a machine. Raises `LiveRefusedError` when no fleet is live, when a unit is
    not approved for live work, when the fleet folder's policy cannot be read,
    when the layout does not match its lock, when a rig's read fails or files
    no reading under the minted run id, or when `admit_live` refuses the
    readings it was given.
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
        # The live file names no fleet, so no rig can be read and nothing is
        # admitted: name the file and the command that puts a fleet in it.
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
            f"of yours that the live fleet {named} does not hold, and that "
            "machine is not approved for live work yet (a machine is approved "
            "by a read of it)"
        )
    # The fleet folder's policy is what the layout is checked against, so a
    # policy that cannot be read refuses live instead of reading as empty.
    try:
        policy = folder_policy(fleet.folder)
    except ProbeError as exc:
        raise LiveRefusedError(str(exc)) from exc
    # Admit with no readings at all: that checks the layout against its lock and
    # policy before any rig is read, and the plan it returns is thrown away.
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
    """Write the door commands that would carry out `plan` for fleet `name`.

    One line per container of ours that a rig holds but this fleet's layout does
    not place, saying how to take the rig's compose down and bring `name`'s units
    back, and one line per unit whose read state is not the state its slot
    gives, naming the unit and the compose that would start it.
    """
    from mcgyvr.serving import spec_name
    from mcgyvr.serving.gatelib import DOOR_MODULE

    door = f"python -m {DOOR_MODULE} serve"
    units = fleet.get("units") or {}
    names = {str(unit.get("unit_id")): unit_name for unit_name, unit in units.items()}
    lines: list[str] = []
    for rig, key in plan.clean:
        compose = spec_name(rig, name)
        lines.append(
            f"clean {rig} {key}: {door} down --host {rig} "
            f"--compose {compose} stops every unit of ours on {rig}, this one "
            f"included; {door} up --host {rig} --compose "
            f"{compose} brings {name}'s back"
        )
    for rig, unit_id, state in plan.restore:
        compose = spec_name(rig, name)
        lines.append(
            f"restore {rig} {unit_id} ({names.get(unit_id, 'no unit of this fleet')}) "
            f"{state}: `mcgyvr emit` writes {compose}; {door} up "
            f"--host {rig} --compose {compose} starts it"
        )
    return lines
