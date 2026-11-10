"""A llama.cpp unit's cache type is one the engine takes, priced at its own width.

llama.cpp takes nine cache types for ``-ctk``/``-ctv`` (``kv_cache_types`` in
its common/arg.cpp: f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1). The
sizer's widths are the scanner's type table (``ggufscan.T``, block bytes over
block elements) filtered to those names, so each of the nine is priced and a
weight type the engine refuses as a cache type (q4_k, mxfp4) is no cache type.
A unit naming one the engine does not take is refused when its launch block is
read, naming the ones it does, rather than failing as a missing key once it is
sized. vLLM names its own (``auto``, ``fp8``) and is not checked here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mcgyvr.config import parse
from mcgyvr.serving import UnitError, check_cache_types, declared_models, vramfit
from tests._paths import TESTS

GEOMETRY: dict[str, Any] = json.loads(
    (TESTS / "fixtures" / "gguf_geometry.json").read_text()
)["deepseek-coder-v2-16b.gguf"]

#: Block elements and block bytes of each type, as ggml defines them.
GGML_BLOCKS = {
    "f32": (1, 4),
    "f16": (1, 2),
    "bf16": (1, 2),
    "q8_0": (32, 34),
    "q4_0": (32, 18),
    "q4_1": (32, 20),
    "iq4_nl": (32, 18),
    "q5_0": (32, 22),
    "q5_1": (32, 24),
}


def test_every_type_llama_cpp_takes_has_a_width_and_nothing_else_does() -> None:
    assert set(vramfit.CACHE_ELEM_BYTES) == set(vramfit.LLAMACPP_CACHE_TYPES)
    assert set(vramfit.LLAMACPP_CACHE_TYPES) == set(GGML_BLOCKS)
    for name, (elements, size) in GGML_BLOCKS.items():
        assert vramfit.CACHE_ELEM_BYTES[name] == size / elements


@pytest.mark.parametrize("cache_type", ["q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"])
def test_a_four_or_five_bit_cache_is_sized_at_its_width(cache_type: str) -> None:
    sized = vramfit.kv_bytes(
        GEOMETRY, 4096, cache_type_k=cache_type, cache_type_v=cache_type
    )
    elements = sum(r["k_elems"] + r["v_elems"] for r in GEOMETRY["kv_layers"])
    blocks, size = GGML_BLOCKS[cache_type]
    assert sized["total"] == int(4096 * elements * size / blocks)


@pytest.mark.parametrize("stated", ["auto", "q4_k", "mxfp4", "Q8_0"])
def test_a_type_llama_cpp_refuses_is_refused_naming_the_ones_it_takes(
    stated: str,
) -> None:
    with pytest.raises(UnitError) as refused:
        check_cache_types("a-model", "llama.cpp", "q8_0", stated)
    message = str(refused.value)
    assert repr(stated) in message and "kv_cache_dtype_v" in message
    assert "q4_0" in message and "iq4_nl" in message


def test_vllm_names_its_own_types_and_an_unstated_one_is_not_checked() -> None:
    check_cache_types("a-model", "vllm", "auto", None)
    check_cache_types("a-model", "llama.cpp", None, None)


def _fleet(engine: str | None, cache_type: str) -> str:
    stated = f"    engine: {engine}\n" if engine else ""
    return (
        "units:\n"
        "  only:\n"
        "    address: http://localhost:8080\n"
        "    model: a-model\n"
        "    rig: local\n"
        f"{stated}"
        "    launch:\n"
        "      vram_gb: 4.0\n"
        f"      kv_cache_dtype_k: {cache_type}\n"
        "      kv_cache_dtype_v: q8_0\n"
        "ladder:\n"
        "- only\n"
    )


def test_a_unit_is_refused_when_its_launch_block_is_read() -> None:
    with pytest.raises(UnitError, match="kv_cache_dtype_k is 'auto'"):
        declared_models(parse(_fleet(None, "auto")))
    assert declared_models(parse(_fleet(None, "q4_0")))["a-model"].kv_cache_dtype_k == (
        "q4_0"
    )
