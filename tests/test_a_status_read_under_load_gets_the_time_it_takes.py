"""A status page that answers slowly under load is still read.

A status page can answer slowly while a generation is starting. A tight ceiling
on the before/after reads drops both readings for exactly the dispatch that
starts beside other work, and its row files ``in_flight``,
``in_flight_source``, ``prefill_tok_s`` and ``prefill_source`` absent while the
row beside it has them. The reads get ``mcgyvr.runner.STATUS_TIMEOUT_S``.

The ceiling is a ceiling, not a measured bound: a page slower than it is still
dropped, and the reads sit outside the request's ``latency_s``, so a slow
status page never slows the decode figure.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.runner import Request, runner_for

ASK = Request(prompt="write a function", max_output_tokens=256)
LABELS = '{engine="0",model_name="/root/.cache/huggingface/hub/m"}'


def endpoint(engine: str) -> Endpoint:
    return Endpoint(
        source="unit",
        base_url="http://localhost:8080",
        protocol=Protocol.OPENAI,
        max_parallel=2,
        credential_env=None,
        engine=engine,
    )


def metrics(running: int = 0) -> str:
    return (
        f"vllm:time_to_first_token_seconds_sum{LABELS} 1.0\n"
        f"vllm:time_to_first_token_seconds_count{LABELS} 10\n"
        f"vllm:num_requests_running{LABELS} {float(running)}\n"
        f"vllm:num_requests_waiting{LABELS} 0.0\n"
    )


def slots(processing: int = 0) -> str:
    return json.dumps([{"id": i, "is_processing": i < processing} for i in range(2)])


ANSWER: dict[str, Any] = {
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "x = 1\n"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1206, "completion_tokens": 503},
}


class SlowUnit:
    """A unit whose status pages take ``delay_s`` and whose reply takes 4.0 s.

    One virtual clock stands in for ``time.monotonic``: a status read advances
    it by the page's delay and answers only if that delay fits the timeout the
    runner passed — what ``urllib`` does with a real slow page — and the POST
    advances it by the reply's 4.0 s.
    """

    REPLY_S = 4.0

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, page: str, delay_s: float
    ) -> None:
        self.now = 100.0
        self.timeouts: list[float] = []

        def fake_get(url: str, timeout: float) -> str | None:
            self.timeouts.append(timeout)
            if delay_s > timeout:
                self.now += timeout
                return None
            self.now += delay_s
            return page

        def fake_post(
            url: str, payload: object, headers: object, timeout: float
        ) -> dict[str, Any]:
            self.now += self.REPLY_S
            return ANSWER

        monkeypatch.setattr(runner_module, "_get_text", fake_get, raising=True)
        monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)
        monkeypatch.setattr("mcgyvr.runner.time.monotonic", lambda: self.now)


@pytest.mark.parametrize(
    ("engine", "page", "source"),
    [
        ("vllm", metrics(), "vllm_metrics"),
        ("llama.cpp", slots(), "slots"),
    ],
    ids=["vllm", "llama.cpp"],
)
@pytest.mark.parametrize("delay_s", [2.666, 3.0, 4.31], ids=["2.666s", "3.0s", "4.31s"])
def test_a_status_page_slower_than_two_seconds_still_yields_in_flight(
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    page: str,
    source: str,
    delay_s: float,
) -> None:
    SlowUnit(monkeypatch, page, delay_s)

    done = runner_for(endpoint(engine)).generate("m", ASK)

    assert (done.in_flight, done.in_flight_source) == (1, source)


def test_a_status_page_slower_than_the_ceiling_is_still_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    SlowUnit(monkeypatch, metrics(), 600.0)

    done = runner_for(endpoint("vllm")).generate("m", ASK)

    assert (done.in_flight, done.in_flight_source) == (None, None)
    assert (done.prefill_tok_s, done.prefill_source) == (None, None)


def test_slow_status_reads_are_not_counted_in_latency_or_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    SlowUnit(monkeypatch, metrics(), 1.5)

    done = runner_for(endpoint("vllm")).generate("m", ASK)

    assert done.latency_s == pytest.approx(SlowUnit.REPLY_S)
    assert done.decode_tok_s == pytest.approx(503 / SlowUnit.REPLY_S)
