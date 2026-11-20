"""A card with no row keeps its reading, and every table fact of it is unknown.

A card the table has no row for keeps what the reading gave (so its fit can
still be calculated), every table fact of it reads as unknown, never as no or
zero, and the record says that no row matched and why: no row has its name, its
memory is a size no row of its name states, or its PCI id is listed by no row
of a vendor whose rows carry ids (a laptop card can carry a desktop card's name,
never its id, so the name is not tried then). A CPU no row lists is the same.
The table and the machines are invented.
"""

from __future__ import annotations

import pytest

from mcgyvr import machine_capability
from mcgyvr.hardware_table import UNKNOWN
from mcgyvr.scan import Device
from tests.invented_hardware import device, row, scan, table

TABLE = table(
    row(
        "acme-vector-7-16gb",
        "nvidia",
        "gpu",
        name="Acme Vector 7",
        pci_device_ids=["1A2B"],
        memory__size_gb=16,
        memory__bandwidth_gbps=448,
    ),
    row("acme-q9-family", "intel", "cpu", name="Acme Q9", models=["Q9 7700"]),
)


@pytest.mark.parametrize(
    ("card", "said"),
    [
        (device("Acme Pathfinder 3", total_mib=8192), "no card row"),
        (device("Acme Vector 7", total_mib=8192), "no size of 8 GB"),
        (
            device("Acme Vector 7", pci_device="0x1a99", total_mib=16384),
            "0x1a99 is listed by no nvidia row",
        ),
        (device(None, total_mib=4096), "names no card"),
        (device("NVIDIA GeForce GPU", total_mib=4096), "names no card"),
    ],
    ids=["unknown-name", "other-memory", "unlisted-id", "unnamed", "all-vendor-words"],
)
def test_a_card_with_no_row_keeps_its_reading_and_knows_no_table_fact(
    card: Device, said: str
) -> None:
    record = machine_capability.of_scan(scan(card), TABLE)
    found = record.cards[0]
    assert found.reading is card
    assert found.reading.total_mib == card.total_mib
    assert not found.table.matched
    assert found.table.rows == () and found.table.by is None
    assert said in found.table.why
    assert found.table.cells == {}
    for field in ("memory.bandwidth_gbps", "memory.size_gb", "compute.fp32_tflops"):
        assert found.table.cell(field).state == UNKNOWN
        assert found.table.cell(field).value is None
    assert record.pools()[0].total_mib == card.total_mib


def test_a_cpu_no_row_lists_has_no_row_and_keeps_its_reading() -> None:
    record = machine_capability.of_scan(
        scan(cpu_model="Intel(R) Acme(TM) Q9 7700X CPU @ 4.00GHz"), TABLE
    )
    assert record.cpu.model == "Intel(R) Acme(TM) Q9 7700X CPU @ 4.00GHz"
    assert (record.cpu.cores, record.cpu.threads) == (8, 16)
    assert not record.cpu.table.matched
    assert "lists a model" in record.cpu.table.why


def test_a_cpu_a_row_lists_is_matched_by_that_model() -> None:
    record = machine_capability.of_scan(
        scan(cpu_model="Intel(R) Acme(TM) Q9 7700 CPU @ 4.00GHz"), TABLE
    )
    assert record.cpu.table.rows == ("acme-q9-family",)
