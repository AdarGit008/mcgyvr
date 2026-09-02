"""The batch width, against the ladder the cell will offer.

llama.cpp reads `/props total_slots` back and refuses a server that came up
narrower than the ramp (`llamacpp.py:674,707`). vLLM has no such endpoint, and
until this guard nothing in that backend read `concurrency.levels` at all --
so `max_num_seqs 8` against an n=32 ramp launched happily, queued 24 of every
32 requests at the scheduler, and recorded the plateau as saturation with
`outcome: ok`.

Three checks, in the order a run meets them: the config-time refusal (costs
nothing), the claim-time refusal (costs nothing, and precedes the launch), and
the engine's own statement of the pool it allocated.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVING = REPO / "tools" / "bench" / "serving"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_py() -> Any:
    return _load("serving_run_guard", SERVING / "run.py")


@pytest.fixture(scope="module")
def vllm() -> Any:
    return _load("serving_vllm_guard", SERVING / "backends" / "vllm.py")


def _entry(width: int, levels: list[int] | None) -> dict[str, Any]:
    return {
        "label": "q15-vllm-srv1",
        "id": "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ",
        "backend": "vllm",
        "hosts": ["srv1"],
        "serve": {"max_model_len": 2048, "max_num_seqs": width},
        "concurrency": {"measure": True, "levels": levels},
    }


def test_config_refuses_a_width_below_the_ladder(run_py: Any) -> None:
    with pytest.raises(Exception) as raised:
        run_py.check_entries([_entry(8, [1, 2, 4, 8, 16, 32])], ["srv1"])
    assert "max_num_seqs 8" in str(raised.value)
    assert "n=32" in str(raised.value)


def test_config_accepts_a_width_at_the_top_of_the_ladder(run_py: Any) -> None:
    run_py.check_entries([_entry(32, [1, 2, 4, 8, 16, 32])], ["srv1"])


def test_a_cell_that_measures_nothing_is_not_checked(run_py: Any) -> None:
    """`measure: false` offers no levels, so no width can be too small."""
    entry = _entry(8, [1, 2, 4, 8, 16, 32])
    entry["concurrency"]["measure"] = False
    run_py.check_entries([entry], ["srv1"])


def test_claim_refuses_before_it_launches(vllm: Any, monkeypatch: Any) -> None:
    """The refusal must precede `_start`, which stops the running server."""
    started: list[Any] = []
    monkeypatch.setattr(vllm, "_start", lambda *a, **k: started.append(a))
    monkeypatch.setattr(vllm, "_running_config", lambda base: {})
    with pytest.raises(Exception) as raised:
        vllm.claim(
            "srv1",
            "http://srv1:8000",
            "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ",
            {"max_num_seqs": 8, "max_model_len": 2048},
            levels=[1, 2, 4, 8, 16, 32],
        )
    assert "max_num_seqs=8" in str(raised.value)
    assert started == [], "the server was stopped in order to report a typo"


def test_kv_capacity_reads_the_engines_own_words(vllm: Any) -> None:
    log = (
        "INFO 08-31 12:00:01 [gpu_worker.py:298] Available KV cache memory: 1.75 GiB\n"
        "INFO 08-31 12:00:01 [kv_cache_utils.py:864] GPU KV cache size: "
        "131,104 tokens\n"
        "INFO 08-31 12:00:01 [kv_cache_utils.py:868] Maximum concurrency for "
        "2,048 tokens per request: 64.01x\n"
    )
    assert vllm.kv_capacity(log) == {
        "kv_cache_tokens": 131104,
        "per_request_tokens": 2048,
        "max_concurrency": 64.01,
    }


def test_kv_capacity_that_could_not_be_read_is_null_not_zero(vllm: Any) -> None:
    """A server already up has a log tail of requests, not of its own start.

    Null must not gate: a capacity nobody could read is not a capacity of
    zero, and refusing on it would refuse every cell that reused a server.
    """
    assert vllm.kv_capacity("INFO ... POST /v1/chat/completions 200 OK") == {
        "kv_cache_tokens": None,
        "per_request_tokens": None,
        "max_concurrency": None,
    }


@pytest.fixture(scope="module")
def contract_py() -> Any:
    return _load("serving_contract_guard", SERVING / "contract.py")


def test_in_flight_reads_the_metrics_the_engine_publishes(vllm: Any) -> None:
    exposition = (
        "# HELP vllm:num_requests_running Number of requests in model "
        "execution batches.\n"
        "# TYPE vllm:num_requests_running gauge\n"
        'vllm:num_requests_running{engine="0",model_name="Qwen"} 8.0\n'
        'vllm:num_requests_waiting{engine="0",model_name="Qwen"} 24.0\n'
    )
    assert vllm._RUNNING.search(exposition).group(1) == "8.0"
    assert vllm._WAITING.search(exposition).group(1) == "24.0"


def test_in_flight_summarises_a_width_that_never_opened(contract_py: Any) -> None:
    """The whole point: n=32 offered, 8 ever running, 24 always queued."""
    samples = [
        {"running": 8, "waiting": 24},
        {"running": 8, "waiting": 21},
        {"running": 7, "waiting": 12},
    ]
    assert contract_py.in_flight(samples, 32) == {
        "samples": 3,
        "max_running": 8,
        "max_waiting": 24,
        "offered": 32,
        "reached_offered": False,
    }


def test_in_flight_that_was_never_asked_is_null(contract_py: Any) -> None:
    """Not zero. The warm-up level and any engine without the endpoint."""
    assert contract_py.in_flight([], 8) is None
