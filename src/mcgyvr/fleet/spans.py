"""
A unit's shards: the rigs and cards it occupies, and the room each card needs.

A unit's ``launch.shards`` lists one shard per card it occupies, in order, the
first on its head rig. A shard names the rig its card is on (``rig``), the
card's index there (``gpu``), and optionally the room that card must hold for it
in MiB (``room_mib``) and the IPv4 address a worker there listens on (``bind``).
:func:`parse_shard` reads one shard and :func:`spans` every unit that declares
shards, keyed by unit name, telling head rig from worker rigs and cards from
rooms.

A unit that spans cards is pinned card by card, so its room on a rig is the sum
of its shards' rooms there (:func:`shard_rooms`, :func:`room_on`), and a layout
holds it whole on every rig it spans (:func:`check_spans`): a slot on a rig it
does not span, a spanned rig with no slot, or a state that differs between the
rigs is refused.
"""

from __future__ import annotations

import ipaddress
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mcgyvr.fleet.layout import FleetError

#: The only keys a shard may state: the rig its card is on, that card's index,
#: the room the card must hold for it in MiB, and the address a worker binds.
_SHARD_KEYS = frozenset({"rig", "gpu", "room_mib", "bind"})


class SpanError(FleetError):
    """A unit's shards name no card it can launch on, or a layout does not hold
    a spanning unit whole.
    """


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(frozen=True)
class Shard:
    """One card a unit occupies: the rig it sits on and its index there.

    ``room_mib`` is the room that card must hold for this shard, None where
    nobody stated one. ``bind`` is the IPv4 address a worker on this shard
    listens on, None where it is not stated.
    """

    rig: str
    gpu: int
    #: The MiB this card must hold for the shard, rounded up from what was
    #: stated; None where the shard states no room of its own.
    room_mib: int | None
    #: The IPv4 address a worker on this shard listens on; None where nobody
    #: named one.
    bind: str | None


@dataclass(frozen=True)
class Span:
    """One unit's shards, in the order ``launch.shards`` lists them.

    The first shard is the head's, so ``head`` is the rig the unit is declared
    on and the first of its ``rigs``.
    """

    unit: str
    #: The rig the unit is declared on, ``units.<unit>.rig``, which its first
    #: shard must be on.
    head: str
    shards: tuple[Shard, ...]

    @property
    def rigs(self) -> tuple[str, ...]:
        """The rigs the unit spans, in shard order and each named once."""
        seen: dict[str, None] = {}
        for shard in self.shards:
            seen.setdefault(shard.rig, None)
        return tuple(seen)

    @property
    def workers(self) -> tuple[str, ...]:
        """The rigs the unit spans other than its head, in shard order."""
        return tuple(rig for rig in self.rigs if rig != self.head)

    @property
    def cards(self) -> dict[str, tuple[int, ...]]:
        """Each rig the unit spans mapped to the cards it occupies there, in
        shard order.
        """
        out: dict[str, list[int]] = {}
        for shard in self.shards:
            out.setdefault(shard.rig, []).append(shard.gpu)
        return {rig: tuple(gpus) for rig, gpus in out.items()}

    @property
    def room(self) -> dict[tuple[str, int], int | None]:
        """Each card the unit occupies, as ``(rig, gpu)``, mapped to the room
        its shard needs there, None where the shard states none.
        """
        return {(shard.rig, shard.gpu): shard.room_mib for shard in self.shards}

    def shards_on(self, rig: str) -> tuple[Shard, ...]:
        """The unit's shards on ``rig`` in shard order, empty when it spans no
        card there.
        """
        return tuple(shard for shard in self.shards if shard.rig == rig)


def parse_shard(unit: str, index: int, raw: Any) -> Shard:
    """Read one entry of ``units.<unit>.launch.shards`` as a :class:`Shard`.

    ``index`` is the entry's position in the list, which names it in a refusal.
    Only rig, gpu, room_mib and bind are read: the rig must be a named one, the
    gpu a whole number from 0, a stated room_mib a number of MiB above 0 (kept
    as a whole MiB, rounded up), and a stated bind an IPv4 address rather than
    a name. Anything else raises :class:`SpanError`.
    """
    where = f"units.{unit}.launch.shards[{index}]"
    if not isinstance(raw, Mapping):
        raise SpanError(
            f"{where}: a shard is a mapping of rig, gpu and room_mib, not {raw!r}"
        )
    for key in raw:
        if key not in _SHARD_KEYS:
            raise SpanError(
                f"{where}: unknown key {key!r}. Valid keys here: "
                f"{', '.join(sorted(_SHARD_KEYS))}"
            )
    rig = raw.get("rig")
    if not isinstance(rig, str) or not rig.strip():
        raise SpanError(f"{where}: names no rig; a shard says which rig its card is on")
    gpu = raw.get("gpu")
    if not isinstance(gpu, int) or isinstance(gpu, bool) or gpu < 0:
        raise SpanError(
            f"{where}: gpu is {gpu!r}; a shard names the card by its index on "
            f"{rig}, a whole number from 0"
        )
    room: int | None = None
    if raw.get("room_mib") is not None:
        stated = raw["room_mib"]
        if not _is_number(stated) or stated <= 0:
            raise SpanError(
                f"{where}: room_mib is {stated!r}; it is the card room this "
                "shard needs, a number of MiB above 0"
            )
        room = math.ceil(stated)
    bind = raw.get("bind")
    if bind is not None:
        try:
            if not isinstance(bind, str):
                raise ValueError(bind)
            ipaddress.IPv4Address(bind)
        except ValueError:
            raise SpanError(
                f"{where}: bind is {bind!r}; it is the IPv4 address a worker "
                "listens on, never a name and never every interface"
            ) from None
    return Shard(rig=rig, gpu=gpu, room_mib=room, bind=bind)


def spans(fleet: Mapping[str, Any]) -> dict[str, Span]:
    """Every unit of ``fleet`` that declares shards, as a :class:`Span` by name.

    A unit whose launch states no ``launch.shards`` spans nothing and is left
    out. A unit that states them states at least one shard, puts its head's
    shard first (on the rig ``units.<unit>.rig`` names), names no card twice,
    and names only rigs the fleet lists under ``rigs``; anything else raises
    :class:`SpanError`.
    """
    rigs = fleet.get("rigs") or {}
    found: dict[str, Span] = {}
    for name, unit in (fleet.get("units") or {}).items():
        launch = unit.get("launch") if isinstance(unit, Mapping) else None
        if not isinstance(launch, Mapping) or "shards" not in launch:
            continue
        raw = launch["shards"]
        where = f"units.{name}.launch.shards"
        if not isinstance(raw, list) or not raw:
            raise SpanError(
                f"{where}: expected a list of shards, one per card the unit "
                f"occupies, not {raw!r}"
            )
        shards = tuple(parse_shard(name, index, item) for index, item in enumerate(raw))
        head = unit.get("rig")
        if not isinstance(head, str) or not head:
            raise SpanError(
                f"units.{name}: declares shards but no `rig`; its first shard's "
                "rig is its head and the unit must name it"
            )
        if shards[0].rig != head:
            raise SpanError(
                f"{where}[0]: the first shard is on {shards[0].rig}, but "
                f"units.{name} is on {head}. The first shard is the head's: "
                "list it first"
            )
        seen: set[tuple[str, int]] = set()
        for shard in shards:
            if (shard.rig, shard.gpu) in seen:
                raise SpanError(
                    f"{where}: card {shard.gpu} of {shard.rig} is named twice; "
                    "a card is one shard"
                )
            seen.add((shard.rig, shard.gpu))
            if shard.rig not in rigs:
                raise SpanError(
                    f"{where}: names rig {shard.rig}, which fleet.yaml does not "
                    f"list under `rigs` ({', '.join(sorted(rigs)) or 'none'})"
                )
        found[name] = Span(unit=name, head=head, shards=shards)
    return found


def shard_rooms(
    unit_name: str, unit: Mapping[str, Any], span: Span, rig: str
) -> dict[int, int]:
    """The room each card of ``rig`` must hold for ``unit``, by card index.

    A shard states its own room_mib. A unit pinned to one card (a span of one
    shard) may state its room once on the unit instead, which its shard then
    takes; a unit stating both must state one figure, not two. A shard on
    ``rig`` whose room nobody states raises :class:`SpanError`, as does a unit
    that spans no card there: a unit that spans cards states the room each
    needs.
    """
    shards = span.shards_on(rig)
    if not shards:
        raise SpanError(f"{unit_name}: spans no card on {rig}")
    pin = len(span.shards) == 1
    stated = unit.get("room_mib")
    own = (
        math.ceil(stated)
        if isinstance(stated, int | float)
        and not isinstance(stated, bool)
        and stated > 0
        else None
    )
    out: dict[int, int] = {}
    for shard in shards:
        room = shard.room_mib
        if pin and own is not None:
            if room is None:
                room = own
            elif room != own:
                raise SpanError(
                    f"{unit_name}: room_mib {own} and its shard's room_mib "
                    f"{room} on {rig} name two rooms for one card"
                )
        if room is None:
            raise SpanError(
                f"{unit_name}: its shard on {rig} card {shard.gpu} states no "
                "room_mib; a unit that spans cards states the room each needs"
            )
        out[shard.gpu] = room
    return out


def room_on(unit_name: str, unit: Mapping[str, Any], span: Span, rig: str) -> int:
    """The unit's whole room on ``rig``: its shards' rooms there summed.

    This is the figure the unit's slots on that rig are fit against; see
    :func:`shard_rooms` for what a shard's room is and when it is refused.
    """
    return sum(shard_rooms(unit_name, unit, span, rig).values())


def check_spans(
    fleet: Mapping[str, Any], layout: Mapping[str, Any], *, name: str = ""
) -> None:
    """Hold ``layout`` to laying every spanning unit out whole.

    ``layout`` maps each rig name to that rig's room slots, each a
    ``(unit, state)`` pair or None for a free room. A unit that spans rigs holds
    a slot on every rig it spans and on no rig it does not, and all its slots
    are in one state, awake or asleep, since it is one unit across those rigs. A
    unit holding no slot is not checked. ``name``, where given, prefixes each
    refusal with the fleet it names.
    """
    prefix = f"{name}: " if name else ""
    for unit, span in spans(fleet).items():
        held: dict[str, set[str]] = {}
        for rig, slots in layout.items():
            for slot in slots:
                if slot is not None and slot[0] == unit:
                    held.setdefault(rig, set()).add(slot[1])
        if not held:
            continue
        for rig in span.rigs:
            if rig not in held:
                raise SpanError(
                    f"{prefix}{unit} spans {', '.join(span.rigs)} but holds no "
                    f"room slot on {rig}; give it one there, in the same state"
                )
        for rig in held:
            if rig not in span.rigs:
                raise SpanError(
                    f"{prefix}{unit} holds a room slot on {rig}, which it does "
                    f"not span ({', '.join(span.rigs)}); add a shard there or "
                    "take the slot out"
                )
        states = {rig: sorted(held[rig]) for rig in span.rigs}
        if len({state for each in states.values() for state in each}) > 1:
            said = ", ".join(
                f"{'/'.join(each)} on {rig}" for rig, each in states.items()
            )
            raise SpanError(
                f"{prefix}{unit} is in two states ({said}); a unit that spans "
                "rigs is awake on all of them or asleep on all of them"
            )
