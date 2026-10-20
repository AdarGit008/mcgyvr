"""A fleet layout: its rigs' room slots named, pinned, and moved along its switches.

A **combination** is one rig's room slots in order, each holding a unit that is
``awake`` or ``asleep`` or standing free. :func:`combination_id` names it
together with the rig, and :func:`layout_sha256` pins a whole layout, one
combination per rig, so a layout edited after it was locked no longer matches
its pin.

A switch is carried out per rig and per slot: slot k of the before layout pairs
with slot k of the after layout, and only slots that differ act
(:func:`actions`).

:func:`mcorch_units` holds a fleet whose policy names an ``mcorch``
orchestrator to keeping that orchestrator's unit and the ``jev`` unit awake.
"""

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
    """A layout, its pin, or a fleet's mcorch units are not what they are held to."""


def combination_id(rig: str, slots: list[Any]) -> str:
    """Name one rig's room slots: ``cmb-`` plus the digest of the rig and the slots.

    Each slot is a ``(unit, state)`` pair or ``None`` for a free room, and
    position is identity, so reordering the slots names another combination. A
    state other than awake or asleep raises :class:`ValueError`.
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
    """The sha256 hex of a layout mapping rig name to combination id.

    The dump is canonical and sorted by key, so the order of the mapping does
    not change the digest.
    """
    return hashlib.sha256(ids._canonical_dump(layout).encode("utf-8")).hexdigest()


def mcorch_units(
    policy: Mapping[str, Any], layout: Mapping[str, Any], *, name: str
) -> None:
    """Hold a fleet with an ``mcorch`` orchestrator to holding its units awake.

    Both the orchestrator's unit and the ``jev`` unit must sit in the layout as
    awake slots; an asleep slot does not count. A policy whose orchestrator is
    not ``mcorch``, or that names no orchestrator, is not checked at all. Every
    missing unit is named once in the one :class:`FleetError`, and a role the
    policy names no unit for is reported by its ``role.unit`` key.
    """
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


def _union_keys(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(set(before) | set(after))


def _slot_actions(before_slot: Any, after_slot: Any) -> list[tuple[str, str]]:
    """The verbs one room slot runs in going from ``before_slot`` to ``after_slot``.

    The same unit staying in its room acts only when its state turns: awake to
    asleep drains and then sleeps, and asleep to awake wakes. A slot that takes a
    new unit drains and stops the leaving unit before it starts the arriving one,
    and starts that arriving unit only when it is awake, so a slot left free or
    handed to an asleep unit is only drained and stopped. A free slot filling
    with an awake unit starts it, and a slot whose two sides match runs nothing.
    """
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
    """Every verb of a switch as ``(rig, verb, unit)``.

    The rigs are the sorted union of both layouts' keys, so a rig present in only
    one of them still acts, and each rig's slots are read in room order.
    """
    out: list[tuple[str, str, str]] = []
    for rig in _union_keys(before, after):
        out.extend(_rig_actions(rig, before.get(rig, []), after.get(rig, [])))
    return out
