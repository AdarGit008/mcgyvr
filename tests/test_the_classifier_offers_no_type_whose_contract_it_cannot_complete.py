"""The classifier offers only the types whose contract it can complete.

No task type's contract forces commands: `code` derives evidence from the
contract's own fields and is judged on the gate alone when the proposal states
no commands, so the classifier — whose contribution is relevance, three
single-token choices — can complete it. This holds what remains true: the
classifier still refuses (returns nothing, so the caller falls back) when the
vocabulary leaves it nothing to choose, and its state names only what it
offers.
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


def test_code_is_offered_alongside_the_other_types(tmp_path: Path) -> None:
    """`code` needs no forced commands, so it is offered with the rest.

    Chosen, it is handed on rather than proposed: a `code` contract states its
    reply cap, which no choice can say, so the prose proposer writes it
    (owner, 2026-10-14).
    """
    seen, classify = _answering({"kind": "code", "symbol": ""})
    evidence = _evidence(tmp_path, _types("chat", "code"))
    proposals = ClassifierProposer(classify=classify)(evidence)
    kind = seen[0]["kind"]
    assert isinstance(kind, Choice)
    assert list(kind.options) == ["chat", "code"]
    assert proposals == ()


def test_an_empty_vocabulary_is_a_refusal_not_a_contract(tmp_path: Path) -> None:
    """No types on offer means nothing to ask; no token is spent."""
    seen, classify = _answering({})
    evidence = _evidence(tmp_path, ())
    assert ClassifierProposer(classify=classify)(evidence) == ()
    assert seen == []  # nothing to ask; no token spent


def test_the_state_names_only_what_is_offered(tmp_path: Path) -> None:
    captured: list[Any] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        captured.append(state)
        _, inner = _answering({"kind": "code", "symbol": ""})
        return inner(state, questions)

    evidence = _evidence(tmp_path, _types("code"))
    ClassifierProposer(classify=classify)(evidence)
    assert captured[0]["task_types"] == ["code"]
