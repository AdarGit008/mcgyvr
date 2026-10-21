"""The classifier proposer leaves work that must state a cap to the prose proposer.

A model-written ``code`` contract states ``limits.max_output_tokens``, and a
proposal without one is refused at
decomposition. The classifier decides relevance by single-token choices and has
no question that could state a cap, so with ``authoring: classifier`` every
``code`` proposal it made was refused, and the prose proposer behind it — which
does state one — was never asked. Now, when the model
chooses ``code``, the classifier returns nothing, and the prose proposer writes
it. ``code`` stays on offer, so a request for code is still recognised as one
rather than pushed onto a type that does not fit it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import ClassifierProposer, proposer_by_authoring
from mcgyvr.orchestrator.decompose import Evidence, Proposal, decompose
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    return build_index(root)


def _chooses_code(asked: list[Mapping[str, Question]]) -> Any:
    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        asked.append(questions)
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        if field == "task_type":
            return Decision(
                answers={
                    field: _sure(_option_for(question, catalog().require("code").doc))
                }
            )
        return Decision(answers={field: _sure(next(iter(question.options)))})

    return classify


def _option_for(question: Choice, text: str) -> str:
    """The candidate id whose option line is `text`."""
    for key, rendered in question.options.items():
        if rendered == text:
            return key
    raise AssertionError(f"{text!r} is not offered")


def _sure(choice: str) -> ChoiceAnswer:
    return ChoiceAnswer(choice=choice, probabilities={choice: 1.0}, confidence=0.9)


def test_code_is_the_type_that_must_state_a_cap() -> None:
    capped = {task.name for task in catalog().task_types if task.needs_output_cap}
    assert capped == {"code"}


def test_the_classifier_offers_code_and_returns_nothing_when_it_is_chosen(
    repo: Index,
) -> None:
    asked: list[Mapping[str, Question]] = []
    propose = ClassifierProposer(classify=_chooses_code(asked))
    evidence = Evidence(
        prompt="document listing",
        index=repo,
        resolution=resolve(repo, "document listing"),
        exploration=explore(repo, resolve(repo, "document listing")),
        vocabulary=catalog().task_types,
    )

    assert propose(evidence) == ()
    (questions,) = asked
    kind = questions["task_type"]
    assert isinstance(kind, Choice)
    assert catalog().require("code").doc in kind.options.values()


def test_a_classifier_request_for_code_reaches_the_prose_proposer(
    repo: Index,
) -> None:
    asked: list[Mapping[str, Question]] = []

    def prose(evidence: Evidence) -> Sequence[Proposal]:
        return (
            Proposal(
                task_type="code",
                task="Make a scoped edit to one named target: listing in listing.py.",
                target="listing.py",
                stop_conditions=("report BLOCKED rather than guess",),
                max_output_tokens=2048,
            ),
        )

    propose = proposer_by_authoring(
        "classifier",
        typed=ClassifierProposer(classify=_chooses_code(asked)),
        prose=prose,
    )
    assert propose is not None
    result = decompose(repo, "document listing", propose=propose)

    assert len(asked) == 1, "no symbol is asked for work the classifier hands on"
    assert result.refusals == ()
    (contract,) = result.contracts
    assert contract.task_type == "code"
    assert contract.limits.max_output_tokens == 2048
