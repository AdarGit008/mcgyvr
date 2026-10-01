"""The typed proposer: relevance decided by single-token choices, not prose.

The Jev-class counterpart to :func:`~mcgyvr.delegate.proposer_for`: where that
proposer asks the orchestrator role for a free-text JSON reply and parses it
back into proposals, :class:`~mcgyvr.delegate.ClassifierProposer` asks the role
for a handful of *typed* decisions through :func:`~mcgyvr.decision.classify`
and builds one proposal from the answers. The model decides relevance — which
kind of work, which file, which symbol — and the repository decides fact, in
``decompose`` as always.

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

from mcgyvr.catalog import TaskType, catalog
from mcgyvr.config import parse
from mcgyvr.decision import Answer, Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import (
    MIN_CONFIDENCE,
    ClassifierProposer,
    classifier_proposer_for,
    proposer_for_install,
)
from mcgyvr.orchestrator.decompose import Evidence, Proposal, decompose
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.pool import Protocol, source_map
from mcgyvr.runner import Completion, StopReason

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


DOCSTRING = catalog().require("docstring")


# --- the typed-decision path ----------------------------------------------


def test_a_classifier_proposer_asks_choices_and_builds_a_proposal(
    repo: Index,
) -> None:
    """The three questions are asked as Choices and the answers become a
    proposal naming the type, target and symbol the model chose."""
    seen: list[tuple[Any, Mapping[str, Question]]] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        seen.append((state, questions))
        if "symbol" in questions:
            return decision_of({"symbol": answer("listing", 0.9)})
        return decision_of(
            {
                "kind": answer("docstring", 0.9),
                "target": answer("listing.py", 0.9),
            }
        )

    propose = ClassifierProposer(classify=classify)
    proposals = propose(evidence_for(repo, "document listing", (DOCSTRING,)))

    (proposal,) = proposals
    assert proposal == Proposal(
        task_type="docstring",
        task="Write or correct a docstring for one named target: "
        "listing in listing.py.",
        target="listing.py",
        stop_conditions=(
            "docstring on listing in listing.py would require deciding "
            "something the contract does not state — report BLOCKED rather "
            "than guess",
        ),
    )

    assert len(seen) == 2
    (_, first), (_, second) = seen

    kind = first["kind"]
    assert isinstance(kind, Choice)
    assert kind.options == {"docstring": DOCSTRING.doc}

    target = first["target"]
    assert isinstance(target, Choice)
    assert "listing.py" in target.options

    symbol = second["symbol"]
    assert isinstance(symbol, Choice)
    assert symbol.options["listing"] != ""
    assert "" in symbol.options, "a no-symbol option must be offered"


def test_a_classifier_proposer_offers_the_catalog_vocabulary_and_candidates(
    repo: Index,
) -> None:
    """The model is shown only the servable types and the ranked shortlist."""
    seen: list[tuple[Any, Mapping[str, Question]]] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        seen.append((state, questions))
        if "symbol" in questions:
            return decision_of({"symbol": answer("", 0.9)})
        return decision_of(
            {
                "kind": answer("docstring", 0.9),
                "target": answer("listing.py", 0.9),
            }
        )

    propose = ClassifierProposer(classify=classify)
    proposals = propose(
        evidence_for(repo, "document the pagination helper", (DOCSTRING,))
    )

    assert len(proposals) == 1
    state, _ = seen[0]
    assert state["request"] == "document the pagination helper"
    assert state["task_types"] == ["docstring"]
    assert "listing.py" in state["candidates"] or "pagination.py" in state["candidates"]


# --- the low-confidence refusal -------------------------------------------


def test_a_classifier_proposer_refuses_when_the_kind_is_uncertain(
    repo: Index,
) -> None:
    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        return decision_of(
            {
                "kind": answer("docstring", MIN_CONFIDENCE - 0.1),
                "target": answer("listing.py", 0.9),
            }
        )

    propose = ClassifierProposer(classify=classify)
    assert propose(evidence_for(repo, "document listing", (DOCSTRING,))) == ()


def test_a_classifier_proposer_refuses_when_the_target_is_uncertain(
    repo: Index,
) -> None:
    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        return decision_of(
            {
                "kind": answer("docstring", 0.9),
                "target": answer("listing.py", MIN_CONFIDENCE - 0.1),
            }
        )

    propose = ClassifierProposer(classify=classify)
    assert propose(evidence_for(repo, "document listing", (DOCSTRING,))) == ()


def test_a_classifier_proposer_refuses_when_the_symbol_is_uncertain(
    repo: Index,
) -> None:
    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        if "symbol" in questions:
            return decision_of({"symbol": answer("listing", MIN_CONFIDENCE - 0.1)})
        return decision_of(
            {
                "kind": answer("docstring", 0.9),
                "target": answer("listing.py", 0.9),
            }
        )

    propose = ClassifierProposer(classify=classify)
    assert propose(evidence_for(repo, "document listing", (DOCSTRING,))) == ()


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


def test_classifier_proposer_for_returns_none_without_an_orchestrator_role() -> None:
    pool = source_map(parse(cfg(LADDER)))

    assert classifier_proposer_for(pool) is None


def test_proposer_for_install_selects_typed_only_when_opted_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``orchestrator.typed`` switches the factory; the default stays free-text."""
    import mcgyvr.delegate as delegate

    calls: list[str] = []

    def fake_classifier(source_map: Any, *, capacity: Any = None) -> Any:
        calls.append("classifier")
        return None

    def fake_proposer(source_map: Any, *, capacity: Any = None) -> Any:
        calls.append("proposer")
        return None

    monkeypatch.setattr(delegate, "classifier_proposer_for", fake_classifier)
    monkeypatch.setattr(delegate, "proposer_for", fake_proposer)

    pool = source_map(parse(cfg(LADDER)))
    proposer_for_install(pool, typed=True)
    proposer_for_install(pool, typed=False)
    assert calls == ["classifier", "proposer"]


def test_classifier_proposer_for_dispatches_through_classify_role(
    repo: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.delegate as delegate

    pool = source_map(parse(cfg(ORCHESTRATOR)))
    sent: list[tuple[Any, Mapping[str, Question]]] = []

    def fake_classify_role(
        source_map: Any,
        role: str,
        state: Any,
        questions: Mapping[str, Question],
        *,
        capacity: Any = None,
        timeout_s: Any = None,
    ) -> Decision:
        assert role == "orchestrator"
        sent.append((state, questions))
        if "symbol" in questions:
            return decision_of({"symbol": answer("listing", 0.9)})
        return decision_of(
            {
                "kind": answer("docstring", 0.9),
                "target": answer("listing.py", 0.9),
            }
        )

    monkeypatch.setattr(delegate, "classify_role", fake_classify_role)

    propose = classifier_proposer_for(pool)
    assert propose is not None
    (proposal,) = propose(evidence_for(repo, "document listing", (DOCSTRING,)))

    assert proposal.target == "listing.py"
    assert len(sent) == 2


def test_decompose_emits_a_validated_contract_through_the_classifier_proposer(
    repo: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.contract as contract_module
    import mcgyvr.delegate as delegate

    config = parse(cfg(ORCHESTRATOR))
    pool = source_map(config)

    def fake_classify_role(
        source_map: Any,
        role: str,
        state: Any,
        questions: Mapping[str, Question],
        *,
        capacity: Any = None,
        timeout_s: Any = None,
    ) -> Decision:
        if "symbol" in questions:
            return decision_of({"symbol": answer("listing", 0.9)})
        return decision_of(
            {
                "kind": answer("docstring", 0.9),
                "target": answer("listing.py", 0.9),
            }
        )

    monkeypatch.setattr(delegate, "classify_role", fake_classify_role)

    propose = classifier_proposer_for(pool)
    assert propose is not None
    result = decompose(repo, "document listing", propose=propose, config=config)

    assert result.refusals == ()
    (contract,) = result.contracts
    assert contract.task_type == "docstring"
    assert contract.target == "listing.py"
    assert contract_module.loads(result.documents[0]) == contract
