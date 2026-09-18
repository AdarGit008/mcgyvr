"""A vLLM unit that declares ``speculative: mtp`` is refused by name.

``speculative: mtp`` is llama.cpp's ``--spec-type draft-mtp``: the grafted
nextn block of a GGUF, run as the draft (``records/evidence/2026-08-28-mtp-
ornith/``). vLLM's speculative decoding is ``--speculative-config``, a
different mechanism with its own knobs, and a vLLM unit declaring this key
would either be silently ignored or be read as something it never measured.
So :func:`~mcgyvr.serving.unit_for` refuses it before sizing, naming the model,
the key and the mechanism vLLM has instead.
"""

from __future__ import annotations

import pytest

from mcgyvr.emit import argv
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, unit_for

WINDOW = 4096
SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
HF_CACHE = "/home/someone/.cache/huggingface"


def card() -> Scan:
    return Scan.of(
        host="srv2",
        vram_mib=12288,
        ram_gb=16.0,
        disk_free_gb=120.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )


def spec(speculative: str) -> ModelSpec:
    return ModelSpec(
        name=SEVEN_B,
        vram_gb=7.12,
        ram_gb=0.0,
        disk_gb=4.93,
        hf_cache=HF_CACHE,
        serve_args=("--gpu-memory-utilization", "0.68"),
        kv_cache_dtype_k="fp8",
        speculative=speculative,
    )


def test_a_vllm_unit_declaring_mtp_is_refused_naming_the_key() -> None:
    with pytest.raises(UnitError) as refused:
        unit_for(card(), spec("mtp"), engine="vllm", ctx_per_slot=WINDOW)
    message = str(refused.value)
    assert SEVEN_B in message
    assert "units.<unit>.launch.speculative" in message
    assert "vLLM" in message
    assert "--speculative-config" in message


def test_a_vllm_unit_declaring_none_is_served_as_before() -> None:
    unit = unit_for(card(), spec("none"), engine="vllm", ctx_per_slot=WINDOW)
    assert "--spec-type" not in argv(unit)
    assert "--spec-draft-n-max" not in argv(unit)
