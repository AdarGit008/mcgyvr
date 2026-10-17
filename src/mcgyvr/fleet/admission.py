""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr.fleet.admit import LiveRefusedError, Plan, admit_live
from mcgyvr.fleet.promote import on_a_users_machine

#
Reader = Callable[[str, str, Sequence[str]], int]


@dataclass(frozen=True)
class Admission:
    ""

    fleet: str
    plan: Plan
    commands: list[str]

    @property
    def admitted(self) -> bool:
        ""
        return not self.plan.clean and not self.plan.restore


def unapproved(
    units: Mapping[str, Mapping[str, Any]], fleet: Mapping[str, Any], name: str
) -> list[str]:
    ""
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
    ""
    from mcgyvr.fleet import read
    from mcgyvr.fleet.probe import ProbeError, folder_policy, journal_dir
    from mcgyvr.fleet.roots import LiveFleetError, live_file, live_fleet
    from mcgyvr.serving.run import mint_read_id

    try:
        named = live_fleet()
    except LiveFleetError as exc:
        raise LiveRefusedError(str(exc)) from exc
    if named is None:
        #
        #
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
    #
    #
    try:
        policy = folder_policy(fleet.folder)
    except ProbeError as exc:
        raise LiveRefusedError(str(exc)) from exc
    #
    #
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
    ""
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
