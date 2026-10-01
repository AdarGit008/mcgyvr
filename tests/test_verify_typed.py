"""The typed verdict path in :mod:`mcgyvr.verify`.

The free-text ``read_verdict`` anchors the first token of a prose reply; the
typed path instead asks a single :class:`~mcgyvr.decision.Noul` and reads a
:class:`~mcgyvr.decision.BoolAnswer` from next-token probabilities. Both paths
sit behind the same two hard rules — the identity check runs first, and a
reviewer-side failure is ``UNUSABLE`` — so these tests pin that the typed path
is a drop-in for the free-text one and never the other way around.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from mcgyvr.catalog import Family
from mcgyvr.contract import loads
from mcgyvr.decision import BoolAnswer, Decision
from mcgyvr.escalate import Opinion
from mcgyvr.gate import GateResult
from mcgyvr.pool import Endpoint, Protocol, RoleBinding, SourceMap
from mcgyvr.verify import decider_for, read_typed_verdict, verdict_state, verify

LOCAL = Endpoint(
    source="llama-server",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=2,
    credential_env=None,
)

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

MODEL_FAMILY = Family(name="local", rank=1, doc="a model on the operator's own machine")

CHANGE = "--- a/src/pkg/fetch.py\n+++ b/src/pkg/fetch.py\n@@\n+    pass\n"


@pytest.fixture
def contract() -> Any:
    return loads(CONTRACT)


def _decide(value: bool) -> Callable[[Any], Decision]:
    """A typed-verdict seam that always answers ``value``."""

    def decide(state: Any) -> Decision:
        return Decision(
            answers={
                "verdict": BoolAnswer(value=value, probability_true=0.9, confidence=0.8)
            }
        )

    return decide


def _never_asked(prompt: str) -> str:
    raise AssertionError("the free-text reviewer must not be asked")


def test_a_typed_approve_is_agreed_and_never_asks_prose(contract: Any) -> None:
    review = verify(
        contract,
        family=MODEL_FAMILY,
        gate=GateResult(),
        change=CHANGE,
        builder="qwen2.5-coder:7b",
        reviewer="qwen2.5-coder:32b",
        ask=_never_asked,
        decide=_decide(True),
    )
    assert review.opinion is Opinion.AGREED


def test_a_typed_refusal_is_refused(contract: Any) -> None:
    review = verify(
        contract,
        family=MODEL_FAMILY,
        gate=GateResult(),
        change=CHANGE,
        builder="qwen2.5-coder:7b",
        reviewer="qwen2.5-coder:32b",
        ask=_never_asked,
        decide=_decide(False),
    )
    assert review.opinion is Opinion.REFUSED


def test_the_identity_check_runs_before_the_typed_spend(contract: Any) -> None:
    asked: list[Any] = []

    def decide(state: Any) -> Decision:
        asked.append(state)
        return _decide(True)(state)

    review = verify(
        contract,
        family=MODEL_FAMILY,
        gate=GateResult(),
        change=CHANGE,
        builder="qwen2.5-coder:7b",
        reviewer="qwen2.5-coder:7b",
        ask=_never_asked,
        decide=decide,
    )
    assert review.opinion is Opinion.UNUSABLE
    assert asked == [], "a self-review was spent before the refusal"


def test_a_decider_that_raises_is_unusable_not_charged_to_the_builder(
    contract: Any,
) -> None:
    def decide(state: Any) -> Decision:
        raise RuntimeError("unreachable")

    review = verify(
        contract,
        family=MODEL_FAMILY,
        gate=GateResult(),
        change=CHANGE,
        builder="qwen2.5-coder:7b",
        reviewer="qwen2.5-coder:32b",
        ask=_never_asked,
        decide=decide,
    )
    assert review.opinion is Opinion.UNUSABLE
    assert "unreachable" in review.detail


def test_the_free_text_path_remains_when_no_decider_is_bound(contract: Any) -> None:
    review = verify(
        contract,
        family=MODEL_FAMILY,
        gate=GateResult(),
        change=CHANGE,
        builder="qwen2.5-coder:7b",
        reviewer="qwen2.5-coder:32b",
        ask=lambda prompt: "APPROVE — the retry policy is stated.",
        decide=None,
    )
    assert review.opinion is Opinion.AGREED


def test_a_typed_verdict_with_no_readable_answer_is_unusable() -> None:
    review = read_typed_verdict(Decision(answers={}))
    assert review.opinion is Opinion.UNUSABLE


def test_verdict_state_carries_the_contract_and_the_change(contract: Any) -> None:
    state = verdict_state(contract, GateResult(), CHANGE)
    assert state["task"] == "Add retry with backoff to the fetch helper."
    assert state["change"] == CHANGE
    assert state["target"] == "src/pkg/fetch.py"


def test_decider_for_returns_none_without_a_verifier_role() -> None:
    pool = SourceMap(rungs=(), skipped=(), endpoints={}, roles={}, role_skips={})
    assert decider_for(pool) is None


def test_decider_for_reads_a_typed_verdict_through_classify_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mcgyvr.verify as verify_module

    pool = SourceMap(
        rungs=(),
        skipped=(),
        endpoints={},
        roles={
            "verifier": RoleBinding(
                role="verifier", model="qwen2.5-coder:32b", endpoint=LOCAL
            )
        },
        role_skips={},
    )
    sent: list[str] = []

    def fake_classify_role(
        source_map: SourceMap,
        role: str,
        state: Any,
        questions: Any,
        *,
        timeout_s: float,
    ) -> Decision:
        sent.append(role)
        return Decision(
            answers={
                "verdict": BoolAnswer(value=True, probability_true=0.9, confidence=0.8)
            }
        )

    monkeypatch.setattr(verify_module, "classify_role", fake_classify_role)
    decide = decider_for(pool)
    assert decide is not None
    review = read_typed_verdict(decide({"change": CHANGE}))

    assert review.opinion is Opinion.AGREED
    assert sent == ["verifier"]
