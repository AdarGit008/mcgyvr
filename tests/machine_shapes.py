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
The product reads cards with its one reader (:mod:`mcgyvr.serving.rigscan`)
and reads servers by asking each conventional port for its model list.
:func:`detection` and :func:`scan` run the product's own code with only those
two seams answered from the shape (the reader's ``_run`` for the tool, over an
empty file root, and ``_get_json`` for a server), so what they return is what
the product's parsers make of this machine. If a parser changes, the answer
here changes with it.

Machines by system
------------------
:func:`host_shapes` are machines with their operating system (:class:`HostShape`):
Macs whose GPU shares the memory, Windows machines, and a Linux box. Each says
its memory and CPU in so many MiB and cores, typed in as invented figures, and
its cards come from the same table of models as below. Their tools answer from
one table (:func:`host_tools`) and their files lie under a populated test root
(:func:`host_files`); :func:`host_reading`, :func:`host_scan` and
:func:`host_detection` run the product's own reader over them in this process,
and :func:`tests.machinereader.stage_host` sets them out for the shipped reader.

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
import json
import tempfile
import types
import urllib.parse
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

if TYPE_CHECKING:
    from mcgyvr.detect import Detection
    from mcgyvr.scan import Scan

__all__ = [
    "CARD_TOOL_PLACES",
    "PCI_VENDOR_IDS",
    "VENDORS",
    "Card",
    "Holder",
    "HostShape",
    "Server",
    "Shape",
    "card_reader_text",
    "detection",
    "device_id",
    "host_detection",
    "host_files",
    "host_reading",
    "host_scan",
    "host_scan_document",
    "host_shape",
    "host_shapes",
    "host_tools",
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

# The query the product's one reader asks the card reading tool. Held to the
# reader's own command by the generator's test, which captures the command
# rather than trusting this copy.
_DETECT_QUERY = "index,memory.total,memory.used,memory.free,name"

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
    if machine.card_reader_missing or "pci.bus_id" in query:
        return None
    return card_reader_text(machine.cards, query=query)


def detection(machine: Shape, /, *, reached: Sequence[Shape] = ()) -> Detection:
    """What :func:`mcgyvr.detect.detect` reports, run as this helper models it.

    The product's own ``detect`` runs, sweeping ``machine.host`` and then the
    host of each machine in ``reached``, with its seams answered from the
    shapes: a server answers its model list on its conventional port, and the
    card tool answers :func:`card_reader_text` (or is absent). RAM, CPU count
    and docker are not part of a shape and are reported as not determined.

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

    ``reached`` are further machines the same command sweeps, in the order
    given, after ``machine``. Each is a machine over the network: its servers
    are found, named by its host as the product names them when a sweep covers
    more than one host, and none of its cards is reported, since the card tool
    reads only the machine the command runs on. A reached machine that is
    local, or whose host is swept already, is refused by name. With nothing
    reached, this is the sweep of one host described above.
    """
    from mcgyvr import detect

    hosts = (machine.host, *(other.host for other in reached))
    for other in reached:
        if other.local:
            raise ValueError(
                f"reached machine {other.label!r} is local; a reached machine "
                "is one over the network"
            )
    if len(set(hosts)) != len(hosts):
        raise ValueError(f"a host is swept twice in {list(hosts)}")
    servers = [server for each in (machine, *reached) for server in each.servers]

    def run(
        command: Sequence[str], *, bound: float = 0.0
    ) -> tuple[str | None, str | None]:
        if not machine.local or command[0] != "nvidia-smi":
            return None, None
        return _reader_answer(machine, command[1:]), None

    def get_json(url: str, timeout: float) -> Any | None:
        asked = urllib.parse.urlsplit(url)
        for server in servers:
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

    def ram(*_: Any) -> tuple[float | None, str]:
        return None, "not determined — an invented machine states no RAM"

    def docker() -> tuple[bool, str]:
        return False, "an invented machine has no docker daemon"

    from mcgyvr.serving import rigscan

    def reading() -> Mapping[str, Any]:
        # An empty root: nothing of the machine the tests run on is read.
        with tempfile.TemporaryDirectory() as root:
            return rigscan.read_machine(root=root)

    no_cpu_count = types.SimpleNamespace(cpu_count=lambda: None)
    with (
        mock.patch.object(rigscan, "_run", run),
        mock.patch.object(detect, "_reading", reading),
        mock.patch.object(detect, "_get_json", get_json),
        mock.patch.object(detect, "detect_ram_gb", ram),
        mock.patch.object(detect, "detect_docker", docker),
        mock.patch.object(detect, "os", no_cpu_count),
    ):
        return detect.detect(detect.targets_for(hosts))


def scan(machine: Shape, /) -> Scan:
    """What :mod:`mcgyvr.scan` reports of this machine, scanned where it is.

    The cards go through the product's one reader (:mod:`mcgyvr.serving.rigscan`)
    with the card reading tool answering :func:`card_reader_text` for its
    query, so its notes on an unreadable row or an absent tool are the
    product's. The
    machine is the shape's id and host with a stand-in kernel. Memory, CPU,
    bandwidth and disk are not part of a shape and are left absent. A machine
    that is not ``local`` is scanned on the far end and read back through
    ``Scan.from_json``, as the product's remote transport does.
    """
    from mcgyvr import scan as product
    from mcgyvr.serving import rigscan

    def run(
        command: Sequence[str], *, bound: float = 0.0
    ) -> tuple[str | None, str | None]:
        if command[0] != "nvidia-smi":
            return None, None
        return _reader_answer(machine, command[1:]), None

    with tempfile.TemporaryDirectory() as root, mock.patch.object(rigscan, "_run", run):
        read = rigscan._Short(root, rigscan.BOUND_S)
        gpus, facts, notes = rigscan._gpus(
            read.rows, read.first_answered, read.document["unread"]
        )
    payload = {
        "machine": {"id": machine.machine_id, "host": machine.host, "kernel": _KERNEL},
        "gpus": gpus,
        "notes": notes,
        "facts": [{"field": "machine.id", "how": "invented"}, *facts],
    }
    return product.Scan.from_json(json.dumps(payload))


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


# Machines by operating system. The shapes above are about cards and servers, and
# are read as Linux machines; the shapes below add the system the machine runs, its
# memory and CPU, and on a Mac the GPU that shares the memory, so the reader's
# macOS and Windows branches run over invented machines too. Their tools answer
# from one table (:func:`host_tools`), which both the in-process seam (the
# reader's ``_run``) and the stub tools of :mod:`tests.machinereader` serve.

#: The PCI vendor id each invented vendor's cards carry, as Windows prints it in
#: a display adapter's device id and sysfs in a card's vendor file.
PCI_VENDOR_IDS: Mapping[str, str] = types.MappingProxyType(
    {"vendor-a": "10DE", "vendor-b": "1002"}
)

#: Where Windows keeps nvidia-smi.exe on an invented machine: on PATH, in the
#: system folder, in the vendor's own folder, or nowhere.
CARD_TOOL_PLACES = ("path", "system32", "nvsmi", "none")

#: The page size an invented Mac's memory statistics count in.
_PAGE_BYTES = 16384
_MIB = 1024 * 1024


def device_id(name: str, /) -> str:
    """The invented PCI device id of a card model: four hex digits of its name."""
    import hashlib

    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:4]


@dataclass(frozen=True, kw_only=True)
class HostShape:
    """One invented machine with its operating system.

    ``system`` is ``linux``, ``darwin`` or ``windows``. ``machine_id`` is the
    invented value the machine's own id source gives (the machine-id file, the
    IOPlatformUUID, the MachineGuid). ``memory_mib`` and ``available_mib`` are
    its memory; ``cpu_model``, ``cores``, ``threads`` and, on a Mac,
    ``performance_cores`` its CPU. ``cards`` are its discrete cards, read as
    :class:`Shape` reads them. A Mac with ``chip`` set is Apple silicon: the
    chip is the CPU brand its GPU is named after, ``wired_limit_mib`` the GPU
    cap its kernel setting names (0 for the kernel's own) and ``gpu_cores`` its
    GPU cores (None when the display data does not carry them). On Windows
    ``card_tool`` says where nvidia-smi.exe is (:data:`CARD_TOOL_PLACES`) and
    ``other_adapters`` names display adapters that are not PCI cards.
    ``memory_modules`` False models a Windows machine (a virtual one) that lists
    no memory modules. A shape that contradicts itself is refused by name.
    """

    label: str
    system: str
    machine_id: str
    memory_mib: int
    available_mib: int
    cpu_model: str
    cores: int
    threads: int
    version: str
    host: str = "box-1.example"
    cards: tuple[Card, ...] = ()
    performance_cores: int | None = None
    chip: str | None = None
    wired_limit_mib: int = 0
    gpu_cores: int | None = None
    card_tool: str = "path"
    other_adapters: tuple[str, ...] = ()
    memory_modules: bool = True
    #: The DDR generation of its memory modules, as Windows reports each
    #: module's SMBIOS type (None: a type the reader does not name).
    ddr: int | None = None

    def __post_init__(self) -> None:
        where = f"host shape {self.label!r}"
        if self.system not in ("linux", "darwin", "windows"):
            raise ValueError(f"{where}: system {self.system!r} is not one read")
        if not 0 <= self.available_mib <= self.memory_mib:
            raise ValueError(f"{where}: available memory outside its total")
        if not 0 < self.cores <= self.threads:
            raise ValueError(f"{where}: {self.cores} cores and {self.threads} threads")
        if self.chip is not None and (self.system != "darwin" or self.cards):
            raise ValueError(f"{where}: a unified chip on a machine that is not a Mac")
        if self.system == "darwin" and self.cards:
            raise ValueError(f"{where}: a Mac with a discrete card is not modelled")
        if self.card_tool not in CARD_TOOL_PLACES:
            raise ValueError(f"{where}: card tool place {self.card_tool!r}")
        if self.ddr is not None and self.system != "windows":
            raise ValueError(f"{where}: a DDR generation is read on Windows alone")
        if any(c.total_mib is None for c in self.cards if c.vendor == "vendor-a"):
            raise ValueError(f"{where}: a card of unreadable size is not modelled")

    @property
    def unified_mib(self) -> int | None:
        """What the GPU of a Mac with a chip may take: the kernel setting when
        it names one, else three quarters of the memory; None without a chip."""
        if self.chip is None:
            return None
        if self.wired_limit_mib:
            return min(self.wired_limit_mib, self.memory_mib)
        return int(self.memory_mib * 0.75)

    @property
    def tool_cards(self) -> tuple[Card, ...]:
        """The cards nvidia-smi answers for: none when it is not installed."""
        if self.system == "windows" and self.card_tool == "none":
            return ()
        return tuple(card for card in self.cards if card.card_reader_reads)


def _vm_stat(machine: HostShape) -> str:
    pages = machine.available_mib * _MIB // _PAGE_BYTES
    free, speculative = pages // 2, pages // 8
    inactive = pages - free - speculative
    lines = [
        f"Mach Virtual Memory Statistics: (page size of {_PAGE_BYTES} bytes)",
        *(
            f"{name:<30} {count:>16}."
            for name, count in (
                ("Pages free:", free),
                ("Pages active:", 4096),
                ("Pages inactive:", inactive),
                ("Pages speculative:", speculative),
                ("Pages throttled:", 0),
                ("Pages wired down:", 2048),
                ("Pages purgeable:", 512),
            )
        ),
    ]
    return "\n".join(lines) + "\n"


#: The SMBIOS memory type Windows reports for a module of each DDR generation
#: (type 17 codes, as dmidecode names them); 0 is "unknown".
_SMBIOS_TYPE = {3: 0x18, 4: 0x1A, 5: 0x22}


def _cim(machine: HostShape) -> str:
    half = machine.memory_mib * _MIB // 2
    adapters = [
        {
            "name": card.name,
            "pnp": f"PCI\\VEN_{PCI_VENDOR_IDS[card.vendor]}&DEV_"
            f"{device_id(card.name).upper()}&SUBSYS_00000000&REV_01\\4&1&0&0008",
        }
        for card in machine.cards
    ] + [
        {"name": name, "pnp": f"ROOT\\DISPLAY\\{number:04d}"}
        for number, name in enumerate(machine.other_adapters)
    ]
    body = {
        "memory": (
            [str(half), str(machine.memory_mib * _MIB - half)]
            if machine.memory_modules
            else []
        ),
        "memory_types": (
            [str(_SMBIOS_TYPE.get(machine.ddr, 0))] * 2
            if machine.memory_modules
            else []
        ),
        "processors": {
            "name": machine.cpu_model,
            "cores": machine.cores,
            "threads": machine.threads,
            "architecture": 9,
        },
        "system": {
            "version": machine.version,
            "free_kb": str(machine.available_mib * 1024),
            "total_kb": str(machine.memory_mib * 1024 - 2048),
        },
        "video": adapters,
    }
    return json.dumps(body, separators=(",", ":"))


def host_tools(machine: HostShape, /) -> dict[tuple[str, ...], tuple[str, int]]:
    """Every question the reader may ask this machine's tools, by its argv, with
    what the tool prints and its exit status. A tool whose name no key starts with
    is not installed. nvidia-smi is keyed by name wherever it is kept: see
    :attr:`HostShape.card_tool`."""
    from mcgyvr.serving import rigscan

    tools: dict[tuple[str, ...], tuple[str, int]] = {}
    if machine.tool_cards:
        query = rigscan.FIRST_QUERY
        argv = ("nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits")
        tools[argv] = (card_reader_text(machine.tool_cards, query=query), 0)
        # The snapshot's questions are not answered by the invented tool, as the
        # card shapes above do not answer them either.
        for asked in (rigscan.SNAPSHOT_QUERY, rigscan.SNAPSHOT_QUERY_OLD):
            unasked = f"--query-gpu={asked}"
            tools[("nvidia-smi", unasked, "--format=csv,noheader,nounits")] = ("", 2)
    if machine.system == "linux":
        tools[("lscpu",)] = (
            f"CPU(s):              {machine.threads}\n"
            f"Core(s) per socket:  {machine.cores}\n"
            "Socket(s):           1\n"
            f"Model name:          {machine.cpu_model}\n",
            0,
        )
    elif machine.system == "darwin":

        def sysctl(name: str, value: object | None) -> None:
            argv = (rigscan.SYSCTL, "-n", name)
            tools[argv] = ("", 1) if value is None else (f"{value}\n", 0)

        sysctl(rigscan.SYSCTL_MEMSIZE, machine.memory_mib * _MIB)
        sysctl(rigscan.SYSCTL_PHYSICAL, machine.cores)
        sysctl(rigscan.SYSCTL_LOGICAL, machine.threads)
        sysctl(rigscan.SYSCTL_PERFORMANCE, machine.performance_cores)
        sysctl(rigscan.SYSCTL_BRAND, machine.chip or machine.cpu_model)
        sysctl(rigscan.SYSCTL_ARM64, 1 if machine.chip else None)
        sysctl(rigscan.SYSCTL_WIRED_LIMIT, machine.wired_limit_mib)
        tools[(rigscan.VM_STAT,)] = (_vm_stat(machine), 0)
        display: dict[str, Any] = {"sppci_model": machine.chip or "Example Display"}
        if machine.gpu_cores is not None:
            display["sppci_cores"] = str(machine.gpu_cores)
        tools[rigscan.SYSTEM_PROFILER_ARGS] = (
            json.dumps({"SPDisplaysDataType": [display]}),
            0,
        )
        tools[rigscan.IOREG_ARGS] = (
            "+-o Example  <class IOPlatformExpertDevice>\n  {\n"
            f'    "IOPlatformUUID" = "{machine.machine_id}"\n  }}\n',
            0,
        )
        tools[rigscan.SW_VERS_ARGS] = (f"{machine.version}\n", 0)
    else:
        tools[rigscan.REG_MACHINE_GUID] = (
            "\r\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography\r\n"
            f"    MachineGuid    REG_SZ    {machine.machine_id}\r\n\r\n",
            0,
        )
        tools[rigscan.CIM_ARGS] = (_cim(machine), 0)
    return tools


def host_files(machine: HostShape, /) -> dict[str, str]:
    """The files the reader finds under its test root on this machine: the host
    name everywhere, and on Linux the machine-id file, meminfo and cpuinfo."""
    files = {"/proc/sys/kernel/hostname": f"{machine.host}\n"}
    if machine.system == "linux":
        files["/etc/machine-id"] = f"{machine.machine_id}\n"
        files["/proc/meminfo"] = (
            f"MemTotal:       {machine.memory_mib * 1024} kB\n"
            f"MemFree:        {machine.available_mib * 512} kB\n"
            f"MemAvailable:   {machine.available_mib * 1024} kB\n"
        )
        files["/proc/cpuinfo"] = f"processor\t: 0\nmodel name\t: {machine.cpu_model}\n"
    return files


def _host_run(machine: HostShape) -> Any:
    tools = host_tools(machine)
    installed = {argv[0] for argv in tools}

    def run(
        command: Sequence[str], *, bound: float = 0.0
    ) -> tuple[str | None, str | None]:
        # A Windows tool is called by its full path (System32, or wherever
        # nvidia-smi.exe is kept): it is the same tool, and the folders it is
        # looked for in are read by the stub tools of tests.machinereader.
        name = Path(command[0].replace("\\", "/")).name.removesuffix(".exe")
        argv = (name, *command[1:])
        if argv[0] not in installed:
            return None, None
        if argv not in tools:
            raise ValueError(f"the invented {machine.label!r} is not asked {argv}")
        text, status = tools[argv]
        if status:
            return None, f"{' '.join(argv[:2])} exited {status}"
        return text, None

    return run


@contextmanager
def _host_root(machine: HostShape) -> Iterator[str]:
    with tempfile.TemporaryDirectory() as root:
        for path, text in host_files(machine).items():
            target = Path(root + path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        yield root


#: Where an invented Windows machine keeps nvidia-smi.exe, by its full path; the
#: shipped reader's own search of these folders is run by tests.machinereader.
_CARD_TOOL_PATHS: Mapping[str, str] = types.MappingProxyType(
    {
        "path": "C:\\Tools\\nvidia-smi.exe",
        "system32": "C:\\Windows\\System32\\nvidia-smi.exe",
        "nvsmi": "C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe",
    }
)


@contextmanager
def _host_tools(machine: HostShape) -> Iterator[None]:
    from mcgyvr.serving import rigscan

    found = _CARD_TOOL_PATHS.get(machine.card_tool) if machine.tool_cards else None
    with (
        mock.patch.object(rigscan, "_run", _host_run(machine)),
        mock.patch.object(rigscan, "_windows_nvidia_smi", lambda: found),
    ):
        yield


def host_reading(machine: HostShape, /) -> dict[str, Any]:
    """The reader's short reading of this machine, read in this process."""
    from mcgyvr.serving import rigscan

    with _host_root(machine) as root, _host_tools(machine):
        return rigscan.read_machine(root=root, system=machine.system)


def host_scan_document(machine: HostShape, /) -> dict[str, Any]:
    """The reader's whole scan of this machine, read in this process, without the
    bandwidth probe and with nothing of the disk the tests run on."""
    from mcgyvr.serving import rigscan

    with (
        _host_root(machine) as root,
        _host_tools(machine),
        mock.patch.object(rigscan, "measure_bandwidth", lambda root="": None),
        tempfile.TemporaryDirectory() as weights,
    ):
        return rigscan.scan(weights, root=root, system=machine.system)


def host_detection(machine: HostShape, /) -> Detection:
    """What :func:`mcgyvr.detect.detect` reports of this machine, swept for no
    server; docker and the CPU count are not part of a host shape."""
    from mcgyvr import detect

    reading = host_reading(machine)
    with (
        mock.patch.object(detect, "_reading", lambda: reading),
        mock.patch.object(detect, "_get_json", lambda url, timeout: None),
        mock.patch.object(
            detect, "detect_docker", lambda: (False, "an invented machine")
        ),
    ):
        return detect.detect(())


def host_scan(machine: HostShape, /) -> Scan:
    """What :mod:`mcgyvr.scan` makes of this machine's whole scan."""
    from mcgyvr import scan as product

    return product.Scan.from_json(json.dumps(host_scan_document(machine)))


@functools.cache
def host_shapes() -> tuple[HostShape, ...]:
    """Every invented machine with its system, in a stable order.

    Covers: a unified-memory laptop with no discrete card; a unified-memory
    desktop whose GPU cap is set and whose display data carries no core count; a
    Mac that is not Apple silicon; a Windows desktop with one card its tool reads,
    with that tool on PATH, in the system folder, and in the vendor's folder; a
    Windows laptop whose only card no tool reads, beside a display that is not a
    card; a Windows machine that lists no memory modules; and a Linux box with
    one card, as the product read it before it read other systems.
    """
    windows_card = _card(0, "Example Card A")
    return (
        HostShape(
            label="unified-laptop",
            system="darwin",
            machine_id="0000AAAA-1111-2222-3333-444455556666",
            memory_mib=24 * 1024,
            available_mib=9000,
            cpu_model="Example Chip U1",
            cores=8,
            threads=8,
            performance_cores=4,
            chip="Example Chip U1",
            gpu_cores=10,
            version="0.1-example",
        ),
        HostShape(
            label="unified-desktop-capped",
            system="darwin",
            machine_id="0000BBBB-1111-2222-3333-444455556666",
            memory_mib=96 * 1024,
            available_mib=90000,
            cpu_model="Example Chip U3",
            cores=24,
            threads=24,
            performance_cores=16,
            chip="Example Chip U3",
            wired_limit_mib=80000,
            gpu_cores=None,
            version="0.2-example",
        ),
        HostShape(
            label="mac-without-unified",
            system="darwin",
            machine_id="0000CCCC-1111-2222-3333-444455556666",
            memory_mib=16 * 1024,
            available_mib=6000,
            cpu_model="Example CPU X8",
            cores=4,
            threads=8,
            version="0.3-example",
        ),
        HostShape(
            label="windows-one-card",
            system="windows",
            machine_id="aaaa0000-bbbb-cccc-dddd-eeeeffff0001",
            memory_mib=32 * 1024,
            available_mib=20000,
            cpu_model="Example CPU W12",
            cores=6,
            threads=12,
            cards=(windows_card,),
            version="0.0.1-example",
        ),
        HostShape(
            label="windows-card-tool-in-system",
            system="windows",
            machine_id="aaaa0000-bbbb-cccc-dddd-eeeeffff0002",
            memory_mib=64 * 1024,
            available_mib=50000,
            cpu_model="Example CPU W16",
            cores=8,
            threads=16,
            cards=(_card(0, "Example Card C"),),
            card_tool="system32",
            version="0.0.2-example",
        ),
        HostShape(
            label="windows-card-tool-in-vendor-folder",
            system="windows",
            machine_id="aaaa0000-bbbb-cccc-dddd-eeeeffff0003",
            memory_mib=16 * 1024,
            available_mib=7000,
            cpu_model="Example CPU W8",
            cores=4,
            threads=8,
            cards=(_card(0, "Example Card B"),),
            card_tool="nvsmi",
            version="0.0.3-example",
        ),
        HostShape(
            label="windows-other-gpu",
            system="windows",
            machine_id="aaaa0000-bbbb-cccc-dddd-eeeeffff0004",
            memory_mib=16 * 1024,
            available_mib=8000,
            cpu_model="Example CPU W8",
            cores=4,
            threads=8,
            cards=(_card(0, "Example Card L"),),
            card_tool="none",
            other_adapters=("Example Remote Display",),
            version="0.0.4-example",
        ),
        HostShape(
            label="windows-no-modules",
            system="windows",
            machine_id="aaaa0000-bbbb-cccc-dddd-eeeeffff0005",
            memory_mib=8 * 1024,
            available_mib=3000,
            cpu_model="Example CPU W4",
            cores=2,
            threads=4,
            card_tool="none",
            memory_modules=False,
            version="0.0.5-example",
        ),
        HostShape(
            label="linux-one-card",
            system="linux",
            machine_id="0123456789abcdef0123456789abcde1",
            memory_mib=48 * 1024,
            available_mib=30000,
            cpu_model="Example CPU L16",
            cores=8,
            threads=16,
            cards=(_card(0, "Example Card A"),),
            version="",
        ),
    )


def host_shape(label: str, /) -> HostShape:
    """The invented machine with its system of this label."""
    for machine in host_shapes():
        if machine.label == label:
            return machine
    known = ", ".join(machine.label for machine in host_shapes())
    raise KeyError(f"no invented host {label!r}; the known ones: {known}")
