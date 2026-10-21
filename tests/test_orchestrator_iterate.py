"""W6 — the self-contained retry loop and its approver gate.

`iterate` drives one classifier proposal through `emit_one` and, when it is
refused, re-asks only the refused field (carrying the fields already decided
and the rejected candidate out of the next question) until an approver stops it
or the attempt budget runs out. The loop is inert unless an `approve` callable
is wired in.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import MIN_CONFIDENCE, ClassifierProposer
from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal, Refusal
from mcgyvr.orchestrator.fields import FIELD_ORDER
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.iterate import MAX_REFUSAL_RETRIES, iterate

AGENT = catalog().require("agent")


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    """A small repository with one indexed target and one symbol."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def agent_proposal(target: str) -> Proposal:
    """A servable proposal against `target`, for the scripted classifier."""
    return Proposal(
        task_type="agent",
        task=f"document {target}",
        target=target,
    )


class ScriptedClassifier:
    """A classifier-like fake whose `.propose` returns the next scripted result."""

    def __init__(self, *results: Proposal | Refusal):
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def propose(
        self,
        evidence: Evidence,
        *,
        decided: Mapping[str, Any] | None = None,
        constraints: Mapping[str, str] | None = None,
        rejected: Mapping[str, Any] | None = None,
    ) -> Proposal | Refusal:
        self.calls.append(
            {"decided": decided, "constraints": constraints, "rejected": rejected}
        )
        if not self.results:
            raise AssertionError("scripted classifier ran out of results")
        return self.results.pop(0)


def approve_always() -> Callable[[Refusal, int], bool]:
    approvals: list[int] = []

    def approve(refusal: Refusal, attempt: int) -> bool:
        approvals.append(attempt)
        return True

    return approve


# --- the retry loop ---------------------------------------------------------


def test_retry_carries_the_rejected_target_and_a_constraint(repo: Index) -> None:
    """Attempt 2 is told to drop the refused target and to obey its directive."""
    classifier = ScriptedClassifier(
        agent_proposal("gone.py"),
        agent_proposal("listing.py"),
    )
    approve = approve_always()

    result = iterate(repo, "document listing", classify=classifier, approve=approve)

    assert result.refusals == ()
    assert [c.target for c in result.contracts] == ["listing.py"]

    assert len(classifier.calls) == 2
    second = classifier.calls[1]
    assert "gone.py" in second["rejected"]["target"]
    assert second["constraints"]["target"]


def test_a_second_pick_that_succeeds_emits_after_exactly_one_retry(
    repo: Index,
) -> None:
    """The loop retries once and returns the emitted contract."""
    classifier = ScriptedClassifier(
        agent_proposal("gone.py"),
        agent_proposal("listing.py"),
    )
    result = iterate(
        repo, "document listing", classify=classifier, approve=lambda r, a: True
    )

    assert len(classifier.calls) == 2
    assert len(result.contracts) == 1
    assert result.contracts[0].target == "listing.py"
    assert result.documents


def test_always_bad_stops_at_max_attempts(repo: Index) -> None:
    """The last refusal is returned once the attempt budget is spent."""
    classifier = ScriptedClassifier(
        agent_proposal("gone.py"),
        agent_proposal("gone.py"),
        agent_proposal("gone.py"),
        agent_proposal("listing.py"),  # never reached
    )
    approvals: list[int] = []

    def approve(refusal: Refusal, attempt: int) -> bool:
        approvals.append(attempt)
        return True

    result = iterate(repo, "x", classify=classifier, approve=approve, max_attempts=3)

    assert result.contracts == ()
    assert len(classifier.calls) == 3
    assert approvals == [1, 2]  # the final attempt is not gated again
    (refusal,) = result.refusals
    assert refusal.field == "target"


def test_approve_false_returns_the_refusal_without_reasking(repo: Index) -> None:
    """An approver that declines stops the loop before a second proposal."""
    classifier = ScriptedClassifier(
        agent_proposal("gone.py"),
        agent_proposal("listing.py"),  # never reached
    )

    def approve(refusal: Refusal, attempt: int) -> bool:
        return False

    result = iterate(repo, "x", classify=classifier, approve=approve)

    assert result.contracts == ()
    assert len(classifier.calls) == 1
    (refusal,) = result.refusals
    assert refusal.field == "target"


def test_a_decline_on_task_type_is_reasked_with_the_constraint(repo: Index) -> None:
    """A `Refusal`-typed proposal re-asks with no upstream decided fields."""
    classifier = ScriptedClassifier(
        Refusal(
            "request",
            "the task_type answer fell below the confidence floor",
            field="task_type",
            what_to_change="answer with a candidate above the confidence floor",
        ),
        agent_proposal("listing.py"),
    )
    result = iterate(
        repo, "document listing", classify=classifier, approve=lambda r, a: True
    )

    assert len(result.contracts) == 1
    assert len(classifier.calls) == 2
    second = classifier.calls[1]
    assert second["decided"] == {}
    assert second["rejected"] == {}
    assert second["constraints"]["task_type"] == (
        "answer with a candidate above the confidence floor"
    )


def test_max_attempts_default_is_the_retry_budget() -> None:
    """The shipped budget is three total attempts (two retries)."""
    assert MAX_REFUSAL_RETRIES == 3


def test_retry_drops_the_rejected_dependency(repo: Index) -> None:
    """A refused `deps` field re-asks with the single `DepRef` dropped, not the tuple.

    `Proposal.deps` is a tuple while `deps` candidates are single `DepRef`s;
    the loop must convert back to the plan representation when recording the
    rejected value, or the next question would carry the whole tuple.
    """
    dep = DepRef("nowhere.py", "nope")
    classifier = ScriptedClassifier(
        Proposal(task_type="agent", task="x", target="listing.py", deps=(dep,)),
        agent_proposal("listing.py"),
    )
    approve = approve_always()

    result = iterate(repo, "x", classify=classifier, approve=approve)

    assert result.refusals == ()
    assert len(classifier.calls) == 2
    second = classifier.calls[1]
    assert dep in second["rejected"]["deps"]
    assert second["constraints"]["deps"]


def test_a_non_askable_field_is_terminal(repo: Index) -> None:
    """A refusal naming a non-`FIELD_ORDER` field is returned without re-asking."""
    classifier = ScriptedClassifier(
        Proposal(task_type="code", task="x", target="listing.py"),
        agent_proposal("listing.py"),  # never reached
    )
    result = iterate(repo, "x", classify=classifier, approve=lambda r, a: True)

    assert result.contracts == ()
    assert len(classifier.calls) == 1
    (refusal,) = result.refusals
    # A `code` proposal without the fields the schema requires refuses with a
    # catch-all `field=""`, and a cap-less `code` with `max_output_tokens`;
    # either way the field is not re-askable, so the loop stops immediately.
    assert refusal.field not in FIELD_ORDER


# --- the loop through the real ClassifierProposer ---------------------------


def test_iterate_retries_a_below_floor_task_type_through_the_real_proposer(
    repo: Index,
) -> None:
    """Attempt 1 declines on `task_type`; attempt 2 answers above the floor."""
    agent_doc = AGENT.doc
    task_type_attempts: list[Choice] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        if field == "task_type":
            task_type_attempts.append(question)
            if len(task_type_attempts) == 1:
                confidence = MIN_CONFIDENCE - 0.1
                return Decision(
                    answers={
                        field: ChoiceAnswer(
                            choice=next(iter(question.options)),
                            probabilities={next(iter(question.options)): 1.0},
                            confidence=confidence,
                        )
                    }
                )
            agent_id = next(
                key for key, text in question.options.items() if text == agent_doc
            )
            return Decision(
                answers={
                    field: ChoiceAnswer(
                        choice=agent_id,
                        probabilities={agent_id: 1.0},
                        confidence=0.9,
                    )
                }
            )
        return Decision(
            answers={
                field: ChoiceAnswer(
                    choice=next(iter(question.options)),
                    probabilities={next(iter(question.options)): 1.0},
                    confidence=0.9,
                )
            }
        )

    proposer = ClassifierProposer(classify=classify)
    result = iterate(
        repo, "document listing", classify=proposer, approve=lambda r, a: True
    )

    assert result.refusals == ()
    (contract,) = result.contracts
    assert contract.task_type == "agent"
    assert contract.target == "listing.py"

    assert len(task_type_attempts) == 2
    assert "CONSTRAINTS" in task_type_attempts[1].instructions
    assert (
        "answer with a candidate above the confidence floor"
        in task_type_attempts[1].instructions
    )
