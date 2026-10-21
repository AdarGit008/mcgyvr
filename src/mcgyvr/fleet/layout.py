"""A fleet layout: its rigs' room slots named and pinned.

A **combination** is one rig's room slots in order, each holding a unit that is
``awake`` or ``asleep`` or standing free. :func:`combination_id` names it
together with the rig, and :func:`layout_sha256` pins a whole layout, one
combination per rig, so a layout edited after it was locked no longer matches
its pin.
"""

from __future__ import annotations

import hashlib
from typing import Any

from mcgyvr.fleet import ids

AWAKE = "awake"
ASLEEP = "asleep"
_STATES = (AWAKE, ASLEEP)


class FleetError(Exception):
    """A layout or its pin is not what it is held to."""


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
