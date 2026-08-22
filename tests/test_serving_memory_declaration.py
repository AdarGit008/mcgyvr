"""A serving memory declaration is bytes, and the bytes match the declaration.

ADR-0039. ``gpu_memory_utilization = 0.85`` was never decided in this project —
it is local-ai's OOM fix for a 12 GB card, applied unchanged to a 6 GB one — and
the reason it survived is that nothing could see it was wrong. A fraction reads
as a tuning knob. What it actually is, in vLLM's own arithmetic
(``vllm/v1/worker/utils.py::request_memory``), is ``total_memory * util`` with a
hard ``free >= requested`` precondition, so it is a statement about a *card*.
Measured on the rigs 2026-08-22, at ``max_num_seqs 8``, ``max_model_len 8192``:

    srv1  0.85 -> 131,104 KV tokens, 4,916 MiB   reachable: 65,536 tokens
    srv2  0.85 -> 322,304 KV tokens, 10,197 MiB  reachable: 65,536 tokens

2.0x and 4.9x over, and the two entries that differ *only* in ``max_num_seqs``
allocated the same KV cache, because ``max_num_seqs`` does not enter the budget.
The instrument could not distinguish the two instruments it was built to be.

These checks hold the configs to bytes and hold ``_start`` to refusing an entry
that declares neither or both. They are static and cost no rig time: the
measurement is in ADR-0039 and in each entry's own ``_footprint_mib``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVING = REPO / "tools" / "bench" / "serving"
CONFIGS = SERVING / "configs"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vllm() -> Any:
    return _by_path("serving_vllm_memory", SERVING / "backends" / "vllm.py")


def _vllm_entries() -> list[tuple[Path, dict[str, Any]]]:
    """Every vLLM entry in every serving config, discovered rather than listed.

    A config added tomorrow is covered without editing this file, which is the
    property a hand-written list cannot have.
    """
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(CONFIGS.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for entry in document.get("models") or []:
            if isinstance(entry, dict) and entry.get("backend") == "vllm":
                found.append((path, entry))
    return found


def test_a_vllm_entry_declares_bytes_and_the_bytes_match_its_own_shape() -> None:
    """ADR-0039 rules 1 and 2, over every vLLM entry in the tree."""
    entries = _vllm_entries()
    assert entries, "no vLLM entry was discovered; the sweep found nothing to hold"
    for path, entry in entries:
        where = f"{path.name}:{entry.get('label')}"
        serve = entry.get("serve") or {}
        assert "gpu_memory_utilization" not in serve, (
            f"{where} declares a fraction. A fraction is a statement about one "
            "card: the same 1,792 MiB of KV cache is 0.565 on srv1 and 0.273 on "
            "srv2 (ADR-0039)"
        )
        assert "kv_cache_memory_bytes" in serve, f"{where} declares no KV cache size"
        expected = (
            serve["max_num_seqs"] * serve["max_model_len"] * serve["bytes_per_token"]
        )
        assert serve["kv_cache_memory_bytes"] == expected, (
            f"{where} declares {serve['kv_cache_memory_bytes']} bytes, but its own "
            f"shape ({serve['max_num_seqs']} seqs x {serve['max_model_len']} tokens "
            f"x {serve['bytes_per_token']} B/token) is {expected}. A declared size "
            "that does not follow from the declaration is the config lying about "
            "itself"
        )


def test_every_declared_model_records_how_its_bytes_per_token_was_derived() -> None:
    """ADR-0039 rule 2: the constant carries its derivation, or it is a magic
    number with a longer name. The note must show the arithmetic AND name a
    measurement, because either alone is how 0.85 travelled."""
    for path, entry in _vllm_entries():
        where = f"{path.name}:{entry.get('label')}"
        serve = entry["serve"]
        note = serve.get("_bytes_per_token_note", "")
        assert "head_dim" in note and "layers" in note, (
            f"{where}: the note does not show where bytes_per_token comes from"
        )
        assert "2026-" in note, f"{where}: the note names no measurement date"
        footprint = serve.get("_footprint_mib")
        assert isinstance(footprint, dict) and footprint, (
            f"{where}: no measured footprint. ADR-0039 rule 4 -- the arithmetic "
            "predicts the KV cache and only the card says what the process took"
        )
        assert all(isinstance(v, int) and v > 0 for v in footprint.values()), where


def test_there_is_no_silent_default_and_both_fields_together_are_a_refusal(
    vllm: Any,
) -> None:
    """ADR-0039 rules 1 and 3, against the argument builder itself.

    Both directions, so the check can be shown to reject: a bare shape must
    raise rather than fall back, and the two fields together must raise rather
    than pick a winner. vLLM's own precedence silently discards the fraction,
    so honouring it here would record a fraction that never applied.
    """
    shape = {"max_model_len": 8192, "max_num_seqs": 8}

    with pytest.raises(vllm.contract.NotCleanError) as bare:
        vllm._memory_args(dict(shape))
    assert "neither" in str(bare.value) and "0.85" not in str(bare.value)

    with pytest.raises(vllm.contract.NotCleanError) as both:
        vllm._memory_args(
            {
                **shape,
                "kv_cache_memory_bytes": 1879048192,
                "gpu_memory_utilization": 0.85,
            }
        )
    assert "exclusive" in str(both.value)

    assert vllm._memory_args({**shape, "kv_cache_memory_bytes": 1879048192}) == [
        "--kv-cache-memory-bytes",
        "1879048192",
    ]
    # Rule 5: a fraction is un-defaulted, not banned.
    assert vllm._memory_args({**shape, "gpu_memory_utilization": 0.5}) == [
        "--gpu-memory-utilization",
        "0.5",
    ]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: decided — ADR-0039 rule 1 reaches calibrate.py's two inline "
        "serve blocks (the width sweep and the sleep arm), and converting them "
        "re-baselines every vLLM cell they produced. That is #329's arm, which "
        "already owes a width-16 measurement, and it lands there rather than "
        "here: at 0.85 srv1 gets 131,088 KV tokens against the 131,072 width 16 "
        "needs (a 16-token margin) while srv2 gets 322,304, so the two arms of "
        "that contrast are 2.46x apart in KV cache from one declared setting"
    ),
)
def test_the_calibration_probes_declare_bytes_too() -> None:
    """The two `serve` blocks built inside `calibrate.py` rather than in a config.

    A config-only sweep would report green while the code that actually launches
    the campaign's vLLM cells still carries the withdrawn fraction — the same
    where-it-is-run defect this lane has now hit four times.
    """
    source = (SERVING / "calibrate.py").read_text(encoding="utf-8")
    assert "gpu_memory_utilization" not in source, (
        "calibrate.py still builds a serve block around a fraction"
    )
