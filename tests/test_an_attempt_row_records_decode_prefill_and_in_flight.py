"""An attempt row records how fast the unit answered, and how busy the unit was.

Owner, 2026-09-15 (F2): live must write "the record of speed and memory (and
anything else we need for tolerance check) to the journal", on every dispatch:
decode tok/s, prefill tok/s and the requests in flight, so a live observation
can be judged against a locked unit's ``warm_decode_tok_s`` and
``prefill_tok_s`` — and judged only when one request was in flight.

"In flight" is the unit's fact, not this process's. On 2026-09-14 three
separate ``mcgyvr run`` processes dispatched to srv2_3b at once; a count kept
per process would have called every one of them solo. So the count is read
off the unit itself, immediately before and immediately after the dispatch,
and the larger reading is kept:

* ``in_flight`` — on a llama.cpp unit, the ``/slots`` entries that are
  ``is_processing``; on a vLLM unit, ``vllm:num_requests_running`` plus
  ``vllm:num_requests_waiting`` from ``/metrics``. Either way this request is
  counted. ``in_flight_source`` says which (``slots`` | ``vllm_metrics``). A
  read that fails leaves both out of the row — a process-local count is never
  written under that name.
* ``decode_tok_s`` — llama.cpp's own ``timings.predicted_per_second``
  (``decode_source: timings``); otherwise ``completion_tokens / latency_s``
  (``usage_latency``), the formula the vLLM units' lock was measured with.
* ``prefill_tok_s`` — llama.cpp's ``timings.prompt_per_second`` (``timings``);
  on vLLM, ``prompt_tokens`` over the ``vllm:time_to_first_token_seconds_sum``
  delta (``metrics_ttft``), only when the unit read 1 at both reads and the
  histogram count moved by exactly one.

Which page is read follows the unit's declared engine: a llama.cpp unit is
asked for no ``/metrics`` (llama-server answers it 501 unless started with
``--metrics``), a vLLM unit for no ``/slots``, and a keyed endpoint — a hosted
provider — for neither.
"""

from __future__ import annotations

import importlib.util
import json
import sys
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

TTFT = "vllm:time_to_first_token_seconds"

LADDER = """\
units:
  llama:
    address: http://localhost:8080
    engine: llama.cpp
    model: deepseek-coder-v2-16b
    rig: srv1
    width: 2
  vllm:
    address: http://localhost:8001
    engine: vllm
    model: Qwen/Qwen2.5-Coder-3B-Instruct-AWQ
    rig: srv2
    width: 8
ladder:
- llama
- vllm
"""


def endpoint(engine: str | None, *, key: str | None = None) -> Endpoint:
    return Endpoint(
        source="unit",
        base_url="http://localhost:8080",
        protocol=Protocol.OPENAI,
        max_parallel=2,
        credential_env=key,
        engine=engine,
    )


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


def metrics(
    *, ttft_sum: float = 1.0, ttft_count: int = 10, running: int = 0, waiting: int = 0
) -> str:
    """A vLLM ``/metrics`` page, in its Prometheus shape with labels."""
    labels = '{engine="0",model_name="/root/.cache/huggingface/hub/m"}'
    return (
        f"# HELP {TTFT} Histogram of time to first token in seconds.\n"
        f"# TYPE {TTFT} histogram\n"
        f"{TTFT}_sum{labels} {ttft_sum}\n"
        f"{TTFT}_count{labels} {ttft_count}\n"
        f"vllm:num_requests_running{labels} {float(running)}\n"
        f"vllm:num_requests_waiting{labels} {float(waiting)}\n"
    )


def slots(processing: int, total: int = 2) -> str:
    """A llama-server ``/slots`` answer with ``processing`` slots busy."""
    return json.dumps(
        [{"id": i, "is_processing": i < processing} for i in range(total)]
    )


class StatusPages:
    """Serve each status path's pages in order, and record every URL asked."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, pages: dict[str, list[str | None]]
    ) -> None:
        self.asked: list[str] = []
        queues = {path: list(queue) for path, queue in pages.items()}

        def fake_get(url: str, timeout: float) -> str | None:
            self.asked.append(url)
            for path, queue in queues.items():
                if url.endswith(path):
                    return queue.pop(0) if queue else None
            return None

        monkeypatch.setattr(runner_module, "_get_text", fake_get, raising=True)


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


# --- decode and prefill, read from the reply ---------------------------------


def test_llama_cpp_timings_are_the_decode_and_prefill_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, answer(timings=LLAMA_TIMINGS))
    stub_clock(monkeypatch, 20.0)
    StatusPages(monkeypatch, {"/slots": [slots(0), slots(0)]})

    done = runner_for(endpoint("llama.cpp")).generate("deepseek-coder-v2-16b", ASK)

    assert (done.decode_tok_s, done.decode_source) == (32.56, "timings")
    assert (done.prefill_tok_s, done.prefill_source) == (307.16, "timings")


def test_a_reply_without_timings_decodes_at_completion_tokens_over_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, answer(completion_tokens=256))
    stub_clock(monkeypatch, 2.0)
    StatusPages(monkeypatch, {})

    done = runner_for(endpoint("vllm")).generate("m", ASK)

    assert (done.decode_tok_s, done.decode_source) == (128.0, "usage_latency")


def test_a_reply_that_reports_no_completion_tokens_records_no_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = answer()
    del document["usage"]
    stub_post(monkeypatch, document)
    stub_clock(monkeypatch, 2.0)
    StatusPages(monkeypatch, {})

    done = runner_for(endpoint("vllm")).generate("m", ASK)

    assert (done.decode_tok_s, done.decode_source) == (None, None)


# --- in flight: the unit's own count -----------------------------------------


def test_a_llama_cpp_unit_counts_its_processing_slots_and_this_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, answer(timings=LLAMA_TIMINGS))
    pages = StatusPages(monkeypatch, {"/slots": [slots(0), slots(0)]})

    done = runner_for(endpoint("llama.cpp")).generate("m", ASK)

    assert (done.in_flight, done.in_flight_source) == (1, "slots")
    assert pages.asked == ["http://localhost:8080/slots"] * 2, (
        "read before and after, and no /metrics: llama-server answers it 501"
    )


def test_a_unit_that_declares_no_engine_is_read_as_llama_cpp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``units.engine``: absent means llama.cpp (``mcgyvr.config``)."""
    stub_post(monkeypatch, answer(timings=LLAMA_TIMINGS))
    pages = StatusPages(monkeypatch, {"/slots": [slots(1), slots(0)]})

    done = runner_for(endpoint(None)).generate("m", ASK)

    assert (done.in_flight, done.in_flight_source) == (2, "slots")
    assert all(url.endswith("/slots") for url in pages.asked)


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [(0, 0, 1), (1, 0, 2), (0, 1, 2), (2, 1, 3)],
)
def test_the_larger_slots_reading_is_kept(
    monkeypatch: pytest.MonkeyPatch, before: int, after: int, expected: int
) -> None:
    stub_post(monkeypatch, answer(timings=LLAMA_TIMINGS))
    StatusPages(
        monkeypatch, {"/slots": [slots(before, total=4), slots(after, total=4)]}
    )

    done = runner_for(endpoint("llama.cpp")).generate("m", ASK)

    assert done.in_flight == expected


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ({"running": 0, "waiting": 0}, {"running": 0, "waiting": 0}, 1),
        ({"running": 1, "waiting": 0}, {"running": 0, "waiting": 0}, 2),
        ({"running": 0, "waiting": 0}, {"running": 1, "waiting": 1}, 3),
    ],
)
def test_a_vllm_unit_counts_running_and_waiting_and_this_request(
    monkeypatch: pytest.MonkeyPatch,
    before: dict[str, int],
    after: dict[str, int],
    expected: int,
) -> None:
    stub_post(monkeypatch, answer())
    pages = StatusPages(
        monkeypatch, {"/metrics": [metrics(**before), metrics(**after)]}
    )

    done = runner_for(endpoint("vllm")).generate("m", ASK)

    assert (done.in_flight, done.in_flight_source) == (expected, "vllm_metrics")
    assert pages.asked == ["http://localhost:8080/metrics"] * 2, "and no /slots"


def test_another_process_on_the_unit_is_counted_where_this_process_counts_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three ``mcgyvr run`` processes on one unit: this one holds one slot."""
    config = parse(LADDER)
    ladder, capacity = build_source_map(config), Capacity.of(config)
    stub_post(monkeypatch, answer(timings=LLAMA_TIMINGS))
    StatusPages(
        monkeypatch, {"/slots": [slots(2, total=4), slots(2, total=4)]}
    )

    done = dispatch(ladder, "llama", ASK, capacity=capacity)

    assert (done.in_flight, done.in_flight_source) == (3, "slots")


@pytest.mark.parametrize(
    ("rung", "path", "page"),
    [
        ("llama", "/slots", None),
        ("llama", "/slots", "not json"),
        ("llama", "/slots", '{"error": "slots endpoint disabled"}'),
        ("vllm", "/metrics", None),
        ("vllm", "/metrics", "# a page without request gauges\n"),
    ],
)
def test_a_count_that_cannot_be_read_is_absent_not_this_processes_count(
    monkeypatch: pytest.MonkeyPatch, rung: str, path: str, page: str | None
) -> None:
    config = parse(LADDER)
    ladder, capacity = build_source_map(config), Capacity.of(config)
    stub_post(monkeypatch, answer())
    StatusPages(monkeypatch, {path: [page, page]})

    done = dispatch(ladder, rung, ASK, capacity=capacity)

    assert (done.in_flight, done.in_flight_source) == (None, None)


def test_a_keyed_endpoint_is_asked_for_no_status_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-test")
    stub_post(monkeypatch, answer())
    pages = StatusPages(monkeypatch, {"/metrics": [metrics(), metrics()]})

    done = runner_for(endpoint("vllm", key="MCGYVR_TEST_KEY")).generate("m", ASK)

    assert pages.asked == []
    assert (done.in_flight, done.in_flight_source) == (None, None)


# --- the vLLM prefill, which only a solo dispatch permits --------------------


def test_a_solo_vllm_dispatch_reads_its_prefill_from_the_metrics_ttft_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, answer(prompt_tokens=2015))
    StatusPages(
        monkeypatch,
        {
            "/metrics": [
                metrics(ttft_sum=1.25, ttft_count=10),
                metrics(ttft_sum=1.75, ttft_count=11),
            ]
        },
    )

    done = runner_for(endpoint("vllm")).generate("m", ASK)

    assert done.in_flight == 1
    assert (done.prefill_tok_s, done.prefill_source) == (4030.0, "metrics_ttft")


@pytest.mark.parametrize(
    "pages",
    [
        # another request on the unit before, or after
        [metrics(ttft_count=10, running=1), metrics(ttft_count=11)],
        [metrics(ttft_count=10), metrics(ttft_count=11, waiting=1)],
        # the histogram moved by other than exactly this request
        [metrics(ttft_count=10), metrics(ttft_sum=1.5, ttft_count=12)],
        [metrics(ttft_count=10), metrics(ttft_count=10)],
        # a read that failed
        [None, metrics(ttft_sum=1.5, ttft_count=11)],
        [metrics(ttft_count=10), None],
    ],
)
def test_a_vllm_prefill_needs_the_unit_alone_and_exactly_this_request(
    monkeypatch: pytest.MonkeyPatch, pages: list[str | None]
) -> None:
    stub_post(monkeypatch, answer())
    StatusPages(monkeypatch, {"/metrics": pages})

    done = runner_for(endpoint("vllm")).generate("m", ASK)

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


def test_the_row_carries_the_rates_the_count_and_their_sources(
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
            in_flight_source="slots",
        ),
    )

    assert row["decode_tok_s"] == 32.56
    assert row["decode_source"] == "timings"
    assert row["prefill_tok_s"] == 307.16
    assert row["prefill_source"] == "timings"
    assert row["in_flight"] == 1
    assert row["in_flight_source"] == "slots"
    assert "in_flight_local" not in row


def test_a_figure_that_was_not_read_is_absent_from_the_row(tmp_path: Path) -> None:
    row = _row(tmp_path / "agent-a.jsonl", _completion())

    for key in (
        "decode_tok_s",
        "decode_source",
        "prefill_tok_s",
        "prefill_source",
        "in_flight",
        "in_flight_source",
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
    assert columns.get("in_flight_source") == "TEXT"
