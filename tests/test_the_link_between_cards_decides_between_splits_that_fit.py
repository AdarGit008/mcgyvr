"""The link between cards decides between splits that fit, and never whether one fits.

Promise: a split is chosen among those that fit by the time a token is
estimated to spend crossing links; two cards in one machine cross the bus and
two machines cross the network, each priced from the figures the link class
has at that moment (a shipped estimate until the user's own reading or setting
replaces it), and the plan names where those figures came from. What a unit
states -- its split, its tensor or pipeline width -- is honoured over the
choice. A split that does not fit is never chosen for crossing less.

Machines and link figures are invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving.interconnect import Link
from mcgyvr.serving.sharding import (
    LLAMACPP_ENGINE,
    SPLIT_LAYER,
    SPLIT_ROW,
    VLLM_ENGINE,
    Grid,
    ShardingError,
    Target,
    choose,
    plan,
)

MIB = 1 << 20
GIB = 1 << 30


def table(blocks: int = 8, block_mib: int = 400) -> dict[str, Any]:
    return {
        "file": "example-model-large.gguf",
        "arch": "invented",
        "n_layer": blocks,
        "n_embd": 4096,
        "n_head": 32,
        "bytes_by_block": {str(b): block_mib * MIB for b in range(blocks)},
        "bytes_matrix_by_block": {str(b): (block_mib - 1) * MIB for b in range(blocks)},
        "bytes_input": 300 * MIB,
        "bytes_output": 302 * MIB,
        "bytes_output_matrix": 300 * MIB,
        "kv_layers": [
            {"layer": b, "is_swa": False, "k_elems": 1024, "v_elems": 1024, "heads": 8}
            for b in range(blocks)
        ],
        "recurrent_blocks": [],
    }


class Book:
    """Invented link figures, counting which classes were asked for."""

    def __init__(self, source: str = "estimate") -> None:
        self.asked: list[str] = []
        self.source = source

    def __call__(self, cls: str) -> Link:
        self.asked.append(cls)
        gib_s, latency_us = {"pcie": (10.0, 10.0), "network": (0.1, 200.0)}[cls]
        return Link(
            link_class=cls,
            gib_s=gib_s,
            latency_us=latency_us,
            source=self.source,
            where=Path("/invented/links.json"),
        )


def targets(*spec: tuple[str, int, float]) -> list[Target]:
    return [Target(host=h, gpu=g, free_bytes=int(f * GIB)) for h, g, f in spec]


def chosen(model: dict[str, Any], cards: list[Target], **kw: Any) -> Any:
    args: dict[str, Any] = {
        "engine": LLAMACPP_ENGINE,
        "slots": 1,
        "ctx_per_slot": 4096,
        "cache_type_k": "f16",
        "cache_type_v": "f16",
        "n_ubatch": 512,
        "name": "example-model-large",
        "links": Book(),
        "allowance_bytes": 256 * MIB,
    }
    args.update(kw)
    return choose(model, cards, **args)


def test_one_machines_cards_cross_the_bus_and_two_machines_the_network() -> None:
    here = Book()
    chosen(
        table(),
        targets(("box-a.example", 0, 6), ("box-a.example", 1, 6)),
        links=here,
    )
    assert set(here.asked) == {"pcie"}
    there = Book()
    made = chosen(
        table(),
        targets(("box-a.example", 0, 6), ("box-b.example", 0, 6)),
        links=there,
    )
    assert "network" in there.asked
    assert any(link.link_class == "network" for link in made.links)


def test_a_split_across_machines_costs_more_per_token_than_one_inside_a_machine() -> (
    None
):
    inside = chosen(table(), targets(("box-a.example", 0, 6), ("box-a.example", 1, 6)))
    across = chosen(table(), targets(("box-a.example", 0, 6), ("box-b.example", 0, 6)))
    assert across.comm_s_per_token > inside.comm_s_per_token > 0


def test_the_layer_split_crosses_less_than_the_row_split_and_is_chosen() -> None:
    cards = targets(("box-a.example", 0, 6), ("box-a.example", 1, 6))
    made = chosen(table(), cards)
    assert made.grid.split == SPLIT_LAYER
    row = plan(
        table(),
        cards,
        Grid(tensor=2, pipeline=1, split=SPLIT_ROW),
        engine=LLAMACPP_ENGINE,
        slots=1,
        ctx_per_slot=4096,
        cache_type_k="f16",
        cache_type_v="f16",
        n_ubatch=512,
        name="example-model-large",
        links=Book(),
        allowance_bytes=256 * MIB,
    )
    assert row.comm_s_per_token > made.comm_s_per_token


def test_a_stated_split_is_honoured_over_the_one_that_crosses_less() -> None:
    cards = targets(("box-a.example", 0, 6), ("box-a.example", 1, 6))
    made = chosen(table(), cards, split=SPLIT_ROW)
    assert made.grid.split == SPLIT_ROW


def test_a_split_that_does_not_fit_is_never_chosen_for_crossing_less() -> None:
    # One block larger than either card: the layer split, which crosses less,
    # cannot place it; the row split, which halves every matrix, can.
    cards = targets(("box-a.example", 0, 1.0), ("box-a.example", 1, 1.0))
    made = chosen(table(blocks=1, block_mib=1000), cards)
    assert made.grid.split == SPLIT_ROW
    assert made.fits


def test_vllm_keeps_a_tensor_split_inside_a_machine_when_it_can() -> None:
    cards = targets(
        ("box-a.example", 0, 6),
        ("box-a.example", 1, 6),
        ("box-b.example", 0, 6),
        ("box-b.example", 1, 6),
    )
    made = chosen(
        table(),
        cards,
        engine=VLLM_ENGINE,
        cache_type_k="fp16",
        cache_type_v="",
    )
    assert made.grid != Grid(tensor=4, pipeline=1)


def test_a_stated_tensor_width_fixes_the_pipeline_to_the_rest_of_the_cards() -> None:
    cards = targets(
        ("box-a.example", 0, 6),
        ("box-a.example", 1, 6),
        ("box-b.example", 0, 6),
        ("box-b.example", 1, 6),
    )
    made = chosen(
        table(),
        cards,
        engine=VLLM_ENGINE,
        cache_type_k="fp16",
        cache_type_v="",
        tensor=2,
    )
    assert made.grid == Grid(tensor=2, pipeline=2)
    # The two cards of a stage share a machine; the stages are the machines.
    stages = {shard.stage: shard.target.host for shard in made.shards}
    assert stages == {0: "box-a.example", 1: "box-b.example"}


def test_the_plan_says_where_its_link_figures_came_from() -> None:
    made = chosen(
        table(),
        targets(("box-a.example", 0, 6), ("box-b.example", 0, 6)),
        links=Book(source="reading"),
    )
    assert all(link.source == "reading" for link in made.links)
    assert "per token" in made.says()


def test_a_unit_on_one_card_crosses_nothing() -> None:
    made = chosen(table(), targets(("box-a.example", 0, 6)))
    assert made.comm_s_per_token == 0.0
    assert made.links == ()


@pytest.mark.parametrize("engine", [LLAMACPP_ENGINE, VLLM_ENGINE])
def test_a_split_option_of_the_other_engine_is_refused(engine: str) -> None:
    cards = targets(("box-a.example", 0, 6), ("box-a.example", 1, 6))
    stated = {"tensor": 2} if engine == LLAMACPP_ENGINE else {"split": SPLIT_LAYER}
    with pytest.raises(ShardingError, match=r"llama\.cpp|vLLM"):
        chosen(
            table(),
            cards,
            engine=engine,
            cache_type_k="f16" if engine == LLAMACPP_ENGINE else "fp16",
            **stated,
        )
