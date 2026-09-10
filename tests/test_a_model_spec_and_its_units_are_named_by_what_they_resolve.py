"""A model spec is named by what it is; a unit by the knobs it resolved to.

RED. ``mcgyvr.fleet.model_spec`` and ``mcgyvr.fleet.unit`` do not exist. The
intent is ``records/plans/fleet-identity.md``.

Two identities, split where the code already splits: ``ModelSpec``
(``src/mcgyvr/serving/__init__.py:238``) is what a model is before any machine
is consulted, and ``Unit`` (``:424``) is one process with its argv "already
sized for this machine". ``UnitKey`` (``:399``) addresses that process by
``host:port/model/engine`` and names no knob, so two placements of one model on
one port read as one key. ``unit_id`` is the content name that tells them apart.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from tests.red_port.conftest import required

#: Qwen3.6-35B-A3B IQ3_XXS as ggufscan reads it (size and params from the live
#: geometry file); ``params_active`` is illustrative.
METADATA: dict[str, Any] = {
    "arch": "qwen35moe",
    "n_layer": 40,
    "quant": "IQ3_XXS",
    "size_bytes": 13_211_155_424,
    "params_total": 34_660_610_688,
    "params_active": 3_000_000_000,
    "mtp_layers": 0,
    "kv_layers": 10,
}
BOUNDS: dict[str, Any] = {
    "ctx": [4096, 16384],
    "cache_types": ["f16", "q8_0"],
    "load_modes": ["mmap", "none"],
    "max_width": 8,
}
IMAGE = "llamacpp:b10644-L3"
RESOLVED: dict[str, Any] = {
    "n_cpu_moe": 30,
    "width": 2,
    "ctx_per_slot": 8192,
    "ubatch": 512,
    "load_mode": "mmap",
    "cache_type": "f16",
    "gpu_memory_utilization": None,
    "port": 8080,
}


def _model_spec_id() -> Any:
    return required(
        "name a model spec by its metadata, engine, image and knob bounds",
        lambda: importlib.import_module("mcgyvr.fleet.model_spec").model_spec_id,
    )


def _unit_id() -> Any:
    return required(
        "name a unit by its model spec plus every knob resolved for a rig",
        lambda: importlib.import_module("mcgyvr.fleet.unit").unit_id,
    )


def test_the_same_weights_under_two_engines_are_two_model_specs() -> None:
    model_spec_id = _model_spec_id()
    llama = model_spec_id(METADATA, "llama.cpp", IMAGE, BOUNDS)
    vllm = model_spec_id(METADATA, "vllm", IMAGE, BOUNDS)
    assert llama.startswith("msp-")
    assert llama != vllm


def test_an_image_or_a_knob_bound_change_is_a_new_model_spec() -> None:
    """One image listed Vulkan0 on srv2 and another did not; the build is identity."""
    model_spec_id = _model_spec_id()
    base = model_spec_id(METADATA, "llama.cpp", IMAGE, BOUNDS)
    stock = "ghcr.io/ggml-org/llama.cpp:server-cuda-b10644"
    assert model_spec_id(METADATA, "llama.cpp", stock, BOUNDS) != base
    wider = {**BOUNDS, "max_width": 16}
    assert model_spec_id(METADATA, "llama.cpp", IMAGE, wider) != base


def test_a_model_spec_missing_a_metadata_field_is_refused_not_hashed() -> None:
    """A partial reading hashed would be a name for a model nobody scanned."""
    model_spec_id = _model_spec_id()
    partial = {k: v for k, v in METADATA.items() if k != "quant"}
    with pytest.raises(ValueError, match="quant"):
        model_spec_id(partial, "llama.cpp", IMAGE, BOUNDS)


def test_every_resolved_knob_including_the_port_is_part_of_the_unit() -> None:
    model_spec_id = _model_spec_id()
    unit_id = _unit_id()
    spec = model_spec_id(METADATA, "llama.cpp", IMAGE, BOUNDS)
    base = unit_id(spec, RESOLVED)
    assert base.startswith("unt-")
    moved = {
        "n_cpu_moe": 29,
        "width": 4,
        "ctx_per_slot": 4096,
        "ubatch": 256,
        "load_mode": "none",
        "cache_type": "q8_0",
        "gpu_memory_utilization": 0.72,
        "port": 8081,
    }
    for knob, value in moved.items():
        assert unit_id(spec, {**RESOLVED, knob: value}) != base, (
            f"{knob} resolved differently must name a different unit"
        )
    other = model_spec_id(METADATA, "vllm", IMAGE, BOUNDS)
    assert unit_id(other, RESOLVED) != base
