"""A diffusers engine is named and refused, never sized or rendered as a text engine.

The media backends land with P2. Until a diffusers image unit has a measured
sizing law and a launch spec of its own, the serving and emit layers refuse
one by name — the same shape ``mcgyvr.gate.output`` gives its P2 validators —
instead of sizing it with llama.cpp's law or rendering it with another
engine's flags.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.emit import EmitError, argv, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    Fit,
    ModelSpec,
    Unit,
    UnitError,
    UnitKey,
    Width,
    unit_for,
)

WINDOW = 4096
MODEL = "stabilityai/stable-diffusion-xl-base-1.0"


def spec() -> ModelSpec:
    return ModelSpec(
        name=MODEL,
        vram_gb=7.0,
        ram_gb=0.0,
        disk_gb=6.9,
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )


def scan() -> Scan:
    return Scan.of(
        host="localhost",
        vram_mib=12288,
        ram_gb=32.0,
        disk_free_gb=120.0,
        cores=8,
        threads=16,
        bandwidth_gbps=41.2,
    )


def test_a_diffusers_unit_is_refused_before_it_is_sized() -> None:
    with pytest.raises(UnitError, match="not wired") as refused:
        unit_for(scan(), spec(), engine="diffusers", ctx_per_slot=WINDOW)
    message = str(refused.value)
    assert "diffusers" in message
    assert MODEL in message


def unit() -> Unit:
    return Unit(
        key=UnitKey(host="localhost", model=MODEL, engine="diffusers", port=8080),
        host="localhost",
        model=MODEL,
        engine="diffusers",
        gpu=0,
        weights=Path("/models/sdxl"),
        width=Width(value=1, how="default"),
        args={},
        fit=Fit(fits=True, headroom_gb=0.0, why=""),
        port=8080,
    )


def test_a_diffusers_unit_is_refused_before_its_argv_is_built() -> None:
    with pytest.raises(EmitError, match="not wired") as refused:
        argv(unit())
    assert "diffusers" in str(refused.value)


def test_a_diffusers_unit_is_refused_before_a_compose_file_is_rendered() -> None:
    with pytest.raises(EmitError, match="not wired") as refused:
        render_compose(unit())
    assert "diffusers" in str(refused.value)
