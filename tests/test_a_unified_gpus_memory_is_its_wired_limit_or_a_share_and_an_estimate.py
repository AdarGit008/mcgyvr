"""A unified GPU's memory is its wired limit or a share of memory, an estimate.

The memory a Mac's GPU may use is the kernel's wired limit when one is set,
else the stated share of the machine's memory, and either is an estimate that
names its basis; the working-set figure llama.cpp logs is a reading and wins.
The reader sizes every invented unified-memory machine's GPU the same way.
"""

from __future__ import annotations

import pytest

from mcgyvr import estimate
from tests import machine_shapes

GIB_IN_MB = 1024


def test_32_gb_with_no_wired_limit_is_24_gb_and_an_estimate() -> None:
    got = estimate.usable_unified_mb(32 * GIB_IN_MB)
    assert got.value == 24 * GIB_IN_MB
    assert got.value == int(32 * GIB_IN_MB * estimate.UNIFIED_SHARE)
    assert got.figure == "estimate"
    assert "no wired limit" in got.basis


@pytest.mark.parametrize(("limit", "expected"), [(20000, 20000), (40000, 32768)])
def test_a_wired_limit_is_the_size_held_to_the_memory(
    limit: int, expected: int
) -> None:
    got = estimate.usable_unified_mb(32 * GIB_IN_MB, limit)
    assert (got.value, got.figure) == (expected, "estimate")
    assert "wired_limit" in got.basis


def test_the_working_set_llama_cpp_logged_is_a_reading_and_wins() -> None:
    got = estimate.usable_unified_mb(32 * GIB_IN_MB, 20000, working_set_mb=22000)
    assert (got.value, got.figure) == (22000, "reading")


@pytest.mark.parametrize(
    "machine",
    [m for m in machine_shapes.host_shapes() if m.chip is not None],
    ids=lambda m: m.label,
)
def test_the_reader_sizes_each_unified_gpu_as_the_product_does(
    machine: machine_shapes.HostShape,
) -> None:
    (gpu,) = machine_shapes.host_scan(machine).gpus
    usable = estimate.usable_unified_mb(machine.memory_mib, machine.wired_limit_mib)
    assert gpu.vram.total_mib == usable.value
    assert gpu.figure == usable.figure == "estimate"


@pytest.mark.parametrize(
    "machine",
    [m for m in machine_shapes.host_shapes() if m.chip is not None],
    ids=lambda m: m.label,
)
def test_a_fit_listing_takes_the_usable_memory_as_the_unified_gpus_vram(
    machine: machine_shapes.HostShape,
) -> None:
    (gpu,) = machine_shapes.host_detection(machine).gpus
    usable = estimate.usable_unified_mb(machine.memory_mib, machine.wired_limit_mib)
    assert gpu.unified and gpu.figure == "estimate"
    assert gpu.vram_gb == round(usable.value / GIB_IN_MB, 1)
    assert gpu.vram_gb is not None and gpu.vram_gb < machine.memory_mib / GIB_IN_MB
