"""Sizing a model, and whose host memory pays for it."""

from __future__ import annotations

from typing import Any

from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, vramfit
from tests import machine_shapes

#: The window every sizing here declares.
WINDOW = 4096


#: The invented model: its name, and how many expert blocks it has.
MODEL = "example-moe"


BLOCKS = 8


def machines() -> list[machine_shapes.Shape]:
    """Every invented machine whose scan reports a card."""
    return [machine for machine in machine_shapes.shapes() if machine.readable_cards]


def spilling(scan: Scan) -> ModelSpec:
    """An invented MoE that fits the roomiest card of ``scan`` only by spilling.

    Its non-expert weights and the card's scratch allowance take half of the
    card's free memory; each expert block takes a quarter of what the
    allowance leaves, so two blocks stay on the card and the rest spill to
    host memory. It caches nothing and has no recurrent state, so its slot
    count moves nothing here.
    """
    free = max(gpu.vram.free_mib for gpu in scan.gpus) << 20
    room = free - (vramfit.SCRATCH_AND_CONTEXT_MIB << 20)
    nonexpert = room // 2
    block = room // 4
    by_block = {str(index): block for index in range(BLOCKS)}
    geometry: dict[str, Any] = {
        "file": f"/models/{MODEL}.gguf",
        "size_bytes": nonexpert + block * BLOCKS,
        "arch": "invented",
        "n_layer": BLOCKS,
        "bytes_nonexpert": nonexpert,
        "bytes_experts": block * BLOCKS,
        "placeable_blocks": list(range(BLOCKS)),
        "expert_bytes_by_block": by_block,
        "kv_layers": [],
        "n_recurrent": 0,
    }
    return ModelSpec(
        name=MODEL,
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=geometry,
        hf_cache="/models/hf",
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )
