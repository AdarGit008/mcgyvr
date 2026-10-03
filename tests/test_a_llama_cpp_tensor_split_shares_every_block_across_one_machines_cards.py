"""A llama.cpp tensor split shares every block across one machine's cards.

Promise: llama.cpp's ``--split-mode tensor`` is sized with the same tensor-split
arithmetic as vLLM's -- each card holds ``1 / N`` of every tensor the engine
divides and of the output head, a whole copy of everything it mirrors, and
``1 / N`` of the KV heads -- plus a per-card allowance that is a shipped
estimate, named as one. It follows the placement rule: a unit that leaves its
split to the product is split by tensor across one machine's cards and by
layer across machines, and a stated split wins. What llama.cpp's own source
refuses is refused here first, by name: an architecture on its refusal list, a
tensor on its partial axis that is not F32, KV heads that do not divide over the
cards, cards on more than one machine. ``row`` stays refused. It is launched as
``--split-mode tensor`` with an even ``--tensor-split`` and every layer on the
cards.

The model and machines are invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import derived
from mcgyvr.serving.interconnect import Link
from mcgyvr.serving.sharding import (
    LLAMACPP_ENGINE,
    SPLIT_LAYER,
    Grid,
    ShardingError,
    Target,
    choose,
    plan,
)
from mcgyvr.serving.shardlaunch import processes

MIB = 1 << 20
GIB = 1 << 30
SPLIT = "tensor"


def table(
    *, blocks: int = 8, heads: int = 8, arch: str = "invented", **over: Any
) -> dict[str, Any]:
    """An invented dense model: of each 400 MiB block, 384 MiB is divided."""
    model: dict[str, Any] = {
        "file": "example-model-large.gguf",
        "arch": arch,
        "n_layer": blocks,
        "n_embd": 4096,
        "n_head": 32,
        "bytes_by_block": {str(b): 400 * MIB for b in range(blocks)},
        "bytes_matrix_by_block": {str(b): 399 * MIB for b in range(blocks)},
        "bytes_tensor_split_by_block": {str(b): 384 * MIB for b in range(blocks)},
        "bytes_input": 300 * MIB,
        "bytes_output": 302 * MIB,
        "bytes_output_matrix": 300 * MIB,
        "bytes_output_tensor_split": 300 * MIB,
        "tensor_split_refused": [],
        "kv_layers": [
            {
                "layer": b,
                "is_swa": False,
                "k_elems": heads * 128,
                "v_elems": heads * 128,
                "heads": heads,
            }
            for b in range(blocks)
        ],
        "recurrent_blocks": [],
    }
    model.update(over)
    return model


def links(cls: str) -> Link:
    gib_s, latency_us = {"pcie": (10.0, 10.0), "network": (0.1, 200.0)}[cls]
    return Link(
        link_class=cls,
        gib_s=gib_s,
        latency_us=latency_us,
        source="estimate",
        where=Path("numbers.json"),
    )


def cards(*spec: tuple[str, int]) -> list[Target]:
    return [Target(host=h, gpu=g, free_bytes=6 * GIB) for h, g in spec]


ONE_MACHINE = (("box-a.example", 0), ("box-a.example", 1))
TWO_MACHINES = (("box-a.example", 0), ("box-b.example", 0))

ARGS: dict[str, Any] = {
    "engine": LLAMACPP_ENGINE,
    "slots": 2,
    "ctx_per_slot": 4096,
    "cache_type_k": "f16",
    "cache_type_v": "f16",
    "n_ubatch": 512,
    "name": "example-model-large",
    "links": links,
}


def sized(model: dict[str, Any], targets: list[Target], **kw: Any) -> Any:
    return plan(model, targets, Grid(tensor=2, pipeline=1, split=SPLIT), **(ARGS | kw))


def chosen(model: dict[str, Any], targets: list[Target], **kw: Any) -> Any:
    return choose(model, targets, **(ARGS | kw))


# Sizing.


def test_each_card_holds_its_share_of_what_is_divided_and_all_of_the_rest() -> None:
    made = sized(table(), cards(*ONE_MACHINE), allowance_bytes=512 * MIB)
    per_block = 400 * MIB - 384 * MIB + 384 * MIB // 2
    output = 302 * MIB - 300 * MIB + 300 * MIB // 2
    for shard in made.shards:
        assert shard.blocks == tuple(range(8))
        assert shard.weights_bytes == 8 * per_block + output
        assert shard.allowance_bytes == 512 * MIB
    # 8 KV heads over two cards: each holds 4, half of what one card would.
    assert made.shards[0].kv_bytes == made.shards[1].kv_bytes
    one_card = plan(
        table(),
        cards(("box-a.example", 0)),
        Grid(tensor=1, pipeline=1, split=SPLIT_LAYER),
        **(ARGS | {"allowance_bytes": 512 * MIB}),
    )
    assert made.shards[0].kv_bytes * 2 == one_card.shards[0].kv_bytes


def test_a_tied_head_is_a_whole_copy_of_the_embedding_on_every_card() -> None:
    model = table(
        tied_embeddings=True, bytes_output=2 * MIB, bytes_output_tensor_split=0
    )
    made = sized(model, cards(*ONE_MACHINE), allowance_bytes=512 * MIB)
    per_block = 400 * MIB - 384 * MIB + 384 * MIB // 2
    for shard in made.shards:
        assert shard.weights_bytes == 8 * per_block + 2 * MIB + 300 * MIB


def test_each_card_is_charged_the_shipped_estimate_for_its_scratch() -> None:
    made = sized(table(), cards(*ONE_MACHINE))
    expected = int(derived.shard_allowance_gib("llama.cpp") * GIB)
    assert [shard.allowance_bytes for shard in made.shards] == [expected, expected]
    answered = derived.lookup(derived.SHARD_ALLOWANCE, "llama.cpp")
    assert answered.source == "estimate"


def test_the_cards_meet_on_the_bus_in_every_block() -> None:
    made = sized(table(), cards(*ONE_MACHINE))
    assert made.comm_s_per_token > 0
    assert {link.link_class for link in made.links} == {"pcie"}


# The placement rule.


def test_one_machines_cards_are_split_by_tensor_when_left_to_the_product() -> None:
    made = chosen(table(), cards(*ONE_MACHINE))
    assert made.grid == Grid(tensor=2, pipeline=1, split=SPLIT)


def test_cards_on_two_machines_are_split_by_layer() -> None:
    made = chosen(table(), cards(*TWO_MACHINES))
    assert made.grid.split == SPLIT_LAYER


def test_a_stated_layer_split_wins_on_one_machine() -> None:
    made = chosen(table(), cards(*ONE_MACHINE), split=SPLIT_LAYER)
    assert made.grid.split == SPLIT_LAYER


def test_a_stated_tensor_split_across_machines_is_refused_by_name() -> None:
    with pytest.raises(ShardingError, match="more than one machine"):
        chosen(table(), cards(*TWO_MACHINES), split=SPLIT)


# What llama.cpp's own source refuses.


def test_an_architecture_llama_cpp_refuses_is_split_by_layer_or_refused() -> None:
    model = table(arch="deepseek2")
    assert chosen(model, cards(*ONE_MACHINE)).grid.split == SPLIT_LAYER
    with pytest.raises(
        ShardingError, match=r"'deepseek2'.*llm_arch_supports_sm_tensor"
    ):
        chosen(model, cards(*ONE_MACHINE), split=SPLIT)


def test_a_partial_axis_tensor_that_is_not_f32_is_refused_by_name() -> None:
    model = table(tensor_split_refused=["blk.0.ffn_down_exps.bias"])
    assert chosen(model, cards(*ONE_MACHINE)).grid.split == SPLIT_LAYER
    with pytest.raises(ShardingError, match=r"blk\.0\.ffn_down_exps\.bias.*F32"):
        chosen(model, cards(*ONE_MACHINE), split=SPLIT)


def test_kv_heads_that_do_not_divide_over_the_cards_are_refused() -> None:
    # vLLM would hold one of two KV heads on each of four cards twice over;
    # llama.cpp's meta device hands out whole heads, so two cards get none.
    four = cards(*(("box-a.example", gpu) for gpu in range(4)))
    model = table(heads=2)
    assert chosen(model, four).grid.split == SPLIT_LAYER
    with pytest.raises(ShardingError, match="2 KV heads"):
        chosen(model, four, split=SPLIT)


def test_a_scan_without_the_tensor_split_sums_asks_for_a_rescan() -> None:
    model = table()
    del model["bytes_tensor_split_by_block"]
    assert chosen(model, cards(*ONE_MACHINE)).grid.split == SPLIT_LAYER
    with pytest.raises(ShardingError, match=r"python -m mcgyvr\.serving\.ggufscan"):
        chosen(model, cards(*ONE_MACHINE), split=SPLIT)


def test_the_row_split_stays_refused() -> None:
    with pytest.raises(ShardingError, match="split buffers"):
        chosen(table(), cards(*ONE_MACHINE), split="row")


# The launch.


def test_it_is_launched_as_one_server_told_split_mode_tensor() -> None:
    made = chosen(table(), cards(*ONE_MACHINE))
    (head,) = processes(
        made,
        model="example-model-large",
        weights=Path("/srv/weights/example-model-large.gguf"),
        port=8080,
        cache_type_k="f16",
        cache_type_v="f16",
        threads=8,
        n_ubatch=512,
        rpc_port=50052,
        master_port=29501,
    )
    assert head.gpus == (0, 1)
    assert head.args["--split-mode"] == "tensor"
    assert head.args["--tensor-split"] == "1,1"
    assert head.args["-ngl"] == "9"
    assert head.args["-fa"] == "on"
    assert "--rpc" not in head.args
