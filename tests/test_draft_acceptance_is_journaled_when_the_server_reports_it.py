"""Draft acceptance is journaled when the server reports it.

The MTP lever's effect is ``timings.draft_n_accepted / draft_n`` on each
completion — how the evidence read acceptance
(``records/evidence/2026-08-28-mtp-ornith/drivers/mtpsweep2.py``). llama-server
puts the two counts on ``timings`` only when it drafted, so a dispatch records
``draft_n`` and ``draft_n_accepted`` on its attempt row when they are reported
and leaves both keys absent otherwise — never zeroed, the rule every token
count in the journal already keeps. A reported zero is a count, and is kept.
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
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.runner import Completion, Request, StopReason, runner_for
from mcgyvr.telemetry import fold, observe

REPO = Path(__file__).resolve().parent.parent
ASK = Request(prompt="write a function", max_output_tokens=256)

TIMINGS = {
    "prompt_n": 12,
    "prompt_ms": 40.0,
    "prompt_per_second": 300.0,
    "predicted_n": 475,
    "predicted_ms": 5200.0,
    "predicted_per_second": 91.2,
}


def endpoint() -> Endpoint:
    return Endpoint(
        source="unit",
        base_url="http://localhost:8080",
        protocol=Protocol.OPENAI,
        max_parallel=2,
        credential_env=None,
        engine="llama.cpp",
    )


def answer(timings: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "x = 1\n"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 475},
        "timings": timings,
    }


def stub(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        return document

    def no_pages(url: str, timeout: float) -> str | None:
        return None

    monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)
    monkeypatch.setattr(runner_module, "_get_text", no_pages, raising=True)


def test_the_counts_are_read_off_the_servers_timings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub(monkeypatch, answer({**TIMINGS, "draft_n": 526, "draft_n_accepted": 474}))
    done = runner_for(endpoint()).generate("Ornith-1.0-35B_Q2_K-AllGPU", ASK)
    assert done.draft_n == 526
    assert done.draft_n_accepted == 474
    assert done.decode_tok_s == 91.2


def test_a_server_that_drafted_nothing_reports_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub(monkeypatch, answer(TIMINGS))
    done = runner_for(endpoint()).generate("Ornith-1.0-35B_Q2_K-AllGPU", ASK)
    assert done.draft_n is None
    assert done.draft_n_accepted is None


def test_a_reported_zero_is_a_count_and_not_an_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub(monkeypatch, answer({**TIMINGS, "draft_n": 4, "draft_n_accepted": 0}))
    done = runner_for(endpoint()).generate("Ornith-1.0-35B_Q2_K-AllGPU", ASK)
    assert (done.draft_n, done.draft_n_accepted) == (4, 0)


def _completion(**extra: Any) -> Completion:
    return Completion(
        text="x = 1\n",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="Ornith-1.0-35B_Q2_K-AllGPU",
        source="unit",
        protocol=Protocol.OPENAI,
        max_output_tokens=256,
        latency_s=5.2,
        **extra,
    )


def _row(sink: Path, completion: Completion) -> dict[str, Any]:
    observe(
        lambda: completion,
        path=sink,
        attempt_id="agent-a:doc:srv2_ornith:1",
        orchestrator="agent-a",
        rung="srv2_ornith",
    )
    (row,) = fold(path=sink)
    return dict(row)


def test_the_row_carries_both_counts_when_reported(tmp_path: Path) -> None:
    row = _row(
        tmp_path / "agent-a.jsonl", _completion(draft_n=526, draft_n_accepted=474)
    )
    assert row["draft_n"] == 526
    assert row["draft_n_accepted"] == 474


def test_the_row_has_no_key_at_all_when_nothing_was_drafted(tmp_path: Path) -> None:
    row = _row(tmp_path / "agent-a.jsonl", _completion())
    assert "draft_n" not in row
    assert "draft_n_accepted" not in row


def test_a_reported_zero_reaches_the_row_as_zero(tmp_path: Path) -> None:
    row = _row(tmp_path / "agent-a.jsonl", _completion(draft_n=4, draft_n_accepted=0))
    assert row["draft_n_accepted"] == 0
    assert json.dumps(row["draft_n_accepted"]) == "0"


def _index() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "live_index_for_draft_counts", REPO / "tools" / "live" / "index.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_journal_index_has_a_column_for_each_count() -> None:
    columns = dict(_index().COLUMNS)
    assert columns.get("draft_n") == "INTEGER"
    assert columns.get("draft_n_accepted") == "INTEGER"
