"""The Jev-composed setup recommendation.

The one property this file pins: a model's answer selects among configs that
were assembled deterministically from measured facts and the declared schema,
so it can never invent a number. The transport is stubbed the way
``tests/test_decision.py`` stubs it — no test here reaches a server.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

import pytest

from mcgyvr import compose as compose_module
from mcgyvr.compose import (
    Recommendation,
    candidate_setups,
    decision_state,
    endpoint_for_backend,
    recommend,
)
from mcgyvr.config import load as load_config
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, DecisionError
from mcgyvr.detect import Detection
from mcgyvr.initialize import ApiUnit, _sources_for, initialize, parse_api_unit
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.propose import Proposal, propose
from tests.machine_shapes import detection, shape, with_server

LOCAL = Endpoint(
    source="llama-server",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=None,
)


def _machine() -> Detection:
    found = detection(
        with_server(
            shape("one-card"), kind="llama-server", models=("example-model-small",)
        )
    )
    return dataclasses.replace(found, cpu_count=8, ram_gb=64.0)


def _proposal(found: Detection) -> Proposal:
    return propose(sources=_sources_for(found))


def _api() -> ApiUnit:
    return parse_api_unit(
        "model=claude-opus-5,address=https://api.anthropic.com,"
        "api_key_env=ANTHROPIC_API_KEY"
    )


def numeric_leaves(value: Any) -> frozenset[int | float]:
    """Every int or float nested in ``value``, never a bool."""
    found: set[int | float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(node)
        elif isinstance(node, Mapping):
            for child in node.values():
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(value)
    return frozenset(found)


def stub_classify(monkeypatch: pytest.MonkeyPatch, choice: str) -> dict[str, Any]:
    """Replace ``compose.classify`` with one that always chooses ``choice``."""
    seen: dict[str, Any] = {}

    def fake_classify(
        endpoint: Endpoint,
        model: str,
        state: Any,
        questions: Mapping[str, Any],
        *,
        timeout_s: float,
    ) -> Decision:
        seen["endpoint"] = endpoint
        seen["model"] = model
        seen["state"] = state
        seen["questions"] = questions
        seen["timeout_s"] = timeout_s
        question = questions["setup"]
        assert isinstance(question, Choice)
        names = list(question.options)
        return Decision(
            answers={
                "setup": ChoiceAnswer(
                    choice=choice,
                    probabilities={
                        name: (1.0 if name == choice else 0.0) for name in names
                    },
                    confidence=1.0,
                )
            }
        )

    monkeypatch.setattr(compose_module, "classify", fake_classify)
    return seen


# --- the candidate family -------------------------------------------------


def test_candidates_are_assembled_deterministically() -> None:
    found = _machine()
    proposal = _proposal(found)
    api = (_api(),)
    first = candidate_setups(found, proposal, api_units=api)
    second = candidate_setups(found, proposal, api_units=api)
    assert [c.name for c in first] == ["own", "escalate", "hosted"]
    assert [c.name for c in second] == ["own", "escalate", "hosted"]
    assert [c.data for c in first] == [c.data for c in second]


def test_a_candidate_with_an_empty_ladder_is_not_offered() -> None:
    found = _machine()
    proposal = _proposal(found)
    # No hosted unit: only the listed rung exists, so only `own`.
    assert [c.name for c in candidate_setups(found, proposal)] == ["own"]

    bare = detection(shape("bare"))
    empty = propose(sources=_sources_for(bare))
    # No listed rung: only the hosted unit exists, so only `hosted`.
    assert [c.name for c in candidate_setups(bare, empty, api_units=(_api(),))] == [
        "hosted"
    ]
    # Nothing bindable: nothing to compose.
    assert candidate_setups(bare, empty) == ()


def test_recommend_refuses_when_nothing_is_bindable() -> None:
    bare = detection(shape("bare"))
    empty = propose(sources=_sources_for(bare))
    with pytest.raises(ValueError, match="nothing to compose"):
        recommend(LOCAL, "m", bare, empty, "cost")


def test_a_composition_changes_only_units_and_never_a_number() -> None:
    found = _machine()
    proposal = _proposal(found)
    candidates = candidate_setups(found, proposal, api_units=(_api(),))
    assert {c.name for c in candidates} == {"own", "escalate", "hosted"}
    # Every candidate carries exactly the numbers build() writes: width 1 (the
    # honest concurrency literal) and the schema defaults max_escalations 1,
    # task_timeout_s 900 and breadth.draws 1. The model's selection cannot
    # change any of them.
    assert {numeric_leaves(c.data) for c in candidates} == {frozenset({1, 900})}


def test_a_detected_backend_is_a_keyless_decision_endpoint() -> None:
    found = _machine()
    backend = found.backends[0]
    endpoint = endpoint_for_backend(backend)
    assert endpoint.base_url == backend.base_url
    assert endpoint.protocol is Protocol.OPENAI
    assert endpoint.credential_env is None


# --- the decision state ----------------------------------------------------


def test_the_decision_state_carries_measured_facts_and_the_profile() -> None:
    found = _machine()
    proposal = _proposal(found)
    state = decision_state(found, proposal, "throughput", api_units=(_api(),))
    assert state["profile"] == "throughput"
    assert state["measured"]["gpus"][0]["vram_gb"] == 14.0
    assert state["measured"]["cpu_count"] == 8
    assert state["measured"]["ram_gb"] == 64.0
    assert state["ladder"][0]["model"] == "example-model-small"
    assert state["hosted"][0]["name"] == "api_claude-opus-5"


# --- the selection ---------------------------------------------------------


def test_the_selected_setup_is_one_of_the_assembled_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = _machine()
    proposal = _proposal(found)
    candidates = candidate_setups(found, proposal, api_units=(_api(),))
    seen = stub_classify(monkeypatch, "hosted")
    result = recommend(
        LOCAL, "example-model-small", found, proposal, "quality", api_units=(_api(),)
    )
    chosen = next(c for c in candidates if c.name == "hosted")
    assert isinstance(result, Recommendation)
    assert result.selected.data == chosen.data
    assert result.decision is not None
    assert seen["endpoint"] is LOCAL
    assert seen["model"] == "example-model-small"


def test_a_single_candidate_needs_no_model_judgment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = _machine()
    proposal = _proposal(found)
    calls: list[Any] = []

    def fail_if_called(*args: Any, **kwargs: Any) -> Decision:
        calls.append((args, kwargs))
        raise AssertionError("no model should be consulted for one candidate")

    monkeypatch.setattr(compose_module, "classify", fail_if_called)
    result = recommend(LOCAL, "m", found, proposal, "cost")
    assert result.selected.name == "own"
    assert result.decision is None
    assert calls == []


def test_recommend_asks_one_choice_question_over_the_candidate_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = _machine()
    proposal = _proposal(found)
    seen = stub_classify(monkeypatch, "escalate")
    recommend(LOCAL, "m", found, proposal, "cost", api_units=(_api(),))
    question = seen["questions"]["setup"]
    assert isinstance(question, Choice)
    assert tuple(question.options) == ("own", "escalate", "hosted")


# --- the additive path through init ----------------------------------------


def test_initialize_writes_the_composed_ladder_when_a_profile_is_given(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _machine()
    stub_classify(monkeypatch, "hosted")
    result = initialize(
        tmp_path / "setup",
        detection=found,
        api_units=(_api(),),
        profile="quality",
        decision_endpoint=LOCAL,
        decision_model="example-model-small",
    )
    assert result.created and result.written
    config = load_config(tmp_path / "setup")
    assert list(config.ladder.names) == ["api_claude-opus-5"]
    assert any("quality" in decision for decision in result.decisions)


def test_a_profile_that_cannot_be_read_falls_back_and_says_so(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _machine()

    def boom(*args: Any, **kwargs: Any) -> Decision:
        raise DecisionError("no label appeared")

    monkeypatch.setattr(compose_module, "classify", boom)
    result = initialize(
        tmp_path / "setup",
        detection=found,
        api_units=(_api(),),
        profile="quality",
        decision_endpoint=LOCAL,
        decision_model="example-model-small",
    )
    assert result.created and result.written
    config = load_config(tmp_path / "setup")
    assert list(config.ladder.names) == [
        "local_example-model-small",
        "api_claude-opus-5",
    ]
    assert any("could not be read" in limit for limit in result.limits)


def test_a_profile_with_no_backend_falls_back_to_the_deterministic_ladder(
    tmp_path: Any,
) -> None:
    bare = detection(shape("bare"))
    result = initialize(
        tmp_path / "setup",
        detection=bare,
        api_units=(_api(),),
        profile="quality",
    )
    assert result.created and result.written
    config = load_config(tmp_path / "setup")
    assert list(config.ladder.names) == ["api_claude-opus-5"]
    assert any("run the Jev decision" in limit for limit in result.limits)
