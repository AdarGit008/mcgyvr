"""The decision primitive: typed questions answered by next-token probability.

The transport is stubbed for everything here — the properties under test are
the label scheme, the prompt shape, the probability reading and the request
body, none of which need a live server. What the wire actually carries is the
runner's own, already held by ``tests/test_runner.py``.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from mcgyvr import decision as decision_module
from mcgyvr.decision import (
    BoolAnswer,
    Choice,
    ChoiceAnswer,
    Decision,
    DecisionError,
    Noul,
    Question,
    Score,
    ScoreAnswer,
    answer_for,
    build_prompt,
    classify,
    confidence,
    labels_for,
    probabilities_from_logprobs,
)
from mcgyvr.local_pool import Endpoint, Protocol

LOCAL = Endpoint(
    source="llama-server",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=2,
    credential_env=None,
)


def entry(token: str, logprob: float) -> dict[str, Any]:
    return {"token": token, "logprob": logprob}


def logprobs_document(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "logprobs": {
                    "content": [{"token": entries[0]["token"], "top_logprobs": entries}]
                },
                "finish_reason": "length",
            }
        ]
    }


# --- labels ----------------------------------------------------------------


def test_a_noul_reads_under_yes_and_no() -> None:
    assert labels_for(Noul("is it done?")) == ("Yes", "No")


def test_a_choice_reads_under_letters_in_option_order() -> None:
    question = Choice(
        instructions="pick", options={"a": "first", "b": "second", "c": "third"}
    )
    assert labels_for(question) == ("A", "B", "C")


def test_a_score_reads_under_digits_up_to_its_levels() -> None:
    question = Score(instructions="rate", levels=("low", "mid", "high"))
    assert labels_for(question) == ("0", "1", "2")


def test_a_choice_of_more_than_sixty_two_options_is_refused() -> None:
    options = {f"o{i}": f"option {i}" for i in range(63)}
    with pytest.raises(ValueError):
        labels_for(Choice(instructions="pick", options=options))


def test_a_score_of_more_than_ten_levels_is_refused() -> None:
    levels = tuple(f"level {i}" for i in range(11))
    with pytest.raises(ValueError):
        labels_for(Score(instructions="rate", levels=levels))


# --- prompt ----------------------------------------------------------------


def test_a_prompt_carries_the_state_and_the_question() -> None:
    prompt = build_prompt({"file": "src/x.py"}, "kind", Noul("is it a docstring?"))
    assert '{"file": "src/x.py"}' in prompt
    assert "is it a docstring?" in prompt
    assert prompt.rstrip().endswith("No")


def test_a_choice_prompt_lists_each_option_under_its_label() -> None:
    prompt = build_prompt(
        "", "kind", Choice(instructions="which", options={"x": "one", "y": "two"})
    )
    assert "A: one" in prompt
    assert "B: two" in prompt


# --- probability reading ---------------------------------------------------


def test_probabilities_are_normalized_over_the_labels_that_appeared() -> None:
    top = [entry("Yes", -0.1), entry("No", -2.3)]
    yes, no = probabilities_from_logprobs(top, ("Yes", "No"))
    assert math.isclose(
        yes, math.exp(-0.1) / (math.exp(-0.1) + math.exp(-2.3)), rel_tol=1e-9
    )
    assert math.isclose(yes + no, 1.0, rel_tol=1e-9)


def test_a_label_the_server_omitted_reads_as_zero() -> None:
    top = [entry("A", 0.0)]
    probabilities = probabilities_from_logprobs(top, ("A", "B"))
    assert probabilities == (1.0, 0.0)


def test_no_label_present_is_unreadable_not_a_weak_answer() -> None:
    with pytest.raises(DecisionError):
        probabilities_from_logprobs([entry("z", 0.0)], ("Yes", "No"))


def test_confidence_is_peak_above_uniform() -> None:
    assert confidence((0.5, 0.5)) == 0.0
    assert confidence((1.0, 0.0)) == 1.0
    assert confidence((0.75,)) == 1.0


# --- answers ---------------------------------------------------------------


def test_a_choice_answer_names_the_peak_option() -> None:
    question = Choice(instructions="pick", options={"a": "first", "b": "second"})
    answer = answer_for(question, [entry("A", -0.1), entry("B", -0.9)])
    assert isinstance(answer, ChoiceAnswer)
    assert answer.choice == "a"
    assert answer.probabilities["b"] < answer.probabilities["a"]
    assert 0.0 < answer.confidence <= 1.0


def test_a_noul_answer_reads_the_yes_probability() -> None:
    answer = answer_for(Noul("done?"), [entry("Yes", -0.1), entry("No", -2.3)])
    assert isinstance(answer, BoolAnswer)
    assert answer.value is True
    assert math.isclose(
        answer.probability_true,
        math.exp(-0.1) / (math.exp(-0.1) + math.exp(-2.3)),
        rel_tol=1e-9,
    )


def test_a_score_answer_is_the_expected_level() -> None:
    question = Score(instructions="rate", levels=("low", "mid", "high"))
    answer = answer_for(question, [entry("0", 0.0), entry("1", 0.0), entry("2", 0.0)])
    assert isinstance(answer, ScoreAnswer)
    assert answer.level == 1.0
    assert set(answer.probabilities) == {"low", "mid", "high"}


# --- the network call ------------------------------------------------------


class Sent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []


def test_classify_sends_one_logprobs_request_per_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = Sent()

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.calls.append({"url": url, "payload": payload, "headers": headers})
        return logprobs_document([entry("Yes", -0.1), entry("No", -2.3)])

    monkeypatch.setattr(decision_module, "_post_json", fake_post)
    questions = {"done": Noul("is it done?"), "safe": Noul("is it safe?")}
    result = classify(LOCAL, "qwen", {"file": "src/x.py"}, questions)

    assert len(sent.calls) == 2
    assert isinstance(result, Decision)
    assert set(result.answers) == {"done", "safe"}
    payload = sent.calls[0]["payload"]
    assert payload["max_tokens"] == 1
    assert payload["logprobs"] is True
    assert payload["top_logprobs"] == 2
    assert sent.calls[0]["url"] == "http://localhost:8080/v1/chat/completions"
    assert sent.calls[0]["headers"] == {"Content-Type": "application/json"}


def test_a_keyed_endpoint_gets_a_bearer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = Sent()
    keyed = Endpoint(
        source="remote",
        base_url="https://api.example.com",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env="MCGYVR_TEST_KEY",
    )
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sekrit")

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.calls.append({"headers": headers})
        return logprobs_document([entry("Yes", 0.0), entry("No", -1.0)])

    monkeypatch.setattr(decision_module, "_post_json", fake_post)
    classify(keyed, "qwen", {}, {"ok": Noul("ok?")})

    assert sent.calls[0]["headers"]["Authorization"] == "Bearer sekrit"


def test_classify_reads_each_answer_from_its_own_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        # The first question is "kind", the second "done".
        if "kind" in payload["messages"][0]["content"]:
            return logprobs_document([entry("A", -0.1), entry("B", -2.0)])
        return logprobs_document([entry("Yes", -0.1), entry("No", -2.0)])

    monkeypatch.setattr(decision_module, "_post_json", fake_post)
    questions: dict[str, Question] = {
        "kind": Choice(instructions="kind?", options={"a": "docstring", "b": "rename"}),
        "done": Noul("done?"),
    }
    result = classify(LOCAL, "qwen", {"file": "src/x.py"}, questions)

    kind = result.answers["kind"]
    assert isinstance(kind, ChoiceAnswer) and kind.choice == "a"
    done = result.answers["done"]
    assert isinstance(done, BoolAnswer) and done.value is True
