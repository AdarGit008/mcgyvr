"""The product's sizer and the hub's planner size a card by one law, in hubwire.

What a card of a llama.cpp layer split holds -- its blocks' weights, their caches
at the run's cells, their state, and an allowance beside them -- is defined once,
in :mod:`mcgyvr.hubwire` (the one module the hub may import), and each planner
keeps its own search. These tests hold the product's side to it:

* the measured runs both planners are held to (``hubwire.FIT_CALIBRATION_RUNS``)
  load and refuse in the product's split search as they did on the rigs, but for
  one whose fit needs the output layer on the worker's card, which the product's
  search never makes (it keeps the head's cards last) and the hub's makes when
  nothing else fits; the law itself admits that run on the hub's split;
* a split card and a single card are charged the same allowance at the same
  context, slots and card (I-23), and it is ``hubwire.card_allowance``;
* a shard's bytes are ``hubwire.bytes_on_card`` of its blocks.

The hub's copy of the first reading runs the same runs through its own planner.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, fit, sharding, vramfit
from mcgyvr.serving.sharding import SPLIT_LAYER, Grid, Target
from tests._paths import TESTS

MIB = 1 << 20
#: The run the product's search refuses although it loaded: the 48-layer MoE over
#: three cards at 180224 tokens.
NEEDS_THE_OUTPUT_ON_A_WORKER = "moe-three-180224"


def table(run: hubwire.MeasuredRun) -> dict[str, Any]:
    """The tensor table of a measured run's model as a hello states it: every
    block the same size, the output on the last card, and every layer's q8_0
    cache the run's bytes a token over the layer count."""
    n = run.n_layers
    block = -(-(run.size_bytes - run.embd_bytes - run.output_bytes) // n)
    elements = run.kv_bytes_per_token * 32 // 34 // n
    assert elements * 34 * n == run.kv_bytes_per_token * 32
    return {
        "n_layer": n,
        "n_embd": run.n_embd,
        "bytes_by_block": {str(b): block for b in range(n)},
        "bytes_matrix_by_block": {str(b): block for b in range(n)},
        "bytes_input": run.embd_bytes,
        "bytes_output": run.output_bytes,
        "bytes_output_matrix": run.output_bytes,
        "kv_layers": [
            {
                "layer": b,
                "is_swa": False,
                "k_elems": elements // 2,
                "v_elems": elements // 2,
                "heads": 8,
            }
            for b in range(n)
        ],
    }


def targets(run: hubwire.MeasuredRun) -> list[Target]:
    head = [
        Target(host="head-rig", gpu=i, free_bytes=free * MIB)
        for i, free in enumerate(run.head_free_mib)
    ]
    worker = [
        Target(host="worker-rig", gpu=i, free_bytes=free * MIB)
        for i, free in enumerate(run.worker_free_mib)
    ]
    return [*head, *worker]


def planned(run: hubwire.MeasuredRun) -> sharding.Plan:
    cards = targets(run)
    return sharding.plan(
        table(run),
        cards,
        Grid(tensor=1, pipeline=len(cards), split=SPLIT_LAYER),
        engine="llama.cpp",
        slots=run.slots,
        ctx_per_slot=run.ctx,
        cache_type_k="q8_0",
        cache_type_v="q8_0",
        n_ubatch=512,
        name=run.label,
    )


@pytest.mark.parametrize("run", hubwire.FIT_CALIBRATION_RUNS, ids=lambda r: r.label)
def test_the_product_loads_and_refuses_the_measured_runs(
    run: hubwire.MeasuredRun,
) -> None:
    made = planned(run)
    if run.label == NEEDS_THE_OUTPUT_ON_A_WORKER:
        assert run.loaded and not made.fits
        return
    assert made.fits == run.loaded, made.says()


def test_the_law_admits_the_run_with_the_output_on_the_worker() -> None:
    """The hub's split of it: 20 blocks on each head card, 8 and the output on
    the worker's, every card within its free memory by the shared law."""
    [run] = [r for r in hubwire.FIT_CALIBRATION_RUNS if r.label == "moe-three-180224"]
    rows = table(run)
    block = rows["bytes_by_block"]["0"]
    per_layer = run.kv_bytes_per_token / run.n_layers

    def card(layers: int, output: bool) -> int:
        return hubwire.bytes_on_card(
            weights=layers * block + (run.output_bytes if output else 0),
            full_bytes_per_token=layers * per_layer,
            n_ctx=run.ctx,
            n_seq_max=run.slots,
            arch=None,
            backend=None,
            unified=False,
            layer_f16_bytes_per_token=vramfit.widest_layer_f16_bytes(rows),
        )

    free = [f * MIB for f in (*run.head_free_mib, *run.worker_free_mib)]
    held = [card(20, False), card(20, False), card(8, True)]
    assert all(h <= f for h, f in zip(held, free, strict=True)), (held, free)


GEOMETRY: dict[str, Any] = json.loads(
    (TESTS / "fixtures" / "gguf_geometry.json").read_text()
)


@pytest.mark.parametrize(
    "name", ["Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", "deepseek-coder-v2-16b.gguf"]
)
@pytest.mark.parametrize(("ctx", "slots"), [(4096, 1), (8192, 4)])
def test_a_split_card_and_a_single_card_are_charged_one_allowance(
    name: str, ctx: int, slots: int
) -> None:
    geometry = GEOMETRY[name]
    law = hubwire.card_allowance(
        geometry["arch"],
        cells=hubwire.cache_cells(ctx * slots, slots),
        n_ubatch=512,
        backend=hubwire.BACKEND_CUDA,
        unified=False,
        layer_f16_bytes_per_token=vramfit.widest_layer_f16_bytes(geometry),
    )
    assert vramfit.allowance(geometry, n_ctx=ctx * slots, n_seq_max=slots) == law

    split = sharding._allowance_bytes(
        geometry,
        [Target(host="a-rig", gpu=0, free_bytes=1 << 34)] * 2,
        engine="llama.cpp",
        slots=slots,
        ctx_per_slot=ctx,
        n_ubatch=512,
        name=name,
        split=SPLIT_LAYER,
    )
    assert split == law.total

    spec = ModelSpec(
        name=name.removesuffix(".gguf"),
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=geometry,
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )
    one_card = Scan.of(host="a-rig", vram_mib=98304, ram_gb=256.0, disk_free_gb=500.0)
    sized = fit(one_card, spec, engine="llama.cpp", width=slots, ctx_per_slot=ctx)
    assert sized.fits, sized.why
    assert sized.headroom_gb == law.total / (1 << 30)


def test_a_measured_arch_is_charged_its_reading_and_another_the_growing_law() -> None:
    measured = hubwire.card_allowance(
        "qwen3next",
        cells=4096,
        n_ubatch=512,
        backend=hubwire.BACKEND_CUDA,
        unified=False,
        layer_f16_bytes_per_token=0,
    )
    assert measured.measured and measured.total == int(829.0 * MIB)
    off_cuda = hubwire.card_allowance(
        "qwen3next",
        cells=4096,
        n_ubatch=512,
        backend=hubwire.BACKEND_METAL,
        unified=True,
        layer_f16_bytes_per_token=0,
    )
    assert not off_cuda.measured
    assert off_cuda.context_bytes == hubwire.UNIFIED_CONTEXT_MIB * MIB
    small, large = (
        hubwire.card_allowance(
            None,
            cells=cells,
            n_ubatch=512,
            backend=None,
            unified=False,
            layer_f16_bytes_per_token=4096,
        ).total
        for cells in (4096, 32768)
    )
    # The dense model's measured buffers: 248 MiB at 4096 tokens, 360 at 32768.
    assert small == (hubwire.CARD_CONTEXT_MIB + 248) * MIB
    assert large == (hubwire.CARD_CONTEXT_MIB + 360) * MIB


def test_a_shard_holds_what_the_law_says_its_blocks_cost_on_its_card() -> None:
    [run] = [r for r in hubwire.FIT_CALIBRATION_RUNS if r.label == "dense-three-16384"]
    made = planned(run)
    rows = table(run)
    for shard in made.shards:
        has_output = shard is made.shards[-1]
        per_token = vramfit.cache_bytes_per_token(
            [r for r in rows["kv_layers"] if r["layer"] in shard.blocks],
            cache_type_k="q8_0",
            cache_type_v="q8_0",
        )
        assert shard.required_bytes == hubwire.bytes_on_card(
            weights=sum(rows["bytes_by_block"][str(b)] for b in shard.blocks)
            + (run.output_bytes if has_output else 0),
            full_bytes_per_token=per_token,
            n_ctx=run.ctx,
            n_seq_max=run.slots,
            arch=None,
            backend=hubwire.BACKEND_CUDA,
            unified=False,
            layer_f16_bytes_per_token=vramfit.widest_layer_f16_bytes(rows),
        )


def _measured(arch: str, cells: int, *, unified: bool = False) -> hubwire.Allowance:
    return hubwire.card_allowance(
        arch,
        cells=cells,
        n_ubatch=512 if arch != "nemotron_h_moe" else 256,
        backend=hubwire.BACKEND_CUDA,
        unified=unified,
        layer_f16_bytes_per_token=0,
    )


def test_a_reading_holds_at_its_context_and_grows_past_it() -> None:
    """qwen35moe's 316.57 MiB was read at ``-c 16384 -np 2``: at those cells it
    is the reading, and past them each cell adds what the law's buffers grow by
    (the KQ mask, 6 bytes an ubatch row), so a context thirteen times larger is
    not charged the small one's buffers."""
    read_at = hubwire.MEASURED_SCRATCH_CELLS["qwen35moe"][512]
    assert read_at == hubwire.cache_cells(16384, 2)
    reading = int(hubwire.MEASURED_SCRATCH_MIB["qwen35moe"][512] * MIB)
    assert _measured("qwen35moe", read_at).total == reading
    assert _measured("qwen35moe", 4096).total == reading
    per_cell = hubwire.compute_bytes_per_cell(n_ubatch=512, layer_f16_bytes_per_token=0)
    assert per_cell == hubwire.KQ_MASK_BYTES_PER_ROW * 512
    for cells in (131072, 211456, 262144):
        grown = _measured("qwen35moe", cells).total
        assert grown == reading + -(-(cells - read_at) * per_cell // MIB) * MIB
        assert grown - reading >= (cells - read_at) * per_cell


def test_a_reading_with_no_context_on_record_grows_from_none() -> None:
    """nemotron_h_moe's reading has no context beside it, so every cell is charged
    growth: never less than the law's slope from zero."""
    assert "nemotron_h_moe" not in hubwire.MEASURED_SCRATCH_CELLS
    reading = int(hubwire.MEASURED_SCRATCH_MIB["nemotron_h_moe"][256] * MIB)
    per_cell = hubwire.KQ_MASK_BYTES_PER_ROW * 256
    assert _measured("nemotron_h_moe", 8192).total == reading + 8192 * per_cell


def test_a_measured_card_is_charged_at_least_its_context() -> None:
    """On a unified CUDA device the card's context (512 MiB) is more than
    qwen35moe's whole reading: the card is charged its context, as the hub's
    planner charges its reserve, and the buffers nothing more."""
    discrete = _measured("qwen35moe", 4096)
    assert discrete.context_bytes == hubwire.CARD_CONTEXT_MIB * MIB
    assert discrete.total == int(hubwire.MEASURED_SCRATCH_MIB["qwen35moe"][512] * MIB)
    unified = _measured("qwen35moe", 4096, unified=True)
    assert unified.measured
    assert unified.context_bytes == hubwire.UNIFIED_CONTEXT_MIB * MIB
    assert unified.compute_bytes == 0
    assert unified.total == hubwire.UNIFIED_CONTEXT_MIB * MIB
