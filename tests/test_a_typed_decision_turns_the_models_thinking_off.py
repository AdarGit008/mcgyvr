"""A typed decision turns the model's thinking off, whatever the unit's launch.

A decision is read from the first token's probabilities. A thinking model's
chat template opens every reply with its thinking tag — in the pilot
Qwen3-4B's first token was `<think>` with probability 1.0 — so no label can
appear in `top_logprobs` and every question is a `DecisionError`. With
thinking off, every question read. So :func:`mcgyvr.decision.classify` sends
`chat_template_kwargs: {"enable_thinking": false}` on every call, in the
request body, which both llama-server and vLLM read as template arguments,
and does not depend on how the unit was launched. The rung's own generations
(:mod:`mcgyvr.runner`) are untouched: a conversing model keeps its thinking.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import decision, runner
from mcgyvr.decision import Noul, classify
from mcgyvr.local_pool import Endpoint, Protocol


def _endpoint() -> Endpoint:
    return Endpoint(
        source="small",
        base_url="http://box.invalid:8081",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def _yes() -> dict[str, Any]:
    return {
        "choices": [
            {
                "logprobs": {
                    "content": [
                        {
                            "top_logprobs": [
                                {"token": "Yes", "logprob": -0.1},
                                {"token": "No", "logprob": -2.0},
                            ]
                        }
                    ]
                }
            }
        ]
    }


def test_every_decision_request_turns_thinking_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[dict[str, Any]] = []

    def wire(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append(payload)
        return _yes()

    monkeypatch.setattr(decision, "_post_json", wire)
    classify(
        _endpoint(),
        "small-model",
        {"x": 1},
        {"a": Noul("A?"), "b": Noul("B?")},
    )
    assert len(posted) == 2
    for payload in posted:
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert payload["max_tokens"] == 1
        assert payload["logprobs"] is True


def test_a_generation_keeps_the_models_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[dict[str, Any]] = []

    def wire(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append(payload)
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "hi"}}],
            "usage": {},
        }

    monkeypatch.setattr(runner, "_post_json", wire)
    runner.runner_for(_endpoint()).generate(
        "big-model", runner.Request(prompt="hello", max_output_tokens=8)
    )
    assert "chat_template_kwargs" not in posted[0]
