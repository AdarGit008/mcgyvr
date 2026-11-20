"""What each device of a machine can do: its reading beside the hardware table's rows.

One record per host (:class:`MachineCapability`). Each card keeps the reading's
own record of it (:class:`mcgyvr.scan.Device`) and the CPU and RAM what the
reading gives of them; beside each device stand the facts of the table's rows it
matched (:class:`TableFacts`), as the table's own cells
(:class:`mcgyvr.hardware_table.Cell`), so every fact keeps its three states (a
value, a stated no, unknown) and the source it came from. A reading names how
it was read (``read_from``); a table fact names its source id. Unknown is never
read as no and never as zero.

Two constructors, both pure: :func:`of_scan` from a reading, and
:func:`of_hello` from the resources a rig's hello lists (``hubwire.Resource``),
where what the wire does not carry (PCI ids, compute capability, CPU flags and
clock, physical cores, the RAM probe) is unknown. No file is read but the
shipped table, nothing is run, nothing is asked.

Matching a device to the table's rows:

- a card: by its PCI device id when the reading has one and the table lists ids
  for its vendor; an id that no row lists matches no row (the id was read, and
  the name is no surer than it). Else by its name (:func:`card_key`) among the
  rows of its vendor. Then by memory: a row that states its size must hold the
  card's MiB / 1024, rounded; an unread memory or an unknown size keeps the row;
- a GPU that shares the machine's memory (a Mac's) and an Apple CPU: the chip's
  row by the same name rule, narrowed by the machine's RAM against the sizes the
  row states;
- any other CPU: a row of the vendor its name names, one of whose listed models
  (:func:`cpu_words`) is a run of whole words of the CPU's name.

Several rows may match (variants a reading cannot tell apart). A fact all of
them state alike is kept; one they differ on is unknown, and the record names
the rows and the fields. Choosing among them is not done here.

A match says what the table holds and no more: these rows list this id, or
carry this name. It is only as right as the table's lists: a vendor may give one
id to more products than the row that lists it, or one name to a laptop part and
a desktop part, and the record cannot tell.

A unified device's memory is a share of the machine's RAM, not a second memory:
:meth:`MachineCapability.pools` counts it once. The RAM's bandwidth is the
reading's probe alone, never a table's maximum.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from mcgyvr import hubwire
from mcgyvr.hardware_table import (
    NO,
    UNKNOWN,
    UNKNOWN_CELL,
    VALUE,
    Cell,
    HardwareTable,
    Row,
    shipped_table,
)
from mcgyvr.scan import Bandwidth, CpuDetail, Device, Host, Scan

#: How a device's rows were found.
BY_PCI_ID = "pci device id"
BY_NAME = "name"

#: Where a record came from: a reading with the wider fields (``scan
#: --hardware``), a reading without them, or a hello's resources.
FROM_HARDWARE_READING = "reading with the hardware fields"
FROM_READING = "reading"
FROM_HELLO = "hello"

#: The ``read_from`` of a device or a figure a hello gave.
READ_FROM_HELLO = "hello"

#: The vendor a card's engine build names, for a card whose reading names no
#: vendor (a reading without the device list, a hello). The reader gives CUDA to
#: NVIDIA, ROCm to AMD and Metal to Apple only (``rigscan._backend``); a Vulkan
#: card may be any vendor's.
VENDOR_OF_BACKEND: Mapping[str, str] = MappingProxyType(
    {
        hubwire.BACKEND_CUDA: "nvidia",
        hubwire.BACKEND_ROCM: "amd",
        hubwire.BACKEND_METAL: "apple",
    }
)
#: The vendor of a reading that names none.
UNKNOWN_VENDOR = "unknown"

#: The table's row kinds.
_GPU, _CPU, _SOC = "gpu", "cpu", "soc"
_APPLE = "apple"

_IDS = "pci_device_ids"
_NAME = "name"
_SIZE = "memory.size_gb"
_SIZES = "memory.sizes_gb"
_MODELS = "models"
_ITS_MEMORY = "its memory"

_MARKS = re.compile(r"\((?:r|tm)\)|[®™]", re.IGNORECASE)
_PARENS = re.compile(r"\([^()]*\)")
_GB = re.compile(r"\b\d+(?:\.\d+)?\s?gb\b")
_CARD_WORDS = frozenset(
    {"nvidia", "geforce", "amd", "intel", "apple", "graphics", "gpu"}
)
# What a CPU's name carries beside its model: the clock, the graphics it comes
# with, its core count, and the words for what it is.
_CPU_TAIL = re.compile(r"@.*$|\bw/.*$|\bwith radeon.*$")
_CPU_COUNT = re.compile(r"\b\d+-cores?\b")
_CPU_WORDS = frozenset({"intel", "amd", "core", "cpu", "processor"})
_CPU_VENDORS = ("intel", "amd", _APPLE)


def _plain(name: str) -> str:
    return _PARENS.sub(" ", _MARKS.sub(" ", name)).lower()


def card_key(name: str) -> str:
    """The name a card or chip is matched by: lower case, without ``(R)``,
    ``(TM)``, anything in parentheses, a memory size (``8GB``, ``8 GB``) and the
    words nvidia, geforce, amd, intel, apple, graphics and gpu. ``NVIDIA
    GeForce RTX 3060 Ti`` and ``GeForce RTX 3060 Ti`` are ``rtx 3060 ti``;
    ``Intel(R) Arc(TM) A770 Graphics`` is ``arc a770``; ``Apple M2 Max GPU``
    and ``M2 Max (12-core CPU, 38-core GPU)`` are ``m2 max``. A name that is
    all such words is ``""``, which matches nothing."""
    words = _GB.sub(" ", _plain(name)).split()
    return " ".join(word for word in words if word not in _CARD_WORDS)


def cpu_words(name: str) -> tuple[str, ...]:
    """The words a CPU is matched by: as :func:`card_key` cleans a name, less
    what follows an ``@`` (the clock), a ``w/`` or ``with Radeon`` (its
    graphics), its core count (``16-Core``), and the words intel, amd, core,
    cpu and processor. ``Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz`` is
    ``i7-8700k``; ``AMD Ryzen 9 5950X 16-Core Processor`` is ``ryzen 9
    5950x``."""
    text = _CPU_COUNT.sub(" ", _CPU_TAIL.sub(" ", _plain(name)))
    return tuple(word for word in text.split() if word not in _CPU_WORDS)


def _cpu_vendor(name: str) -> str | None:
    words = set(_plain(name).split())
    return next((vendor for vendor in _CPU_VENDORS if vendor in words), None)


def _pci_id(printed: object) -> int | None:
    """A PCI device id as a number, whichever way it was printed (``0x2b85``,
    ``2B85``); None for anything else."""
    if not isinstance(printed, str):
        return None
    text = printed.strip().lower().removeprefix("0x")
    if not re.fullmatch(r"[0-9a-f]{1,4}", text):
        return None
    return int(text, 16)


def _ids_of(row: Row) -> set[int | None]:
    """The PCI device ids a row lists, as numbers."""
    return {_pci_id(one) for one in row.cell(_IDS).value}


def _held(words: tuple[str, ...], inside: tuple[str, ...]) -> bool:
    """True when ``words`` is a run of whole words of ``inside``."""
    span = len(words)
    return span > 0 and any(
        inside[at : at + span] == words for at in range(len(inside) - span + 1)
    )


@dataclass(frozen=True)
class TableFacts:
    """What the hardware table says of one device.

    ``rows`` are the ids of the rows it matched, in the table's order, empty
    when none did; ``by`` says how they were found (:data:`BY_PCI_ID`,
    :data:`BY_NAME`), None when none was; ``why`` says in a sentence what
    matched or why nothing did. ``cells`` are the facts the rows state alike,
    each the table's own cell; ``differing`` names the fields the rows do not
    state alike, which read as unknown."""

    rows: tuple[str, ...]
    by: str | None
    why: str
    cells: Mapping[str, Cell] = MappingProxyType({})
    differing: tuple[str, ...] = ()

    @property
    def matched(self) -> bool:
        return bool(self.rows)

    def cell(self, field: str) -> Cell:
        """The fact for ``field`` (``memory.bandwidth_gbps``): the rows' cell
        when they state it alike, else unknown."""
        return self.cells.get(field, UNKNOWN_CELL)


def _none(why: str) -> TableFacts:
    return TableFacts(rows=(), by=None, why=why)


def _agreed(rows: Sequence[Row]) -> tuple[Mapping[str, Cell], tuple[str, ...]]:
    """The cells every row states alike, each as the first row has it, and the
    fields they do not. A value is alike when every row states the same value; a
    no is alike when every row states a no, however each spells it (``false``,
    an empty list, no value with a page cited)."""
    fields = sorted({field for row in rows for field in row.cells})
    kept: dict[str, Cell] = {}
    differing: list[str] = []
    for field in fields:
        cells = [row.cell(field) for row in rows]
        first = cells[0]
        if first.state == NO and all(c.state == NO for c in cells):
            kept[field] = first
        elif all(c.state == first.state and c.value == first.value for c in cells):
            if first.state != UNKNOWN:
                kept[field] = first
        else:
            differing.append(field)
    return MappingProxyType(kept), tuple(differing)


def _facts(rows: Sequence[Row], by: str, listed: str) -> TableFacts:
    """The facts of ``rows``, which list what ``listed`` says the reading gave.
    The ``why`` says that the table lists it on these rows, not that the device
    is one of them."""
    cells, differing = _agreed(rows)
    ids = tuple(row.id for row in rows)
    if len(rows) == 1:
        why = f"the table lists {listed} on row {ids[0]}"
    else:
        why = (
            f"the table lists {listed} on {len(rows)} rows the reading cannot tell "
            f"apart: {', '.join(ids)}"
        )
    return TableFacts(rows=ids, by=by, why=why, cells=cells, differing=differing)


def _by_size(
    rows: list[Row], field: str, mib: int | None
) -> tuple[list[Row], str | None]:
    """The rows whose stated size (``field``) holds ``mib`` / 1024 rounded, with
    a row that states none kept; and what was matched, or None when ``mib`` is
    unread. The size field is a number (``memory.size_gb``) or a list of them
    (``memory.sizes_gb``)."""
    if mib is None:
        return rows, None
    gb = round(mib / 1024)

    def holds(row: Row) -> bool:
        cell = row.cell(field)
        if cell.state != VALUE:
            return True
        stated = cell.value if isinstance(cell.value, list) else [cell.value]
        return any(
            isinstance(one, int | float) and not isinstance(one, bool) and one == gb
            for one in stated
        )

    return [row for row in rows if holds(row)], f"{gb} GB"


def _of_vendor(table: HardwareTable, kind: str, vendor: str | None) -> list[Row]:
    known = {row.vendor for row in table.rows}
    return [
        row
        for row in table.rows
        if row.kind == kind and (vendor not in known or row.vendor == vendor)
    ]


def _named(rows: list[Row], key: str) -> list[Row]:
    return [row for row in rows if card_key(str(row.cell(_NAME).value or "")) == key]


def _sized(
    rows: list[Row], by: str, matched: str, field: str, mib: int | None, what: str
) -> TableFacts:
    kept, size = _by_size(rows, field, mib)
    if not kept:
        ids = ", ".join(row.id for row in rows)
        return _none(
            f"the rows that list the reading's {matched} ({ids}) state no size of "
            f"{size}"
        )
    if size is None:
        return _facts(kept, by, f"the reading's {matched} ({what} unread)")
    return _facts(kept, by, f"the reading's {matched} with {size}")


def _chip(table: HardwareTable, name: str | None, ram_mib: int | None) -> TableFacts:
    """The Apple chip's rows by name, narrowed by the machine's RAM."""
    key = card_key(name or "")
    if not key:
        return _none("the reading names no chip")
    rows = _named(_of_vendor(table, _SOC, _APPLE), key)
    if not rows:
        return _none(f"no row of the table is named {key!r}")
    return _sized(rows, BY_NAME, f"name {key!r}", _SIZES, ram_mib, "the machine's RAM")


def _card(table: HardwareTable, device: Device, ram_mib: int | None) -> TableFacts:
    if device.kind == hubwire.RESOURCE_UNIFIED or device.vendor == _APPLE:
        return _chip(table, device.name, ram_mib)
    rows = _of_vendor(table, _GPU, device.vendor)
    listed = [row for row in rows if row.cell(_IDS).state == VALUE]
    known = device.vendor in {row.vendor for row in table.rows}
    pci = _pci_id(device.pci_device)
    if pci is not None and known and listed:
        found = [row for row in listed if pci in _ids_of(row)]
        printed = f"PCI device id 0x{pci:04x}"
        if not found:
            where = f"no {device.vendor} row of the table"
            return _none(f"{printed} is listed by {where}")
        return _sized(found, BY_PCI_ID, printed, _SIZE, device.total_mib, _ITS_MEMORY)
    key = card_key(device.name or "")
    if not key:
        return _none("the reading names no card the table could be searched by")
    found = _named(rows, key)
    if not found:
        return _none(f"no card row of the table is named {key!r}")
    return _sized(found, BY_NAME, f"name {key!r}", _SIZE, device.total_mib, _ITS_MEMORY)


def _processor(
    table: HardwareTable, model: str | None, ram_mib: int | None
) -> TableFacts:
    if model is None:
        return _none("the reading names no CPU")
    vendor = _cpu_vendor(model)
    if vendor == _APPLE:
        return _chip(table, model, ram_mib)
    words = cpu_words(model)
    if not words:
        return _none("the reading names no CPU the table could be searched by")
    rows = [
        row
        for row in _of_vendor(table, _CPU, vendor)
        if any(
            _held(cpu_words(str(one)), words)
            for one in (row.cell(_MODELS).value or ())
            if row.cell(_MODELS).state == VALUE
        )
    ]
    if not rows:
        return _none(f"no CPU row of the table lists a model of {' '.join(words)!r}")
    return _facts(rows, BY_NAME, f"a model the CPU name {' '.join(words)!r} holds")


@dataclass(frozen=True)
class Card:
    """One card or GPU: the reading's record of it as it is, and the table's
    facts. A ``unified`` card's memory is a share of the machine's RAM."""

    reading: Device
    table: TableFacts

    @property
    def unified(self) -> bool:
        return self.reading.kind == hubwire.RESOURCE_UNIFIED


@dataclass(frozen=True)
class Processor:
    """The CPU as read: its name, physical cores and logical threads (None when
    unread), its flags and clock (``detail``, None when the reading carries
    none), how the reading got them, and the table's facts."""

    model: str | None
    cores: int | None
    threads: int | None
    detail: CpuDetail | None
    read_from: str | None
    table: TableFacts


@dataclass(frozen=True)
class Ram:
    """The machine's RAM as read, in MiB (None when unread), and its bandwidth:
    the reading's probe, None when there was none. No table figure stands in."""

    total_mib: int | None
    available_mib: int | None
    bandwidth: Bandwidth | None
    read_from: str | None


@dataclass(frozen=True)
class Pool:
    """One memory of the machine, counted once: a card's own (``name`` is its
    id) or the RAM (``ram``), with the devices that draw on it."""

    name: str
    total_mib: int | None
    held_by: tuple[str, ...]


#: The name of the RAM's pool and of the RAM among a pool's holders.
RAM = "ram"


@dataclass(frozen=True)
class MachineCapability:
    """One host: what was read of it and what the table says of each device.

    ``host`` is the name the reading gave, ``system`` the system it was read on
    (None when unread), ``source`` which kind of reading it was
    (:data:`FROM_HARDWARE_READING`, :data:`FROM_READING`, :data:`FROM_HELLO`),
    and ``table_built`` the date of the table the facts come from."""

    host: str
    system: Host | None
    cards: tuple[Card, ...]
    cpu: Processor
    ram: Ram
    source: str
    table_built: datetime.date

    def pools(self) -> tuple[Pool, ...]:
        """The machine's memories, each once: one per card with memory of its
        own, then the RAM, held by the RAM and by every card that shares it."""
        own = tuple(
            Pool(card.reading.id, card.reading.total_mib, (card.reading.id,))
            for card in self.cards
            if not card.unified
        )
        shared = tuple(card.reading.id for card in self.cards if card.unified)
        return (*own, Pool(RAM, self.ram.total_mib, (RAM, *shared)))


def _how(scan: Scan, field: str) -> str | None:
    return next((fact.how for fact in scan.facts if fact.field == field), None)


def _mib(gb: float | None) -> int | None:
    return None if gb is None else round(gb * 1024)


def _devices(scan: Scan) -> tuple[Device, ...]:
    """The reading's device list; for a reading without one, its sized cards
    (``gpus``), with a vendor only where their engine build names one."""
    if scan.devices is not None:
        return scan.devices
    found = []
    for gpu in scan.gpus:
        vendor = VENDOR_OF_BACKEND.get(gpu.backend, UNKNOWN_VENDOR)
        found.append(
            Device(
                vendor=vendor,
                index=gpu.index,
                id=f"{vendor}:{gpu.index}",
                name=gpu.name,
                total_mib=gpu.vram.total_mib,
                used_mib=gpu.vram.used_mib,
                free_mib=gpu.vram.free_mib,
                kind=gpu.kind,
                backend=gpu.backend,
                figure=gpu.figure,
                read_from=_how(scan, f"gpu[{gpu.index}].vram.total_mib"),
            )
        )
    return tuple(found)


def _record(
    *,
    host: str,
    system: Host | None,
    devices: Sequence[Device],
    cpu: tuple[str | None, int | None, int | None, CpuDetail | None, str | None],
    ram: Ram,
    source: str,
    table: HardwareTable,
) -> MachineCapability:
    model, cores, threads, detail, cpu_from = cpu
    return MachineCapability(
        host=host,
        system=system,
        cards=tuple(
            Card(reading=device, table=_card(table, device, ram.total_mib))
            for device in devices
        ),
        cpu=Processor(
            model=model,
            cores=cores,
            threads=threads,
            detail=detail,
            read_from=cpu_from,
            table=_processor(table, model, ram.total_mib),
        ),
        ram=ram,
        source=source,
        table_built=table.built,
    )


def of_scan(scan: Scan, table: HardwareTable | None = None) -> MachineCapability:
    """The record of the machine ``scan`` read, with ``table``'s facts (the
    shipped table when None). A reading without the wider fields (an older
    reader, or a scan not asked for them) gives its sized cards with their PCI
    ids, compute capability, CPU flags and clock unknown."""
    table = table or shipped_table()
    memory = scan.memory
    cpu = scan.cpu
    wider = scan.devices is not None or scan.cpu_detail is not None
    return _record(
        host=scan.machine.host,
        system=scan.host,
        devices=_devices(scan),
        cpu=(
            None if cpu is None else cpu.model,
            None if cpu is None else cpu.cores,
            None if cpu is None else cpu.threads,
            scan.cpu_detail,
            _how(scan, "cpu.model") or _how(scan, "cpu.cores"),
        ),
        ram=Ram(
            total_mib=None if memory is None else _mib(memory.total_gb),
            available_mib=None if memory is None else _mib(memory.available_gb),
            bandwidth=scan.bandwidth,
            read_from=_how(scan, "memory.total_gb"),
        ),
        source=FROM_HARDWARE_READING if wider else FROM_READING,
        table=table,
    )


def of_hello(
    resources: Sequence[hubwire.Resource],
    *,
    host: hubwire.Host | None = None,
    name: str = "",
    table: HardwareTable | None = None,
) -> MachineCapability:
    """The record a hub can build from a rig's hello: its ``resources`` and, when
    the hello names one, its ``host``. The wire carries no PCI id, compute
    capability, used memory, CPU flags, clock or physical core count, so those
    are unknown and a card is matched by its name. A card's bandwidth on the wire
    is the older device-class table's estimate, not a reading, and is not taken;
    the RAM's is taken only as a reading.

    Where the hello cannot give the reading's value, the record holds the
    hello's:

    - a card's ``index`` is the wire's, which counts per kind (``gpu``,
      ``unified``) where a reading counts per vendor, so on a machine with cards
      of two vendors the second vendor's card has another index; it is kept as
      the hello's because a heartbeat names the resource by it;
    - a card's ``id`` is its vendor and that index, as a reading's is only when
      it read no PCI address, so the pools of :meth:`MachineCapability.pools`
      are named by it;
    - a card whose engine build names no vendor (Vulkan) has the vendor
      :data:`UNKNOWN_VENDOR`, and is matched by name among every vendor's rows;
    - the RAM is the hello's MiB as sent, where a reading's record has its
      total to a tenth of a GiB;
    - a name the rig wrote for a card or a CPU it read no name of (the vendor
      and ``card``, or ``CPU``) is held as the name the hello gives, and matches
      no row."""
    table = table or shipped_table()
    cards = []
    ram = Ram(total_mib=None, available_mib=None, bandwidth=None, read_from=None)
    cpu: tuple[str | None, int | None, int | None, CpuDetail | None, str | None] = (
        None,
        None,
        None,
        None,
        None,
    )
    for resource in resources:
        if resource.kind in hubwire.CARD_KINDS:
            vendor = VENDOR_OF_BACKEND.get(resource.backend, UNKNOWN_VENDOR)
            cards.append(
                Device(
                    vendor=vendor,
                    index=resource.index,
                    id=f"{vendor}:{resource.index}",
                    name=resource.name,
                    total_mib=resource.total_mb,
                    free_mib=resource.free_mb,
                    kind=resource.kind,
                    backend=resource.backend,
                    figure=resource.figure,
                    read_from=READ_FROM_HELLO,
                )
            )
        elif resource.kind == hubwire.RESOURCE_RAM:
            probed = (
                resource.bandwidth_gbps is not None
                and resource.bandwidth_figure == hubwire.FIGURE_READING
            )
            ram = Ram(
                total_mib=resource.total_mb,
                available_mib=resource.free_mb,
                bandwidth=(
                    Bandwidth(
                        measured_gbps=resource.bandwidth_gbps, how=READ_FROM_HELLO
                    )
                    if probed and resource.bandwidth_gbps is not None
                    else None
                ),
                read_from=READ_FROM_HELLO,
            )
        elif resource.kind == hubwire.RESOURCE_CPU:
            cpu = (resource.name, None, resource.cores, None, READ_FROM_HELLO)
    system = None
    if host is not None:
        system = Host(os=host.os, arch=host.arch, version=host.version)
    return _record(
        host=name,
        system=system,
        devices=cards,
        cpu=cpu,
        ram=ram,
        source=FROM_HELLO,
        table=table,
    )
