"""The one generator of invented machines for the product's tests.

A product test that needs a machine takes it from here, never from a reading of
a real one. Every machine below is invented in name and in shape: its host
names, ids, card names, vendors, processes and models are placeholders, and its
card sizes and counts are spread over what users bring rather than copied from
the machines the product was developed on. A test that runs over every shape
(``@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)``)
proves a promise for a user; a test that picks one proves it for that one kind
of machine, and says which by its label.

The names in this module are an interface other tests import. They are kept
stable: a shape may be added, but a label, a field or a function is not renamed.

Importing this module costs nothing: the product modules it reads
(:mod:`mcgyvr.detect`, :mod:`mcgyvr.scan`) are imported inside the functions
that need them, and nothing here needs a pytest fixture.

How the product's readers are fed
---------------------------------
The product reads cards with one vendor's tool (``nvidia-smi``) and reads
servers by asking each conventional port for its model list. :func:`detection`
and :func:`scan` run the product's own code with only those two seams answered
from the shape (``_run`` for the tool, ``_get_json`` for a server), so what they
return is what the product's parsers make of this machine. If a parser changes,
the answer here changes with it.
"""

from __future__ import annotations

import functools
import types
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest import mock

if TYPE_CHECKING:
    from mcgyvr.detect import Detection
    from mcgyvr.scan import Scan

#: Invented vendor labels, each mapped to whether the product's card reader
#: reads that vendor's cards. The product reads cards with one vendor's tool
#: only (see :func:`mcgyvr.detect.detect_gpus`), so a vendor is either the one
#: that tool is for (``True``) or any other (``False``). No real vendor is named.
VENDORS: Mapping[str, bool] = types.MappingProxyType(
    {"vendor-a": True, "vendor-b": False}
)

#: What the card reading tool prints for a value it cannot read.
NOT_AVAILABLE = "[N/A]"

#: The query :mod:`mcgyvr.detect` asks the card reading tool. Held to detect's
#: own command by the generator's test, which captures the command rather than
#: trusting this copy.
DETECT_QUERY = "name,memory.total"

#: The kernel release every invented machine reports: a placeholder, so no scan
#: built here carries the release of the machine the tests happen to run on.
KERNEL = "0.0.0-example"


@dataclass(frozen=True)
class Holder:
    """A process that holds memory on a card and is not the product's.

    ``name`` is an invented process name; ``mib`` is what it holds.
    """

    name: str
    mib: int


@dataclass(frozen=True)
class Card:
    """One card as the machine has it.

    ``index`` is the card's position as its own vendor's tool numbers it, so
    on a machine of two vendors each vendor counts from zero. ``name`` is an
    invented card name ("Example Card A"), never a real model. ``vendor`` is a
    key of :data:`VENDORS`. ``total_mib`` is the memory size as the reading tool
    prints it, in MiB, or ``None`` when this card's size cannot be read.
    ``holders`` are the processes already holding part of it.
    """

    index: int
    name: str
    vendor: str
    total_mib: int | None
    holders: tuple[Holder, ...] = ()

    def __post_init__(self) -> None:
        if self.vendor not in VENDORS:
            raise ValueError(f"vendor {self.vendor!r} is not one of {sorted(VENDORS)}")
        if self.total_mib is None and self.holders:
            raise ValueError(f"{self.name}: holders on a card of unreadable size")
        if self.total_mib is not None and self.used_mib > self.total_mib:
            raise ValueError(f"{self.name}: holders hold more than the card has")

    @property
    def card_reader_reads(self) -> bool:
        """Whether the product's card reader is for this card's vendor."""
        return VENDORS[self.vendor]

    @property
    def used_mib(self) -> int:
        """What the holders hold, together."""
        return sum(holder.mib for holder in self.holders)

    @property
    def free_mib(self) -> int | None:
        """The total minus what the holders hold; ``None`` when the total is."""
        if self.total_mib is None:
            return None
        return self.total_mib - self.used_mib


@dataclass(frozen=True)
class Server:
    """A model server on a machine, as the product would find it.

    ``kind`` is a backend kind :mod:`mcgyvr.detect` probes (one of the names in
    its ``PORT_CONVENTIONS``) and ``port`` the port that convention gives it, so
    the product's sweep finds it. ``host`` is the machine's host. ``models`` is
    the model list the server answers with, invented names only.
    """

    kind: str
    host: str
    port: int
    models: tuple[str, ...]


@dataclass(frozen=True)
class Shape:
    """One invented machine.

    ``label`` is short, unique and stable, and usable as a pytest id.
    ``machine_id`` is an invented id. ``host`` is an invented host name, and
    ``"localhost"`` exactly when ``local``: ``local`` is the machine the command
    runs on, otherwise one reached over the network. ``cards`` and ``servers``
    are what it has. ``card_reader_missing`` means the tool that reads cards is
    not installed on it.
    """

    label: str
    machine_id: str
    host: str
    local: bool
    cards: tuple[Card, ...]
    servers: tuple[Server, ...] = ()
    card_reader_missing: bool = False


def _query_of(arguments: Sequence[str]) -> str:
    """The field list a card reading command asks for."""
    for argument in arguments:
        if argument.startswith("--query-gpu="):
            return argument.removeprefix("--query-gpu=")
    raise ValueError(f"no --query-gpu= in {list(arguments)}")


def _field(card: Card, field: str) -> str:
    def mib(value: int | None) -> str:
        return NOT_AVAILABLE if value is None else str(value)

    if field == "index":
        return str(card.index)
    if field == "name":
        return card.name
    if field == "memory.total":
        return mib(card.total_mib)
    if field == "memory.used":
        return mib(None if card.total_mib is None else card.used_mib)
    if field == "memory.free":
        return mib(card.free_mib)
    raise ValueError(f"the invented card reader does not answer {field!r}")


def nvidia_smi_text(cards: Sequence[Card], query: str = DETECT_QUERY) -> str:
    """What the card reading tool prints for the cards it can read.

    The format is the tool's, as the product asks for it: one line per card,
    the fields of ``query`` in order, comma separated, with
    ``--format=csv,noheader,nounits``. Cards of a vendor the tool is not for
    are not printed. A card whose size cannot be read prints ``[N/A]`` for its
    memory fields. With nothing to print the text is empty.

    ``query`` defaults to :mod:`mcgyvr.detect`'s; :mod:`mcgyvr.scan` asks for
    more fields (its ``NVIDIA_SMI_QUERY``). A field this does not know is
    refused by name.
    """
    fields = [field.strip() for field in query.split(",")]
    lines = [
        ", ".join(_field(card, field) for field in fields)
        for card in cards
        if card.card_reader_reads
    ]
    return "".join(f"{line}\n" for line in lines)


def _reader_answer(machine: Shape, arguments: Sequence[str]) -> str | None:
    """What the card reading tool answers on this machine: None when absent."""
    if machine.card_reader_missing:
        return None
    return nvidia_smi_text(machine.cards, query=_query_of(arguments))


def detection(machine: Shape) -> Detection:
    """What :func:`mcgyvr.detect.detect` reports, run for this machine.

    The product's own ``detect`` runs with its seams answered from the shape:
    the card reading tool answers :func:`nvidia_smi_text` (or is absent), and a
    server answers its model list on its conventional port. The sweep asks the
    machine's host. RAM, CPU count and docker are not part of a shape and are
    reported as not determined.

    Detection reads cards only on the machine it runs on. For a machine that is
    not ``local`` the command runs elsewhere, on a machine modelled without a
    card reader, so no card is reported and the note says the tool is absent:
    that is what the product reports of a remote machine's cards.
    """
    from mcgyvr import detect

    def run(command: Sequence[str]) -> str | None:
        if not machine.local or command[0] != "nvidia-smi":
            return None
        return _reader_answer(machine, command[1:])

    def get_json(url: str, timeout: float) -> Any | None:
        asked = urllib.parse.urlsplit(url)
        for server in machine.servers:
            if (
                asked.hostname == server.host
                and asked.port == server.port
                and asked.path == "/v1/models"
            ):
                return {
                    "object": "list",
                    "data": [{"id": m, "object": "model"} for m in server.models],
                }
        return None

    def ram() -> tuple[float | None, str]:
        return None, "not determined — an invented machine states no RAM"

    def docker() -> tuple[bool, str]:
        return False, "an invented machine has no docker daemon"

    no_cpu_count = types.SimpleNamespace(cpu_count=lambda: None)
    with (
        mock.patch.object(detect, "_run", run),
        mock.patch.object(detect, "_get_json", get_json),
        mock.patch.object(detect, "detect_ram_gb", ram),
        mock.patch.object(detect, "detect_docker", docker),
        mock.patch.object(detect, "os", no_cpu_count),
    ):
        return detect.detect(detect.targets_for((machine.host,)))


def scan(machine: Shape) -> Scan:
    """What :mod:`mcgyvr.scan` reports of this machine.

    The cards go through the product's own reader (``_scan_gpus``) with the
    card reading tool answering :func:`nvidia_smi_text` for scan's query, so
    its notes on an unreadable row or an absent tool are the product's. The
    machine is the shape's id and host with a placeholder kernel. Memory, CPU,
    bandwidth and disk are not part of a shape and are left absent. A machine
    that is not ``local`` is scanned on the far end and read back through
    ``Scan.from_json``, as the product's remote transport does.
    """
    from mcgyvr import scan as product

    def run(binary: str, *arguments: str, timeout: float = 0.0) -> str | None:
        if binary != "nvidia-smi":
            return None
        return _reader_answer(machine, arguments)

    with mock.patch.object(product, "_run", run):
        gpus, facts, notes = product._scan_gpus()
    measured = product.Scan(
        machine=product.Machine(
            id=machine.machine_id, host=machine.host, kernel=KERNEL
        ),
        gpus=gpus,
        notes=notes,
        facts=(product.Fact(field="machine.id", how="invented"), *facts),
    )
    if machine.local:
        return measured
    return product.Scan.from_json(measured.to_json())


# The invented cards. Sizes are MiB as the reading tool prints them, spread
# from 4 to 48 GB, some exactly the nominal size and some a little under it,
# as real cards read.
_A = "vendor-a"
_B = "vendor-b"


def _card(index: int, name: str, total_mib: int | None, vendor: str = _A) -> Card:
    return Card(index=index, name=name, vendor=vendor, total_mib=total_mib)


@functools.cache
def shapes() -> tuple[Shape, ...]:
    """Every invented machine, in a stable order.

    Covers: no card and no server; no card with a server here; no card with a
    server elsewhere; one card; four equal cards; two cards of different sizes;
    several cards of several sizes; a busy card; a card of unreadable size
    beside a readable one; cards all of a vendor the reader is not for; two
    vendors mixed; cards without the card reading tool; and the same cards on
    this machine and on one over the network.
    """
    from mcgyvr.detect import PORT_CONVENTIONS

    (first, first_port, _), (second, second_port, _) = PORT_CONVENTIONS[:2]
    small, medium, large = (
        "example-model-small",
        "example-model-medium",
        "example-model-large",
    )
    here = "localhost"
    far = "box-7.example"
    documented = "192.0.2.10"
    same_cards = (
        _card(0, "Example Card B", 8188),
        _card(1, "Example Card B", 8188),
        _card(2, "Example Card G", 49140),
    )
    return (
        Shape("bare", "machine-0f3a", here, True, (), card_reader_missing=True),
        Shape(
            "bare-local-server",
            "machine-1b7c",
            here,
            True,
            (),
            servers=(Server(first, here, first_port, (small,)),),
            card_reader_missing=True,
        ),
        Shape(
            "bare-remote-server",
            "machine-2d4e",
            far,
            False,
            (),
            servers=(Server(second, far, second_port, (small, medium)),),
            card_reader_missing=True,
        ),
        Shape(
            "one-card", "machine-3e91", here, True, (_card(0, "Example Card A", 16376),)
        ),
        Shape(
            "four-equal",
            "machine-4a02",
            here,
            True,
            tuple(_card(i, "Example Card C", 24564) for i in range(4)),
        ),
        Shape(
            "two-sizes",
            "machine-5c13",
            here,
            True,
            (_card(0, "Example Card B", 8188), _card(1, "Example Card D", 20475)),
        ),
        Shape(
            "several-sizes",
            "machine-6d24",
            here,
            True,
            (
                _card(0, "Example Card E", 4096),
                _card(1, "Example Card F", 10240),
                _card(2, "Example Card A", 16311),
                _card(3, "Example Card C", 24564),
                _card(4, "Example Card G", 49140),
            ),
        ),
        Shape(
            "busy-card",
            "machine-7e35",
            here,
            True,
            (
                Card(
                    index=0,
                    name="Example Card H",
                    vendor=_A,
                    total_mib=32607,
                    holders=(
                        Holder("example-renderer", 2750),
                        Holder("example-notebook", 1210),
                    ),
                ),
            ),
            servers=(Server(first, here, first_port, (large,)),),
        ),
        Shape(
            "unreadable-size",
            "machine-8f46",
            here,
            True,
            (_card(0, "Example Card A", 16376), _card(1, "Example Card J", None)),
        ),
        Shape(
            "other-vendor",
            "machine-9a57",
            here,
            True,
            (
                _card(0, "Example Card K", 16368, _B),
                _card(1, "Example Card K", 16368, _B),
            ),
        ),
        Shape(
            "mixed-vendors",
            "machine-a068",
            here,
            True,
            (
                _card(0, "Example Card F", 10240),
                _card(0, "Example Card L", 8176, _B),
                _card(1, "Example Card C", 24564),
            ),
        ),
        Shape(
            "no-reader",
            "machine-b179",
            here,
            True,
            (
                _card(0, "Example Card D", 20475),
                _card(1, "Example Card D", 20475),
                _card(2, "Example Card E", 4096),
            ),
            card_reader_missing=True,
        ),
        Shape("same-cards-here", "machine-c28a", here, True, same_cards),
        Shape(
            "same-cards-there",
            "machine-d39b",
            documented,
            False,
            same_cards,
            servers=(Server(first, documented, first_port, (medium,)),),
        ),
    )


def shape(label: str) -> Shape:
    """The invented machine of this label. An unknown label names the known ones."""
    for machine in shapes():
        if machine.label == label:
            return machine
    known = ", ".join(machine.label for machine in shapes())
    raise KeyError(f"no invented machine {label!r}; the known ones: {known}")
