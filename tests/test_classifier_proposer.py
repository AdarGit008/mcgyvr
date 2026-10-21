"""The typed proposer: relevance decided by single-token choices, not prose.

The Jev-class counterpart to :func:`~mcgyvr.delegate.proposer_for`: where that
proposer asks the orchestrator role for a free-text JSON reply and parses it
back into proposals, :class:`~mcgyvr.delegate.ClassifierProposer` asks the jev
role one typed ``Choice`` per field — ``task_type``, ``target``, ``symbol``,
``interface``, ``deps``, ``allow`` — in dependency order, and builds one
proposal from the answers. The model decides relevance — which kind of work,
which file, which symbol — and the repository decides fact, in ``decompose`` as
always.

The transport is stubbed throughout: the properties under test are the shape of
the questions asked, the mapping from answers to a proposal, and the refusal on
low confidence. None of them need a live server.
"""

from __future__ import annotations

import subprocess
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import TaskType
from mcgyvr.config import parse
from mcgyvr.decision import Answer, Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import (
    MIN_CONFIDENCE,
    ClassifierProposer,
    classifier_proposer_for,
)
from mcgyvr.local_pool import Protocol, source_map
from mcgyvr.orchestrator.candidates import collapse, enumerate_candidates
from mcgyvr.orchestrator.decompose import Evidence, Proposal
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.runner import Completion, StopReason
from tests import ungated

#: A keyless local ladder with no orchestrator block.
LADDER = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
    width: 2
ladder:
- local_qwen-7b
"""

#: The same install with the orchestrator role bound to a usable source.
ORCHESTRATOR = (
    LADDER
    + """
orchestrator:
  unit: local_qwen-7b
  model: qwen2.5-coder:14b
"""
)


def cfg(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    """A small repository with a target and a symbol worth proposing work on."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    (root / "pagination.py").write_text(
        "def paginate(items, size=10):\n    return items[:size]\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def evidence_for(
    repo: Index, prompt: str, vocabulary: tuple[TaskType, ...]
) -> Evidence:
    """The deterministic pass ``decompose`` would hand a proposer."""
    resolution = resolve(repo, prompt)
    return Evidence(
        prompt=prompt,
        index=repo,
        resolution=resolution,
        exploration=explore(repo, resolution),
        vocabulary=vocabulary,
    )


def completion(text: str) -> Completion:
    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:14b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=4096,
        latency_s=0.0,
    )


def decision_of(answers: Mapping[str, Answer]) -> Decision:
    return Decision(answers=answers)


def answer(choice: str, confidence: float) -> ChoiceAnswer:
    return ChoiceAnswer(
        choice=choice,
        probabilities={choice: 1.0},
        confidence=confidence,
    )


def _rank0(seen: list[tuple[Any, Mapping[str, Question]]]) -> Any:
    """A classify fake that answers each field's single question with its rank-0."""

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        seen.append((state, questions))
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        return decision_of({field: answer(next(iter(question.options)), 0.9)})

    return classify


#: The ungated example kind (tests/ungated.py). Not ``code``: a
#: ``code`` contract states its reply cap, which no choice can say, so the
#: classifier hands that work to the prose proposer
#: (test_the_classifier_leaves_capped_work_to_the_prose_proposer.py).
AGENT = ungated.ungated()
pytestmark = pytest.mark.usefixtures("ungated_catalog")


# --- the typed-decision path ----------------------------------------------


def test_a_classifier_proposer_asks_choices_and_builds_a_proposal(
    repo: Index,
) -> None:
    """One Choice per field, keyed by candidate id, folds into one proposal."""
    seen: list[tuple[Any, Mapping[str, Question]]] = []
    propose = ClassifierProposer(classify=_rank0(seen))
    proposals = propose(evidence_for(repo, "document listing", (AGENT,)))

    (proposal,) = proposals
    assert proposal == Proposal(
        task_type="agent",
        task=(
            "Answer a prompt in plain prose from the repository files the "
            "contract names as its sources, ungated: listing in listing.py."
        ),
        target="listing.py",
        stop_conditions=(
            "agent on listing in listing.py would require deciding "
            "something the contract does not state — report BLOCKED rather "
            "than guess",
        ),
    )

    assert len(seen) == 6
    task_type = seen[0][1]["task_type"]
    assert isinstance(task_type, Choice)
    assert task_type.options == {"task_type:0": AGENT.doc}

    target = seen[1][1]["target"]
    assert isinstance(target, Choice)
    assert target.options == {"target:0": "listing.py"}

    symbol = seen[2][1]["symbol"]
    assert isinstance(symbol, Choice)
    assert list(symbol.options) == ["symbol:0", "symbol:1"]
    assert symbol.options["symbol:1"] != "", "a no-symbol option must be offered"


def test_a_classifier_proposer_offers_the_catalog_vocabulary_and_candidates(
    repo: Index,
) -> None:
    """The model is shown only the servable types and the ranked shortlist."""
    seen: list[tuple[Any, Mapping[str, Question]]] = []
    propose = ClassifierProposer(classify=_rank0(seen))
    proposals = propose(evidence_for(repo, "document the pagination helper", (AGENT,)))

    assert len(proposals) == 1
    assert len(seen) == 6
    state, _ = seen[0]
    assert state["request"] == "document the pagination helper"
    assert state["task_types"] == ["agent"]
    assert "listing.py" in state["candidates"] or "pagination.py" in state["candidates"]


# --- the low-confidence refusal -------------------------------------------


def test_a_classifier_proposer_refuses_when_the_task_type_is_uncertain(
    repo: Index,
) -> None:
    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        confidence = MIN_CONFIDENCE - 0.1 if field == "task_type" else 0.9
        return decision_of({field: answer(next(iter(question.options)), confidence)})

    propose = ClassifierProposer(classify=classify)
    assert propose(evidence_for(repo, "document listing", (AGENT,))) == ()


def test_a_classifier_proposer_refuses_when_the_target_is_uncertain(
    repo: Index,
) -> None:
    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        confidence = MIN_CONFIDENCE - 0.1 if field == "target" else 0.9
        return decision_of({field: answer(next(iter(question.options)), confidence)})

    propose = ClassifierProposer(classify=classify)
    assert propose(evidence_for(repo, "document listing", (AGENT,))) == ()


def test_a_classifier_proposer_degrades_when_the_symbol_is_uncertain(
    repo: Index,
) -> None:
    """A low-confidence symbol leaves rank-0 — the first definition — not a refusal."""
    evidence = evidence_for(repo, "document listing", (AGENT,))

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        confidence = MIN_CONFIDENCE - 0.1 if field == "symbol" else 0.9
        return decision_of({field: answer(next(iter(question.options)), confidence)})

    propose = ClassifierProposer(classify=classify)
    assert propose(evidence) == (collapse(enumerate_candidates(evidence)),)


def test_a_classifier_proposer_refuses_when_nothing_matched(
    repo: Index,
) -> None:
    """No candidate and no vocabulary mean there is nothing to choose among."""
    called: list[bool] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        called.append(True)
        return decision_of({})

    propose = ClassifierProposer(classify=classify)
    resolution = resolve(repo, "nothing matches this query at all")
    evidence = Evidence(
        prompt="nothing matches this query at all",
        index=repo,
        resolution=resolution,
        exploration=explore(repo, resolution),
        vocabulary=(),
    )
    assert propose(evidence) == ()
    assert called == [], "the model must not be asked when there is no choice to make"


# --- the factory, through the below-seam bridge ----------------------------


def test_classifier_proposer_for_degrades_without_a_jev_unit(
    repo: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without jev the factory returns the rank-0 proposer and asks nothing."""
    import mcgyvr.decision as decision

    pool = source_map(parse(cfg(ORCHESTRATOR)))

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no typed question goes to the orchestrator without jev")

    monkeypatch.setattr(decision, "_post_json", fail)
    propose = classifier_proposer_for(pool)
    assert propose is not None
    evidence = evidence_for(repo, "document listing", (AGENT,))
    assert propose(evidence) == (collapse(enumerate_candidates(evidence)),)
