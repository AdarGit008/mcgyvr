"""A KV declaration is sized at the cache dtype it launches with.

``okf/config/vllm.md`` recorded the gap in one line: nothing read
``--kv-cache-dtype``. the rule is ``max_num_seqs x max_model_len x
bytes_per_token``, and every ``bytes_per_token`` in the tree is derived at two
bytes an element -- the fp16 width of the checkpoint's K and V. Under
``--kv-cache-dtype fp8`` an element is one byte, so the rule overstated an fp8
entry's KV by exactly 2x. Measured, not derived: srv2's q15 held 332,160 KV
tokens at ``auto`` and 664,320 at ``fp8``
(``records/evidence/2026-09-01-prompt-realism/srv2-fp8-ab-and-lcp-smoke.tsv``),
and q34b 52,192 and 104,400
(``records/measurements/measuring-gaps-2026-09-10/results-q2-vllm-fp8.json``).
The gate therefore refused the cell the 2026-08-31 plan predicted it would --
q34b at n=32 -- and that cell ran.

These checks are static and cost no rig time. They say nothing about whether an
fp8 cache answers correctly, which is a separate question with its own
measurement.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVING = REPO / "tools" / "bench" / "serving"

#: Qwen3-4B-AWQ (q34b) as the tree declares it: 36 layers x 8 KV heads x 128
#: head_dim x 2 (K and V) x 2 bytes, with 2.5 GiB of weights from the engine's
#: own ``Model loading took`` line (``test_serving_memory_declaration.py``).
Q34B_BYTES_PER_TOKEN = 147456
Q34B_WEIGHTS_BYTES = int(2.5 * 1024**3)

#: srv2's card at rest, as phase 0 read it: nameplate less the 1 MiB used.
SRV2_EMPTY_FREE_MIB = 12288 - 1


@pytest.fixture(scope="module")
def vllm() -> Any:
    spec = importlib.util.spec_from_file_location(
        "serving_vllm_kv_dtype", SERVING / "backends" / "vllm.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("flags", "per_token"),
    [
        (["--kv-cache-dtype", "auto"], 147456),
        (["--kv-cache-dtype", "float16"], 147456),
        (["--kv-cache-dtype", "bfloat16"], 147456),
        (["--kv-cache-dtype", "fp8"], 73728),
        (["--kv-cache-dtype", "fp8_e4m3"], 73728),
        (["--kv-cache-dtype", "fp8_e5m2"], 73728),
        (["--enforce-eager", "--kv-cache-dtype=fp8"], 73728),
    ],
)
def test_an_fp8_cache_holds_a_token_in_half_the_bytes_of_an_fp16_one(
    vllm: Any, flags: list[str], per_token: int
) -> None:
    """The flag is read where the launch reads it, in either spelling."""
    serve = {"bytes_per_token": Q34B_BYTES_PER_TOKEN, "flags": flags}
    assert vllm.kv_bytes_per_token(serve) == per_token


@pytest.mark.parametrize(
    "flags",
    [["--kv-cache-dtype", "fp4"], ["--kv-cache-dtype"], ["--kv-cache-dtype="]],
)
def test_a_cache_dtype_the_gate_has_no_width_for_is_refused_by_name(
    vllm: Any, flags: list[str]
) -> None:
    """Not guessed at two bytes, not guessed at one: refused, naming what was
    declared, before the card is weighed. The declaration would otherwise fit --
    2,304 MiB of KV beside 2,560 of weights on a 12 GiB card -- so the refusal
    can only be the dtype."""
    serve = {
        "max_model_len": 2048,
        "max_num_seqs": 8,
        "kv_cache_memory_bytes": 8 * 2048 * Q34B_BYTES_PER_TOKEN,
        "bytes_per_token": Q34B_BYTES_PER_TOKEN,
        "weights_bytes": Q34B_WEIGHTS_BYTES,
        "flags": flags,
    }
    with pytest.raises(vllm.contract.NotCleanError) as raised:
        vllm.declaration_fits(
            "srv2", "thewimo/Qwen3-4B-AWQ", serve, SRV2_EMPTY_FREE_MIB
        )
    assert "--kv-cache-dtype" in str(raised.value)
    if flags[-1] == "fp4":
        assert "'fp4'" in str(raised.value)
    with pytest.raises(vllm.contract.NotCleanError):
        vllm.kv_bytes_per_token(serve)


def test_the_cell_the_fp16_rule_refused_fits_when_sized_at_fp8(vllm: Any) -> None:
    """q34b at n=32 on srv2: 65,536 KV tokens.

    At the fp16 width that is 9,216 MiB of KV, and with the weights and the
    residue the declaration is 222 MiB past the card, so the gate refused it.
    At the width the flag actually allocates it is 4,608 MiB and fits with room
    to spare -- the cell that ran to n=32 without trouble.
    """
    shape = {
        "max_model_len": 2048,
        "max_num_seqs": 32,
        "bytes_per_token": Q34B_BYTES_PER_TOKEN,
        "weights_bytes": Q34B_WEIGHTS_BYTES,
    }
    fp8 = {**shape, "flags": ["--kv-cache-dtype", "fp8"]}
    fp8["kv_cache_memory_bytes"] = 32 * 2048 * vllm.kv_bytes_per_token(fp8)
    assert fp8["kv_cache_memory_bytes"] == 4608 * 1024 * 1024
    vllm.declaration_fits("srv2", "thewimo/Qwen3-4B-AWQ", fp8, SRV2_EMPTY_FREE_MIB)

    fp16 = {
        **shape,
        "flags": ["--kv-cache-dtype", "float16"],
        "kv_cache_memory_bytes": 32 * 2048 * Q34B_BYTES_PER_TOKEN,
    }
    with pytest.raises(vllm.contract.NotCleanError) as raised:
        vllm.declaration_fits("srv2", "thewimo/Qwen3-4B-AWQ", fp16, SRV2_EMPTY_FREE_MIB)
    assert "Short by 222 MiB" in str(raised.value)


def test_the_ways_out_count_tokens_at_the_cache_dtype(vllm: Any) -> None:
    """The refusal turns its budget back into a shape, and a shape is tokens.

    8,994 MiB of budget is 127,914 tokens at fp8's 73,728 B/token. Counted at
    the fp16 width it would read 63,957, and the two ways out would name a
    batch and a window half the size of what this card can hold.
    """
    serve = {
        "max_model_len": 8192,
        "max_num_seqs": 16,
        "bytes_per_token": Q34B_BYTES_PER_TOKEN,
        "weights_bytes": Q34B_WEIGHTS_BYTES,
        "flags": ["--kv-cache-dtype", "fp8"],
        "kv_cache_memory_bytes": 16 * 8192 * (Q34B_BYTES_PER_TOKEN // 2),
    }
    with pytest.raises(vllm.contract.NotCleanError) as raised:
        vllm.declaration_fits(
            "srv2", "thewimo/Qwen3-4B-AWQ", serve, SRV2_EMPTY_FREE_MIB
        )
    message = str(raised.value)
    assert "127,914 KV tokens at this model's 73,728 B/token" in message
    assert "max_num_seqs 15 at the declared max_model_len 8,192" in message
    assert "max_model_len 7,994 at the declared max_num_seqs 16" in message


def test_every_bytes_per_token_is_derived_at_two_bytes_an_element() -> None:
    """The width the rule halves for fp8 is the width the entries were derived
    at. An entry whose note derived ``bytes_per_token`` at some other width
    would be halved from the wrong starting point, so the derivation is read,
    not assumed."""
    entries = 0
    for path in sorted((SERVING / "configs").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("models") or []:
            if not (isinstance(entry, dict) and entry.get("backend") == "vllm"):
                continue
            entries += 1
            note = (entry.get("serve") or {}).get("_bytes_per_token_note", "")
            assert "x 2 bytes" in note, (
                f"{path.name}:{entry.get('label')}: the note does not derive "
                "bytes_per_token at two bytes an element"
            )
    assert entries, "no vLLM entry was discovered; the check read nothing"
