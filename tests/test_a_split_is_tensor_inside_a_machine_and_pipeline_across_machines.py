"""A split is tensor inside a machine and pipeline across machines, unless stated.

Promise: when a unit leaves its split to the product, the cards of one machine
share every block (a tensor split, as wide as the heads allow) and the machines
are pipeline stages. That is vLLM's own guidance and the rule both engines'
users apply: a tensor split meets twice in every block and wants the bus, a
pipeline passes one hidden state per stage and tolerates the network. A split
that does not fit is never taken; when the rule's split does not fit, the next
widest one that does is. What a unit states -- its tensor or pipeline width --
always wins. llama.cpp is split by layer only: its row split has no split
buffers on the CUDA backend and is refused by name.

What a token spends crossing links is still estimated for every plan -- the bus
for two cards of one machine, the network between machines, each from the
figures the link class has (a shipped estimate until the user's own reading or
setting replaces it) -- and the plan says where those figures came from. It is
reported; it does not choose the split.

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
    SPLITS,
    VLLM_ENGINE,
    Grid,
    ShardingError,
    Target,
    choose,
)

MIB = 1 << 20
GIB = 1 << 30


def table(
    blocks: int = 8, block_mib: int = 400, *, heads: int = 8, n_head: int = 32
) -> dict[str, Any]:
    return {
        "file": "example-model-large.gguf",
        "arch": "invented",
        "n_layer": blocks,
        "n_embd": 4096,
        "n_head": n_head,
        "bytes_by_block": {str(b): block_mib * MIB for b in range(blocks)},
        "bytes_matrix_by_block": {str(b): (block_mib - 1) * MIB for b in range(blocks)},
        "bytes_input": 300 * MIB,
        "bytes_output": 302 * MIB,
        "bytes_output_matrix": 300 * MIB,
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


class Book:
    """Invented link figures, counting which classes were asked for."""

    def __init__(
        self,
        source: str = "estimate",
        *,
        pcie: tuple[float, float] = (10.0, 10.0),
        network: tuple[float, float] = (0.1, 200.0),
    ) -> None:
        self.asked: list[str] = []
        self.source = source
        self.figures = {"pcie": pcie, "network": network}

    def __call__(self, cls: str) -> Link:
        self.asked.append(cls)
        gib_s, latency_us = self.figures[cls]
        return Link(
            link_class=cls,
            gib_s=gib_s,
            latency_us=latency_us,
            source=self.source,
            where=Path("/invented/links.json"),
        )


def targets(*spec: tuple[str, int, float]) -> list[Target]:
    return [Target(host=h, gpu=g, free_bytes=int(f * GIB)) for h, g, f in spec]


def one_machine(cards: int, free_gib: float = 6) -> list[Target]:
    return targets(*(("box-a.example", gpu, free_gib) for gpu in range(cards)))


def two_machines_of_two() -> list[Target]:
    return targets(
        ("box-a.example", 0, 6),
        ("box-a.example", 1, 6),
        ("box-b.example", 0, 6),
        ("box-b.example", 1, 6),
    )


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


def vllm(model: dict[str, Any], cards: list[Target], **kw: Any) -> Any:
    args: dict[str, Any] = {
        "engine": VLLM_ENGINE,
        "cache_type_k": "float16",
        "cache_type_v": "",
    }
    args.update(kw)
    return chosen(model, cards, **args)


# The placement rule.


def test_two_cards_of_one_machine_share_every_block() -> None:
    made = vllm(table(), one_machine(2))
    assert made.grid == Grid(tensor=2, pipeline=1)


def test_four_cards_of_one_machine_are_one_tensor_group() -> None:
    made = vllm(table(), one_machine(4))
    assert made.grid == Grid(tensor=4, pipeline=1)


def test_two_machines_of_two_cards_are_tensor_inside_and_pipeline_across() -> None:
    made = vllm(table(), two_machines_of_two())
    assert made.grid == Grid(tensor=2, pipeline=2)
    # Each stage is one machine's two cards.
    stages: dict[int, set[str]] = {}
    for shard in made.shards:
        stages.setdefault(shard.stage, set()).add(shard.target.host)
    assert stages == {0: {"box-a.example"}, 1: {"box-b.example"}}


def test_two_machines_of_one_card_are_a_pipeline() -> None:
    made = vllm(table(), targets(("box-a.example", 0, 6), ("box-b.example", 0, 6)))
    assert made.grid == Grid(tensor=1, pipeline=2)


@pytest.mark.parametrize(
    "book",
    [
        Book(pcie=(0.5, 500.0), network=(100.0, 1.0)),
        Book(pcie=(100.0, 1.0), network=(0.01, 5000.0)),
    ],
    ids=["slow-bus-fast-network", "fast-bus-slow-network"],
)
def test_no_link_figure_changes_the_split_the_rule_takes(book: Book) -> None:
    made = vllm(table(), two_machines_of_two(), links=book)
    assert made.grid == Grid(tensor=2, pipeline=2)


def test_heads_that_do_not_divide_a_machines_cards_narrow_the_tensor_split() -> None:
    # Three heads cannot be shared by two cards, so the two cards are stages.
    made = vllm(table(heads=3, n_head=3), one_machine(2))
    assert made.grid == Grid(tensor=1, pipeline=2)


def test_a_split_that_does_not_fit_is_not_taken_for_the_rule() -> None:
    # A tensor split puts half of everything on the small card, which cannot
    # hold it; a pipeline gives the small card a short run of blocks.
    cards = targets(("box-a.example", 0, 6), ("box-a.example", 1, 1.3))
    made = vllm(table(), cards)
    assert made.grid == Grid(tensor=1, pipeline=2)
    assert made.fits


def test_a_stated_pipeline_is_honoured_over_the_rule() -> None:
    made = vllm(table(), one_machine(2), pipeline=2)
    assert made.grid == Grid(tensor=1, pipeline=2)


def test_a_stated_tensor_width_fixes_the_pipeline_to_the_rest_of_the_cards() -> None:
    made = vllm(table(), two_machines_of_two(), tensor=2)
    assert made.grid == Grid(tensor=2, pipeline=2)
    stages = {shard.stage: shard.target.host for shard in made.shards}
    assert stages == {0: "box-a.example", 1: "box-b.example"}


# llama.cpp: by layer only.


def test_llama_cpp_offers_the_layer_split_alone() -> None:
    assert list(SPLITS) == [SPLIT_LAYER]
    made = chosen(table(), one_machine(2))
    assert made.grid == Grid(tensor=1, pipeline=2, split=SPLIT_LAYER)


def test_llama_cpp_falls_to_no_row_split_when_the_layer_split_does_not_fit() -> None:
    # One block larger than either card: no split llama.cpp can run holds it.
    with pytest.raises(ShardingError, match="does not fit"):
        chosen(table(blocks=1, block_mib=1000), one_machine(2, free_gib=1.0))


def test_a_stated_row_split_is_refused_by_name_and_pointed_at_layer() -> None:
    with pytest.raises(ShardingError, match=r"row.*split buffers.*split: layer"):
        chosen(table(), one_machine(2), split="row")


# What crossing costs is reported with the plan.


def test_one_machines_cards_cross_the_bus_and_two_machines_the_network() -> None:
    here = Book()
    chosen(table(), one_machine(2), links=here)
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
    inside = chosen(table(), one_machine(2))
    across = chosen(table(), targets(("box-a.example", 0, 6), ("box-b.example", 0, 6)))
    assert across.comm_s_per_token > inside.comm_s_per_token > 0


def test_the_plan_says_where_its_link_figures_came_from() -> None:
    made = chosen(
        table(),
        targets(("box-a.example", 0, 6), ("box-b.example", 0, 6)),
        links=Book(source="reading"),
    )
    assert all(link.source == "reading" for link in made.links)
    assert "per token" in made.says()


def test_a_unit_on_one_card_crosses_nothing() -> None:
    made = chosen(table(), one_machine(1))
    assert made.comm_s_per_token == 0.0
    assert made.links == ()


@pytest.mark.parametrize("engine", [LLAMACPP_ENGINE, VLLM_ENGINE])
def test_a_split_option_of_the_other_engine_is_refused(engine: str) -> None:
    stated = {"tensor": 2} if engine == LLAMACPP_ENGINE else {"split": SPLIT_LAYER}
    with pytest.raises(ShardingError, match=r"llama\.cpp|vLLM"):
        chosen(
            table(),
            one_machine(2),
            engine=engine,
            cache_type_k="f16" if engine == LLAMACPP_ENGINE else "float16",
            **stated,
        )
