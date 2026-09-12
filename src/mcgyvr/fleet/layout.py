"""A fleet is a named layout, and it moves only along the switches listed for it.

* A **combination** is one rig's **room slots**, in order. Each slot holds a
  unit, ``awake`` or ``asleep``, or is free. Slot k is identity; the order
  units start in is not.
* A **fleet** is a name pinned to the sha256 of its layout, one combination per
  rig. A layout edited after it was locked no longer matches its pin.
* A **switch** is listed: a fleet may move only to the fleets its ``next``
  names. It is commanded at fleet level and carried out per rig and per slot:
  slot k of the source pairs with slot k of the target, and a leaving slot's
  stop precedes its arrival's start.
* A switch's dev run is keyed by its **rig move** (the rig, the combination it
  starts from and the actions), so one run proves every fleet switch that
  derives the same move.
"""

from __future__ import annotations

import hashlib
from typing import Any

from mcgyvr.fleet import ids

AWAKE = "awake"
ASLEEP = "asleep"
_STATES = (AWAKE, ASLEEP)


class FleetError(Exception):
    """A fleet layout or switch does not satisfy its lock or its listing."""


class SwitchRefusedError(FleetError):
    """A switch was asked toward a fleet the source does not list."""


def combination_id(rig: str, slots: list[Any]) -> str:
    """``cmb-`` for one rig's room slots, each awake, asleep or free.

    Slot position is identity: the same units in another order are a different
    combination, and an asleep unit keeps a room a freed unit does not.
    """
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
    """The sha256 of a layout's canonical dump (rig -> combination), order-free."""
    return hashlib.sha256(ids._canonical_dump(layout).encode("utf-8")).hexdigest()


def check_pin(name: str, layout: dict[str, str], pinned: str) -> None:
    """``None`` when ``layout`` still matches its pin; ``FleetError`` naming it."""
    if layout_sha256(layout) != pinned:
        raise FleetError(f"{name}: the layout no longer matches its pin — re-lock")


def approve_switch(
    next_map: dict[str, list[str]], from_fleet: str, to_fleet: str
) -> None:
    """``None`` for a listed switch, ``SwitchRefusedError`` naming the refusal."""
    if to_fleet not in next_map.get(from_fleet, []):
        raise SwitchRefusedError(
            f"switch refused: {to_fleet} is not listed as a switch from {from_fleet}"
        )


def _union_keys(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(set(before) | set(after))


def _slot_actions(before_slot: Any, after_slot: Any) -> list[tuple[str, str]]:
    """The verbs that turn one room slot into another, in order."""
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
    """The per-rig, per-slot verbs that transform ``before`` into ``after``."""
    out: list[tuple[str, str, str]] = []
    for rig in _union_keys(before, after):
        out.extend(_rig_actions(rig, before.get(rig, []), after.get(rig, [])))
    return out


#: One rig's part of a switch: the rig, the combination it starts from, and
#: the verbs that transform its slots.
Move = tuple[str, str, tuple[tuple[str, str], ...]]


def rig_moves(before: dict[str, list[Any]], after: dict[str, list[Any]]) -> list[Move]:
    """The distinct per-rig moves of a switch.

    Two fleet switches that derive the same move return equal lists, so a dev
    run keyed by a rig move proves every switch that uses it.
    """
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
