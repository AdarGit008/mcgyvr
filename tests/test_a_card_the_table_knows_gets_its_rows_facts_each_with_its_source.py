"""A card the table knows gets its row's facts, each with its source.

A card is matched to its row by its PCI device id where the reading has one and
the table lists ids for its vendor, whichever way the table spells the id, else
by its name and memory. The record keeps the reading's own entry of the card,
and beside it the row's cells as the table states them: a value, a stated no
(false, an empty list, or no value with a page cited), or unknown (a field the
row does not carry). A stated no stays a no; an absent cell stays unknown. The
table and the machines are invented.
"""

from __future__ import annotations

from mcgyvr import machine_capability
from mcgyvr.hardware_table import NO, UNKNOWN, VALUE, Cell
from mcgyvr.scan import Device
from tests.invented_hardware import cell, device, row, scan, table

VECTOR = row(
    "acme-vector-7-16gb",
    "nvidia",
    "gpu",
    name="Acme Vector 7",
    pci_device_ids=["1A2B"],
    memory__size_gb=16,
    memory__bandwidth_gbps=448,
    compute__fp32_tflops=cell(20.1, "s2"),
    compute__matrix_units=False,
    formats__matrix__precisions=[],
    formats__int8_dot=Cell(value=None, source="s1"),
    compute__fp64_tflops=Cell(),
)
ARC = row(
    "acme-arc-5",
    "intel",
    "gpu",
    name="Acme Arc 5 Graphics (12GB)",
    pci_device_ids=["0x5C0D"],
    memory__size_gb=12,
)
RIVER = row(
    "acme-river-9",
    "amd",
    "gpu",
    name="Acme River 9 XT",
    pci_device_ids=Cell(),
    memory__size_gb=20,
    memory__bandwidth_gbps=800,
)
TABLE = table(VECTOR, ARC, RIVER)


def _card(card: Device) -> machine_capability.Card:
    return machine_capability.of_scan(scan(card), TABLE).cards[0]


def test_a_card_read_with_its_pci_id_gets_its_rows_facts_and_sources() -> None:
    card = device(
        "Example Card", pci_device="0x1a2b", total_mib=16376, read_from="nvidia-smi"
    )
    found = _card(card)
    assert found.reading is card
    assert found.table.rows == ("acme-vector-7-16gb",)
    assert found.table.by == machine_capability.BY_PCI_ID
    bandwidth = found.table.cell("memory.bandwidth_gbps")
    assert (bandwidth.state, bandwidth.value, bandwidth.source) == (VALUE, 448, "s1")
    fp32 = found.table.cell("compute.fp32_tflops")
    assert (fp32.value, fp32.source) == (20.1, "s2")
    assert found.table.differing == ()


def test_the_table_spells_an_id_either_way_and_the_reading_matches_it() -> None:
    found = _card(
        device(
            None, vendor="intel", pci_device="0x5c0d", total_mib=None, backend="vulkan"
        )
    )
    assert found.table.rows == ("acme-arc-5",)
    assert found.table.by == machine_capability.BY_PCI_ID


def test_a_card_whose_vendor_lists_no_ids_is_matched_by_name_and_memory() -> None:
    found = _card(
        device(
            "AMD Acme River 9 XT",
            vendor="amd",
            pci_device="0x744c",
            total_mib=20464,
            backend="rocm",
        )
    )
    assert found.table.rows == ("acme-river-9",)
    assert found.table.by == machine_capability.BY_NAME
    assert "20 GB" in found.table.why


def test_a_card_read_without_an_id_is_matched_by_name() -> None:
    found = _card(device("NVIDIA Acme Vector 7", total_mib=16384))
    assert found.table.rows == ("acme-vector-7-16gb",)
    assert found.table.by == machine_capability.BY_NAME


def test_a_stated_no_stays_a_no_and_an_absent_cell_stays_unknown() -> None:
    facts = _card(device("Acme Vector 7", total_mib=16384)).table
    assert facts.cell("compute.matrix_units").state == NO
    assert facts.cell("formats.matrix.precisions").state == NO
    assert facts.cell("formats.int8_dot").state == NO
    assert facts.cell("compute.fp64_tflops").state == UNKNOWN
    assert facts.cell("api.cuda_compute_capability").state == UNKNOWN
    assert facts.cell("api.cuda_compute_capability").value is None
