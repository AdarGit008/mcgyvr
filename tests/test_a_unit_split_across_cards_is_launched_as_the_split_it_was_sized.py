"""A unit split across cards is launched as the split it was sized.

Promise: a unit whose ``launch.shards`` names several cards -- of one machine
or of several -- becomes the processes that split needs: the one that answers
at the unit's address, holding its own machine's cards, and on every other
machine one that lends its cards to it. Every card's free memory is the scan's
of that card, what each card holds is sized from the model's tensor table, and
the argv each process carries states the split that was sized, so the engine
does not split it again. A card the split holds is never shared with another
unit. A split that cannot be sized, or names a machine nobody scanned, is
refused by name; a unit that declares no shards is served as it always was.

Machines, cards and the model are invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import Config, Ladder
from mcgyvr.config import Unit as UnitConfig
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    ROLE_HEADLESS,
    ROLE_RPC,
    ROLE_SERVE,
    UnitError,
    alternate,
    units_for,
)
from tests import machine_shapes as ms

MIB = 1 << 20
GIB = 1 << 30
MODEL = "example-model-large"
WINDOW = 4096


def machine(host: str, cards: int, *, mib: int = 12288) -> Scan:
    shape = ms.Shape(
        label=f"split-{host}",
        machine_id=f"machine-{host[4]}0{cards}",
        host=host,
        local=False,
        cards=tuple(
            ms.Card(index=i, name="Example Card C", vendor="vendor-a", total_mib=mib)
            for i in range(cards)
        ),
    )
    return ms.scan(shape)


def scan_rows(blocks: int = 8, block_gib: int = 2) -> dict[str, Any]:
    """A dense invented model too large for one invented card."""
    block = block_gib * GIB
    return {
        "file": f"/weights/{MODEL}.gguf",
        "size_bytes": blocks * block + 600 * MIB,
        "arch": "invented",
        "n_layer": blocks,
        "n_embd": 4096,
        "n_head": 32,
        "bytes_nonexpert": blocks * block + 600 * MIB,
        "bytes_experts": 0,
        "placeable_blocks": [],
        "expert_bytes_by_block": {},
        "bytes_by_block": {str(b): block for b in range(blocks)},
        "bytes_matrix_by_block": {str(b): block - MIB for b in range(blocks)},
        "bytes_input": 300 * MIB,
        "bytes_output": 300 * MIB,
        "bytes_output_matrix": 299 * MIB,
        "kv_layers": [
            {"layer": b, "is_swa": False, "k_elems": 1024, "v_elems": 1024, "heads": 8}
            for b in range(blocks)
        ],
        "recurrent_blocks": [],
        "n_recurrent": 0,
    }


def config(tmp_path: Path, launch: dict[str, Any], **unit: Any) -> Config:
    stated: dict[str, Any] = {"kv_cache_dtype_k": "f16", "kv_cache_dtype_v": "f16"}
    if unit.get("engine") != "vllm":
        (tmp_path / "scan.json").write_text(json.dumps(scan_rows()), encoding="utf-8")
        stated["geometry_json"] = "scan.json"
    stated.update(launch)
    units = {
        "big": UnitConfig(
            name="big",
            address=unit.pop("address", "http://box-a.example:8080"),
            model=MODEL,
            launch=stated,
            **unit,
        )
    }
    return Config(path=tmp_path, data={}, units=units, ladder=Ladder(names=("big",)))


def scans() -> dict[str, Scan]:
    return {
        "box-a.example": machine("box-a.example", 2),
        "box-b.example": machine("box-b.example", 2),
    }


def test_a_split_over_two_cards_of_one_machine_is_one_process_holding_both(
    tmp_path: Path,
) -> None:
    shards = [{"rig": "box-a.example", "gpu": 0}, {"rig": "box-a.example", "gpu": 1}]
    (unit,) = units_for(
        config(tmp_path, {"shards": shards}), scans(), specs=(), ctx_per_slot=WINDOW
    )
    assert unit.role == ROLE_SERVE
    assert unit.cards == (0, 1)
    assert unit.rungs == ("big",)
    assert unit.args["--split-mode"] == "layer"
    counts = [int(c) for c in unit.args["--tensor-split"].split(",")]
    assert sum(counts) == 8 + 1
    assert "--n-cpu-moe" not in unit.args
    assert unit.env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert 0 < unit.fit.vram_gb <= unit.fit.card_free_gb
    assert "estimate" in unit.fit.why


def test_a_split_across_machines_lends_the_other_machines_card_over_rpc(
    tmp_path: Path,
) -> None:
    shards = [
        {"rig": "box-a.example", "gpu": 0},
        {"rig": "box-b.example", "gpu": 0, "bind": "192.0.2.20"},
    ]
    head, worker = units_for(
        config(tmp_path, {"shards": shards}, image="example/llama-rpc:1"),
        scans(),
        specs=(),
        ctx_per_slot=WINDOW,
    )
    assert head.host == "box-a.example"
    assert head.args["--rpc"] == "192.0.2.20:50052"
    assert worker.host == "box-b.example"
    assert worker.role == ROLE_RPC
    assert worker.port == 50052
    assert worker.args["-H"] == "192.0.2.20"
    assert worker.cards == (0,)
    assert worker.rungs == ()
    assert worker.image == "example/llama-rpc:1"


def test_a_card_the_split_holds_is_never_shared_with_another_unit(
    tmp_path: Path,
) -> None:
    shards = [{"rig": "box-a.example", "gpu": 0}, {"rig": "box-a.example", "gpu": 1}]
    (split,) = units_for(
        config(tmp_path, {"shards": shards}), scans(), specs=(), ctx_per_slot=WINDOW
    )
    from dataclasses import replace

    alone = replace(split, gpus=(), gpu=1, port=8081, role=ROLE_SERVE)
    assert alternate(split, alone)


def test_vllm_split_over_two_machines_runs_a_headless_node_on_the_second(
    tmp_path: Path,
) -> None:
    table = {
        key: value
        for key, value in scan_rows().items()
        if key not in ("bytes_nonexpert", "bytes_experts", "placeable_blocks")
    }
    table["file"] = "/cache/example-model-large"
    (tmp_path / "table.json").write_text(json.dumps(table), encoding="utf-8")
    shards = [
        {"rig": "box-a.example", "gpu": 0},
        {"rig": "box-a.example", "gpu": 1},
        {"rig": "box-b.example", "gpu": 0},
        {"rig": "box-b.example", "gpu": 1},
    ]
    launch = {
        "shards": shards,
        "tensor_parallel": 2,
        "tensor_table_json": "table.json",
        "kv_cache_dtype_k": "float16",
    }
    made = config(tmp_path, launch, engine="vllm", hf_cache="/cache")
    head, worker = units_for(made, scans(), specs=(), ctx_per_slot=WINDOW)
    for unit in (head, worker):
        assert unit.args["--tensor-parallel-size"] == "2"
        assert unit.args["--pipeline-parallel-size"] == "2"
        assert unit.args["--nnodes"] == "2"
        assert unit.args["--distributed-executor-backend"] == "mp"
        assert "VLLM_PP_LAYER_PARTITION" in unit.env
    assert head.args["--node-rank"] == "0"
    assert worker.args["--node-rank"] == "1"
    assert head.role == ROLE_SERVE
    assert worker.role == ROLE_HEADLESS
    assert "--headless" in worker.extra
    assert "--headless" not in head.extra


def test_a_shard_on_a_machine_nobody_scanned_is_refused(tmp_path: Path) -> None:
    shards = [{"rig": "box-a.example", "gpu": 0}, {"rig": "box-c.example", "gpu": 0}]
    with pytest.raises(UnitError, match="unscanned"):
        units_for(
            config(tmp_path, {"shards": shards}), scans(), specs=(), ctx_per_slot=WINDOW
        )


def test_a_split_whose_first_card_is_not_where_the_unit_answers_is_refused(
    tmp_path: Path,
) -> None:
    shards = [{"rig": "box-b.example", "gpu": 0}, {"rig": "box-a.example", "gpu": 0}]
    with pytest.raises(UnitError, match="first shard"):
        units_for(
            config(tmp_path, {"shards": shards}), scans(), specs=(), ctx_per_slot=WINDOW
        )


def test_a_card_the_scan_did_not_find_is_refused(tmp_path: Path) -> None:
    shards = [{"rig": "box-a.example", "gpu": 0}, {"rig": "box-a.example", "gpu": 5}]
    with pytest.raises(UnitError, match="no card 5"):
        units_for(
            config(tmp_path, {"shards": shards}), scans(), specs=(), ctx_per_slot=WINDOW
        )


def test_a_split_that_fits_no_card_is_refused_as_the_card_being_too_small(
    tmp_path: Path,
) -> None:
    shards = [{"rig": "box-a.example", "gpu": 0}, {"rig": "box-a.example", "gpu": 1}]
    small = {
        "box-a.example": machine("box-a.example", 2, mib=4096),
        "box-b.example": machine("box-b.example", 2),
    }
    with pytest.raises(UnitError, match="no split"):
        units_for(
            config(tmp_path, {"shards": shards}), small, specs=(), ctx_per_slot=WINDOW
        )


def test_a_vllm_split_without_its_tensor_table_is_told_how_to_read_one(
    tmp_path: Path,
) -> None:
    shards = [{"rig": "box-a.example", "gpu": 0}, {"rig": "box-a.example", "gpu": 1}]
    made = config(
        tmp_path,
        {"shards": shards, "kv_cache_dtype_k": "float16"},
        engine="vllm",
        hf_cache="/cache",
    )
    with pytest.raises(UnitError, match="safetensorscan"):
        units_for(made, scans(), specs=(), ctx_per_slot=WINDOW)


def test_a_split_and_a_draft_head_are_not_combined(tmp_path: Path) -> None:
    shards = [{"rig": "box-a.example", "gpu": 0}, {"rig": "box-a.example", "gpu": 1}]
    with pytest.raises(UnitError, match="speculative"):
        units_for(
            config(tmp_path, {"shards": shards, "speculative": "mtp"}),
            scans(),
            specs=(),
            ctx_per_slot=WINDOW,
        )
