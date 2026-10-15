"""The hardware a rig reports to its hub: the product's own reading, as it is now.

Nothing here detects anything. The one reader (:mod:`mcgyvr.serving.rigscan`)
reads the machine — its short reading, :func:`~mcgyvr.serving.rigscan.read_machine`,
which asks for no raised rights and times no copy — and the machine is named on
the hub by its rig id (:func:`mcgyvr.fleet.ids.rig_id`), the digest of its
machine id and its cards: the same id the lock pins and live admission reads.

So the hub hears of the machine what the product knows of it, and the same
rules hold: a machine the product would not name (a card whose name or size
was not read, a card tool that failed) is not reported under another name —
the refusal is the rig id's own, with what the user can do. The hub binds a
rig to the first machine id it hears, so a machine whose cards change is a
different machine to it, as it is to the product.

Of a card, the report carries what the protocol has room for: its name made
printable and cut to fit, its total and free memory in MiB. A card whose free
memory was not read is reported with none free, the reading that promises
nothing; a card the reading names unsized is not a card the hub can use and
is left out, as the rig id leaves it out. Cards are numbered for the hub in
the reading's order (by vendor, then the vendor's index), so a machine of two
vendors gives each card its own number.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcgyvr.fleet import ids
from mcgyvr.rig import protocol


class HardwareError(Exception):
    """This machine could not be read, or not named; the message says why."""


@dataclass(frozen=True, kw_only=True)
class Report:
    """What a hello says of this machine, and what a heartbeat refreshes."""

    machine_id: str
    ram_total_mb: int
    ram_free_mb: int | None
    cards: tuple[protocol.CardReport, ...]
    notes: tuple[str, ...]
    #: Each reported card's vendor and the vendor's own index of it, in the
    #: order of :attr:`cards`: what a container is given the card by.
    sources: tuple[tuple[str, int], ...] = ()


def read_machine() -> Mapping[str, Any]:
    """This machine's short reading, by the one reader."""
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
    """This machine as a hello reports it, read now: by :func:`read_machine`
    unless another reader is named."""
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
    )


def hello_frame(
    report: Report,
    message_id: str,
    *,
    agent_version: str,
    offer: protocol.Offer | None = None,
) -> str:
    """The hello that says ``report``, and ``offer`` when the rig lends."""
    return protocol.hello(
        message_id,
        machine_id=report.machine_id,
        agent_version=agent_version,
        ram_total_mb=report.ram_total_mb,
        ram_free_mb=report.ram_free_mb,
        cards=report.cards,
        offer=offer,
    )


def heartbeat_frame(report: Report, message_id: str) -> str:
    """The heartbeat that refreshes the free memory ``report`` read."""
    return protocol.heartbeat(
        message_id,
        ram_free_mb=report.ram_free_mb,
        cards=tuple(
            protocol.CardReading(index=card.index, vram_free_mb=card.vram_free_mb)
            for card in report.cards
        ),
    )
