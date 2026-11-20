"""A hello gives the same capability record, less what the wire does not carry.

A hub can build a machine's record from the resources a rig's hello lists
(``hubwire.Resource``) and the host it names. Each card is matched by its name
and memory to the same rows, with the same facts, as the reading of that
machine gives; its system, RAM and CPU name are the same. What the wire does not
carry is unknown: PCI ids, compute capability, used memory, CPU flags and
clock, physical cores, and the RAM probe unless the hello carries it as a
reading. A card's bandwidth on the wire (the older class table's estimate) is
not taken.

Where the hello cannot give the reading's value the record holds the hello's,
and the tests below pin each: a card's index is the wire's, counted per kind
where a reading counts per vendor; its id is its vendor and that index, where a
reading's is its PCI address, so the pools are named apart; a Vulkan card's
vendor is unknown and it is matched among every vendor's rows; the RAM is the
MiB the hello sent, where a reading's record has a tenth of a GiB; and a name
the rig wrote for a card or CPU it read no name of matches no row. The table
and the machines are invented.
"""

from __future__ import annotations

import dataclasses

from mcgyvr import hubwire, machine_capability
from mcgyvr.scan import Bandwidth, Device, Host
from tests.invented_hardware import HOST, device, row, scan, table

TABLE = table(
    row(
        "acme-vector-7",
        "nvidia",
        "gpu",
        name="Acme Vector 7",
        pci_device_ids=["1A2B"],
        memory__size_gb=16,
        memory__bandwidth_gbps=448,
    ),
    row(
        "acme-river-9",
        "amd",
        "gpu",
        name="AMD Acme River 9 XT",
        memory__size_gb=20,
        memory__bandwidth_gbps=800,
    ),
    row("acme-q9-family", "amd", "cpu", name="Acme Q9", models=["Q9 7700"]),
)
CPU = "AMD Acme Q9 7700 8-Core Processor"
CARD = device(
    "NVIDIA Acme Vector 7",
    pci_device="0x1a2b",
    pci_vendor="0x10de",
    pci_bus="0000:01:00.0",
    total_mib=16376,
    compute_cap="9.1",
    read_from="nvidia-smi",
)

#: What a hello cannot carry, on a card.
CARD_EXTRAS = (
    "id",
    "pci_vendor",
    "pci_device",
    "pci_bus",
    "drm_card",
    "drm_render",
    "used_mib",
    "compute_cap",
    "read_from",
)


def _hello(
    ram_bandwidth: float | None = None, figure: str | None = None
) -> list[hubwire.Resource]:
    resources = [
        hubwire.Resource(
            kind=hubwire.RESOURCE_GPU,
            index=0,
            name="NVIDIA Acme Vector 7",
            total_mb=16376,
            free_mb=16376,
            bandwidth_gbps=999.0,
            bandwidth_figure=hubwire.FIGURE_ESTIMATE,
            figure=hubwire.FIGURE_READING,
            backend=hubwire.BACKEND_CUDA,
        ),
        hubwire.Resource(
            kind=hubwire.RESOURCE_RAM,
            index=0,
            name="host RAM",
            total_mb=64 * 1024,
            free_mb=60 * 1024,
            bandwidth_gbps=ram_bandwidth,
            bandwidth_figure=figure,
            figure=hubwire.FIGURE_READING,
            backend=hubwire.BACKEND_CPU,
        ),
        hubwire.Resource(
            kind=hubwire.RESOURCE_CPU,
            index=0,
            name=CPU,
            total_mb=0,
            cores=16,
            figure=hubwire.FIGURE_READING,
            backend=hubwire.BACKEND_CPU,
        ),
    ]
    hubwire.resources_fit(resources)
    return resources


WIRE_HOST = hubwire.Host(os="linux", arch="x86_64", version="6.1.0-example")


def _without(card: Device, fields: tuple[str, ...]) -> dict[str, object]:
    kept = dataclasses.asdict(card)
    return {key: value for key, value in kept.items() if key not in fields}


def test_a_hello_gives_the_readings_record_less_the_extras() -> None:
    read = machine_capability.of_scan(scan(CARD, cpu_model=CPU), TABLE)
    hello = machine_capability.of_hello(
        _hello(), host=WIRE_HOST, name=HOST, table=TABLE
    )
    assert hello.source == machine_capability.FROM_HELLO
    assert (hello.host, hello.system) == (read.host, read.system)
    (card,), (wire,) = read.cards, hello.cards
    assert _without(wire.reading, CARD_EXTRAS) == _without(card.reading, CARD_EXTRAS)
    assert (wire.table.rows, wire.table.cells) == (card.table.rows, card.table.cells)
    assert card.table.by == machine_capability.BY_PCI_ID
    assert wire.table.by == machine_capability.BY_NAME
    assert hello.cpu.model == read.cpu.model
    assert hello.cpu.threads == read.cpu.threads
    assert (hello.cpu.table.rows, hello.cpu.table.cells) == (
        read.cpu.table.rows,
        read.cpu.table.cells,
    )
    assert (hello.ram.total_mib, hello.ram.available_mib) == (
        read.ram.total_mib,
        read.ram.available_mib,
    )
    assert hello.pools() == read.pools()
    assert hello.table_built == read.table_built


def test_what_the_wire_does_not_carry_is_unknown_in_a_hellos_record() -> None:
    hello = machine_capability.of_hello(_hello(), table=TABLE)
    (card,) = hello.cards
    for field in CARD_EXTRAS[1:-1]:
        assert getattr(card.reading, field) is None, field
    assert card.reading.read_from == machine_capability.READ_FROM_HELLO
    assert (hello.cpu.cores, hello.cpu.detail) == (None, None)
    assert hello.ram.bandwidth is None
    assert hello.system is None and hello.host == ""
    assert card.table.cell("memory.bandwidth_gbps").value == 448


def test_a_hellos_ram_bandwidth_is_taken_only_as_a_reading() -> None:
    estimated = machine_capability.of_hello(
        _hello(40.0, hubwire.FIGURE_ESTIMATE), table=TABLE
    )
    assert estimated.ram.bandwidth is None
    read = machine_capability.of_hello(
        _hello(40.0, hubwire.FIGURE_READING), table=TABLE
    )
    assert read.ram.bandwidth == Bandwidth(
        measured_gbps=40.0, how=machine_capability.READ_FROM_HELLO
    )


def test_a_hellos_host_is_the_readings_host_type() -> None:
    hello = machine_capability.of_hello(_hello(), host=WIRE_HOST, table=TABLE)
    assert hello.system == Host(os="linux", arch="x86_64", version="6.1.0-example")


def _card_resource(index: int, name: str, mib: int, backend: str) -> hubwire.Resource:
    return hubwire.Resource(
        kind=hubwire.RESOURCE_GPU,
        index=index,
        name=name,
        total_mb=mib,
        free_mb=mib,
        figure=hubwire.FIGURE_READING,
        backend=backend,
    )


def test_a_hellos_cards_of_two_vendors_keep_the_wires_index_and_id() -> None:
    nvidia = dataclasses.replace(
        device("NVIDIA Acme Vector 7", total_mib=16384, pci_device="0x1a2b"),
        id="pci:0000:01:00.0",
    )
    amd = dataclasses.replace(
        device("AMD Acme River 9 XT", vendor="amd", total_mib=20480, backend="rocm"),
        id="pci:0000:03:00.0",
    )
    read = machine_capability.of_scan(scan(nvidia, amd), TABLE)
    resources = [
        _card_resource(0, "NVIDIA Acme Vector 7", 16384, hubwire.BACKEND_CUDA),
        _card_resource(1, "AMD Acme River 9 XT", 20480, hubwire.BACKEND_ROCM),
    ]
    hubwire.resources_fit(resources)
    hello = machine_capability.of_hello(resources, table=TABLE)
    assert [c.table.rows for c in hello.cards] == [c.table.rows for c in read.cards]
    assert [(c.reading.vendor, c.reading.index) for c in read.cards] == [
        ("nvidia", 0),
        ("amd", 0),
    ]
    assert [(c.reading.vendor, c.reading.index) for c in hello.cards] == [
        ("nvidia", 0),
        ("amd", 1),
    ]
    assert [c.reading.id for c in hello.cards] == ["nvidia:0", "amd:1"]
    assert [p.name for p in hello.pools()][:2] == ["nvidia:0", "amd:1"]
    assert [p.name for p in read.pools()][:2] == [
        "pci:0000:01:00.0",
        "pci:0000:03:00.0",
    ]


def test_a_hellos_vulkan_card_is_matched_among_every_vendors_rows() -> None:
    river = _card_resource(0, "AMD Acme River 9 XT", 20480, hubwire.BACKEND_VULKAN)
    resources = [river]
    hubwire.resources_fit(resources)
    (card,) = machine_capability.of_hello(resources, table=TABLE).cards
    assert card.reading.vendor == machine_capability.UNKNOWN_VENDOR
    assert card.table.rows == ("acme-river-9",)


def test_a_hellos_ram_is_the_mib_it_sent() -> None:
    resources = [
        hubwire.Resource(
            kind=hubwire.RESOURCE_RAM,
            index=0,
            name="host RAM",
            total_mb=65471,
            free_mb=60000,
            figure=hubwire.FIGURE_READING,
            backend=hubwire.BACKEND_CPU,
        )
    ]
    hubwire.resources_fit(resources)
    hello = machine_capability.of_hello(resources, table=TABLE)
    assert (hello.ram.total_mib, hello.ram.available_mib) == (65471, 60000)
    assert machine_capability.of_scan(scan(ram_gib=64), TABLE).ram.total_mib == 65536


def test_a_name_the_rig_wrote_for_an_unnamed_card_or_cpu_matches_no_row() -> None:
    resources = [
        _card_resource(0, "nvidia card", 16384, hubwire.BACKEND_CUDA),
        hubwire.Resource(
            kind=hubwire.RESOURCE_CPU,
            index=0,
            name="CPU",
            total_mb=0,
            cores=16,
            figure=hubwire.FIGURE_READING,
            backend=hubwire.BACKEND_CPU,
        ),
    ]
    hubwire.resources_fit(resources)
    hello = machine_capability.of_hello(resources, table=TABLE)
    (card,) = hello.cards
    assert card.reading.name == "nvidia card"
    assert not card.table.matched
    assert hello.cpu.model == "CPU"
    assert not hello.cpu.table.matched
