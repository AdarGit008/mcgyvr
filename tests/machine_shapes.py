"""The one generator of invented machines for the product's tests.

A product test that needs a machine takes it from here, never from a reading of
a real one. Every machine below is invented in name and in shape: its host
names, ids, card names, vendors, processes and models are placeholders, and its
card sizes and counts are spread over what users bring rather than copied from
the machines the product was developed on. A test that runs over every shape
(``@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)``)
proves a promise for a user; a test that picks one proves it for that one kind
of machine, and says which by its label.

The names in :data:`__all__` are an interface other tests import. They are kept
stable: a shape may be added, but a label, a field or a function is not renamed.
Every class is built by keyword only, and every function takes its machine
positionally only, so a field or a keyword may be added later without breaking
a caller.

Importing this module costs nothing: the product modules it reads
(:mod:`mcgyvr.detect`, :mod:`mcgyvr.scan`) are imported inside the functions
that need them, and nothing here needs a pytest fixture.

How the product's readers are fed
---------------------------------
The product reads cards with one vendor's tool and reads servers by asking each
conventional port for its model list. :func:`detection` and :func:`scan` run
the product's own code with only those two seams answered from the shape
(``_run`` for the tool, ``_get_json`` for a server), so what they return is
what the product's parsers make of this machine. If a parser changes, the
answer here changes with it.

How the card sizes are made
---------------------------
No size in MiB is typed in. Each invented card model has a nominal size in GiB and a
position in the table of models (:data:`_MODELS`), and its figures are
computed from those two by one rule:

- ``total_mib`` is the nominal size times 1024, less a shortfall: none for a
  model at an even position, ``(29 * position) % 97`` MiB for one at an odd
  position;
- ``reserved_mib`` (memory the card keeps for itself) is ``64 + 8 * position``
  MiB for a model whose position is a multiple of three, and none otherwise.

The nominal sizes run from small to large and are not the sizes of any card
line a reader would recognise.
"""

from __future__ import annotations

import dataclasses
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

__all__ = [
    "VENDORS",
    "Card",
    "Holder",
    "Server",
    "Shape",
    "card_reader_text",
    "detection",
    "scan",
    "shape",
    "shapes",
    "with_server",
]

#: Invented vendor labels, each mapped to whether the product's card reader
#: reads that vendor's cards. The product reads cards with one vendor's tool
#: only (see :func:`mcgyvr.detect.detect_gpus`), so a vendor is either the one
#: that tool is for (``True``) or any other (``False``). No real vendor is named.
VENDORS: Mapping[str, bool] = types.MappingProxyType(
    {"vendor-a": True, "vendor-b": False}
)

# What the card reading tool prints for a value it cannot read.
_NOT_AVAILABLE = "[N/A]"

# The query mcgyvr.detect asks the card reading tool. Held to detect's own
# command by the generator's test, which captures the command rather than
# trusting this copy.
_DETECT_QUERY = "name,memory.total"

# The kernel release every invented machine reports: a stand-in, so no scan
# built here carries the release of the machine the tests happen to run on.
_KERNEL = "0.0.0-example"

# The host name that means "the machine the command runs on".
_LOCALHOST = "localhost"


@dataclass(frozen=True, kw_only=True)
class Holder:
    """A process that holds memory on a card and is not the product's.

    ``name`` is an invented process name; ``mib`` is what it holds; ``pid`` is
    an invented process id, positive and unique on its card, so that a reader
    of the card tool's process listing can be served later. The listing itself
    is not answered today: a reader that asks for it is refused by name. A
    negative ``mib`` or a non-positive ``pid`` is refused by name.
    """

    name: str
    mib: int
    pid: int

    def __post_init__(self) -> None:
        if self.mib < 0:
            raise ValueError(
                f"holder {self.name!r} holds {self.mib} MiB, a negative amount"
            )
        if self.pid <= 0:
            raise ValueError(
                f"holder {self.name!r}: process id {self.pid} is not positive"
            )


@dataclass(frozen=True, kw_only=True)
class Card:
    """One card as the machine has it.

    ``index`` is the card's position as its own vendor's tool numbers it, so
    on a machine of two vendors each vendor counts from zero. ``name`` is an
    invented card name ("Example Card A"), never a real model; a name with a
    line break is refused, as the card tool prints one line per card, and a
    name with a comma is refused too, as a limit of this helper and not of the
    product, whose readers take a comma in a name as part of the name.
    ``vendor`` is a
    key of :data:`VENDORS`. ``total_mib`` is the memory size as the card tool
    prints it, in MiB, or ``None`` when this card's size cannot be read.
    ``holders`` are the processes already holding part of it.
    ``reserved_mib`` is memory the card keeps for itself and gives to no
    process.
    """

    index: int
    name: str
    vendor: str
    total_mib: int | None
    holders: tuple[Holder, ...] = ()
    reserved_mib: int = 0

    def __post_init__(self) -> None:
        if "," in self.name:
            raise ValueError(
                f"card {self.index} ({self.name!r}): a comma in its name, which "
                "this helper does not model"
            )
        if "".join(self.name.splitlines()) != self.name:
            raise ValueError(
                f"card {self.index} ({self.name!r}): a line break in its name, "
                "which this helper does not model"
            )
        where = f"card {self.index} ({self.name})"
        if self.vendor not in VENDORS:
            raise ValueError(
                f"{where}: vendor {self.vendor!r} is not one of {sorted(VENDORS)}"
            )
        if self.index < 0:
            raise ValueError(f"{where}: a negative index")
        if self.total_mib is not None and self.total_mib < 0:
            raise ValueError(f"{where}: a negative total of {self.total_mib} MiB")
        if self.reserved_mib < 0:
            raise ValueError(f"{where}: a negative reserve of {self.reserved_mib} MiB")
        pids = [holder.pid for holder in self.holders]
        if len(pids) != len(set(pids)):
            raise ValueError(f"{where}: two holders share a process id in {pids}")
        if self.total_mib is None:
            if self.holders:
                raise ValueError(f"{where}: holders on a card of unreadable size")
            if self.reserved_mib:
                raise ValueError(f"{where}: a reserve on a card of unreadable size")
            return
        if self.reserved_mib > self.total_mib:
            raise ValueError(
                f"{where}: keeps {self.reserved_mib} MiB for itself, more than "
                f"its total of {self.total_mib} MiB"
            )
        room = self.total_mib - self.reserved_mib
        if self.used_mib > room:
            raise ValueError(
                f"{where}: holders hold {self.used_mib} MiB, more than the "
                f"{room} MiB the card has for them (total {self.total_mib}, "
                f"reserved {self.reserved_mib})"
            )

    @property
    def card_reader_reads(self) -> bool:
        """Whether the product's card reader is for this card's vendor."""
        return VENDORS[self.vendor]

    @property
    def used_mib(self) -> int:
        """What the holders hold, together (the reserve is not in it)."""
        return sum(holder.mib for holder in self.holders)

    @property
    def free_mib(self) -> int | None:
        """What the card tool prints as free: the total less the reserve and
        less what the holders hold; ``None`` when the total is."""
        if self.total_mib is None:
            return None
        return self.total_mib - self.reserved_mib - self.used_mib


@dataclass(frozen=True, kw_only=True)
class Server:
    """A model server on a machine, as the product would find it.

    ``kind`` is a backend kind the product probes (a name in
    :data:`mcgyvr.detect.PORT_CONVENTIONS`) and ``port`` the port that
    convention gives it, so the product's sweep finds it. ``host`` is where the
    server listens; today it must be its machine's host (a :class:`Shape`
    refuses any other), and it is kept as a field so that a later version may
    model a machine that reaches servers elsewhere. ``models`` is the model
    list the server answers with, invented names only.
    """

    kind: str
    host: str
    port: int
    models: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class Shape:
    """One invented machine.

    ``label`` is short and stable, unique among :func:`shapes`, and usable as
    a pytest id (a copy made by :func:`with_server` keeps it).
    ``machine_id`` is an invented id. ``local`` means the machine the command
    runs on. An invented local machine is named ``"localhost"``, so ``local``
    holds exactly when ``host`` is ``"localhost"``; any other host is a machine
    reached over the network, by an invented name or a documentation address.
    ``cards`` and ``servers`` are what the machine has. ``card_reader_missing``
    means the tool that reads cards is not installed on it.

    A shape that contradicts itself is refused by name: an empty host; a host
    other than ``"localhost"`` that the product holds to be this machine (its
    :attr:`mcgyvr.detect.Backend.is_local` rule, read when the shape is made);
    ``local`` against ``host``; a server on another host than the machine's; a
    server of a kind or on a port the product does not probe; two servers on
    one port; two cards of one vendor with the same index.
    """

    label: str
    machine_id: str
    host: str
    local: bool
    cards: tuple[Card, ...]
    servers: tuple[Server, ...] = ()
    card_reader_missing: bool = False

    def __post_init__(self) -> None:
        from mcgyvr.detect import PORT_CONVENTIONS, Backend

        where = f"shape {self.label!r}"
        if not self.host:
            raise ValueError(f"{where}: an empty host")
        held_local = Backend(
            name=self.label, base_url="", api="", models=(), how="", host=self.host
        ).is_local
        if held_local and self.host != _LOCALHOST:
            raise ValueError(
                f"{where}: host {self.host!r} is one the product holds to be this "
                f"machine; an invented local machine is named {_LOCALHOST!r}"
            )
        if self.local != (self.host == _LOCALHOST):
            raise ValueError(
                f"{where}: local={self.local} contradicts host {self.host!r}; "
                f"an invented local machine is named {_LOCALHOST!r}"
            )
        ports = {kind: port for kind, port, _ in PORT_CONVENTIONS}
        for server in self.servers:
            if server.host != self.host:
                raise ValueError(
                    f"{where}: a server on host {server.host!r}, not on the "
                    f"machine's host {self.host!r}"
                )
            if server.kind not in ports:
                raise ValueError(
                    f"{where}: server kind {server.kind!r} is not one the "
                    f"product probes: {sorted(ports)}"
                )
            if server.port != ports[server.kind]:
                raise ValueError(
                    f"{where}: a {server.kind} server on port {server.port}; the "
                    f"product probes {server.kind} on port {ports[server.kind]} only"
                )
        used = [server.port for server in self.servers]
        if len(used) != len(set(used)):
            raise ValueError(f"{where}: two servers on one port in {used}")
        seen: set[tuple[str, int]] = set()
        for card in self.cards:
            key = (card.vendor, card.index)
            if key in seen:
                raise ValueError(
                    f"{where}: two {card.vendor} cards with index {card.index}"
                )
            seen.add(key)

    @property
    def readable_cards(self) -> tuple[Card, ...]:
        """The cards the product's card reader reads on this machine, in order.

        A card is read when all three hold, as the product's readers behave:

        - the card tool is present (``card_reader_missing`` is false): without
          it the readers report no card and say the tool is absent;
        - the card is of the vendor the tool is for: the tool prints no other
          vendor's cards;
        - its size is readable (``total_mib`` is not ``None``): a row that
          prints ``[N/A]`` for memory is dropped by :mod:`mcgyvr.scan`, with a
          note naming the row.

        These are the cards a scan of the machine reports, the machine being
        scanned where it is. :mod:`mcgyvr.detect` lists more of them: see
        :attr:`detected_cards`.
        """
        if self.card_reader_missing:
            return ()
        return tuple(
            card
            for card in self.cards
            if card.card_reader_reads and card.total_mib is not None
        )

    @property
    def detected_cards(self) -> tuple[Card, ...]:
        """The cards :mod:`mcgyvr.detect` lists when it runs on this machine.

        The first two conditions of :attr:`readable_cards` hold, and the third
        does not apply: a card whose size the tool prints as ``[N/A]`` is
        listed with no size (``vram_gb`` is ``None``) and a note that begins
        with :data:`mcgyvr.detect.GPU_SIZE_UNDETERMINED` and names the card.
        So these are the readable cards and the cards of unreadable size of the
        tool's vendor, in the order the tool prints them. What
        :func:`detection` reports of a machine that is not local is another
        matter; see there.
        """
        if self.card_reader_missing:
            return ()
        return tuple(card for card in self.cards if card.card_reader_reads)


def _query_of(arguments: Sequence[str]) -> str:
    """The field list a card reading command asks for."""
    for argument in arguments:
        if argument.startswith("--query-gpu="):
            return argument.removeprefix("--query-gpu=")
        if argument.startswith("--query-compute-apps="):
            raise ValueError(
                "the invented card reader does not answer the process listing "
                f"({argument}); a holder's pid is there for when it does"
            )
    raise ValueError(f"no --query-gpu= in {list(arguments)}")


def _field(card: Card, field: str) -> str:
    def mib(value: int | None) -> str:
        return _NOT_AVAILABLE if value is None else str(value)

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


def card_reader_text(cards: Sequence[Card], /, *, query: str = _DETECT_QUERY) -> str:
    """What the card reading tool prints for the cards it can read.

    The format is the tool's, as the product asks for it: one line per card,
    the fields of ``query`` in order, comma separated, as its
    ``--format=csv,noheader,nounits`` prints them. Cards of a vendor the tool
    is not for are not printed. A card whose size cannot be read prints
    ``[N/A]`` for its memory fields. With nothing to print the text is empty.

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
    query = _query_of(arguments)
    if machine.card_reader_missing:
        return None
    return card_reader_text(machine.cards, query=query)


def detection(machine: Shape, /) -> Detection:
    """What :func:`mcgyvr.detect.detect` reports, run as this helper models it.

    The product's own ``detect`` runs, sweeping only ``machine.host``, with its
    seams answered from the shape: a server answers its model list on its
    conventional port, and the card tool answers :func:`card_reader_text` (or
    is absent). RAM, CPU count and docker are not part of a shape and are
    reported as not determined.

    Where the command runs is the helper's model, not a statement about the
    product. The product's ``detect`` reads the cards of whatever machine it
    runs on, whichever host it sweeps. So today:

    - for a ``local`` machine the command runs on that machine: the card tool
      answers for its cards, and the sweep asks ``localhost``. The cards
      reported are :attr:`Shape.detected_cards`: a card whose size the tool
      prints as not available is listed with no size, and a note that begins
      with :data:`mcgyvr.detect.GPU_SIZE_UNDETERMINED` names it;
    - for a machine that is not ``local`` the command runs on another machine
      that has no card tool and no server of its own, and sweeps the far
      machine's host: its servers are found, no card is reported, and the
      notes say the card tool is absent.

    A later version may add machines the same command sweeps as well, as
    ``detection(machine, reached=())``; with nothing reached that call means
    exactly what this one means today.
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


def scan(machine: Shape, /) -> Scan:
    """What :mod:`mcgyvr.scan` reports of this machine, scanned where it is.

    The cards go through the product's own reader (``_scan_gpus``) with the
    card reading tool answering :func:`card_reader_text` for scan's query, so
    its notes on an unreadable row or an absent tool are the product's. The
    machine is the shape's id and host with a stand-in kernel. Memory, CPU,
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
            id=machine.machine_id, host=machine.host, kernel=_KERNEL
        ),
        gpus=gpus,
        notes=notes,
        facts=(product.Fact(field="machine.id", how="invented"), *facts),
    )
    if machine.local:
        return measured
    return product.Scan.from_json(measured.to_json())


def with_server(
    machine: Shape,
    /,
    *,
    kind: str,
    models: Sequence[str],
    port: int | None = None,
) -> Shape:
    """A copy of the machine with one more server, on the machine's host.

    ``kind`` is a kind the product probes; ``port`` defaults to the port the
    product's convention gives that kind. ``models`` is the invented model
    list the server answers with. The copy keeps the machine's label, so it is
    not the machine :func:`shape` gives for that label. A kind
    the product does not probe, a port it does not ask that kind on, or a port
    already taken is refused by name, as :class:`Shape` refuses it.
    """
    from mcgyvr.detect import PORT_CONVENTIONS

    if isinstance(models, str):
        raise TypeError(f"models is a sequence of model names, not {models!r}")
    if port is None:
        ports = {known: number for known, number, _ in PORT_CONVENTIONS}
        if kind not in ports:
            raise ValueError(
                f"server kind {kind!r} is not one the product probes: {sorted(ports)}"
            )
        port = ports[kind]
    server = Server(kind=kind, host=machine.host, port=port, models=tuple(models))
    return dataclasses.replace(machine, servers=(*machine.servers, server))


# The invented card models: (name, vendor, nominal size in GiB, or None for a
# card whose size the tool cannot read). A model's position in this table is
# what the size rule in the module docstring computes from.
_A = "vendor-a"
_B = "vendor-b"
_MODELS: tuple[tuple[str, str, int | None], ...] = (
    ("Example Card A", _A, 14),
    ("Example Card B", _A, 7),
    ("Example Card C", _A, 28),
    ("Example Card D", _A, 18),
    ("Example Card E", _A, 9),
    ("Example Card F", _A, 44),
    ("Example Card G", _A, 56),
    ("Example Card H", _A, 36),
    ("Example Card J", _A, None),
    ("Example Card K", _B, 30),
    ("Example Card L", _B, 26),
)


def _total_mib(nominal_gib: int, position: int) -> int:
    shortfall = 0 if position % 2 == 0 else (29 * position) % 97
    return nominal_gib * 1024 - shortfall


def _reserved_mib(position: int) -> int:
    return 64 + 8 * position if position % 3 == 0 else 0


def _card(index: int, name: str, *holders: Holder) -> Card:
    position = next(i for i, model in enumerate(_MODELS) if model[0] == name)
    _, vendor, nominal = _MODELS[position]
    if nominal is None:
        return Card(index=index, name=name, vendor=vendor, total_mib=None)
    return Card(
        index=index,
        name=name,
        vendor=vendor,
        total_mib=_total_mib(nominal, position),
        holders=holders,
        reserved_mib=_reserved_mib(position),
    )


@functools.cache
def shapes() -> tuple[Shape, ...]:
    """Every invented machine, in a stable order.

    Covers: no card and no server; no card with a server here; no card with a
    server elsewhere; one card; four equal cards; two cards of different sizes;
    several cards of several sizes; a busy card; a busy card beside a free one;
    a card of unreadable size beside a readable one, in either order; cards
    all of a vendor the reader is not for, with the card tool and without it;
    two vendors mixed; cards without the card reading tool; and the same cards
    on this machine and on one over the network.
    """
    from mcgyvr.detect import PORT_CONVENTIONS

    (first, first_port, _), (second, second_port, _) = PORT_CONVENTIONS[:2]
    small, medium, large = (
        "example-model-small",
        "example-model-medium",
        "example-model-large",
    )
    here = _LOCALHOST
    far = "box-7.example"
    documented = "192.0.2.10"

    def server(kind: str, host: str, port: int, *models: str) -> Server:
        return Server(kind=kind, host=host, port=port, models=models)

    def local(label: str, machine_id: str, *cards: Card, **extra: Any) -> Shape:
        return Shape(
            label=label,
            machine_id=machine_id,
            host=here,
            local=True,
            cards=cards,
            **extra,
        )

    same_cards = (
        _card(0, "Example Card E"),
        _card(1, "Example Card E"),
        _card(2, "Example Card G"),
    )
    return (
        local("bare", "machine-0f3a", card_reader_missing=True),
        local(
            "bare-local-server",
            "machine-1b7c",
            servers=(server(first, here, first_port, small),),
            card_reader_missing=True,
        ),
        Shape(
            label="bare-remote-server",
            machine_id="machine-2d4e",
            host=far,
            local=False,
            cards=(),
            servers=(server(second, far, second_port, small, medium),),
            card_reader_missing=True,
        ),
        local("one-card", "machine-3e91", _card(0, "Example Card A")),
        local(
            "four-equal",
            "machine-4a02",
            *(_card(i, "Example Card C") for i in range(4)),
        ),
        local(
            "two-sizes",
            "machine-5c13",
            _card(0, "Example Card B"),
            _card(1, "Example Card D"),
        ),
        local(
            "several-sizes",
            "machine-6d24",
            _card(0, "Example Card B"),
            _card(1, "Example Card E"),
            _card(2, "Example Card A"),
            _card(3, "Example Card C"),
            _card(4, "Example Card F"),
        ),
        local(
            "busy-card",
            "machine-7e35",
            _card(
                0,
                "Example Card H",
                Holder(name="example-renderer", mib=2750, pid=4101),
                Holder(name="example-notebook", mib=1210, pid=4187),
            ),
            servers=(server(first, here, first_port, large),),
        ),
        local(
            "busy-beside-free",
            "machine-e4ac",
            _card(
                0, "Example Card A", Holder(name="example-trainer", mib=9000, pid=5230)
            ),
            _card(1, "Example Card A"),
        ),
        local(
            "unreadable-size",
            "machine-8f46",
            _card(0, "Example Card A"),
            _card(1, "Example Card J"),
        ),
        local(
            "other-vendor",
            "machine-9a57",
            _card(0, "Example Card K"),
            _card(1, "Example Card K"),
        ),
        local(
            "other-vendor-no-reader",
            "machine-f5bd",
            _card(0, "Example Card L"),
            _card(1, "Example Card L"),
            card_reader_missing=True,
        ),
        local(
            "mixed-vendors",
            "machine-a068",
            _card(0, "Example Card E"),
            _card(0, "Example Card K"),
            _card(1, "Example Card G"),
        ),
        local(
            "no-reader",
            "machine-b179",
            _card(0, "Example Card D"),
            _card(1, "Example Card D"),
            _card(2, "Example Card B"),
            card_reader_missing=True,
        ),
        local("same-cards-here", "machine-c28a", *same_cards),
        Shape(
            label="same-cards-there",
            machine_id="machine-d39b",
            host=documented,
            local=False,
            cards=same_cards,
            servers=(server(first, documented, first_port, medium),),
        ),
        local(
            "unreadable-size-first",
            "machine-e6ce",
            _card(0, "Example Card J"),
            _card(1, "Example Card A"),
        ),
    )


def shape(label: str, /) -> Shape:
    """The invented machine of this label. An unknown label names the known ones."""
    for machine in shapes():
        if machine.label == label:
            return machine
    known = ", ".join(machine.label for machine in shapes())
    raise KeyError(f"no invented machine {label!r}; the known ones: {known}")
