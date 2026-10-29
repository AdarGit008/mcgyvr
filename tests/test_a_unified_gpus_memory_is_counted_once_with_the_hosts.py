"""A unified GPU's memory is counted once with the host's.

A unified GPU holds what it is given in the host's own memory, so what a unit
takes on it is not also there for the experts it spills or the blob it maps;
the same sizing on a card with memory of its own leaves the host's memory
whole. A claim on a unified GPU leaves the host's memory as well. The scratch
readings taken under one backend are never given to a card of another. The
machine is an invented unified-memory shape, and its twin with a discrete card
is the same figures with the card's kind changed.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from mcgyvr import recommend
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    ModelSpec,
    UnitError,
    _remaining_scan,
    fit,
    hold_together,
    unit_for,
    vramfit,
)
from tests import machine_shapes

WINDOW = 4096
BLOCKS = 3
GIB = 1 << 30


def unified() -> Scan:
    return replace(
        machine_shapes.host_scan(machine_shapes.host_shape("unified-desktop-capped")),
        disk=None,
    )


def discrete(scan: Scan) -> Scan:
    """The same machine with its card's memory its own."""
    (gpu,) = scan.gpus
    return replace(scan, gpus=(replace(gpu, kind="gpu", backend="cuda"),))


def geometry(scan: Scan) -> dict[str, Any]:
    """An invented MoE whose shared weights take half of the card beside the
    scratch allowance and whose three expert blocks a quarter each: two stay on
    the card and one spills."""
    room = (max(g.vram.free_mib for g in scan.gpus) << 20) - (
        vramfit.SCRATCH_AND_CONTEXT_MIB << 20
    )
    nonexpert, block = room // 2, room // 4
    return {
        "file": "/models/example-moe.gguf",
        "size_bytes": nonexpert + block * BLOCKS,
        "arch": "invented",
        "n_layer": BLOCKS,
        "bytes_nonexpert": nonexpert,
        "bytes_experts": block * BLOCKS,
        "placeable_blocks": list(range(BLOCKS)),
        "expert_bytes_by_block": {str(i): block for i in range(BLOCKS)},
        "kv_layers": [],
        "n_recurrent": 0,
    }


def spec(scan: Scan) -> ModelSpec:
    shape = geometry(scan)
    return ModelSpec(
        name="example-moe",
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=shape["size_bytes"] / GIB,
        geometry=shape,
        hf_cache="/models/hf",
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )


def test_the_spill_must_fit_beside_what_the_unified_gpu_holds() -> None:
    scan = unified()
    shared = fit(scan, spec(scan), engine="llama.cpp", ctx_per_slot=WINDOW)
    own = fit(discrete(scan), spec(scan), engine="llama.cpp", ctx_per_slot=WINDOW)
    assert own.fits, own.why
    assert own.load_mode == "none" and own.ram_gb > 0
    assert not shared.fits
    assert "unified GPU taken from the host's" in shared.why


def test_a_plan_keeps_the_experts_to_what_the_unified_gpu_leaves() -> None:
    scan = unified()
    header = {**geometry(scan), "n_ctx_train": WINDOW}
    assert recommend._fits(discrete(scan), header, 1)
    assert not recommend._fits(scan, header, 1)


def test_a_claim_on_a_unified_gpu_leaves_the_host_too() -> None:
    scan = unified()
    assert scan.memory is not None and scan.memory.available_gb is not None
    left = _remaining_scan(scan, 10.0)
    assert left.memory is not None and left.memory.available_gb is not None
    assert left.memory.available_gb == pytest.approx(scan.memory.available_gb - 10.0)
    assert left.gpus[0].vram.free_mib == scan.gpus[0].vram.free_mib - 10 * 1024
    other = _remaining_scan(discrete(scan), 10.0)
    assert other.memory == scan.memory


@pytest.mark.parametrize("backend", ["metal", "vulkan", "rocm"])
def test_a_scratch_reading_taken_under_cuda_is_not_another_backends(
    backend: str,
) -> None:
    arch, by_batch = next(iter(vramfit.MEASURED_SCRATCH_MIB.items()))
    batch, reading = next(iter(by_batch.items()))
    shape = {"arch": arch}
    assert vramfit.allowance_mib(shape, n_ubatch=batch) == reading
    assert (
        vramfit.allowance_mib(shape, n_ubatch=batch, backend=backend)
        == vramfit.SCRATCH_AND_CONTEXT_MIB
    )


def test_co_resident_units_on_a_unified_gpu_sum_card_and_host_memory() -> None:
    """Two units whose stated card and host figures fit a discrete card and the
    host together: on a unified GPU what they hold on the card is host memory
    too, and the pair no longer fits."""
    own = Scan.of(
        host="box-1.example",
        vram_mib=12288,
        ram_gb=14.0,
        disk_free_gb=900.0,
        cores=8,
        threads=8,
        bandwidth_gbps=40.0,
    )
    (gpu,) = own.gpus
    shared = replace(own, gpus=(replace(gpu, kind="unified", backend="metal"),))
    units = tuple(
        unit_for(
            own,
            ModelSpec(
                name=name,
                vram_gb=3.0,
                ram_gb=1.0,
                disk_gb=5.0,
                kv_cache_dtype_k="f16",
                kv_cache_dtype_v="f16",
            ),
            engine="llama.cpp",
            port=port,
            ctx_per_slot=WINDOW,
        )
        for name, port in (("first", 8080), ("second", 8081))
    )
    assert hold_together(units, {"box-1.example": own}) == ()
    with pytest.raises(UnitError, match=r"first .* second .* unified GPU"):
        hold_together(units, {"box-1.example": shared})
