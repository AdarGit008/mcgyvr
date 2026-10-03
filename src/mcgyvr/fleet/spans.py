"""A unit may span several cards or several rigs, and its fleet must hold it whole.

A unit says which cards it occupies inside its free-form ``launch`` block, so
``fleet.yaml`` needs no schema of its own for it::

    launch:
      shards:                  # the first shard is the head's
        - {rig: box-a.example, gpu: 0, room_mib: 9000}
        - {rig: box-b.example, gpu: 0, room_mib: 7000, bind: 192.0.2.20}

A unit with no ``shards`` is exactly what it always was. A unit with them is a
:class:`Span`: its head (the unit's own ``rig``, where its address answers), the
rigs it spans in order, and its cards.

A spanning unit lives on several rigs at once, and a rig's identity is not
touched by that: a combination is still one rig's room slots and its id is
still hashed from that rig's slots alone. What changes is what a fleet's layout
must hold. A unit whose workers sleep while its head serves, or whose head sits
on a rig whose workers have no room for it, is not a unit that can answer, so
:func:`check_spans` refuses the layout, by unit, fleet and rig, before a lock is
written or a fleet is promoted. Nothing here reads a rig.
"""

from __future__ import annotations

import ipaddress
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mcgyvr.fleet.layout import FleetError

#: The keys a shard names. Any other is refused: an ignored key is a unit that
#: does not do what it says.
_SHARD_KEYS = frozenset({"rig", "gpu", "room_mib", "bind"})


class SpanError(FleetError):
    """A unit's span is declared wrongly, or a layout does not hold it whole."""


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(frozen=True)
class Shard:
    """One card a unit occupies: its rig, its index there, the room it needs."""

    rig: str
    gpu: int
    #: The card room this shard needs, in MiB; ``None`` when the shard states none.
    room_mib: int | None
    #: The IPv4 literal a worker's listener binds to; ``None`` when not stated.
    bind: str | None


@dataclass(frozen=True)
class Span:
    """The cards one unit occupies, head first."""

    unit: str
    #: The unit's own rig: where its address answers and where it is measured.
    head: str
    shards: tuple[Shard, ...]

    @property
    def rigs(self) -> tuple[str, ...]:
        """Every rig spanned: the head first, then the others in declaration
        order, each once."""
        seen: dict[str, None] = {}
        for shard in self.shards:
            seen.setdefault(shard.rig, None)
        return tuple(seen)

    @property
    def workers(self) -> tuple[str, ...]:
        """The rigs spanned other than the head."""
        return tuple(rig for rig in self.rigs if rig != self.head)

    @property
    def cards(self) -> dict[str, tuple[int, ...]]:
        """``rig -> (gpu, ...)`` in declaration order."""
        out: dict[str, list[int]] = {}
        for shard in self.shards:
            out.setdefault(shard.rig, []).append(shard.gpu)
        return {rig: tuple(gpus) for rig, gpus in out.items()}

    @property
    def room(self) -> dict[tuple[str, int], int | None]:
        """``(rig, gpu) -> room_mib`` as each shard states it."""
        return {(shard.rig, shard.gpu): shard.room_mib for shard in self.shards}

    def shards_on(self, rig: str) -> tuple[Shard, ...]:
        """This unit's shards on ``rig``, in declaration order."""
        return tuple(shard for shard in self.shards if shard.rig == rig)


def parse_shard(unit: str, index: int, raw: Any) -> Shard:
    """One entry of ``units.<unit>.launch.shards``, checked; the one reader of it.

    The fleet's lock and the serving sizing both read a shard through here, so
    the two cannot disagree about what a declaration says.
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
    """Every unit of ``fleet`` that declares ``launch.shards``, by unit name.

    A unit that does not declare them is not in the result and is what it was
    before spans existed. Refused, by unit and shard: ``shards`` that is not a
    non-empty list of mappings; a shard with no rig or no card index; a first
    shard that is not on the unit's own rig (the head is the unit's, so the
    address a unit answers at is where its first shard sits); a card named
    twice; a shard on a rig ``fleet.yaml`` does not list under ``rigs``.
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
    """``gpu -> room_mib`` of ``unit_name``'s shards on ``rig``.

    Each shard states its own room, and a spanning unit that left one out is
    refused by name: its room is a sum and a sum with a missing term is a
    guess. A unit that only pins itself to one card (a single shard) may state
    its room once, as ``room_mib``, as every unit does; stating it twice, with
    two different figures, is refused.
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
    """A spanning unit's room on ``rig``: the sum of its shards' there."""
    return sum(shard_rooms(unit_name, unit, span, rig).values())


def check_spans(
    fleet: Mapping[str, Any], layout: Mapping[str, Any], *, name: str = ""
) -> None:
    """``None`` when ``layout`` holds every spanning unit it places whole.

    A unit that spans must hold a room slot on every rig it spans, in the same
    state (awake or asleep) on all of them, and on no rig it does not span: its
    head answers only while its workers are listening, so a layout that wakes
    one and not the other, or leaves a worker no room, describes a unit that
    cannot serve. A unit the layout does not place is not judged. Refused by
    unit, fleet (``name``) and rig.
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
