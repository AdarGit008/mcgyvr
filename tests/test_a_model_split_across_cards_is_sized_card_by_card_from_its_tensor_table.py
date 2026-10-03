"""A model split across cards is sized card by card from its tensor table.

Promise: when a model is split over several cards, each card is charged the
bytes of the blocks it actually holds as the scan sums them, the cache and the
state of those blocks' layers, and one allowance of its own; never a share of
the file size. The split is stated to the engine in whole layers, so the engine
places every block where the sizing put it. A split that cannot be sized is
refused by name, and so is one that fits on no card.

The model and the machines here are invented: their sizes are chosen so the
arithmetic is checkable by eye.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import vramfit
from mcgyvr.serving.interconnect import Link
from mcgyvr.serving.sharding import (
    LLAMACPP_ENGINE,
    SPLIT_LAYER,
    VLLM_ENGINE,
    Grid,
    ShardingError,
    Target,
    choose,
    plan,
)

MIB = 1 << 20
GIB = 1 << 30
ALLOWANCE = 512 * MIB


def table(
    *,
    blocks: int = 8,
    block_mib: int = 400,
    norms_mib: int = 1,
    heads: int = 8,
    n_head: int = 32,
    head_dim: int = 128,
) -> dict[str, Any]:
    """An invented dense model: ``blocks`` equal blocks, an embedding, a head."""
    return {
        "file": "example-model-large.gguf",
        "arch": "invented",
        "n_layer": blocks,
        "n_embd": 4096,
        "n_head": n_head,
        "bytes_by_block": {str(b): block_mib * MIB for b in range(blocks)},
        "bytes_matrix_by_block": {
            str(b): (block_mib - norms_mib) * MIB for b in range(blocks)
        },
        "bytes_input": 300 * MIB,
        "bytes_output": 302 * MIB,
        "bytes_output_matrix": 300 * MIB,
        "kv_layers": [
            {
                "layer": b,
                "is_swa": False,
                "k_elems": heads * head_dim,
                "v_elems": heads * head_dim,
                "heads": heads,
            }
            for b in range(blocks)
        ],
        "recurrent_blocks": [],
    }


def links(cls: str) -> Link:
    """Fixed, invented link figures, so a test's crossing cost is its own."""
    figures = {"pcie": (10.0, 10.0), "network": (0.1, 200.0)}
    gib_s, latency_us = figures[cls]
    return Link(
        link_class=cls,
        gib_s=gib_s,
        latency_us=latency_us,
        source="estimate",
        where=Path("numbers.json"),
    )


def cards(*frees_gib: float, host: str = "box-a.example") -> list[Target]:
    return [
        Target(host=host, gpu=i, free_bytes=int(f * GIB))
        for i, f in enumerate(frees_gib)
    ]


def sized(model: dict[str, Any], targets: list[Target], grid: Grid, **kw: Any) -> Any:
    args: dict[str, Any] = {
        "engine": LLAMACPP_ENGINE,
        "slots": 2,
        "ctx_per_slot": 4096,
        "cache_type_k": "f16",
        "cache_type_v": "f16",
        "n_ubatch": 512,
        "name": "example-model-large",
        "links": links,
        "allowance_bytes": ALLOWANCE,
    }
    args.update(kw)
    return plan(model, targets, grid, **args)


# A layer split: whole blocks per card.


def test_each_card_holds_the_bytes_of_its_own_blocks_and_the_last_the_output() -> None:
    model = table()
    made = sized(model, cards(6, 6), Grid(tensor=1, pipeline=2, split=SPLIT_LAYER))

    held = [shard.blocks for shard in made.shards]
    assert held[0] + held[1] == tuple(range(8))
    for shard in made.shards[:-1]:
        assert shard.weights_bytes == 400 * MIB * len(shard.blocks)
    last = made.shards[-1]
    assert last.weights_bytes == 400 * MIB * len(last.blocks) + 302 * MIB


def test_the_input_embedding_stays_in_host_memory_under_llamacpp() -> None:
    model = table()
    made = sized(model, cards(6, 6), Grid(tensor=1, pipeline=2, split=SPLIT_LAYER))
    on_cards = sum(shard.weights_bytes for shard in made.shards)
    whole = 8 * 400 * MIB + 300 * MIB + 302 * MIB
    assert on_cards == whole - 300 * MIB


def test_the_split_is_stated_in_whole_layers_counting_the_output_layer() -> None:
    model = table()
    made = sized(model, cards(6, 6, 6), Grid(tensor=1, pipeline=3, split=SPLIT_LAYER))
    assert sum(made.layer_counts) == 8 + 1
    start = 0
    for shard, count in zip(made.shards, made.layer_counts, strict=True):
        assert shard.blocks == tuple(b for b in range(start, start + count) if b < 8)
        start += count


def test_a_roomier_card_is_given_more_blocks_so_the_fullest_is_as_empty_as_can_be() -> (
    None
):
    model = table()
    made = sized(model, cards(2, 6), Grid(tensor=1, pipeline=2, split=SPLIT_LAYER))
    small, large = made.shards
    assert len(small.blocks) < len(large.blocks)
    assert made.fits
    # Moving one block either way leaves some card fuller than the fullest now.
    fullest = max(shard.fullness for shard in made.shards)
    for shift in (-1, 1):
        counts = [made.layer_counts[0] + shift, made.layer_counts[1] - shift]
        if min(counts) < 1:
            continue
        first = counts[0] * 400 * MIB + ALLOWANCE
        assert (
            first / small.target.free_bytes >= fullest
            or ((counts[1] - 1) * 400 * MIB + 302 * MIB + ALLOWANCE)
            / large.target.free_bytes
            >= fullest
        )


def test_each_cards_cache_is_the_cache_of_its_own_layers() -> None:
    model = table()
    made = sized(model, cards(6, 6), Grid(tensor=1, pipeline=2, split=SPLIT_LAYER))
    whole = vramfit.kv_bytes(model, 2 * 4096, n_seq_max=2, n_ubatch=512)["total"]
    assert sum(shard.kv_bytes for shard in made.shards) == whole
    for shard in made.shards:
        rows = [r for r in model["kv_layers"] if r["layer"] in shard.blocks]
        expected = vramfit.kv_bytes(
            model, 2 * 4096, n_seq_max=2, n_ubatch=512, layers=rows
        )["total"]
        assert shard.kv_bytes == expected


def test_every_card_is_charged_the_allowance_a_single_card_fit_charges() -> None:
    model = table()
    made = sized(
        model,
        cards(6, 6),
        Grid(tensor=1, pipeline=2, split=SPLIT_LAYER),
        allowance_bytes=None,
    )
    expected = int(vramfit.allowance_mib(model, n_ubatch=512) * MIB)
    assert [shard.allowance_bytes for shard in made.shards] == [expected, expected]


# vLLM: tensor x pipeline.


def vllm(model: dict[str, Any], targets: list[Target], grid: Grid, **kw: Any) -> Any:
    args: dict[str, Any] = {
        "engine": VLLM_ENGINE,
        "cache_type_k": "float16",
        "cache_type_v": "",
    }
    args.update(kw)
    return sized(model, targets, grid, **args)


def test_a_vllm_tensor_split_gives_each_card_a_share_of_every_matrix_and_head() -> None:
    model = table()
    made = vllm(model, cards(6, 6), Grid(tensor=2, pipeline=1))
    for shard in made.shards:
        assert shard.blocks == tuple(range(8))
        per_block = 399 * MIB // 2 + 1 * MIB
        ends = 300 * MIB // 2 + 300 * MIB // 2 + 2 * MIB
        assert shard.weights_bytes == 8 * per_block + ends
        # 8 heads of 128 over two cards: 4 heads each, K and V, 2 bytes, at
        # every slot's window.
        assert shard.kv_bytes == 8 * (4 * 128 * 2) * 2 * 4096 * 2


def test_a_vllm_pipeline_gives_the_input_to_the_first_stage_the_head_to_the_last() -> (
    None
):
    model = table()
    made = vllm(model, cards(6, 6), Grid(tensor=1, pipeline=2))
    first, last = made.shards
    assert first.weights_bytes == 400 * MIB * len(first.blocks) + 300 * MIB
    assert last.weights_bytes == 400 * MIB * len(last.blocks) + 302 * MIB
    assert sum(made.layer_counts) == 8


def test_kv_heads_that_do_not_divide_over_the_cards_are_refused() -> None:
    model = table(heads=6, n_head=24)
    with pytest.raises(ShardingError, match="KV heads"):
        vllm(model, cards(6, 6, 6, 6), Grid(tensor=4, pipeline=1))


def test_vllm_is_never_asked_to_run_unequal_card_counts_on_two_machines() -> None:
    model = table()
    targets = [*cards(6, 6), *cards(6, host="box-b.example")]
    with pytest.raises(ShardingError, match="same number of cards"):
        vllm(model, targets, Grid(tensor=1, pipeline=3))


def test_a_vllm_cache_dtype_must_be_spelled_to_be_sized() -> None:
    with pytest.raises(ShardingError, match="auto"):
        vllm(table(), cards(6, 6), Grid(tensor=2, pipeline=1), cache_type_k="auto")


def test_a_vllm_cache_dtype_is_spelled_as_vllm_spells_it() -> None:
    # vLLM's --kv-cache-dtype takes float16 and bfloat16; fp16 and bf16 are
    # an argparse error at launch, so they are refused before anything starts.
    for spelled in ("fp16", "bf16"):
        with pytest.raises(ShardingError, match="float16"):
            vllm(table(), cards(6, 6), Grid(tensor=2, pipeline=1), cache_type_k=spelled)
    for spelled in ("float16", "bfloat16", "fp8"):
        vllm(table(), cards(6, 6), Grid(tensor=2, pipeline=1), cache_type_k=spelled)


# Tied embeddings: the output head is the input embedding.


def tied(model: dict[str, Any]) -> dict[str, Any]:
    """``model`` with no output head of its own, as a tied checkpoint has."""
    model = dict(model)
    model["tied_embeddings"] = True
    model["bytes_output"] = 2 * MIB
    model["bytes_output_matrix"] = 0
    return model


def test_a_vllm_pipelines_last_stage_holds_its_share_of_a_tied_embedding() -> None:
    made = vllm(tied(table()), cards(6, 6, 6, 6), Grid(tensor=2, pipeline=2))
    for shard in made.shards:
        per_block = 399 * MIB // 2 + 1 * MIB
        blocks = per_block * len(shard.blocks)
        if shard.stage == 0:
            assert shard.weights_bytes == blocks + 300 * MIB // 2
        else:
            # vLLM builds embed_tokens on the last rank too, to tie lm_head.
            assert shard.weights_bytes == blocks + 300 * MIB // 2 + 2 * MIB


def test_one_vllm_stage_holds_a_tied_embedding_once() -> None:
    made = vllm(tied(table()), cards(6, 6), Grid(tensor=2, pipeline=1))
    for shard in made.shards:
        assert shard.weights_bytes == 8 * (399 * MIB // 2 + 1 * MIB) + 150 * MIB + (
            2 * MIB
        )


def test_llamacpp_puts_a_copy_of_a_tied_embedding_on_the_output_layers_card() -> None:
    made = sized(
        tied(table()), cards(6, 6), Grid(tensor=1, pipeline=2, split=SPLIT_LAYER)
    )
    first, last = made.shards
    assert first.weights_bytes == 400 * MIB * len(first.blocks)
    # The input stays in host memory, and the output layer is a copy of it.
    assert last.weights_bytes == 400 * MIB * len(last.blocks) + 2 * MIB + 300 * MIB


# A multimodal tower sits on every vLLM rank, apart from the decoder blocks.


def test_a_vision_tower_is_charged_whole_to_every_vllm_rank() -> None:
    model = table()
    model["bytes_tower"] = 200 * MIB
    made = vllm(model, cards(6, 6), Grid(tensor=1, pipeline=2))
    first, last = made.shards
    assert first.weights_bytes == 400 * MIB * len(first.blocks) + 300 * MIB + 200 * MIB
    assert last.weights_bytes == 400 * MIB * len(last.blocks) + 302 * MIB + 200 * MIB


# Refusals.


def test_a_scan_without_the_per_block_sums_is_refused_with_the_command_to_rescan() -> (
    None
):
    model = table()
    del model["bytes_by_block"]
    with pytest.raises(ShardingError, match=r"python -m mcgyvr\.serving\.ggufscan"):
        sized(model, cards(6, 6), Grid(tensor=1, pipeline=2, split=SPLIT_LAYER))


def test_a_grid_that_does_not_match_the_cards_named_is_refused() -> None:
    with pytest.raises(ShardingError, match="names 2"):
        sized(table(), cards(6, 6), Grid(tensor=1, pipeline=3, split=SPLIT_LAYER))


def test_one_card_named_twice_is_refused() -> None:
    twice = [*cards(6), *cards(6)]
    with pytest.raises(ShardingError, match="twice"):
        sized(table(), twice, Grid(tensor=1, pipeline=2, split=SPLIT_LAYER))


def test_a_model_that_fits_on_no_split_is_refused_naming_the_fullest_card() -> None:
    with pytest.raises(ShardingError, match=r"box-a\.example card \d"):
        choose(
            table(),
            cards(1, 1),
            engine=LLAMACPP_ENGINE,
            slots=2,
            ctx_per_slot=4096,
            cache_type_k="f16",
            cache_type_v="f16",
            n_ubatch=512,
            name="example-model-large",
            links=links,
            allowance_bytes=ALLOWANCE,
        )
