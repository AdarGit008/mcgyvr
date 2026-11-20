"""Rows a reading cannot tell apart keep only the facts they share.

When more than one row matches a device (variants of one name, a PCI id two
cards share, a card whose memory was not read), a fact every candidate states
alike, in one state with one value, is kept; a fact they state differently (a
value against another value, a stated no against unknown) is unknown, and the
record names the candidate rows and the fields they differ on. Nothing picks
one of them. A memory read that only one variant holds leaves that one. The
table and the machines are invented.
"""

from __future__ import annotations

from mcgyvr import machine_capability
from mcgyvr.hardware_table import UNKNOWN, VALUE, Cell
from mcgyvr.scan import Device
from tests.invented_hardware import cell, device, row, scan, table

SHARED = ["1B00", "1B01"]
TABLE = table(
    row(
        "acme-vector-5-fast",
        "nvidia",
        "gpu",
        name="Acme Vector 5",
        pci_device_ids=SHARED,
        memory__size_gb=12,
        memory__type="XDDR6X",
        memory__bandwidth_gbps=504,
        compute__fp32_tflops=29.1,
        api__cuda_compute_capability="9.1",
        compute__matrix_units=Cell(),
    ),
    row(
        "acme-vector-5-slow",
        "nvidia",
        "gpu",
        name="Acme Vector 5",
        pci_device_ids=SHARED,
        memory__size_gb=12,
        memory__type="XDDR6",
        memory__bandwidth_gbps=480,
        compute__fp32_tflops=cell(29.1, "s2"),
        api__cuda_compute_capability="9.1",
        compute__matrix_units=False,
    ),
    row(
        "acme-arc-3-16gb",
        "intel",
        "gpu",
        name="Acme Arc 3 (16GB)",
        pci_device_ids=["0x5D00"],
        memory__size_gb=16,
        memory__bandwidth_gbps=560,
    ),
    row(
        "acme-arc-3-8gb",
        "intel",
        "gpu",
        name="Acme Arc 3 (8GB)",
        pci_device_ids=["0x5D00"],
        memory__size_gb=8,
        memory__bandwidth_gbps=512,
    ),
    row(
        "acme-q9-desktop",
        "amd",
        "cpu",
        name="Q9 desktop",
        models=["Q9 7700"],
        cores={"largest": 8},
    ),
    row(
        "acme-q9-wide",
        "amd",
        "cpu",
        name="Q9 wide",
        models=["Q9 7700", "Q9 7900"],
        cores={"largest": 12},
    ),
)


def _facts(card: Device) -> machine_capability.TableFacts:
    return machine_capability.of_scan(scan(card), TABLE).cards[0].table


def test_variants_of_one_id_keep_the_facts_they_share_and_name_the_rest() -> None:
    facts = _facts(device("Acme Vector 5", pci_device="0x1b01", total_mib=12282))
    assert facts.rows == ("acme-vector-5-fast", "acme-vector-5-slow")
    assert "cannot tell them apart" in facts.why
    assert facts.cell("compute.fp32_tflops").state == VALUE
    assert facts.cell("compute.fp32_tflops").value == 29.1
    assert facts.cell("api.cuda_compute_capability").value == "9.1"
    for field in ("memory.type", "memory.bandwidth_gbps", "compute.matrix_units"):
        assert facts.cell(field).state == UNKNOWN, field
        assert field in facts.differing
    assert "compute.fp32_tflops" not in facts.differing


def test_an_unread_memory_keeps_every_size_its_id_is_listed_with() -> None:
    facts = _facts(
        device(
            "PCI 0x8086:0x5d00",
            vendor="intel",
            pci_device="0x5d00",
            total_mib=None,
            backend="vulkan",
        )
    )
    assert facts.rows == ("acme-arc-3-16gb", "acme-arc-3-8gb")
    assert "its memory unread" in facts.why
    assert facts.cell("memory.size_gb").state == UNKNOWN
    assert "memory.size_gb" in facts.differing


def test_a_memory_one_variant_holds_leaves_that_variant() -> None:
    facts = _facts(
        device(
            None, vendor="intel", pci_device="0x5d00", total_mib=8192, backend="vulkan"
        )
    )
    assert facts.rows == ("acme-arc-3-8gb",)
    assert facts.cell("memory.bandwidth_gbps").value == 512
    assert facts.differing == ()


def test_a_cpu_two_rows_list_is_matched_to_both() -> None:
    record = machine_capability.of_scan(
        scan(cpu_model="AMD Acme Q9 7700 8-Core Processor"), TABLE
    )
    assert record.cpu.table.rows == ("acme-q9-desktop", "acme-q9-wide")
    assert record.cpu.table.cell("cores").state == UNKNOWN
    assert "models" in record.cpu.table.differing
