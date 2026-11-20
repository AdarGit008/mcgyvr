"""A line's fit before a download is the launch check's verdict after it.

:func:`estimate.line_fit` takes the file's header row, as the hub's header read
gives it before a byte of weights is fetched, and returns what
:func:`mcgyvr.serving.fit` returns once the file is on disk and its scan is read
back as a unit's geometry (:func:`mcgyvr.serving.load_geometry`, as
``declared_models`` builds the model). The whole ``Fit`` is equal, not only the
yes or no, over every invented machine with a readable card, a dense and an MoE
header at several sizes, contexts, slot counts and cache types. At recommend's
own f16 cache and with the disk not weighed, its yes or no is the one
``mcgyvr recommend`` gives today. Invented machines and headers only.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import estimate, recommend
from mcgyvr.config import DEFAULT_ENGINE
from mcgyvr.serving import Fit, ModelSpec, fit, load_geometry
from tests import machine_shapes
from tests.sizings import machines

GIB = 1 << 30
LAYERS = 24
#: (context per slot, slots, cache type) for each header.
LINES = [(4096, 1, "f16"), (32768, 1, "f16"), (8192, 4, "q8_0"), (65536, 2, "q4_0")]
SIZES_GIB = [2, 7, 30, 120]


def _kv() -> list[dict[str, Any]]:
    return [
        {"layer": b, "is_swa": False, "k_elems": 1024, "v_elems": 1024}
        for b in range(LAYERS)
    ]


def dense(size_gib: int) -> dict[str, Any]:
    """An invented dense header, as a ggufscan row states it."""
    size = size_gib * GIB
    block = (size - 600 * (1 << 20)) // LAYERS
    return {
        "file": f"/models/invented-dense-{size_gib}g.gguf",
        "size_bytes": size,
        "arch": "invented",
        "n_layer": LAYERS,
        "params_total": size // 2,
        "n_ctx_train": 65536,
        "bytes_nonexpert": size,
        "bytes_experts": 0,
        "placeable_blocks": [],
        "expert_bytes_by_block": {},
        "bytes_by_block": {str(b): block for b in range(LAYERS)},
        "kv_layers": _kv(),
        "recurrent_blocks": [],
        "n_recurrent": 0,
    }


def moe(size_gib: int) -> dict[str, Any]:
    """An invented MoE header: most of its bytes in expert blocks."""
    size = size_gib * GIB
    block = size * 3 // 4 // LAYERS
    return {
        "file": f"/models/invented-moe-{size_gib}g.gguf",
        "size_bytes": size,
        "arch": "invented-moe",
        "n_layer": LAYERS,
        "n_expert": 8,
        "n_expert_used": 2,
        "n_ctx_train": 65536,
        "bytes_nonexpert": size - block * LAYERS,
        "bytes_experts": block * LAYERS,
        "placeable_blocks": list(range(LAYERS)),
        "expert_bytes_by_block": {str(b): block for b in range(LAYERS)},
        "kv_layers": _kv(),
        "recurrent_blocks": [],
        "n_recurrent": 0,
    }


HEADERS = [make(size) for make in (dense, moe) for size in SIZES_GIB]


def _launch_check(
    scan: Any,
    header: dict[str, Any],
    where: Path,
    *,
    ctx_per_slot: int,
    slots: int,
    cache_type: str,
) -> Fit:
    """The launch check on the downloaded file: its scan written, read back as a
    unit's geometry and sized, as a unit that names the file is."""
    name = Path(header["file"]).name.removesuffix(".gguf")
    stored = where / f"{name}.json"
    stored.write_text(json.dumps(header), encoding="utf-8")
    spec = ModelSpec(
        name=name,
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=load_geometry(stored, name=name),
        kv_cache_dtype_k=cache_type,
        kv_cache_dtype_v=cache_type,
    )
    return fit(
        scan, spec, engine=DEFAULT_ENGINE, width=slots, ctx_per_slot=ctx_per_slot
    )


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
def test_the_fit_before_a_download_equals_the_launch_checks(
    machine: machine_shapes.Shape, tmp_path: Path
) -> None:
    scan = machine_shapes.scan(machine)
    for header in HEADERS:
        for ctx_per_slot, slots, cache_type in LINES:
            before = estimate.line_fit(
                scan,
                header,
                ctx_per_slot=ctx_per_slot,
                slots=slots,
                cache_type=cache_type,
            )
            after = _launch_check(
                scan,
                header,
                tmp_path,
                ctx_per_slot=ctx_per_slot,
                slots=slots,
                cache_type=cache_type,
            )
            assert before == after, (header["file"], ctx_per_slot, slots, cache_type)


def test_the_invented_lines_hold_both_verdicts() -> None:
    verdicts = set()
    for machine in machines():
        scan = machine_shapes.scan(machine)
        for header in HEADERS:
            got = estimate.line_fit(scan, header, ctx_per_slot=4096)
            assert isinstance(got, Fit)
            verdicts.add(got.fits)
    assert verdicts == {True, False}


@pytest.mark.parametrize("machine", machines(), ids=lambda machine: machine.label)
def test_at_an_f16_cache_its_verdict_is_recommends(
    machine: machine_shapes.Shape,
) -> None:
    scan = machine_shapes.scan(machine)
    for header in HEADERS:
        for ctx_per_slot, slots, _ in LINES:
            got = estimate.line_fit(
                replace(scan, disk=None), header, ctx_per_slot=ctx_per_slot, slots=slots
            )
            assert isinstance(got, Fit)
            today = recommend._sized(
                scan, recommend._header_spec(header), slots, ctx_per_slot
            )
            assert got.fits == today, (header["file"], ctx_per_slot, slots)


@pytest.mark.parametrize(
    ("header", "kwargs", "named"),
    [
        (dense(7), {"ctx_per_slot": 0}, "at least 1"),
        (dense(7), {"ctx_per_slot": 4096, "slots": 0}, "at least 1"),
        (dense(7), {"ctx_per_slot": 4096, "cache_type": "q3_k"}, "has no width"),
        ({**dense(7), "size_bytes": None}, {"ctx_per_slot": 4096}, "no file size"),
        ({**dense(7), "size_bytes": True}, {"ctx_per_slot": 4096}, "no file size"),
        (
            {key: value for key, value in dense(7).items() if key != "kv_layers"},
            {"ctx_per_slot": 4096},
            "cannot size this header",
        ),
    ],
)
def test_a_line_the_law_cannot_size_gets_no_verdict_and_says_why(
    header: dict[str, Any], kwargs: dict[str, Any], named: str
) -> None:
    scan = machine_shapes.scan(machines()[0])
    got = estimate.line_fit(scan, header, **kwargs)
    assert isinstance(got, estimate.NoEstimate)
    assert named in got.why
