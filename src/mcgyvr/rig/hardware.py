"""The hardware a rig reports to its hub: the product's own reading, as it is now.

Nothing here detects anything. The machine reader the door ships
(``serving/gate-scripts/machine-read.sh``) reads the machine, run here as the
door runs it on any machine (``bash -s``, the script on stdin);
:func:`mcgyvr.fleet.machine.parse` reads what it prints; and the machine is
named on the hub by its short id (:func:`mcgyvr.fleet.machine.short_id`), the
digest of its machine id and its cards. Memory is :func:`mcgyvr.scan.read_memory`.

So the hub hears of the machine what the product knows of it, and the same
rules hold: a machine the product would not name (a card whose name or size
was not read, a card tool that failed) is not reported under another name —
the refusal is the short id's own, with what the user can do. The hub binds a
rig to the first machine id it hears, so a machine whose cards change is a
different machine to it, as it is to the product.

Of a card, the report carries what the protocol has room for: its name made
printable and cut to fit, its total and free memory in MiB. A card whose free
memory was not read is reported with none free, the reading that promises
nothing; a card the reading names unsized is not a card the hub can use and
is left out, as the short id leaves it out. Cards are numbered for the hub in
the reading's order (by vendor, then the vendor's index), so a machine of two
vendors gives each card its own number.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from mcgyvr import scan
from mcgyvr.fleet import machine
from mcgyvr.rig import protocol
from mcgyvr.serving.run import GATE_SCRIPTS

#: The machine reader, as the door ships it.
READER = GATE_SCRIPTS / "machine-read.sh"
#: How long the reader may take, in seconds, before the reading is refused.
READER_TIMEOUT_S = 60.0
#: The variables the reader takes for the product's tests only.
_TEST_VARIABLES = "MCGYVR_TEST_"


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


def run_reader() -> str:
    """What the machine reader prints for this machine, or :class:`HardwareError`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_TEST_VARIABLES)}
    try:
        done = subprocess.run(
            ["bash", "-s"],
            input=READER.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            timeout=READER_TIMEOUT_S,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HardwareError(
            f"the machine reader did not finish in {READER_TIMEOUT_S:g} s"
        ) from exc
    except OSError as exc:
        raise HardwareError(f"the machine reader could not run: {exc}") from exc
    if done.returncode != 0:
        raise HardwareError(f"the machine reader exited {done.returncode}")
    return done.stdout


def _printable(name: str | None, vendor: str) -> str:
    kept = "".join(
        char for char in (name or "") if protocol.CARD_NAME.fullmatch(char)
    ).strip()
    return kept[: protocol.CARD_NAME_MAX] or f"{vendor} card"


def _mib(gb: float) -> int:
    return max(0, min(round(gb * 1024), protocol.MAX_MB))


def read(
    *,
    reader: Callable[[], str] | None = None,
    memory: Callable[[], scan.Memory | None] | None = None,
) -> Report:
    """This machine as a hello reports it, read now: by :func:`run_reader` and
    :func:`mcgyvr.scan.read_memory` unless others are named."""
    reading = machine.parse((reader or run_reader)())
    try:
        machine_id = machine.short_id(reading)
    except ValueError as refusal:
        raise HardwareError(f"this machine has no short id: {refusal}") from refusal
    notes: list[str] = []
    sized = [card for card in reading.cards if card.key not in reading.unsized]
    if len(sized) > protocol.MAX_CARDS:
        notes.append(
            f"{len(sized)} cards read; a report carries {protocol.MAX_CARDS}, so "
            "the rest are not reported"
        )
        sized = sized[: protocol.MAX_CARDS]
    cards: list[protocol.CardReport] = []
    sources: list[tuple[str, int]] = []
    for number, card in enumerate(sized):
        total = min(card.total_mib or 0, protocol.MAX_MB)
        free = card.free_mib
        if free is None:
            notes.append(f"{card.key}: free memory not read; reported as none free")
            free = 0
        cards.append(
            protocol.CardReport(
                index=number,
                name=_printable(card.name, card.vendor),
                vram_total_mb=total,
                vram_free_mb=max(0, min(free, total)),
            )
        )
        sources.append((card.vendor, card.index))
    read_memory = (memory or scan.read_memory)()
    if read_memory is None:
        notes.append("memory: not read; reported as 0 MiB total")
        ram_total, ram_free = 0, None
    else:
        ram_total = _mib(read_memory.total_gb)
        ram_free = min(_mib(read_memory.available_gb), ram_total)
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
