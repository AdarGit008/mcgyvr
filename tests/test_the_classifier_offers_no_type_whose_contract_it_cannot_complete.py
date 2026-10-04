"""The classifier offers no task type whose contract it cannot complete.

A `type_annotation`, `function_implementation` or `test_scaffold` contract must
carry `acceptance` commands and a `bug_fix` must carry `demonstration` ones;
the loader refuses one without. The classifier proposer writes neither — its
contribution is relevance, three single-token choices — so a contract of those
types from it is a contract the loader refuses, and in the pilot every one
was. It therefore offers the model only the types whose contract it can
complete, and refuses (returns nothing, so the caller falls back) when the
vocabulary leaves it none. The state it sends names only what it offers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from mcgyvr.catalog import TaskType
from mcgyvr.catalog import catalog as load_catalog
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import ClassifierProposer
from mcgyvr.orchestrator.decompose import Evidence
from mcgyvr.orchestrator.index import build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from tests.livejournal import git


def _types(*names: str) -> tuple[TaskType, ...]:
    known = load_catalog()
    return tuple(known.require(name) for name in names)


def _evidence(tmp_path: Path, vocabulary: tuple[TaskType, ...]) -> Evidence:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "listing.py").write_text("def paginate(items):\n    return items\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    index = build_index(root)
    resolution = resolve(index, "document paginate in listing.py")
    return Evidence(
        prompt="document paginate in listing.py",
        index=index,
        resolution=resolution,
        exploration=explore(index, resolution),
        vocabulary=vocabulary,
    )


Classify = Callable[[Any, Mapping[str, Question]], Decision]


def _answering(
    choice_by_name: Mapping[str, str],
) -> tuple[list[Mapping[str, Question]], Classify]:
    seen: list[Mapping[str, Question]] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        seen.append(questions)
        answers = {}
        for name, question in questions.items():
            assert isinstance(question, Choice)
            chosen = choice_by_name.get(name, next(iter(question.options)))
            answers[name] = ChoiceAnswer(
                choice=chosen,
                probabilities={key: 0.0 for key in question.options} | {chosen: 1.0},
                confidence=1.0,
            )
        return Decision(answers=answers)

    return seen, classify


def test_types_needing_commands_are_not_offered(tmp_path: Path) -> None:
    seen, classify = _answering({"kind": "docstring", "symbol": ""})
    evidence = _evidence(
        tmp_path,
        _types("docstring", "type_annotation", "function_implementation", "bug_fix"),
    )
    proposals = ClassifierProposer(classify=classify)(evidence)
    kind = seen[0]["kind"]
    assert isinstance(kind, Choice)
    assert list(kind.options) == ["docstring"]
    assert proposals[0].task_type == "docstring"


def test_a_vocabulary_of_only_such_types_is_a_refusal_not_a_contract(
    tmp_path: Path,
) -> None:
    seen, classify = _answering({})
    evidence = _evidence(tmp_path, _types("type_annotation", "bug_fix"))
    assert ClassifierProposer(classify=classify)(evidence) == ()
    assert seen == []  # nothing to ask; no token spent


def test_the_state_names_only_what_is_offered(tmp_path: Path) -> None:
    captured: list[Any] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        captured.append(state)
        _, inner = _answering({"kind": "format", "symbol": ""})
        return inner(state, questions)

    evidence = _evidence(tmp_path, _types("format", "test_scaffold"))
    ClassifierProposer(classify=classify)(evidence)
    assert captured[0]["task_types"] == ["format"]
