"""A reading without the wider fields gives a capability record with them unknown.

A reading from an older reader, or a scan that was not asked for the wider
fields, carries no device list and no CPU flags or clock. Its record is made
from the cards it sized (``gpus``), each placed by its vendor where its engine
build names one, matched by name and memory; its PCI ids, compute capability,
CPU flags and clock are unknown, and no error is raised. A reading with nothing
in it gives a record with nothing matched. The table and the machines are
invented.
"""

from __future__ import annotations

from mcgyvr import machine_capability
from mcgyvr.scan import Scan
from tests.invented_hardware import gpu, row, scan, table

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
    row("acme-river-9", "amd", "gpu", name="Acme River 9", memory__size_gb=20),
    row("acme-q3-max", "apple", "soc", name="Q3 Max", memory__sizes_gb=[48]),
)


def test_an_older_reading_gives_its_sized_cards_with_the_extras_unknown() -> None:
    record = machine_capability.of_scan(
        scan(gpus=(gpu("NVIDIA Acme Vector 7", 16376),), wider=False), TABLE
    )
    assert record.source == machine_capability.FROM_READING
    (card,) = record.cards
    assert card.reading.vendor == "nvidia"
    assert card.reading.id == "nvidia:0"
    assert card.reading.read_from == "nvidia-smi"
    assert (card.reading.pci_device, card.reading.compute_cap) == (None, None)
    assert card.table.rows == ("acme-vector-7",)
    assert card.table.by == machine_capability.BY_NAME
    assert record.cpu.detail is None
    assert record.cpu.table.rows == ()


def test_an_older_macs_gpu_is_its_chip_by_its_engine_build() -> None:
    record = machine_capability.of_scan(
        scan(
            gpus=(gpu("Apple Q3 Max GPU", 36864, kind="unified", backend="metal"),),
            ram_gib=48,
            wider=False,
        ),
        TABLE,
    )
    (card,) = record.cards
    assert (card.reading.vendor, card.unified) == ("apple", True)
    assert card.table.rows == ("acme-q3-max",)


def test_a_card_whose_build_names_no_vendor_is_matched_by_name_among_all() -> None:
    record = machine_capability.of_scan(
        scan(gpus=(gpu("Acme River 9", 20480, backend="vulkan"),), wider=False),
        TABLE,
    )
    (card,) = record.cards
    assert card.reading.vendor == machine_capability.UNKNOWN_VENDOR
    assert card.table.rows == ("acme-river-9",)


def test_a_reading_with_the_wider_fields_says_so() -> None:
    record = machine_capability.of_scan(scan(), TABLE)
    assert record.source == machine_capability.FROM_HARDWARE_READING
    assert record.cards == ()
    assert record.cpu.detail is not None and record.cpu.detail.has("avx2") is True
    assert record.cpu.detail.has("amx_tile") is None


def test_a_reading_with_nothing_in_it_gives_a_record_with_nothing_matched() -> None:
    record = machine_capability.of_scan(Scan.of(host="box-b.example"), TABLE)
    assert record.host == "box-b.example"
    assert record.cards == ()
    assert record.cpu.model is None and not record.cpu.table.matched
    assert (record.ram.total_mib, record.ram.bandwidth) == (None, None)
    assert record.system is None
    assert record.table_built == TABLE.built
