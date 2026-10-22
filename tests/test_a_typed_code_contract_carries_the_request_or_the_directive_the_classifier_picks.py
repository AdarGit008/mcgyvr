"""A typed ``code`` contract's task is the line the classifier picks.

The typed proposer used to state every task line itself, from the type's doc
and the subject, so a ``code`` contract it emitted dropped the request: a
worker asked to "split a list into groups of at most size elements" was handed
"Make a scoped edit to one named target: chunk in src/pkg/chunk.py." and
nothing else. `task` is now one of the typed questions. Its candidates are the
request as it was asked (rank 0) and that directive line, and whichever the
classifier picks goes into the contract unchanged.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import ClassifierProposer
from mcgyvr.orchestrator.candidates import directive
from mcgyvr.orchestrator.decompose import decompose
from mcgyvr.orchestrator.index import Index, build_index

REQUEST = (
    "Implement chunk in chunk.py: split a list into groups of at most size elements"
)


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
    (root / "chunk.py").write_text("def chunk(items, size):\n    return [items]\n")
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    return build_index(root)


def _sure(choice: str) -> ChoiceAnswer:
    return ChoiceAnswer(choice=choice, probabilities={choice: 1.0}, confidence=0.9)


def _choosing(asked: dict[str, Choice], *, task: str | None = None) -> Any:
    """Pick `code`, the task line reading `task` (else rank 0), rank 0 elsewhere."""

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        asked[field] = question
        wanted = {"task_type": catalog().require("code").doc, "task": task}.get(field)
        if wanted is None:
            return Decision(answers={field: _sure(next(iter(question.options)))})
        (key,) = (k for k, line in question.options.items() if line == wanted)
        return Decision(answers={field: _sure(key)})

    return classify


def test_the_task_question_offers_the_request_then_the_directive(repo: Index) -> None:
    asked: dict[str, Choice] = {}
    decompose(repo, REQUEST, propose=ClassifierProposer(classify=_choosing(asked)))

    code = catalog().require("code")
    assert list(asked["task"].options.values()) == [
        REQUEST,
        directive(code, "chunk.py", "chunk"),
    ]


def test_a_rank_0_pick_carries_the_request_into_the_contract(repo: Index) -> None:
    asked: dict[str, Choice] = {}
    result = decompose(
        repo, REQUEST, propose=ClassifierProposer(classify=_choosing(asked))
    )

    assert result.refusals == ()
    (contract,) = result.contracts
    assert contract.task_type == "code"
    assert contract.task == REQUEST


def test_a_directive_pick_goes_into_the_contract_unchanged(repo: Index) -> None:
    line = directive(catalog().require("code"), "chunk.py", "chunk")
    asked: dict[str, Choice] = {}
    result = decompose(
        repo, REQUEST, propose=ClassifierProposer(classify=_choosing(asked, task=line))
    )

    (contract,) = result.contracts
    assert contract.task == line
