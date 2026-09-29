"""A unit states its KV cache dtype, and a unit that does not is refused.

What is specified here, where the product declares a launch
(:func:`mcgyvr.serving.unit_for`, before anything is rendered): a unit whose
model states no KV cache dtype is refused naming the model and the knob; a
stated one reaches the argv as written.

Nothing here changes a value. ``fp8`` stays ``fp8`` and ``auto`` stays
``auto``: each unit declares what it already launches with, not a different
cache.
"""

from __future__ import annotations

import pytest

from mcgyvr.emit import argv
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, unit_for

#: The window these tests declare, as every unit test here must.
WINDOW = 4096

HF_CACHE = "/home/someone/.cache/huggingface"
SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
UTILISATION = ("--gpu-memory-utilization", "0.68")

VLLM_KNOB = ("--kv-cache-dtype", "kv_cache_dtype")
CTK_KNOB = ("-ctk", "--cache-type-k", "cache_type_k")
CTV_KNOB = ("-ctv", "--cache-type-v", "cache_type_v")


def _names(message: str, spellings: tuple[str, ...]) -> bool:
    return any(spelling in message for spelling in spellings)


# --- the product -----------------------------------------------------------


def _card() -> Scan:
    return Scan.of(
        host="desktop-2",
        vram_mib=12288,
        ram_gb=16.0,
        disk_free_gb=120.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )


def _vllm_spec(*, kv_cache_dtype_k: str | None = None) -> ModelSpec:
    return ModelSpec(
        name=SEVEN_B,
        vram_gb=7.12,
        ram_gb=0.0,
        disk_gb=4.93,
        hf_cache=HF_CACHE,
        serve_args=UTILISATION,
        kv_cache_dtype_k=kv_cache_dtype_k,
    )


def _llamacpp_spec(
    *,
    kv_cache_dtype_k: str | None = None,
    kv_cache_dtype_v: str | None = None,
) -> ModelSpec:
    return ModelSpec(
        name="qwen2.5-coder-3b",
        vram_gb=2.4,
        ram_gb=0.0,
        disk_gb=2.1,
        kv_cache_dtype_k=kv_cache_dtype_k,
        kv_cache_dtype_v=kv_cache_dtype_v,
    )


def test_a_vllm_unit_whose_model_states_no_kv_cache_dtype_is_refused_by_name() -> None:
    with pytest.raises(UnitError) as refused:
        unit_for(_card(), _vllm_spec(), engine="vllm", ctx_per_slot=WINDOW)
    message = str(refused.value)
    assert SEVEN_B in message
    assert _names(message, VLLM_KNOB), message


@pytest.mark.parametrize(
    ("kwargs", "missing"),
    [
        ({}, (CTK_KNOB, CTV_KNOB)),
        ({"kv_cache_dtype_k": "q8_0"}, (CTV_KNOB,)),
        ({"kv_cache_dtype_v": "q8_0"}, (CTK_KNOB,)),
    ],
    ids=["neither", "only-k", "only-v"],
)
def test_a_llamacpp_unit_whose_model_states_no_cache_types_is_refused_by_name(
    kwargs: dict[str, str], missing: tuple[tuple[str, ...], ...]
) -> None:
    with pytest.raises(UnitError) as refused:
        unit_for(
            _card(),
            _llamacpp_spec(**kwargs),
            engine="llama.cpp",
            ctx_per_slot=WINDOW,
        )
    message = str(refused.value)
    assert "qwen2.5-coder-3b" in message
    for knob in missing:
        assert _names(message, knob), message


def _contains(parts: tuple[str, ...], run: tuple[str, ...]) -> bool:
    return any(parts[i : i + len(run)] == run for i in range(len(parts)))


@pytest.mark.parametrize("dtype", ["fp8", "auto"])
def test_a_stated_kv_cache_dtype_reaches_a_vllm_argv_as_written(dtype: str) -> None:
    unit = unit_for(
        _card(),
        _vllm_spec(kv_cache_dtype_k=dtype),
        engine="vllm",
        ctx_per_slot=WINDOW,
    )
    assert _contains(argv(unit), ("--kv-cache-dtype", dtype))


def test_stated_cache_types_reach_a_llamacpp_argv_as_written() -> None:
    unit = unit_for(
        _card(),
        _llamacpp_spec(kv_cache_dtype_k="q8_0", kv_cache_dtype_v="f16"),
        engine="llama.cpp",
        ctx_per_slot=WINDOW,
    )
    parts = argv(unit)
    assert _contains(parts, ("-ctk", "q8_0"))
    assert _contains(parts, ("-ctv", "f16"))
