"""W3 — the per-field jev top-1 seam and its degrade-to-rank-0 fallback.

The classifier proposer asks one typed ``Choice`` per jev-decided field in
dependency order (`task_type`, `target`, `symbol`, `interface`, `deps`,
`allow`), re-enumerating each downstream set against the values already chosen,
and folds the picks into one proposal. A load-bearing answer that is unusable
or low-confidence declines the whole proposal; an optional field degrades to
its rank-0 candidate. Without a jev unit the factory returns a deterministic
proposer that collapses rank-0 per field and asks nothing, and one
``DecisionRecord`` per decision lands in the W1 ``ShadowSink``.

The transport is stubbed throughout: the properties under test are the shape
and order of the questions, the mapping from answers to a proposal, the
rank-0 degrade, and the telemetry records.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr.catalog import TaskType
from mcgyvr.config import parse
from mcgyvr.decision import (
    Answer,
    Choice,
    ChoiceAnswer,
    Decision,
    DecisionError,
    Question,
)
from mcgyvr.delegate import MIN_CONFIDENCE, ClassifierProposer, classifier_proposer_for
from mcgyvr.local_pool import source_map
from mcgyvr.orchestrator.candidates import (
    _NO_SYMBOL,
    CandidateSet,
    Provenance,
    choose,
    collapse,
    deps_candidates,
    directive,
    enumerate_candidates,
    interface_candidates,
    scope_candidates,
    stop_condition,
    symbol_candidates,
    target_candidates,
    task_candidates,
    task_type_candidates,
)
from mcgyvr.orchestrator.decompose import Evidence, Refusal
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.orchestrator.telemetry import ShadowSink, read
from tests import ungated

#: A keyless local ladder with no orchestrator or jev block.
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

#: The ungated example kind (tests/ungated.py), as in test_classifier_proposer.py:
#: not ``code``, whose proposal also carries a derived reply cap.
AGENT = ungated.ungated()
pytestmark = pytest.mark.usefixtures("ungated_catalog")

#: The fields the proposer asks, in the order it follows.
FIELD_ORDER = ("task_type", "target", "symbol", "task", "interface", "deps", "allow")


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


def decision_of(answers: Mapping[str, Answer]) -> Decision:
    return Decision(answers=answers)


def answer(choice: str, confidence: float) -> ChoiceAnswer:
    return ChoiceAnswer(
        choice=choice,
        probabilities={choice: 1.0},
        confidence=confidence,
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
    task: str,
    interface: str,
    deps: Any,
    allow: Any,
    confidence: float = 0.9,
) -> Callable[[Any, Mapping[str, Question]], Decision]:
    """A classify fake answering each field's single question with a chosen value."""
    symbol_name = None if symbol == _NO_SYMBOL else symbol
    kind = next(k for k in evidence.vocabulary if k.name == task_type)
    sets: dict[str, CandidateSet] = {
        "task_type": task_type_candidates(evidence),
        "target": target_candidates(evidence),
        "symbol": symbol_candidates(evidence, target),
        "task": task_candidates(kind, target, symbol_name, evidence.prompt),
        "interface": interface_candidates(evidence, target, symbol_name),
        "deps": deps_candidates(evidence, target),
        "allow": scope_candidates(evidence, target)[0],
    }
    values: dict[str, Any] = {
        "task_type": task_type,
        "target": target,
        "symbol": symbol,
        "task": task,
        "interface": interface,
        "deps": deps,
        "allow": allow,
    }

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        return decision_of(
            {field: answer(_id_of(sets[field], values[field]), confidence)}
        )

    return classify


# --- the per-field question shape and order --------------------------------


def test_asks_one_choice_per_field_in_dependency_order(repo: Index) -> None:
    """Each field is one Choice, asked in dependency order, keyed by candidate id."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    seen: list[tuple[Any, Mapping[str, Question]]] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        seen.append((state, questions))
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        return decision_of({field: answer(next(iter(question.options)), 0.9)})

    (proposal,) = ClassifierProposer(classify=classify)(evidence)
    assert proposal.task_type == "agent"

    assert [next(iter(q)) for _, q in seen] == list(FIELD_ORDER)

    target_set = target_candidates(evidence)
    target = target_set.rank0.value if target_set.rank0 is not None else ""
    symbol_set = symbol_candidates(evidence, target)
    symbol_name = symbol_set.rank0.value if symbol_set.rank0 is not None else _NO_SYMBOL
    expected: dict[str, CandidateSet] = {
        "task_type": task_type_candidates(evidence),
        "target": target_set,
        "symbol": symbol_set,
        "task": task_candidates(
            AGENT, target, _symbol_of(symbol_name), evidence.prompt
        ),
        "interface": interface_candidates(evidence, target, _symbol_of(symbol_name)),
        "deps": deps_candidates(evidence, target),
        "allow": scope_candidates(evidence, target)[0],
    }

    for _, questions in seen:
        assert len(questions) == 1
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        assert tuple(question.options) == tuple(
            c.id for c in expected[field].candidates
        )


def test_per_field_picks_reach_the_collapsed_proposal(repo: Index) -> None:
    """Picks away from rank-0 (no symbol, the directive, a named allow) fold in."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    target = "listing.py"
    propose = ClassifierProposer(
        classify=_choosing(
            evidence,
            task_type="agent",
            target=target,
            symbol=_NO_SYMBOL,
            task=directive(AGENT, target, None),
            interface="",
            deps=(),
            allow=(target,),
        )
    )
    (proposal,) = propose(evidence)

    kind = AGENT
    plan = enumerate_candidates(evidence)
    plan = choose(plan, "task_type", "agent")
    plan = choose(plan, "target", target)
    plan = choose(plan, "symbol", _NO_SYMBOL)
    plan = choose(plan, "task", directive(kind, target, None))
    plan = choose(
        plan,
        "stop_conditions",
        stop_condition(kind, target, None),
        provenance=Provenance.DETERMINISTIC,
    )
    plan = choose(plan, "interface", "")
    plan = choose(plan, "deps", ())
    plan = choose(plan, "allow", (target,))

    assert proposal == collapse(plan)


def test_abstain_sentinel_is_a_real_option_and_round_trips(
    repo: Index, tmp_path: Path
) -> None:
    """The deps `()` candidate is a real option; picking it records an abstain."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    deps_set = deps_candidates(evidence, "listing.py")
    sentinel_id = _id_of(deps_set, ())
    sink = ShadowSink(tmp_path / "decisions.jsonl")

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        if field == "deps":
            return decision_of({field: answer(sentinel_id, 0.9)})
        return decision_of({field: answer(next(iter(question.options)), 0.9)})

    (proposal,) = ClassifierProposer(classify=classify, sink=sink, model="m")(evidence)
    assert proposal.deps == ()

    deps_record = next(
        r for r in read(tmp_path / "decisions.jsonl") if r.field == "deps"
    )
    assert deps_record.abstain is True
    assert deps_record.pick == sentinel_id


def test_degrades_deterministically_without_jev(
    repo: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No jev means no model call: the proposer collapses rank-0 per field."""
    pool = source_map(parse(LADDER))

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no model call without a jev unit")

    monkeypatch.setattr(decision, "_post_json", fail)
    propose = classifier_proposer_for(pool)
    assert propose is not None
    evidence = evidence_for(repo, "document listing", (AGENT,))
    assert propose(evidence) == (collapse(enumerate_candidates(evidence)),)


def test_one_decision_record_per_field(repo: Index, tmp_path: Path) -> None:
    """Each asked field writes one DecisionRecord with the decision's shape."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    sink_path = tmp_path / "decisions.jsonl"

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        return decision_of({field: answer(next(iter(question.options)), 0.8)})

    ClassifierProposer(classify=classify, sink=ShadowSink(sink_path), model="m")(
        evidence
    )

    records = read(sink_path)
    assert [r.field for r in records] == list(FIELD_ORDER)
    for record in records:
        assert record.model == "m"
        assert record.seed == ""
        assert record.latency_ms >= 0
        assert record.parse_fail is False
        assert record.confidence == 0.8
        assert record.rank1 == record.candidates[0]
        assert record.pick == record.candidates[0]


def test_low_confidence_optional_field_leaves_rank0_but_load_bearing_declines(
    repo: Index,
) -> None:
    """A low-confidence `allow` degrades to (); low `task_type` declines all."""
    evidence = evidence_for(repo, "document listing", (AGENT,))

    def classify_low_allow(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        confidence = MIN_CONFIDENCE - 0.1 if field == "allow" else 0.9
        return decision_of({field: answer(next(iter(question.options)), confidence)})

    (proposal,) = ClassifierProposer(classify=classify_low_allow)(evidence)
    assert proposal.allow == ()

    kind = AGENT
    target_set = target_candidates(evidence)
    target = target_set.rank0.value if target_set.rank0 is not None else ""
    symbol_set = symbol_candidates(evidence, target)
    symbol = symbol_set.rank0.value if symbol_set.rank0 is not None else _NO_SYMBOL
    symbol_name = _symbol_of(symbol)

    plan = enumerate_candidates(evidence)
    plan = choose(plan, "task_type", kind.name)
    plan = choose(plan, "target", target)
    plan = choose(plan, "symbol", symbol_name or _NO_SYMBOL)
    plan = choose(plan, "task", evidence.prompt)
    plan = choose(
        plan,
        "stop_conditions",
        stop_condition(kind, target, symbol_name),
        provenance=Provenance.DETERMINISTIC,
    )
    plan = choose(plan, "interface", "")
    plan = choose(plan, "deps", ())

    assert proposal == collapse(plan)
    assert plan["allow"].rank0 is not None
    assert plan["allow"].rank0.provenance is Provenance.DETERMINISTIC

    def classify_low_type(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        confidence = MIN_CONFIDENCE - 0.1 if field == "task_type" else 0.9
        return decision_of({field: answer(next(iter(question.options)), confidence)})

    assert ClassifierProposer(classify=classify_low_type)(evidence) == ()


def test_parse_fail_records_and_degrades(repo: Index, tmp_path: Path) -> None:
    """A DecisionError on an optional field records parse_fail and leaves rank-0."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    sink = ShadowSink(tmp_path / "decisions.jsonl")

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        if field == "interface":
            raise DecisionError("no label in the reply")
        return decision_of({field: answer(next(iter(question.options)), 0.9)})

    (proposal,) = ClassifierProposer(classify=classify, sink=sink, model="m")(evidence)
    assert proposal.interface == ""

    interface_record = next(
        r for r in read(tmp_path / "decisions.jsonl") if r.field == "interface"
    )
    assert interface_record.parse_fail is True
    assert interface_record.abstain is True
    assert interface_record.pick is None


def test_symbol_parse_fail_falls_back_to_deterministic_rank0(repo: Index) -> None:
    """A parse-fail on `symbol` degrades to rank-0 with DETERMINISTIC provenance."""
    evidence = evidence_for(repo, "document listing", (AGENT,))

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        if field == "symbol":
            raise DecisionError("no label in the reply")
        return decision_of({field: answer(next(iter(question.options)), 0.9)})

    (proposal,) = ClassifierProposer(classify=classify)(evidence)

    kind = AGENT
    target_set = target_candidates(evidence)
    target = target_set.rank0.value if target_set.rank0 is not None else ""
    symbol_set = symbol_candidates(evidence, target)
    symbol = symbol_set.rank0.value if symbol_set.rank0 is not None else _NO_SYMBOL
    symbol_name = _symbol_of(symbol)

    plan = enumerate_candidates(evidence)
    plan = choose(plan, "task_type", kind.name)
    plan = choose(plan, "target", target)
    plan = choose(
        plan,
        "symbol",
        symbol_name or _NO_SYMBOL,
        provenance=Provenance.DETERMINISTIC,
    )
    plan = choose(plan, "task", evidence.prompt)
    plan = choose(
        plan,
        "stop_conditions",
        stop_condition(kind, target, symbol_name),
        provenance=Provenance.DETERMINISTIC,
    )
    plan = choose(plan, "interface", "")
    plan = choose(plan, "deps", ())

    assert proposal == collapse(plan)
    assert plan["symbol"].rank0 is not None
    assert plan["symbol"].rank0.provenance is Provenance.DETERMINISTIC


def test_value_by_id_keyerror_degrades_and_records_parse_fail(
    repo: Index, tmp_path: Path
) -> None:
    """A choice id not among the options degrades and records a parse failure."""
    evidence = evidence_for(repo, "document listing", (AGENT,))
    sink = ShadowSink(tmp_path / "decisions.jsonl")

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        if field == "deps":
            return decision_of({field: answer("bogus", 0.9)})
        return decision_of({field: answer(next(iter(question.options)), 0.9)})

    (proposal,) = ClassifierProposer(classify=classify, sink=sink, model="m")(evidence)
    assert proposal.deps == ()

    deps_record = next(
        r for r in read(tmp_path / "decisions.jsonl") if r.field == "deps"
    )
    assert deps_record.parse_fail is True
    assert deps_record.abstain is True
    assert deps_record.pick is None


def _symbol_of(name: Any) -> str | None:
    """The symbol name, or None for the no-symbol option (test mirror)."""
    return None if name == _NO_SYMBOL else str(name)


def test_propose_refuses_a_below_floor_task_type_but_call_declines(
    repo: Index,
) -> None:
    """`propose` names the refusal; `__call__` still returns () for fallback."""
    evidence = evidence_for(repo, "document listing", (AGENT,))

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        confidence = MIN_CONFIDENCE - 0.1 if field == "task_type" else 0.9
        return decision_of({field: answer(next(iter(question.options)), confidence)})

    proposer = ClassifierProposer(classify=classify)
    refusal = proposer.propose(evidence)
    assert isinstance(refusal, Refusal)
    assert refusal.field == "task_type"
    assert (
        refusal.what_to_change == "answer with a candidate above the confidence floor"
    )
    assert proposer(evidence) == ()


def test_propose_drops_rejected_candidates_from_the_choice(repo: Index) -> None:
    """`rejected` filters a candidate out of the Choice the model is shown."""
    evidence = evidence_for(repo, "listing pagination", (AGENT,))
    seen: list[Mapping[str, Question]] = []

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        seen.append(questions)
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        return decision_of({field: answer(next(iter(question.options)), 0.9)})

    result = ClassifierProposer(classify=classify).propose(
        evidence, rejected={"target": ["listing.py"]}
    )
    assert not isinstance(result, Refusal)
    assert result.target == "pagination.py"

    target_question = next(q["target"] for q in seen if "target" in q)
    assert isinstance(target_question, Choice)
    assert "target:0" not in target_question.options  # listing.py was dropped
    assert "target:1" in target_question.options  # pagination.py keeps its id
