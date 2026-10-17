""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from mcgyvr.config import MCORCH
from mcgyvr.fleet import ids

AWAKE = "awake"
ASLEEP = "asleep"
_STATES = (AWAKE, ASLEEP)


class FleetError(Exception):
    ""


class SwitchRefusedError(FleetError):
    ""


def combination_id(rig: str, slots: list[Any]) -> str:
    ""
    plain_slots: list[Any] = []
    for slot in slots:
        if slot is None:
            plain_slots.append(None)
            continue
        unit, state = slot
        if state not in _STATES:
            raise ValueError(
                f"a unit is awake or asleep and nothing else, not {state!r}"
            )
        plain_slots.append((unit, state))
    return ids.digest("cmb-", {"rig": rig, "slots": plain_slots})


def layout_sha256(layout: dict[str, str]) -> str:
    ""
    return hashlib.sha256(ids._canonical_dump(layout).encode("utf-8")).hexdigest()


def check_pin(name: str, layout: dict[str, str], pinned: str) -> None:
    ""
    if layout_sha256(layout) != pinned:
        raise FleetError(f"{name}: the layout no longer matches its pin — re-lock")


def mcorch_units(
    policy: Mapping[str, Any], layout: Mapping[str, Any], *, name: str
) -> None:
    ""
    orchestrator = policy.get("orchestrator")
    if not isinstance(orchestrator, Mapping) or orchestrator.get("type") != MCORCH:
        return
    jev = policy.get("jev")
    needed = (
        ("orchestrator", orchestrator.get("unit")),
        ("jev", jev.get("unit") if isinstance(jev, Mapping) else None),
    )
    awake = {
        slot[0]
        for slots in layout.values()
        for slot in slots or ()
        if slot is not None and slot[1] == AWAKE
    }
    missing: list[str] = []
    for role, unit in needed:
        if unit is None:
            line = (
                f"mcorch needs the {role} unit awake, and the policy names none "
                f"({role}.unit)"
            )
        elif unit not in awake:
            line = f"mcorch needs {unit!r} awake, and its layout does not hold it"
        else:
            continue
        if line not in missing:
            missing.append(line)
    if missing:
        raise FleetError(f"fleet {name}: " + "; ".join(missing))


def approve_switch(
    next_map: dict[str, list[str]], from_fleet: str, to_fleet: str
) -> None:
    ""
    if to_fleet not in next_map.get(from_fleet, []):
        raise SwitchRefusedError(
            f"switch refused: {to_fleet} is not listed as a switch from {from_fleet}"
        )


def _union_keys(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(set(before) | set(after))


def _slot_actions(before_slot: Any, after_slot: Any) -> list[tuple[str, str]]:
    ""
    if before_slot == after_slot:
        return []

    before_unit: str | None
    before_state: str | None
    if before_slot is None:
        before_unit, before_state = None, None
    else:
        before_unit, before_state = before_slot

    after_unit: str | None
    after_state: str | None
    if after_slot is None:
        after_unit, after_state = None, None
    else:
        after_unit, after_state = after_slot

    if before_unit is not None and before_unit == after_unit:
        if before_state == AWAKE and after_state == ASLEEP:
            return [("drain", before_unit), ("sleep", before_unit)]
        if before_state == ASLEEP and after_state == AWAKE:
            return [("wake", before_unit)]
        return []

    if before_unit is not None:
        actions: list[tuple[str, str]] = [
            ("drain", before_unit),
            ("stop", before_unit),
        ]
        if after_unit is not None and after_state == AWAKE:
            actions.append(("start", after_unit))
        return actions

    if after_unit is not None and after_state == AWAKE:
        return [("start", after_unit)]
    return []


def _rig_actions(
    rig: str, before_slots: list[Any], after_slots: list[Any]
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for k in range(max(len(before_slots), len(after_slots))):
        before_slot = before_slots[k] if k < len(before_slots) else None
        after_slot = after_slots[k] if k < len(after_slots) else None
        for verb, unit in _slot_actions(before_slot, after_slot):
            out.append((rig, verb, unit))
    return out


def actions(
    before: dict[str, list[Any]], after: dict[str, list[Any]]
) -> list[tuple[str, str, str]]:
    ""
    out: list[tuple[str, str, str]] = []
    for rig in _union_keys(before, after):
        out.extend(_rig_actions(rig, before.get(rig, []), after.get(rig, [])))
    return out


#
#
Move = tuple[str, str, tuple[tuple[str, str], ...]]


def rig_moves(before: dict[str, list[Any]], after: dict[str, list[Any]]) -> list[Move]:
    ""
    moves: list[Move] = []
    for rig in _union_keys(before, after):
        before_slots = before.get(rig, [])
        after_slots = after.get(rig, [])
        verbs = [
            (verb, unit)
            for _, verb, unit in _rig_actions(rig, before_slots, after_slots)
        ]
        if not verbs:
            continue
        moves.append((rig, combination_id(rig, before_slots), tuple(verbs)))
    return moves
