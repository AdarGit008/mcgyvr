"""Unified memory is one pool, and the RAM's bandwidth is the reading's probe.

A GPU that shares the machine's memory (a Mac's) is matched to its chip's row by
name and by the machine's RAM against the sizes the row states, and so is the
Mac's CPU. Its memory is a share of the RAM, not a second memory: the record's
pools count the RAM once, held by the RAM and the GPU, while a card with memory
of its own is a pool of its own. The RAM's bandwidth is the probe's figure, or
none; a table's maximum never stands in for it. The table and the machines are
invented.
"""

from __future__ import annotations

from mcgyvr import machine_capability
from mcgyvr.machine_capability import RAM, Pool
from mcgyvr.scan import Bandwidth
from tests.invented_hardware import device, row, scan, table

TABLE = table(
    row(
        "acme-q3-max-30c",
        "apple",
        "soc",
        name="Q3 Max (14-core CPU, 30-core GPU)",
        memory__sizes_gb=[36, 96],
        memory__bandwidth_gbps=300,
    ),
    row(
        "acme-q3-max-40c",
        "apple",
        "soc",
        name="Q3 Max (16-core CPU, 40-core GPU)",
        memory__sizes_gb=[48, 64, 128],
        memory__bandwidth_gbps=400,
    ),
    row(
        "acme-q9-family",
        "intel",
        "cpu",
        name="Acme Q9",
        models=["Q9 7700"],
        memory__max_bandwidth_gbps=89.6,
    ),
    row("acme-vector-7", "nvidia", "gpu", name="Acme Vector 7", memory__size_gb=16),
)
GPU = device(
    "Apple Q3 Max GPU",
    vendor="apple",
    kind="unified",
    backend="metal",
    total_mib=36864,
    read_from="sysctl",
)


def test_a_macs_gpu_and_cpu_meet_their_chips_row_by_name_and_ram() -> None:
    record = machine_capability.of_scan(
        scan(GPU, ram_gib=48, cpu_model="Apple Q3 Max"), TABLE
    )
    (card,) = record.cards
    assert card.unified
    assert card.table.rows == ("acme-q3-max-40c",)
    assert "48 GB" in card.table.why
    assert card.table.cell("memory.bandwidth_gbps").value == 400
    assert record.cpu.table.rows == ("acme-q3-max-40c",)


def test_unified_memory_is_one_pool_counted_once() -> None:
    record = machine_capability.of_scan(
        scan(GPU, ram_gib=48, cpu_model="Apple Q3 Max"), TABLE
    )
    assert record.pools() == (Pool(RAM, 48 * 1024, (RAM, "apple:0")),)
    assert sum(pool.total_mib or 0 for pool in record.pools()) == 48 * 1024


def test_a_card_with_its_own_memory_is_a_pool_beside_the_ram() -> None:
    card = device("Acme Vector 7", total_mib=16384)
    record = machine_capability.of_scan(scan(card, ram_gib=64), TABLE)
    assert record.pools() == (
        Pool("nvidia:0", 16384, ("nvidia:0",)),
        Pool(RAM, 64 * 1024, (RAM,)),
    )


def test_the_rams_bandwidth_is_the_probes_and_never_a_tables_maximum() -> None:
    probed = machine_capability.of_scan(
        scan(cpu_model="Intel Acme Q9 7700", bandwidth_gbps=51.5), TABLE
    )
    assert probed.ram.bandwidth == Bandwidth(measured_gbps=51.5, how="memcpy probe")
    unprobed = machine_capability.of_scan(
        scan(cpu_model="Intel Acme Q9 7700", bandwidth_gbps=None), TABLE
    )
    assert unprobed.cpu.table.cell("memory.max_bandwidth_gbps").value == 89.6
    assert unprobed.ram.bandwidth is None
    mac = machine_capability.of_scan(scan(GPU, ram_gib=48, bandwidth_gbps=None), TABLE)
    assert mac.cards[0].table.cell("memory.bandwidth_gbps").value == 400
    assert mac.ram.bandwidth is None
