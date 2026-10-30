"""The rig's own report of the machine it runs on.

This module holds no detection of its own: the one reader,
:mod:`mcgyvr.serving.rigscan`, makes the short reading of the machine, and
:func:`mcgyvr.fleet.ids.rig_id` names it with the ``rig-`` id the hub knows it
by. :func:`read` turns that reading into a :class:`Report`, and the report
makes the two frames an agent sends about its hardware, a ``hello`` and a
``heartbeat``: what the rig lends of it, as resources in the hub's contract
(:mod:`mcgyvr.hubwire`), and the legacy cards those make. A reading that
fails or that cannot be named is raised as :class:`HardwareError` rather
than reported as a guess.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcgyvr import estimate, hubwire
from mcgyvr.fleet import ids
from mcgyvr.hubwire import CARD_KINDS, FIGURE_ESTIMATE, RESOURCE_CPU
from mcgyvr.rig import protocol
from mcgyvr.scan import Host


class HardwareError(Exception):
    """The machine could not be read or could not be named, so no report exists."""


@dataclass(frozen=True, kw_only=True)
class Report:
    """One reading of this machine, as the rig reports it to a hub.

    ``machine_id`` is the machine's ``rig-`` id, the RAM figures are MiB, and
    ``cards`` are the sized cards renumbered from 0, at most as many as the
    protocol carries. ``notes`` says in prose what a reader left out or could
    not read, since a figure that was not read is reported as absent or zero
    and never as a guess.
    """

    machine_id: str
    ram_total_mb: int
    ram_free_mb: int | None
    cards: tuple[protocol.CardReport, ...]
    notes: tuple[str, ...]
    #: Which card of the reading each reported card came from, position for
    #: position: its vendor and the reading's own index, since the report
    #: renumbers its cards from 0.
    sources: tuple[tuple[str, int], ...] = ()
    #: The kind of each reported card, position for position: ``gpu``, or
    #: ``unified`` for a GPU that shares the machine's memory.
    kinds: tuple[str, ...] = ()
    #: The machine's resources in the hub's resource contract (kind, index,
    #: name, total_mb, free_mb, cores, bandwidth_gbps, bandwidth_figure, figure,
    #: backend), every one it has, lent or not: a card's only when the report
    #: carries that card, each name held to what the protocol carries and each
    #: size to its most.
    resources: tuple[Mapping[str, Any], ...] = ()
    #: The system the reading was taken on; None when the reading had none.
    host: Host | None = None
    #: What the rig lends of this machine, as its hello advertises it: none
    #: until the lending settings say (:meth:`mcgyvr.rig.sharing.Sharing.lendable`).
    lent: tuple[hubwire.Resource, ...] = ()


def read_machine() -> Mapping[str, Any]:
    """The short reading of this machine, as the product's own scanner makes it.

    Rigscan is imported here rather than at import time, and its reading asks
    for no raised rights: identity, cards and memory, with the fields that
    could not be read named in it.
    """
    from mcgyvr.serving import rigscan

    return rigscan.read_machine()


def _printable(name: str | None, vendor: str) -> str:
    kept = "".join(
        char for char in (name or "") if protocol.CARD_NAME.fullmatch(char)
    ).strip()
    return kept[: protocol.CARD_NAME_MAX] or f"{vendor} card"


def _mib(gb: float) -> int:
    return max(0, min(round(gb * 1024), protocol.MAX_MB))


def read(*, reader: Callable[[], Mapping[str, Any]] | None = None) -> Report:
    """The report of this machine, from one reading of it.

    The reading comes from ``reader`` when one is given and from
    :func:`read_machine` otherwise, so a caller can hand in a document instead
    of touching the machine. A reader that raises ``OSError``, and a reading
    that :func:`mcgyvr.fleet.ids.rig_id` refuses to name, are raised as
    :class:`HardwareError`. Cards the reading left unsized are dropped, and
    cards past :data:`mcgyvr.rig.protocol.MAX_CARDS` are cut with a note. Each
    kept card is renumbered from 0, its total is held to
    :data:`mcgyvr.rig.protocol.MAX_MB`, its free VRAM to its total, and free
    VRAM the reading did not give is reported as 0 with a note. RAM that was
    not read is reported as 0 MiB total and no free figure, with a note; free
    RAM the reading gave is held to the total.
    """
    try:
        reading = (reader or read_machine)()
    except OSError as exc:
        raise HardwareError(f"the machine could not be read: {exc}") from exc
    try:
        machine_id = ids.rig_id(reading)
    except ValueError as refusal:
        raise HardwareError(f"this machine has no rig id: {refusal}") from refusal
    notes: list[str] = []
    unsized = set(reading.get("unsized") or ())
    sized = [
        card
        for card in reading.get("cards") or ()
        if f"card.{card['vendor']}.{card['index']}" not in unsized
    ]
    if len(sized) > protocol.MAX_CARDS:
        notes.append(
            f"{len(sized)} cards read; a report carries {protocol.MAX_CARDS}, so "
            "the rest are not reported"
        )
        sized = sized[: protocol.MAX_CARDS]
    cards: list[protocol.CardReport] = []
    sources: list[tuple[str, int]] = []
    kinds: list[str] = []
    for number, card in enumerate(sized):
        key = f"card.{card['vendor']}.{card['index']}"
        total = min(card.get("total_mib") or 0, protocol.MAX_MB)
        free = card.get("free_mib")
        if free is None:
            notes.append(f"{key}: free memory not read; reported as none free")
            free = 0
        cards.append(
            protocol.CardReport(
                index=number,
                name=_printable(card.get("name"), str(card["vendor"])),
                vram_total_mb=total,
                vram_free_mb=max(0, min(free, total)),
            )
        )
        sources.append((str(card["vendor"]), int(card["index"])))
        kinds.append(str(card.get("kind") or "gpu"))
    memory = reading.get("memory")
    total_gb = memory.get("total_gb") if isinstance(memory, Mapping) else None
    if total_gb is None:
        notes.append("memory: not read; reported as 0 MiB total")
        ram_total, ram_free = 0, None
    else:
        ram_total = _mib(float(total_gb))
        available = memory.get("available_gb") if isinstance(memory, Mapping) else None
        ram_free = None if available is None else min(_mib(float(available)), ram_total)
    return Report(
        machine_id=machine_id,
        ram_total_mb=ram_total,
        ram_free_mb=ram_free,
        cards=tuple(cards),
        notes=tuple(notes),
        sources=tuple(sources),
        kinds=tuple(kinds),
        resources=_resources(reading, kinds, ram_total),
        host=Host.from_reading(reading.get("host")),
    )


def _resources(
    reading: Mapping[str, Any], kinds: list[str], ram_total_mb: int
) -> tuple[Mapping[str, Any], ...]:
    """The reading's resources as the report may carry them: a card's resource
    only when its index is a card the report keeps, its name printable and held
    to the protocol's, its sizes to MAX_MB. A card whose bandwidth the reader
    did not read gets its class's (:func:`_class_bandwidth`)."""
    kept: list[Mapping[str, Any]] = []
    for resource in reading.get("resources") or ():
        if not isinstance(resource, Mapping) or not isinstance(
            resource.get("kind"), str
        ):
            continue
        kind, index = resource["kind"], resource.get("index")
        if kind in ("gpu", "unified") and not (
            isinstance(index, int) and 0 <= index < len(kinds) and kinds[index] == kind
        ):
            continue
        sizes = {
            key: max(0, min(resource[key], protocol.MAX_MB))
            for key in ("total_mb", "free_mb")
            if isinstance(resource.get(key), int)
        }
        name = _printable(str(resource.get("name") or ""), kind)
        made = {**resource, **sizes, "name": name}
        if kind in CARD_KINDS and made.get("bandwidth_gbps") is None:
            made.update(_class_bandwidth(made, ram_total_mb))
        kept.append(made)
    return tuple(kept)


def _class_bandwidth(card: Mapping[str, Any], ram_total_mb: int) -> dict[str, Any]:
    """The memory bandwidth of a card's class (:func:`mcgyvr.estimate.match`),
    as an estimate, since the card is only matched to the class; nothing when
    no class names it. The reader cannot ship the table, so the agent adds it."""
    found = estimate.match(
        str(card["name"]),
        vram_mib=card.get("total_mb"),
        memory_mib=ram_total_mb or None,
    )
    if isinstance(found, estimate.NoEstimate):
        return {}
    return {"bandwidth_gbps": found.bandwidth_gbps, "bandwidth_figure": FIGURE_ESTIMATE}


def _host(host: Host | None) -> hubwire.Host | None:
    """The host a hello names: the reading's, when it names all three of its
    fields as the wire takes them; else none."""
    if host is None or host.arch is None or host.version is None:
        return None
    wire = hubwire.Host(os=host.os, arch=host.arch, version=host.version)
    try:
        wire.validate()
    except ValueError:
        return None
    return wire


def hello_frame(
    report: Report,
    message_id: str,
    *,
    agent_version: str,
    offer: protocol.Offer | None = None,
) -> str:
    """The ``hello`` frame this report makes, under ``message_id``.

    It carries the machine id, the agent version, the RAM totals, what the rig
    lends (``report.lent``) with the cards those make
    (:func:`mcgyvr.hubwire.cards_from_resources`, never every card the machine
    has: a rig that lends nothing names no card), the host beside what it lends,
    and ``offer`` when the agent advertises what it can do.
    """
    return protocol.hello(
        message_id,
        machine_id=report.machine_id,
        agent_version=agent_version,
        ram_total_mb=report.ram_total_mb,
        ram_free_mb=report.ram_free_mb,
        cards=tuple(
            protocol.CardReport(**card)
            for card in hubwire.cards_from_resources(report.lent)
        ),
        offer=offer,
        resources=report.lent,
        # The host (its version is the machine's patch level) only beside
        # what it lends, which is what the hub plans by.
        host=_host(report.host) if report.lent else None,
    )


def heartbeat_frame(report: Report, message_id: str) -> str:
    """The ``heartbeat`` frame this report makes, under ``message_id``.

    A heartbeat carries only what changes: free RAM when the report has it, the
    free MiB of each lent resource that has memory and a reading of it, and the
    card readings those make (:func:`mcgyvr.hubwire.card_readings_from`), so
    the cards match the hello's.
    """
    readings = tuple(
        hubwire.ResourceReading(kind=r.kind, index=r.index, free_mb=r.free_mb)
        for r in report.lent
        if r.kind != RESOURCE_CPU and r.free_mb is not None
    )
    return protocol.heartbeat(
        message_id,
        ram_free_mb=report.ram_free_mb,
        cards=tuple(
            protocol.CardReading(**card)
            for card in hubwire.card_readings_from(readings)
        ),
        resources=readings,
    )
