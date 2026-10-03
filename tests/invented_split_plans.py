"""Invented plans of a split model, for the tests of how a split is launched.

The model, the machines and the link figures are made up here and sized so the
arithmetic is checkable by eye; a test built on them promises what is launched
from a plan, never what any shipped number is. Every plan is made by the
product's own :func:`mcgyvr.serving.sharding.plan`, with the allowance and the
links injected so no shipped number is read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.serving.interconnect import Link
from mcgyvr.serving.sharding import (
    LLAMACPP_ENGINE,
    SPLIT_LAYER,
    VLLM_ENGINE,
    Grid,
    Plan,
    Target,
    plan,
)
from mcgyvr.serving.shardlaunch import Process, processes

MIB = 1 << 20
GIB = 1 << 30

HOST_A = "box-a.example"
HOST_B = "box-b.example"
HOST_C = "box-c.example"
ADDR_A = "192.0.2.10"
ADDR_B = "192.0.2.20"
ADDR_C = "192.0.2.30"

NAME = "example-model-large"
WEIGHTS = Path("/srv/weights/example-model-large.gguf")
HF_CACHE = Path("/srv/hf-cache")

#: What a launch is asked for, stated where a test does not vary it.
PORT = 8080
RPC_PORT = 50052
MASTER_PORT = 29501
THREADS = 8
UBATCH = 512


def table(*, blocks: int = 8, block_mib: int = 400) -> dict[str, Any]:
    """An invented dense model: ``blocks`` equal blocks, an embedding, a head."""
    heads, head_dim = 8, 128
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
    """Fixed, invented link figures."""
    gib_s, latency_us = {"pcie": (10.0, 10.0), "network": (0.1, 200.0)}[cls]
    return Link(
        link_class=cls,
        gib_s=gib_s,
        latency_us=latency_us,
        source="estimate",
        where=Path("numbers.json"),
    )


def card(
    host: str, gpu: int, *, free_gib: float = 6, bind: str | None = None
) -> Target:
    return Target(host=host, gpu=gpu, free_bytes=int(free_gib * GIB), bind=bind)


def sized(targets: list[Target], grid: Grid, *, engine: str, **kw: Any) -> Plan:
    args: dict[str, Any] = {
        "engine": engine,
        "slots": 2,
        "ctx_per_slot": 4096,
        "cache_type_k": "f16" if engine == LLAMACPP_ENGINE else "float16",
        "cache_type_v": "f16",
        "n_ubatch": UBATCH,
        "name": NAME,
        "links": links,
        "allowance_bytes": 512 * MIB,
    }
    args.update(kw)
    return plan(table(), targets, grid, **args)


def llama_plan(targets: list[Target], grid: Grid | None = None) -> Plan:
    wide = grid or Grid(tensor=1, pipeline=len(targets), split=SPLIT_LAYER)
    return sized(targets, wide, engine=LLAMACPP_ENGINE)


def vllm_plan(targets: list[Target], grid: Grid) -> Plan:
    return sized(targets, grid, engine=VLLM_ENGINE)


def launch(made: Plan, **kw: Any) -> tuple[Process, ...]:
    """The processes of ``made`` at the launch values above, any of them replaced."""
    args: dict[str, Any] = {
        "model": NAME,
        "weights": WEIGHTS if made.engine == LLAMACPP_ENGINE else HF_CACHE,
        "port": PORT,
        "cache_type_k": "f16" if made.engine == LLAMACPP_ENGINE else "float16",
        "cache_type_v": "f16",
        "threads": THREADS,
        "n_ubatch": UBATCH,
        "rpc_port": RPC_PORT,
        "master_port": MASTER_PORT,
    }
    args.update(kw)
    return processes(made, **args)


def two_machines_llama() -> list[Target]:
    """Two cards on the head's machine and two on a worker machine."""
    return [
        card(HOST_A, 0),
        card(HOST_A, 1),
        card(HOST_B, 0, bind=ADDR_B),
        card(HOST_B, 1, bind=ADDR_B),
    ]
