"""An attempt row records how fast the unit answered, and how busy it was.

Owner, 2026-09-15 (F2): live must write "the record of speed and memory (and
anything else we need for tolerance check) to the journal", on every dispatch:
decode tok/s, prefill tok/s and the requests in flight, so a live observation
can be judged against a locked unit's ``warm_decode_tok_s`` and
``prefill_tok_s`` — and judged only when it ran alone.

Where each figure comes from is part of the figure, so every rate carries its
source:

* ``decode_tok_s`` — llama.cpp's own ``timings.predicted_per_second``
  (``decode_source: timings``); otherwise ``completion_tokens / latency_s``
  (``usage_latency``), the formula the vLLM units' lock was measured with
  (``records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py``).
* ``prefill_tok_s`` — llama.cpp's ``timings.prompt_per_second`` (``timings``);
  otherwise, for a dispatch that was the only one in flight, ``prompt_tokens``
  over the ``vllm:time_to_first_token_seconds_sum`` delta read from
  ``/metrics`` around it (``metrics_ttft``). Anything less certain records no
  prefill at all.
* ``in_flight`` — the slots held on the dispatch's bound while it ran, itself
  included.

Absent is honest: a figure that could not be read is left out of the row.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
import types
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.capacity import Capacity
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.pool import source_map as build_source_map
from mcgyvr.runner import Completion, Request, StopReason, dispatch, runner_for
from mcgyvr.telemetry import fold, observe

REPO = Path(__file__).resolve().parent.parent

ASK = Request(prompt="write a function", max_output_tokens=256)

ENDPOINT = Endpoint(
    source="unit",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=2,
    credential_env=None,
)

LADDER = """\
units:
  cheap:
    address: http://localhost:8081
    model: qwen2.5-coder:7b
    rig: local
    width: 3
ladder:
- cheap
"""

TTFT = "vllm:time_to_first_token_seconds"


def answer(
    *,
    prompt_tokens: int = 2015,
    completion_tokens: int = 256,
    timings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A chat-completions answer; ``timings`` is what llama-server adds."""
    document: dict[str, Any] = {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "x = 1\n"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }
    if timings is not None:
        document["timings"] = timings
    return document


LLAMA_TIMINGS = {
    "prompt_n": 2015,
    "prompt_ms": 6560.099,
    "prompt_per_second": 307.16,
    "predicted_n": 256,
    "predicted_ms": 7863.5,
    "predicted_per_second": 32.56,
}


def metrics(ttft_sum: float, ttft_count: int) -> str:
    """A ``/metrics`` page in vLLM's Prometheus shape, labels included."""
    labels = '{engine="0",model_name="/root/.cache/huggingface/hub/m"}'
    return textwrap.dedent(
        f"""\
        # HELP {TTFT} Histogram of time to first token in seconds.
        # TYPE {TTFT} histogram
        {TTFT}_sum{labels} {ttft_sum}
        {TTFT}_count{labels} {ttft_count}
        vllm:num_requests_running{labels} 0.0
        """
    )


def stub_post(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        return document

    monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)


def stub_clock(monkeypatch: pytest.MonkeyPatch, elapsed: float) -> None:
    ticks = iter([10.0, 10.0 + elapsed])

    def clock() -> float:
        return next(ticks, 10.0 + elapsed)

    monkeypatch.setattr("mcgyvr.runner.time.monotonic", clock)


def stub_metrics(monkeypatch: pytest.MonkeyPatch, pages: list[str | None]) -> list[str]:
    """Serve ``pages`` in order from ``/metrics``; return the URLs asked for."""
    asked: list[str] = []
    queue = list(pages)

    def fake_get(url: str, timeout: float) -> str | None:
        asked.append(url)
        return queue.pop(0) if queue else None

    monkeypatch.setattr(runner_module, "_get_text", fake_get, raising=True)
    return asked


# --- decode and prefill, read from the reply ---------------------------------


def test_llama_cpp_timings_are_the_decode_and_prefill_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, answer(timings=LLAMA_TIMINGS))
    stub_clock(monkeypatch, 20.0)
    stub_metrics(monkeypatch, [])

    done = runner_for(ENDPOINT).generate("deepseek-coder-v2-16b", ASK)

    assert (done.decode_tok_s, done.decode_source) == (32.56, "timings")
    assert (done.prefill_tok_s, done.prefill_source) == (307.16, "timings")


def test_a_reply_without_timings_decodes_at_completion_tokens_over_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, answer(completion_tokens=256))
    stub_clock(monkeypatch, 2.0)
    stub_metrics(monkeypatch, [])

    done = runner_for(ENDPOINT).generate("Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", ASK)

    assert (done.decode_tok_s, done.decode_source) == (128.0, "usage_latency")


def test_no_timings_and_no_in_flight_count_records_no_prefill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, answer())
    stub_clock(monkeypatch, 2.0)
    asked = stub_metrics(monkeypatch, [metrics(1.0, 10), metrics(1.5, 11)])

    done = runner_for(ENDPOINT).generate("Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", ASK)

    assert (done.prefill_tok_s, done.prefill_source, done.in_flight) == (
        None,
        None,
        None,
    )
    assert asked == [], "without an in-flight count nothing says the dispatch ran alone"


def test_a_reply_that_reports_no_completion_tokens_records_no_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = answer()
    del document["usage"]
    stub_post(monkeypatch, document)
    stub_clock(monkeypatch, 2.0)
    stub_metrics(monkeypatch, [])

    done = runner_for(ENDPOINT).generate("m", ASK)

    assert (done.decode_tok_s, done.decode_source) == (None, None)


# --- in flight, and the vLLM prefill it permits ------------------------------


def test_a_dispatch_records_the_slots_held_while_it_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse(LADDER)
    ladder, capacity = build_source_map(config), Capacity.of(config)
    stub_post(monkeypatch, answer(timings=LLAMA_TIMINGS))
    stub_metrics(monkeypatch, [])

    done = dispatch(ladder, "cheap", ASK, capacity=capacity)

    assert done.in_flight == 1


def test_a_solo_dispatch_reads_its_prefill_from_the_metrics_ttft_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse(LADDER)
    ladder, capacity = build_source_map(config), Capacity.of(config)
    stub_post(monkeypatch, answer(prompt_tokens=2015))
    stub_clock(monkeypatch, 2.0)
    asked = stub_metrics(monkeypatch, [metrics(1.25, 10), metrics(1.75, 11)])

    done = dispatch(ladder, "cheap", ASK, capacity=capacity)

    assert asked == ["http://localhost:8081/metrics"] * 2, "read before and after"
    assert (done.prefill_tok_s, done.prefill_source) == (4030.0, "metrics_ttft")


def test_a_dispatch_that_did_not_run_alone_records_no_metrics_prefill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse(LADDER)
    ladder, capacity = build_source_map(config), Capacity.of(config)
    endpoint = ladder.bind("cheap")
    stub_post(monkeypatch, answer())
    asked = stub_metrics(monkeypatch, [metrics(1.25, 10), metrics(1.75, 11)])

    with capacity.hold(endpoint, rung="cheap"):
        done = dispatch(ladder, "cheap", ASK, capacity=capacity)

    assert done.in_flight == 2
    assert (done.prefill_tok_s, done.prefill_source) == (None, None)
    assert asked == [], "a TTFT delta shared with another request is not this prefill"


@pytest.mark.parametrize(
    "pages",
    [
        [metrics(1.25, 10), metrics(1.75, 12)],  # another request finished too
        [metrics(1.25, 10), metrics(1.25, 10)],  # nothing was counted
        [None, metrics(1.75, 11)],  # no /metrics before
        ["# llama-server has no vllm metrics\n", "#\n"],  # not a vLLM unit
    ],
)
def test_a_ttft_delta_that_is_not_exactly_this_request_records_no_prefill(
    monkeypatch: pytest.MonkeyPatch, pages: list[str | None]
) -> None:
    config = parse(LADDER)
    ladder, capacity = build_source_map(config), Capacity.of(config)
    stub_post(monkeypatch, answer())
    stub_metrics(monkeypatch, pages)

    done = dispatch(ladder, "cheap", ASK, capacity=capacity)

    assert done.in_flight == 1
    assert (done.prefill_tok_s, done.prefill_source) == (None, None)


# --- the row, and the index over it ------------------------------------------


def _completion(**fields: Any) -> Completion:
    return Completion(
        text="x = 1\n",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="deepseek-coder-v2-16b",
        source="srv1_deepseek",
        protocol=Protocol.OPENAI,
        max_output_tokens=2048,
        latency_s=8.0,
        **fields,
    )


def _row(sink: Path, completion: Completion) -> dict[str, Any]:
    observe(
        lambda: completion,
        path=sink,
        attempt_id="agent-a:doc:srv1_deepseek:1",
        orchestrator="agent-a",
        rung="srv1_deepseek",
    )
    (row,) = fold(path=sink)
    return row


def test_the_row_carries_the_rates_their_sources_and_the_in_flight_count(
    tmp_path: Path,
) -> None:
    row = _row(
        tmp_path / "agent-a.jsonl",
        _completion(
            decode_tok_s=32.56,
            decode_source="timings",
            prefill_tok_s=307.16,
            prefill_source="timings",
            in_flight=1,
        ),
    )

    assert row["decode_tok_s"] == 32.56
    assert row["decode_source"] == "timings"
    assert row["prefill_tok_s"] == 307.16
    assert row["prefill_source"] == "timings"
    assert row["in_flight"] == 1


def test_a_figure_that_was_not_read_is_absent_from_the_row(tmp_path: Path) -> None:
    row = _row(tmp_path / "agent-a.jsonl", _completion())

    for key in (
        "decode_tok_s",
        "decode_source",
        "prefill_tok_s",
        "prefill_source",
        "in_flight",
    ):
        assert key not in row, f"{key} was never read and must not be written"


def _index() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "live_index_for_rates", REPO / "tools" / "live" / "index.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_journal_index_has_a_column_for_each_new_field() -> None:
    columns = dict(_index().COLUMNS)

    assert columns.get("decode_tok_s") == "REAL"
    assert columns.get("decode_source") == "TEXT"
    assert columns.get("prefill_tok_s") == "REAL"
    assert columns.get("prefill_source") == "TEXT"
    assert columns.get("in_flight") == "INTEGER"
