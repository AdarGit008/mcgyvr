"""A unit states its KV cache dtype, and a unit that does not is refused.

RED. Owner, 2026-09-11: "make this field a knob that must be set. fail loud on
null." Today the KV cache dtype is implicit wherever it is absent. The bench
vLLM gate reads a missing ``--kv-cache-dtype`` as ``auto``
(``tools/bench/serving/backends/vllm.py`` ``kv_cache_dtype``, since #442), a
llama.cpp launch that omits ``-ctk``/``-ctv`` gets the engine's own ``f16``,
and a product unit renders whatever ``serve_args`` happen to say. Four srv2
bench entries state ``fp8``; every other served entry in the tree states
nothing, and so does every model in the live config. A dtype nobody wrote is a
number nobody chose: fp8 moves an sm_86 card off FlashAttention and changed
the 7B's answers (7a4d048f M5), so which cache a unit runs is a decision, and
a decision is declared.

What is specified here, at the two places a launch is declared:

* **The bench survey** (``tools/bench/serving/run.py`` ``check_entries``, the
  config-time refusals that precede the first ssh). A vLLM entry states
  ``--kv-cache-dtype``; a llama.cpp entry states both ``-ctk`` and ``-ctv``
  (either spelling). Missing is refused naming the entry and the knob; an
  unknown value is refused naming the value; a stated one is accepted and left
  exactly as written. The vLLM gate itself stops defaulting to ``auto``.
* **The product** (:func:`mcgyvr.serving.unit_for`, before anything is
  rendered). A unit whose model states no KV cache dtype is refused naming the
  model and the knob; a stated one reaches the argv as written.

Nothing here changes a value. ``fp8`` stays ``fp8`` and ``auto`` stays
``auto``: the GREEN declares what each entry already launches with, it does
not choose a different cache.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.emit import argv
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, unit_for

REPO = Path(__file__).resolve().parent.parent
SERVING = REPO / "tools" / "bench" / "serving"
CONFIGS = SERVING / "configs"

#: The window these tests declare, as every unit test here must.
WINDOW = 4096

HF_CACHE = "/home/someone/.cache/huggingface"
SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
UTILISATION = ("--gpu-memory-utilization", "0.68")

VLLM_KNOB = ("--kv-cache-dtype", "kv_cache_dtype")
CTK_KNOB = ("-ctk", "--cache-type-k", "cache_type_k")
CTV_KNOB = ("-ctv", "--cache-type-v", "cache_type_v")


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_py() -> Any:
    return _load("serving_run_kv_dtype_knob", SERVING / "run.py")


@pytest.fixture(scope="module")
def vllm() -> Any:
    return _load("serving_vllm_kv_dtype_knob", SERVING / "backends" / "vllm.py")


def _names(message: str, spellings: tuple[str, ...]) -> bool:
    return any(spelling in message for spelling in spellings)


def _vllm_entry(flags: list[str]) -> dict[str, Any]:
    return {
        "label": "q7-vllm-srv2",
        "id": SEVEN_B,
        "backend": "vllm",
        "hosts": ["srv2"],
        "serve": {"max_model_len": 2048, "max_num_seqs": 8, "flags": flags},
        "concurrency": {"measure": True, "levels": [1, 2, 4, 8]},
    }


def _llamacpp_entry(flags: list[str]) -> dict[str, Any]:
    return {
        "label": "m_q36iq3-lcpp-srv1",
        "id": "/home/someone/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf",
        "backend": "llamacpp",
        "hosts": ["srv1"],
        "serve": {"ctx_per_slot": 2048, "parallel": 8, "flags": flags},
        "concurrency": {"measure": True, "levels": [1, 2, 4, 8]},
    }


# --- the bench survey ------------------------------------------------------


def test_a_vllm_entry_that_states_no_kv_cache_dtype_is_refused_by_name(
    run_py: Any,
) -> None:
    """Refused at config time, naming the entry and the flag it must state."""
    with pytest.raises(run_py.contract.NotCleanError) as refused:
        run_py.check_entries([_vllm_entry(["--enforce-eager"])], ["srv2"])
    message = str(refused.value)
    assert "q7-vllm-srv2" in message
    assert _names(message, VLLM_KNOB), message


@pytest.mark.parametrize(
    ("flags", "missing"),
    [
        ([], (CTK_KNOB, CTV_KNOB)),
        (["-ctk", "f16"], (CTV_KNOB,)),
        (["--cache-type-v", "f16"], (CTK_KNOB,)),
    ],
    ids=["neither", "only-k", "only-v"],
)
def test_a_llamacpp_entry_states_both_cache_types_or_is_refused_by_name(
    run_py: Any, flags: list[str], missing: tuple[tuple[str, ...], ...]
) -> None:
    """K and V are two knobs, and each one left unstated is named."""
    with pytest.raises(run_py.contract.NotCleanError) as refused:
        run_py.check_entries([_llamacpp_entry(flags)], ["srv1"])
    message = str(refused.value)
    assert "m_q36iq3-lcpp-srv1" in message
    for knob in missing:
        assert _names(message, knob), message


@pytest.mark.parametrize(
    ("entry", "host", "value"),
    [
        (_vllm_entry(["--kv-cache-dtype", "fp4"]), "srv2", "fp4"),
        (_llamacpp_entry(["-ctk", "q9_9", "-ctv", "f16"]), "srv1", "q9_9"),
    ],
    ids=["vllm", "llamacpp"],
)
def test_a_cache_dtype_nothing_knows_is_refused_at_config_time_by_name(
    run_py: Any, entry: dict[str, Any], host: str, value: str
) -> None:
    """Before any claim or launch, not when the gate first weighs the card."""
    with pytest.raises(run_py.contract.NotCleanError) as refused:
        run_py.check_entries([entry], [host])
    assert value in str(refused.value)


@pytest.mark.parametrize(
    ("entry", "host"),
    [
        (_vllm_entry(["--kv-cache-dtype", "fp8"]), "srv2"),
        (_vllm_entry(["--kv-cache-dtype=auto"]), "srv2"),
        (_llamacpp_entry(["-ctk", "f16", "-ctv", "f16"]), "srv1"),
        (_llamacpp_entry(["--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]), "srv1"),
    ],
    ids=["vllm-fp8", "vllm-auto", "llamacpp-f16", "llamacpp-q8_0"],
)
def test_a_stated_cache_dtype_is_accepted_and_left_as_written(
    run_py: Any, entry: dict[str, Any], host: str
) -> None:
    """Declaring is not converting: the entry leaves the check byte-for-byte."""
    before = copy.deepcopy(entry)
    run_py.check_entries([entry], [host])
    assert entry == before


def test_the_vllm_gate_does_not_read_a_missing_cache_dtype_as_auto(vllm: Any) -> None:
    """#442 read no flag as vLLM's own default; a default is what the knob removes.

    ``test_a_kv_declaration_is_sized_at_its_cache_dtype.py`` still sizes the
    no-flag case at ``auto``; the GREEN retires that case with this default.
    """
    with pytest.raises(vllm.contract.NotCleanError) as refused:
        vllm.kv_cache_dtype({"bytes_per_token": 147456, "flags": []})
    assert _names(str(refused.value), VLLM_KNOB)


@pytest.mark.parametrize(
    ("flags", "declared"),
    [
        (["--kv-cache-dtype", "fp8"], "fp8"),
        (["--kv-cache-dtype", "auto"], "auto"),
        (["--kv-cache-dtype=float16"], "float16"),
    ],
)
def test_the_vllm_gate_reads_a_stated_cache_dtype_unchanged(
    vllm: Any, flags: list[str], declared: str
) -> None:
    assert vllm.kv_cache_dtype({"bytes_per_token": 147456, "flags": flags}) == declared


def _served_entries() -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(CONFIGS.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for entry in document.get("models") or []:
            if isinstance(entry, dict) and entry.get("backend") in {"vllm", "llamacpp"}:
                found.append((path.name, entry))
    return found


def _states(flags: list[str], spellings: tuple[str, ...]) -> bool:
    return any(
        flag in spellings or flag.split("=", 1)[0] in spellings for flag in flags
    )


def test_every_served_entry_in_the_tree_states_its_kv_cache_dtype() -> None:
    """The entries the refusal would stop, listed so the GREEN declares them.

    Declared as each one launched, not changed: the fp8 entries stay fp8, and
    an entry that ran with no flag states the dtype that launch actually used.
    """
    unstated = []
    for config, entry in _served_entries():
        flags = [str(flag) for flag in (entry.get("serve") or {}).get("flags") or []]
        knobs: list[tuple[str, ...]]
        if entry["backend"] == "vllm":
            knobs = [VLLM_KNOB[:1]]
        else:
            knobs = [CTK_KNOB[:2], CTV_KNOB[:2]]
        if not all(_states(flags, knob) for knob in knobs):
            unstated.append(f"{config}:{entry.get('label') or entry.get('id')}")
    assert not unstated, (
        f"{len(unstated)} served entries state no KV cache dtype: {unstated}"
    )


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


def _vllm_spec(*serve_args: str) -> ModelSpec:
    return ModelSpec(
        name=SEVEN_B,
        vram_gb=7.12,
        ram_gb=0.0,
        disk_gb=4.93,
        hf_cache=HF_CACHE,
        serve_args=(*UTILISATION, *serve_args),
    )


def _llamacpp_spec(*serve_args: str) -> ModelSpec:
    return ModelSpec(
        name="qwen2.5-coder-3b",
        vram_gb=2.4,
        ram_gb=0.0,
        disk_gb=2.1,
        serve_args=serve_args,
    )


def test_a_vllm_unit_whose_model_states_no_kv_cache_dtype_is_refused_by_name() -> None:
    with pytest.raises(UnitError) as refused:
        unit_for(_card(), _vllm_spec(), engine="vllm", ctx_per_slot=WINDOW)
    message = str(refused.value)
    assert SEVEN_B in message
    assert _names(message, VLLM_KNOB), message


@pytest.mark.parametrize(
    ("serve_args", "missing"),
    [
        ((), (CTK_KNOB, CTV_KNOB)),
        (("-ctk", "q8_0"), (CTV_KNOB,)),
        (("-ctv", "q8_0"), (CTK_KNOB,)),
    ],
    ids=["neither", "only-k", "only-v"],
)
def test_a_llamacpp_unit_whose_model_states_no_cache_types_is_refused_by_name(
    serve_args: tuple[str, ...], missing: tuple[tuple[str, ...], ...]
) -> None:
    with pytest.raises(UnitError) as refused:
        unit_for(
            _card(),
            _llamacpp_spec(*serve_args),
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
        _vllm_spec("--kv-cache-dtype", dtype),
        engine="vllm",
        ctx_per_slot=WINDOW,
    )
    assert _contains(argv(unit), ("--kv-cache-dtype", dtype))


def test_stated_cache_types_reach_a_llamacpp_argv_as_written() -> None:
    unit = unit_for(
        _card(),
        _llamacpp_spec("-ctk", "q8_0", "-ctv", "f16"),
        engine="llama.cpp",
        ctx_per_slot=WINDOW,
    )
    parts = argv(unit)
    assert _contains(parts, ("-ctk", "q8_0"))
    assert _contains(parts, ("-ctv", "f16"))
