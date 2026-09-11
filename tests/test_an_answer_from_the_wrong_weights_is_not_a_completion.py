"""A dispatch names a model; a backend answers with whichever weights it has
actually loaded. Until now those two were never compared, so a rung pointed at a
model that is not resident was answered from the wrong checkpoint and the answer
was *recorded as valid* — the hole `cli._climb` carries as a comment.

The close is the one that costs no network: chat-completions already reports the
model it answered with, `Runner.generate` already receives the one that was
asked for, and `availability` already knows how to read a served id against a
declared name. Comparing them turns a wrong-weights answer into a failed
attempt, which is what it always was.

These tests hold the check to four things: it fires on a real mismatch, it does
not fire on llama.cpp's path-shaped id for the model that *was* asked for, it
does not fire when the backend reports nothing, and it fails as a
:class:`RunnerError` so every existing caller already treats it as a dispatch
that did not produce a completion.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.runner import Request, RunnerError, WrongWeightsError, runner_for

SRV1 = Endpoint(
    source="llama-server",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=2,
    credential_env=None,
)

ASK = Request(prompt="p", max_output_tokens=64)


def answer(model: str | None) -> dict[str, Any]:
    """A chat-completions answer reporting ``model``, or reporting none."""
    document: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    if model is not None:
        document["model"] = model
    return document


def stub_post(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    """Replace the transport with one that returns ``document``."""

    def fake_post(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        return document

    monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)


def test_an_answer_from_another_model_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hole itself. A rung asks for the 35B, the rig has the 3B resident,
    and the 3B answers. That answer must not become a completion."""
    stub_post(monkeypatch, answer("Qwen2.5-Coder-3B-Instruct"))
    with pytest.raises(WrongWeightsError) as caught:
        runner_for(SRV1).generate("Qwen3.6-35B-A3B-UD-IQ3_XXS", ASK)

    said = str(caught.value)
    assert "Qwen3.6-35B-A3B-UD-IQ3_XXS" in said, "the model that was asked for"
    assert "Qwen2.5-Coder-3B-Instruct" in said, "the model that answered"
    assert "llama-server" in said, "the source it happened on"


def test_the_refusal_is_a_dispatch_that_did_not_produce_a_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every caller of `generate` already handles `RunnerError` as an attempt
    that failed. A new sibling of it needs no call site to change, and a class
    outside that tree would escape all of them."""
    stub_post(monkeypatch, answer("something-else"))
    with pytest.raises(RunnerError):
        runner_for(SRV1).generate("declared", ASK)


def test_llama_cpps_path_for_the_model_asked_for_is_not_a_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """llama.cpp reports the path it was handed, not a name — the two
    vocabularies `availability` exists to reconcile. Reading them as different
    models would refuse every dispatch on srv1's ceiling rung, which is the
    failure this check must not trade for the one it closes."""
    stub_post(
        monkeypatch,
        answer("/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS-00001-of-00002.gguf"),
    )
    done = runner_for(SRV1).generate("Qwen3.6-35B-A3B-UD-IQ3_XXS", ASK)
    assert done.text == "ok"
    assert done.model == "Qwen3.6-35B-A3B-UD-IQ3_XXS", "what was asked for"
    assert done.served_model == (
        "/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS-00001-of-00002.gguf"
    ), "what the backend said it answered with, kept as it said it"


def test_a_backend_that_reports_no_model_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silence is not a mismatch. A server that names nothing cannot be checked,
    and refusing it would make an optional key a requirement — the completion
    says it does not know rather than claiming agreement."""
    stub_post(monkeypatch, answer(None))
    done = runner_for(SRV1).generate("declared", ASK)
    assert done.served_model is None
    assert done.text == "ok"
