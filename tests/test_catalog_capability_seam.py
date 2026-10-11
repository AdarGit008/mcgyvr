"""The seam between the model catalog and the capability table.

``mcgyvr recommend`` picks by the catalog's repository id; ``mcgyvr emit``
sizes units from serving specs. The two tables name one file two ways, so the
seam is the shared ``model_id``: a catalog pick must resolve to the row that
benchmarked the same weights, and a catalog model with no table row must still
be servable from the catalog's own facts.

Promises:

* The two Qwen rows of the capability table carry the catalog repository id
  their GGUF weights match.
* A unit whose ``model`` is ``Qwen/Qwen2.5-Coder-7B-Instruct`` emits even
  though that id is not a table row's ``id``: it resolves to the mapped row's
  measured figure.
* A catalog model the table does not name is servable from the catalog's own
  bytes and KV figures, keyed by its ``model_id``.
* ``declared_models`` (the operator's ``launch`` block) still wins over both.
"""

from __future__ import annotations

import pytest

from mcgyvr import cli
from mcgyvr.capability import GB_PER_GIB
from mcgyvr.capability import load as load_capability
from mcgyvr.config import Config, Ladder, Unit
from mcgyvr.knowledge import store as ks
from mcgyvr.scan import Scan
from mcgyvr.serving import units_for

REPO = "Qwen/Qwen2.5-Coder-7B-Instruct"
REPO_14B = "Qwen/Qwen2.5-Coder-14B-Instruct"
DEEPSEEK = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"


def _scan(host: str = "rig.example") -> Scan:
    return Scan.of(
        host=host,
        vram_mib=12288,
        ram_gb=48.0,
        disk_free_gb=900.0,
        cores=8,
        threads=16,
        bandwidth_gbps=41.2,
    )


def _config(model: str) -> Config:
    return Config(
        path=None,
        data={},
        units={
            "rung": Unit(name="rung", address="http://rig.example:8080", model=model),
        },
        ladder=Ladder(names=("rung",)),
    )


def test_the_two_qwen_rows_carry_their_catalog_model_id() -> None:
    by_id = {m.id: m for m in load_capability().models}
    assert by_id["qwen2.5-coder:7b"].model_id == REPO
    assert by_id["qwen2.5-coder:14b"].model_id == REPO_14B


def test_a_catalog_pick_emits_via_the_mapped_measured_row() -> None:
    specs = {s.name: s for s in cli._model_specs()}

    assert REPO in specs
    row = {m.id: m for m in load_capability().models}["qwen2.5-coder:7b"]
    # The measured working set wins over the catalog's computed figure.
    assert specs[REPO].vram_gb == pytest.approx(row.vram_gb_working / GB_PER_GIB)

    units = units_for(
        _config(REPO),
        {"rig.example": _scan()},
        specs=cli._model_specs(),
        ctx_per_slot=4096,
    )
    assert len(units) == 1
    assert units[0].model == REPO
    assert units[0].fit.fits is True


def test_a_catalog_model_the_table_does_not_name_is_servable() -> None:
    specs = {s.name: s for s in cli._model_specs()}

    record = next(r for r in ks.shipped() if r.model_id == DEEPSEEK)
    spec = specs[record.model_id]
    assert spec.geometry is None
    assert spec.moe is False
    assert spec.disk_gb == pytest.approx(record.size_bytes.value / (1024**3))
    assert spec.vram_gb == pytest.approx(
        (
            record.size_bytes.value
            + record.context_length.value * record.kv_bytes_per_token.value
        )
        / (1024**3)
    )


def test_a_declared_launch_still_wins_over_the_catalog_and_the_table() -> None:
    declared = Unit(
        name="rung",
        address="http://rig.example:8080",
        model=REPO,
        launch={
            "vram_gb": 7.5,
            "disk_gb": 5.0,
            "kv_cache_dtype_k": "f16",
            "kv_cache_dtype_v": "f16",
        },
    )
    config = Config(
        path=None,
        data={},
        units={"rung": declared},
        ladder=Ladder(names=("rung",)),
    )
    units = units_for(
        config,
        {"rig.example": _scan()},
        specs=cli._model_specs(),
        ctx_per_slot=4096,
    )
    assert len(units) == 1
    assert units[0].fit.vram_gb == pytest.approx(7.5)
