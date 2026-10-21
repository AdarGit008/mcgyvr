"""The deterministic candidate-set layer: enumeration, collapse and choose.

The classifier proposer's output is byte-identical to the hand-built
``Proposal`` it replaced; the new machinery sits between ``Evidence`` and
``Proposal`` as a ranked candidate plan whose rank-0 values fold back into the
same proposal. This module tests that layer directly, plus the regression that
the classifier path did not change.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import TaskType, catalog
from mcgyvr.decision import Answer, Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import ClassifierProposer
from mcgyvr.orchestrator.baseline import BaselineObservation
from mcgyvr.orchestrator.candidates import (
    CandidateSet,
    FieldCandidate,
    Provenance,
    acceptance_candidates,
    candidate_targets,
    choose,
    collapse,
    completable,
    demonstration_candidates,
    deps_candidates,
    directive,
    enumerate_candidates,
    interface_candidates,
    kind_for,
    scope_candidates,
    sources_candidates,
    stop_condition,
    symbol_candidates,
    symbols_of,
    target_candidates,
    task_type_candidates,
    without,
)
from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import Exploration, TargetedRead, explore
from mcgyvr.orchestrator.resolve import Candidate, Resolution, Verdict, resolve
from tests import ungated

#: The example kind, as in test_classifier_proposer.py: not ``code``, because a
#: ``code`` contract states its reply cap, which no choice can say.
#: The ungated example kind (tests/ungated.py): not ``code``, whose contract
#: states a reply cap no choice can say.
AGENT = ungated.ungated()
pytestmark = pytest.mark.usefixtures("ungated_catalog")


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
    repo: Index,
    prompt: str,
    vocabulary: tuple[TaskType, ...],
    baseline: BaselineObservation | None = None,
) -> Evidence:
    """The deterministic pass ``decompose`` would hand a proposer."""
    resolution = resolve(repo, prompt)
    return Evidence(
        prompt=prompt,
        index=repo,
        resolution=resolution,
        exploration=explore(repo, resolution),
        vocabulary=vocabulary,
        baseline=baseline,
    )


def decision_of(answers: Mapping[str, Answer]) -> Decision:
    return Decision(answers=answers)


def answer(choice: str, confidence: float) -> ChoiceAnswer:
    return ChoiceAnswer(
        choice=choice,
        probabilities={choice: 1.0},
        confidence=confidence,
    )


def _synthetic_evidence(
    repo: Index,
    *,
    candidates: tuple[tuple[str, ...], ...],
    reads: tuple[str, ...],
) -> Evidence:
    """An evidence whose resolution and reads are controlled by the caller."""
    resolution = Resolution(
        query="x",
        verdict=Verdict.RESOLVED,
        candidates=tuple(
            Candidate(path=path, score=float(len(candidates) - index), evidence=(path,))
            for index, (path,) in enumerate(candidates)
        ),
    )
    exploration = Exploration(
        query="x",
        budget=1,
        spent=0,
        reads=tuple(
            TargetedRead(
                path=path,
                start=1,
                end=1,
                text="",
                reason="read",
                candidate_rank=index + 1,
                estimated_tokens=1,
            )
            for index, path in enumerate(reads)
        ),
        deferred=(),
        exhausted=False,
    )
    return Evidence(
        prompt="x",
        index=repo,
        resolution=resolution,
        exploration=exploration,
        vocabulary=(AGENT,),
    )


def _id_of(set: CandidateSet, value: Any) -> str:
    """The candidate id whose value is `value`, in the shown order."""
    for candidate in set.candidates:
        if candidate.value == value:
            return candidate.id
    raise AssertionError(f"{value!r} is not a candidate of {set.field}")


def _choosing(
    evidence: Evidence,
    *,
    task_type: str,
    target: str,
    symbol: str,
    interface: str = "",
    deps: Any = (),
    allow: Any = (),
) -> Any:
    """A classify fake answering each field's single question with a chosen value."""
    symbol_name = None if symbol == "" else symbol
    sets: dict[str, CandidateSet] = {
        "task_type": task_type_candidates(evidence),
        "target": target_candidates(evidence),
        "symbol": symbol_candidates(evidence, target),
        "interface": interface_candidates(evidence, target, symbol_name),
        "deps": deps_candidates(evidence, target),
        "allow": scope_candidates(evidence, target)[0],
    }
    values: dict[str, Any] = {
        "task_type": task_type,
        "target": target,
        "symbol": symbol,
        "interface": interface,
        "deps": deps,
        "allow": allow,
    }

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        return decision_of({field: answer(_id_of(sets[field], values[field]), 0.9)})

    return classify


# --- the deterministic plan and its collapse -------------------------------


def test_collapse_of_enumerated_plan_yields_the_deterministic_proposal(
    repo: Index,
) -> None:
    """Rank-0 of every field folds into the deterministic proposal."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    proposal = collapse(enumerate_candidates(evidence))

    kind = completable((AGENT,))[0]
    target = candidate_targets(evidence)[0]
    symbols = symbols_of(evidence, target)
    symbol = symbols[0].name if symbols else None

    assert proposal == Proposal(
        task_type=kind.name,
        task=directive(kind, target, symbol),
        target=target,
        stop_conditions=stop_condition(kind, target, symbol),
    )
    assert proposal.allow == ()
    assert proposal.forbid == ()
    assert proposal.deps == ()
    assert proposal.interface == ""
    assert proposal.acceptance == ()
    assert proposal.demonstration == ()
    assert proposal.operation == ""
    assert proposal.sources == ()
    assert proposal.depends_on == ()


def test_collapse_wraps_a_chosen_dependency_in_a_tuple(repo: Index) -> None:
    """A chosen `DepRef` folds to a one-element `deps` tuple, never a bare ref.

    `deps` candidates are one dependency each, so collapsing a chosen `DepRef`
    must yield a tuple for `Proposal.deps`, or `_emit`'s iteration over
    ``proposal.deps`` would crash on a real dependency.
    """
    evidence = evidence_for(repo, "document listing", (AGENT,))
    plan = enumerate_candidates(evidence)
    dep = DepRef("pagination.py", "paginate")
    plan = choose(plan, "deps", dep)

    assert collapse(plan).deps == (dep,)


def test_choose_promotes_operation_and_sources_into_collapse(repo: Index) -> None:
    """The fan-out fields fold through `choose` like every other field."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    plan = enumerate_candidates(evidence)
    plan = choose(plan, "sources", ("a.py",))
    plan = choose(plan, "operation", "rename_symbol")

    proposal = collapse(plan)

    assert proposal.operation == "rename_symbol"
    assert proposal.sources == ("a.py",)
    assert proposal.depends_on == ()


def test_enumerate_candidates_ranks_targets_candidates_then_reads(
    repo: Index,
) -> None:
    """Candidates come first, then reads, deduplicated."""
    evidence = _synthetic_evidence(
        repo,
        candidates=(("listing.py",), ("pagination.py",)),
        reads=("pagination.py", "other.py"),
    )
    target_set = enumerate_candidates(evidence)["target"]
    assert [c.value for c in target_set.candidates] == [
        "listing.py",
        "pagination.py",
        "other.py",
    ]


def test_symbol_candidates_are_definitions_then_no_symbol(repo: Index) -> None:
    """Definitions appear in index order, with the no-symbol option last."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    names = [symbol.name for symbol in symbols_of(evidence, "listing.py")]
    values = [c.value for c in symbol_candidates(evidence, "listing.py").candidates]
    assert values == [*names, ""]
    assert values[-1] == ""


def test_deps_candidates_map_imports_to_definitions_in_other_files(
    tmp_path: Path,
) -> None:
    """An import becomes a dep only when the definition lives in another file."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "helpers.py").write_text("def helper():\n    return 1\n")
    (root / "main.py").write_text(
        "from helpers import helper\n\n\ndef helper():\n    return 2\n\n"
        "\ndef run():\n    return helper()\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    index = build_index(root)
    evidence = evidence_for(index, "helper", (AGENT,))

    values = [c.value for c in deps_candidates(evidence, "main.py").candidates]
    assert values[0] == ()
    assert DepRef(path="helpers.py", symbol="helper") in values
    assert DepRef(path="main.py", symbol="helper") not in values


def test_sources_candidates_exclude_target_and_dedup(repo: Index) -> None:
    """Sources read the evidence's other paths, leaving the target out."""
    evidence = _synthetic_evidence(
        repo,
        candidates=(("listing.py",), ("pagination.py",)),
        reads=("pagination.py", "other.py"),
    )
    values = [c.value for c in sources_candidates(evidence, "listing.py").candidates]
    assert values == [(), "pagination.py", "other.py"]


def test_acceptance_and_demonstration_derive_only_from_the_baseline(
    repo: Index,
) -> None:
    """Only an evidence-derived kind with a baseline yields command candidates."""
    code = catalog().require("code")
    baseline = BaselineObservation(
        runner=("pytest",), red=("test_red",), green=("test_green",)
    )

    evidence = evidence_for(repo, "document listing", (code,), baseline=baseline)
    assert [c.value for c in acceptance_candidates(evidence, code).candidates] == [
        (),
        ("pytest --deselect=test_red",),
    ]
    assert [c.value for c in demonstration_candidates(evidence, code).candidates] == [
        (),
        ("pytest test_red",),
    ]

    without_baseline = evidence_for(repo, "document listing", (code,), baseline=None)
    assert [
        c.value for c in acceptance_candidates(without_baseline, code).candidates
    ] == [()]
    assert [
        c.value for c in demonstration_candidates(without_baseline, code).candidates
    ] == [()]

    not_derived = evidence_for(repo, "document listing", (AGENT,), baseline=baseline)
    assert [c.value for c in acceptance_candidates(not_derived, AGENT).candidates] == [
        ()
    ]
    assert [
        c.value for c in demonstration_candidates(not_derived, AGENT).candidates
    ] == [()]


def test_choose_promotes_a_value_to_rank_zero_and_tags_model(repo: Index) -> None:
    """The promoted value leads, is MODEL-tagged, and the rest stay below it."""
    plan = enumerate_candidates(evidence_for(repo, "document listing", (AGENT,)))
    chosen = choose(plan, "target", "pagination.py")
    target_set = chosen["target"]

    assert target_set.rank0 is not None
    assert target_set.rank0.value == "pagination.py"
    assert target_set.rank0.provenance is Provenance.MODEL
    assert [c.value for c in target_set.candidates[1:]] == [
        c.value for c in plan["target"].candidates if c.value != "pagination.py"
    ]
    assert all(
        c.provenance is Provenance.DETERMINISTIC for c in target_set.candidates[1:]
    )


def test_scope_candidates_dedup_when_the_target_is_the_only_path(
    repo: Index,
) -> None:
    """`allow` has no duplicate when the evidence points at only the target."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    allow, _ = scope_candidates(evidence, "listing.py")
    assert [c.value for c in allow.candidates] == [(), ("listing.py",)]


def test_without_drops_a_value_and_renormalizes_ranks() -> None:
    """`without` removes the rejected value and re-ranks 0..n-1 in place."""
    target_set = CandidateSet(
        field="target",
        candidates=(
            FieldCandidate(id="target:0", value="listing.py", rank=0),
            FieldCandidate(id="target:1", value="pagination.py", rank=1),
            FieldCandidate(id="target:2", value="other.py", rank=2),
        ),
    )

    pruned = without(target_set, {"pagination.py"})

    assert [c.value for c in pruned.candidates] == ["listing.py", "other.py"]
    assert [c.rank for c in pruned.candidates] == [0, 1]
    # Ids and provenance are preserved; only the ranks move up.
    assert [c.id for c in pruned.candidates] == ["target:0", "target:2"]
    assert [c.provenance for c in pruned.candidates] == [
        Provenance.DETERMINISTIC,
        Provenance.DETERMINISTIC,
    ]


def test_without_keeps_the_set_unchanged_for_unknown_values() -> None:
    """Dropping a value that is not present leaves every candidate in place."""
    target_set = CandidateSet(
        field="target",
        candidates=(FieldCandidate(id="target:0", value="listing.py", rank=0),),
    )
    pruned = without(target_set, {"not-a-target.py"})

    assert pruned.candidates == target_set.candidates


# --- the regression that pins the classifier path --------------------------


def test_classifier_proposer_output_is_bit_identical(repo: Index) -> None:
    """The refactored proposer emits exactly the proposal it hand-built before."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    propose = ClassifierProposer(
        classify=_choosing(
            evidence, task_type="agent", target="listing.py", symbol="listing"
        )
    )
    (proposal,) = propose(evidence)

    expected = Proposal(
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
    assert proposal == expected

    kind = kind_for("agent", completable((AGENT,)))
    assert kind is not None
    plan = enumerate_candidates(evidence)
    plan = choose(plan, "task_type", "agent")
    plan = choose(plan, "target", "listing.py")
    plan = choose(plan, "symbol", "listing")
    plan = choose(
        plan,
        "task",
        directive(kind, "listing.py", "listing"),
        provenance=Provenance.DETERMINISTIC,
    )
    plan = choose(
        plan,
        "stop_conditions",
        stop_condition(kind, "listing.py", "listing"),
        provenance=Provenance.DETERMINISTIC,
    )
    assert collapse(plan) == expected


def test_classifier_proposer_reflects_the_models_override_picks(
    repo: Index,
) -> None:
    """An override away from rank-0 emits the model's target and symbol."""
    evidence = _synthetic_evidence(
        repo,
        candidates=(("listing.py",), ("pagination.py",)),
        reads=(),
    )
    propose = ClassifierProposer(
        classify=_choosing(
            evidence,
            task_type="agent",
            target="pagination.py",
            symbol="paginate",
        )
    )
    (proposal,) = propose(evidence)

    kind = kind_for("agent", completable((AGENT,)))
    assert kind is not None
    assert proposal == Proposal(
        task_type="agent",
        task=directive(kind, "pagination.py", "paginate"),
        target="pagination.py",
        stop_conditions=stop_condition(kind, "pagination.py", "paginate"),
    )


def test_classifier_proposer_no_symbol_pins_the_whole_file(repo: Index) -> None:
    """A whole-file pick names only the target in task and stop conditions."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    propose = ClassifierProposer(
        classify=_choosing(evidence, task_type="agent", target="listing.py", symbol="")
    )
    (proposal,) = propose(evidence)

    kind = kind_for("agent", completable((AGENT,)))
    assert kind is not None
    assert proposal == Proposal(
        task_type="agent",
        task=directive(kind, "listing.py", None),
        target="listing.py",
        stop_conditions=stop_condition(kind, "listing.py", None),
    )
