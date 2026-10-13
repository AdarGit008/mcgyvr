"""Reasoning tokens are recorded when the backend reports them.

A hosted reasoning model bills hidden reasoning against the same `max_tokens`
as the reply, and the journal recorded only input and output: an empty reply
at the cap could not be told from a model that wrote nothing (the e2e run of
2026-10-13). The count is read where OpenAI and the OpenAI-compatible reasoning
providers report it, ``usage.completion_tokens_details.reasoning_tokens``,
carried on the completion and written to the attempt row; absent when not
reported, never zeroed or estimated — the rule every count in the journal
keeps. The row also says how the cap it was sent under was reached.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import Completion, Request, StopReason, runner_for
from mcgyvr.telemetry import fold, observe

ASK = Request(prompt="write a parser", max_output_tokens=1024, cap_basis="pinned")


def endpoint() -> Endpoint:
    return Endpoint(
        source="deepseek",
        base_url="https://api.example.invalid",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def answer(content: str, finish: str, usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish,
            }
        ],
        "usage": usage,
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


def test_the_count_is_read_off_the_completion_token_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub(
        monkeypatch,
        answer(
            "x = 1\n",
            "stop",
            {
                "prompt_tokens": 40,
                "completion_tokens": 900,
                "completion_tokens_details": {"reasoning_tokens": 850},
            },
        ),
    )
    done = runner_for(endpoint()).generate("deepseek-reasoner", ASK)
    assert done.output_tokens == 900
    assert done.reasoning_tokens == 850
    assert done.cap_basis == "pinned"


def test_a_backend_that_reports_none_records_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub(
        monkeypatch,
        answer("x = 1\n", "stop", {"prompt_tokens": 40, "completion_tokens": 9}),
    )
    done = runner_for(endpoint()).generate("qwen", ASK)
    assert done.reasoning_tokens is None


def test_an_empty_reply_at_the_cap_is_noted_as_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run-2 shape: no content, every token of the cap spent, stop length."""
    stub(
        monkeypatch,
        answer(
            "",
            "length",
            {
                "prompt_tokens": 40,
                "completion_tokens": 1024,
                "completion_tokens_details": {"reasoning_tokens": 1024},
            },
        ),
    )
    done = runner_for(endpoint()).generate("deepseek-reasoner", ASK)
    assert done.truncated
    assert done.reasoning_tokens == 1024
    assert any("hidden reasoning" in note for note in done.notes), done.notes


def _completion(**extra: Any) -> Completion:
    return Completion(
        text="x = 1\n",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="deepseek-reasoner",
        source="deepseek",
        protocol=Protocol.OPENAI,
        max_output_tokens=25600,
        latency_s=5.2,
        output_tokens=900,
        **extra,
    )


def _row(sink: Path, completion: Completion) -> dict[str, Any]:
    observe(
        lambda: completion,
        path=sink,
        attempt_id="agent-a:impl:api_deepseek:1",
        orchestrator="agent-a",
        rung="api_deepseek",
    )
    (row,) = fold(path=sink)
    return dict(row)


def test_the_row_carries_the_count_and_the_caps_basis(tmp_path: Path) -> None:
    row = _row(
        tmp_path / "agent-a.jsonl",
        _completion(reasoning_tokens=850, cap_basis="auto: 1024 + 512 + 24576"),
    )
    assert row["reasoning_tokens"] == 850
    assert row["output_tokens"] == 900
    assert row["max_output_tokens"] == 25600
    assert row["cap_basis"] == "auto: 1024 + 512 + 24576"


def test_the_row_has_no_key_when_nothing_was_reported(tmp_path: Path) -> None:
    row = _row(tmp_path / "agent-a.jsonl", _completion())
    assert "reasoning_tokens" not in row
    assert "cap_basis" not in row
