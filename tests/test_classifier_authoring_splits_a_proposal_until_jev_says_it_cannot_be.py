"""Classifier authoring splits a proposal until one file per contract and jev says no.

The typed classifier proposes once for a request; the refining proposer breaks
that proposal down again and again. A proposal whose scope names more files than
its target becomes one proposal per file. A proposal on one file is put to jev as
one typed yes/no question, `split`; No makes it a contract, Yes splits it by a
partition the survey read from the request and the repository (its sentences,
the target's definitions it names, the failing tests the baseline attaches),
chosen by jev as one typed Choice, `partition`, when there is more than one. The
parts on one file are ordered by the tree: one that spells a name another
creates waits on it, the rest are kept apart by their scopes.

A split past `max_refine_depth`, or into more parts than `max_refine_fanout`, is
a refusal with what to change, never a silent stop. When jev declines — an
answer it cannot give, or a Yes with no partition the survey could build — the
prose proposer stands in for the whole request, as it did before. Every answer
is scripted (`tests/refines.py`); nothing sleeps and nothing leaves the machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.board import GitSource
from mcgyvr.catalog import catalog
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.decision import Choice, Noul
from mcgyvr.delegate import ClassifierProposer, proposer_by_authoring
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.local_pool import source_map
from mcgyvr.orchestrator.baseline import BaselineObservation
from mcgyvr.orchestrator.decompose import (
    Evidence,
    Proposal,
    Refusal,
    decompose,
    emit_one,
)
from mcgyvr.orchestrator.fields import FIELD_ORDER
from mcgyvr.orchestrator.index import Index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.orchestrator.telemetry import ShadowSink, read
from mcgyvr.refine import RefiningProposer, max_depth, max_fanout, survey
from mcgyvr.tree import State, Tree
from tests.refines import MODEL, ScriptedJev, refining, repository, tasks

#: The parts a split proposal's questions are asked again for, per child.
CHILD_FIELDS = ["symbol", "interface", "deps"]

RED = ("tests/test_listing.py::test_negative", "tests/test_listing.py::test_doc")


@pytest.fixture
def index(tmp_path: Path) -> Index:
    return repository(tmp_path / "repo")


def evidence_for(
    index: Index, prompt: str, *, baseline: BaselineObservation | None = None
) -> Evidence:
    """What `decompose` hands a proposer, with the baseline a test names."""
    resolution = resolve(index, prompt)
    return Evidence(
        prompt=prompt,
        index=index,
        resolution=resolution,
        exploration=explore(index, resolution),
        vocabulary=catalog().task_types,
        baseline=baseline,
    )


def proposal(task: str, **fields: Any) -> Proposal:
    return Proposal(
        task_type="code",
        task=task,
        target="listing.py",
        stop_conditions=("the request is ambiguous",),
        **fields,
    )


def no_prose(evidence: Evidence) -> Sequence[Proposal]:
    raise AssertionError("jev answered, so prose is not asked")


# -- the stop: one file, and jev says it cannot be split ----------------------


def test_a_one_file_proposal_jev_will_not_split_is_one_contract(
    index: Index, tmp_path: Path
) -> None:
    jev = ScriptedJev()
    sink = ShadowSink(tmp_path / "decisions.jsonl")

    result = decompose(index, "document listing", propose=refining(jev, sink=sink))

    assert result.refusals == ()
    (contract,) = result.contracts
    assert (contract.target, contract.task) == ("listing.py", "document listing")
    assert jev.names() == [*FIELD_ORDER, "split"]
    split = jev.asked[-1]
    assert isinstance(split.question, Noul)
    assert "listing.py" in split.question.instructions
    assert split.state["task"] == "document listing"
    assert split.state["target"] == "listing.py"
    record = read(tmp_path / "decisions.jsonl")[-1]
    assert (record.field, record.pick, record.model) == ("split", "split:no", MODEL)
    assert record.candidates == ("split:no", "split:yes")


# -- a split: two or more contracts on one file, ordered by the tree ----------


def test_a_proposal_jev_splits_is_one_contract_per_sentence_in_tree_order(
    index: Index,
) -> None:
    """The part that spells the name a rename creates waits on the rename."""
    prompt = "Rename paginate to page in listing.py. Call page from listing."
    jev = ScriptedJev(split=tasks(prompt))

    result = decompose(index, prompt, propose=refining(jev))

    assert result.refusals == ()
    rename, call = result.contracts
    assert rename.task == "Rename paginate to page in listing.py."
    assert call.task == "Call page from listing."
    assert rename.target == call.target == "listing.py"
    assert call.depends_on == (rename.id,)
    # A Yes is followed by which split, even with one to pick; both parts are
    # proposed, then each is asked whether it splits again.
    assert jev.names() == [
        *FIELD_ORDER,
        "split",
        "partition",
        *CHILD_FIELDS * 2,
        "split",
        "split",
    ]
    (partition,) = (a for a in jev.asked if a.name == "partition")
    assert isinstance(partition.question, Choice)
    assert list(partition.question.options) == ["partition:sentence", "partition:none"]

    tree = Tree.of(result.contracts, GitSource(index.root), tree_id="split")
    assert tree.ready() == (rename,)
    assert tree.state(call.id) is State.WAITING
    assert tree.levels() == {rename.id: 1, call.id: 2}


def test_parts_with_no_edge_are_both_ready_and_kept_apart_by_their_scopes(
    index: Index, tmp_path: Path
) -> None:
    """With two partitions to choose from, jev is asked which, and it is recorded."""
    prompt = "Document listing. Make paginate reject a negative size."
    jev = ScriptedJev(split=tasks(prompt), picks={"partition": "sentence"})
    sink = ShadowSink(tmp_path / "decisions.jsonl")

    result = decompose(index, prompt, propose=refining(jev, sink=sink))

    assert result.refusals == ()
    first, second = result.contracts
    assert (first.task, second.task) == (
        "Document listing.",
        "Make paginate reject a negative size.",
    )
    assert first.depends_on == second.depends_on == ()
    tree = Tree.of(result.contracts, GitSource(index.root), tree_id="apart")
    assert tree.ready() == (first, second)
    # What keeps them from running at once under --jobs (Scope.meets).
    assert first.scope.meets(second.scope)

    (partition,) = (a for a in jev.asked if a.name == "partition")
    assert isinstance(partition.question, Choice)
    assert dict(partition.question.options) == {
        "partition:sentence": (
            "one contract per sentence: Document listing. | "
            "Make paginate reject a negative size."
        ),
        "partition:symbol": "one contract per symbol: listing, paginate",
        "partition:none": (
            "none of these: a part would not be one behaviour change that can "
            "land on its own"
        ),
    }
    records = {r.field: r for r in read(tmp_path / "decisions.jsonl")}
    assert records["partition"].pick == "partition:sentence"
    assert records["partition"].candidates == (
        "partition:sentence",
        "partition:symbol",
        "partition:none",
    )
    assert records["partition"].model == MODEL


def test_a_proposal_split_by_symbol_is_one_contract_per_definition_it_names(
    index: Index,
) -> None:
    prompt = "Add type hints to listing and paginate."
    jev = ScriptedJev(split=tasks(prompt))

    result = decompose(index, prompt, propose=refining(jev))

    assert result.refusals == ()
    hints = result.contracts
    assert [c.task for c in hints] == [
        f"{prompt} This contract's part of that work is `listing` only.",
        f"{prompt} This contract's part of that work is `paginate` only.",
    ]
    assert "listing in listing.py" in hints[0].stop_conditions[0]
    assert "paginate in listing.py" in hints[1].stop_conditions[0]
    # The symbol is the part's: only the interface and deps are asked again.
    assert jev.names() == [
        *FIELD_ORDER,
        "split",
        "partition",
        *["interface", "deps"] * 2,
        "split",
        "split",
    ]


def test_failing_tests_split_one_contract_per_test_it_demonstrates(
    index: Index,
) -> None:
    """With the baseline's red tests attached, only a split by test can land."""
    baseline = BaselineObservation(
        runner=("pytest",), red=RED, green=("tests/test_listing.py::test_ok",)
    )
    prompt = "Make paginate reject a negative size. Document listing."
    evidence = evidence_for(index, prompt, baseline=baseline)
    jev = ScriptedJev(split=tasks(prompt))

    refined = refining(jev)(evidence)

    assert jev.names() == [*FIELD_ORDER, "split", "partition", "split", "split"]
    owners = (PythonAdapter(), JavaScriptAdapter())
    built = []
    for each in refined:
        assert isinstance(each, Proposal)
        emitted = emit_one(
            evidence, each, seen={}, adapters=owners, ceiling=evidence.ceiling
        )
        assert not isinstance(emitted, Refusal)
        built.append(emitted[0])
    assert [c.demonstration for c in built] == [
        (f"pytest {RED[0]}",),
        (f"pytest {RED[1]}",),
    ]
    deselected = " ".join(f"--deselect={test}" for test in RED)
    assert [c.acceptance for c in built] == [(f"pytest {deselected}",)] * 2
    assert built[0].id != built[1].id


def test_a_proposal_over_two_files_is_one_contract_per_file(index: Index) -> None:
    prompt = "Document listing in listing.py. Document render in report.py."
    jev = ScriptedJev(picks={"allow": "every evidence path"})

    result = decompose(index, prompt, propose=refining(jev))

    assert result.refusals == ()
    by_target = {c.target: c for c in result.contracts}
    assert set(by_target) == {"listing.py", "report.py"}
    assert by_target["report.py"].task == "Document render in report.py."
    assert by_target["listing.py"].task == "Document listing in listing.py."
    assert by_target["report.py"].scope.allow == ("report.py",)
    assert by_target["listing.py"].scope.allow == ("listing.py",)
    # Each file's proposal is asked again with its file as target and scope.
    per_file = ["symbol", "task", "interface", "deps"]
    assert jev.names() == [*FIELD_ORDER, *per_file * 2, "split", "split"]


# -- what the survey offers is read, never invented ---------------------------


def test_the_survey_offers_only_what_the_request_and_repository_hold(
    index: Index,
) -> None:
    prompt = "Document listing. Make paginate reject a negative size."
    evidence = evidence_for(index, prompt)
    sentence, symbol = survey(evidence, proposal(prompt), prompt)
    assert sentence.kind == "sentence"
    assert [p.task for p in sentence.parts] == [
        "Document listing.",
        "Make paginate reject a negative size.",
    ]
    assert symbol.kind == "symbol"
    assert [p.symbol for p in symbol.parts] == ["listing", "paginate"]

    # One sentence naming one definition has nothing to split by.
    assert survey(evidence, proposal("document listing"), "document listing") == ()
    # The target's own path is not read as definitions it names.
    said = "Fix listing in listing.py."
    assert survey(evidence, proposal(said), said) == ()
    # A rename makes a split by symbol ambiguous: none is offered.
    rename = "Rename paginate to page and update listing."
    assert survey(evidence, proposal(rename), rename) == ()
    # A part scoped to one symbol is not split by symbol again.
    hints = "Add type hints to listing and paginate."
    assert survey(evidence, proposal(hints), hints, scoped=True) == ()


def test_a_split_that_would_repeat_a_demonstration_is_not_offered(
    index: Index,
) -> None:
    """Each part would inherit every red test and could not pass the others'."""
    prompt = "Document listing. Make paginate reject a negative size."
    one_red = BaselineObservation(runner=("pytest",), red=RED[:1], green=("t",))
    evidence = evidence_for(index, prompt, baseline=one_red)
    assert survey(evidence, proposal(prompt), prompt) == ()
    # A part that already demonstrates one test is not split again.
    two_red = evidence_for(index, prompt, baseline=replace(one_red, red=RED))
    stated = proposal(prompt, demonstration=(f"pytest {RED[0]}",))
    assert survey(two_red, stated, prompt) == ()
    (by_test,) = survey(two_red, proposal(prompt), prompt)
    assert by_test.kind == "test"
    assert [p.demonstration for p in by_test.parts] == [
        (f"pytest {RED[0]}",),
        (f"pytest {RED[1]}",),
    ]


# -- bounds: a refusal with what to change, never a silent stop ---------------


def test_a_split_below_max_refine_depth_is_refused_with_what_to_change(
    index: Index,
) -> None:
    prompt = "Document listing. Add type hints to listing and paginate."
    jev = ScriptedJev(
        split=tasks(prompt, "Add type hints to listing and paginate."),
        picks={"partition": "sentence"},
    )

    result = decompose(index, prompt, propose=refining(jev, max_depth=1))

    (contract,) = result.contracts
    assert contract.task == "Document listing."
    (refusal,) = result.refusals
    assert refusal.subject == "listing.py"
    assert refusal.field == "task"
    assert "max_refine_depth" in refusal.what_to_change
    assert "max_refine_depth" in refusal.reason


def test_a_split_into_more_parts_than_max_refine_fanout_is_refused(
    index: Index,
) -> None:
    prompt = (
        "Document listing. Document paginate. Make paginate reject a negative size."
    )
    jev = ScriptedJev(split=tasks(prompt), picks={"partition": "sentence"})
    propose = proposer_by_authoring(
        "classifier", typed=refining(jev, max_fanout=2), prose=no_prose
    )
    assert propose is not None

    result = decompose(index, prompt, propose=propose)

    assert result.contracts == ()
    (refusal,) = result.refusals
    assert refusal.field == "task"
    assert "max_refine_fanout" in refusal.what_to_change
    assert "3" in refusal.reason


def test_a_scope_over_more_files_than_max_refine_fanout_is_refused(
    index: Index,
) -> None:
    prompt = "Document listing in listing.py. Document render in report.py."
    jev = ScriptedJev(picks={"allow": "every evidence path"})

    result = decompose(index, prompt, propose=refining(jev, max_fanout=1))

    assert result.contracts == ()
    (refusal,) = result.refusals
    assert refusal.field == "allow"
    assert "max_refine_fanout" in refusal.what_to_change
    assert jev.names() == list(FIELD_ORDER)


def test_a_jev_that_always_says_yes_ends_in_a_decline_never_a_loop(
    index: Index,
) -> None:
    prompt = "Document listing. Add type hints to listing and paginate."
    jev = ScriptedJev(split=lambda state: True, picks={"partition": "sentence"})

    assert refining(jev)(evidence_for(index, prompt)) == ()
    assert len(jev.asked) < 30


# -- jev declines: prose stands in, as before ---------------------------------


def prose_answer(evidence: Evidence) -> Sequence[Proposal]:
    return (proposal("from prose"),)


@pytest.mark.parametrize(
    ("prompt", "jev"),
    [
        # The split answer falls below the confidence floor.
        ("document listing", ScriptedJev(confidences={"split": 0.1})),
        # Jev says it can be split, and the survey has no partition to offer.
        ("document listing", ScriptedJev(split=lambda state: True)),
        # The partition answer falls below the confidence floor.
        (
            "Document listing. Make paginate reject a negative size.",
            ScriptedJev(
                split=tasks("Document listing. Make paginate reject a negative size."),
                confidences={"partition": 0.1},
            ),
        ),
        # Jev picks none of the partitions the survey offers.
        (
            "Document listing. Make paginate reject a negative size.",
            ScriptedJev(
                split=tasks("Document listing. Make paginate reject a negative size."),
                picks={"partition": "none of these"},
            ),
        ),
        # The target answer falls below the floor: the classifier declines.
        ("document listing", ScriptedJev(confidences={"target": 0.1})),
        # A file of the scope no sentence names, by path or by a definition.
        (
            "Document listing and the report.",
            ScriptedJev(picks={"allow": "every evidence path"}),
        ),
    ],
    ids=[
        "split-unsure",
        "split-with-no-partition",
        "partition-unsure",
        "partition-none-fits",
        "target",
        "a-file-nothing-is-about",
    ],
)
def test_when_jev_declines_prose_stands_in_for_the_whole_request(
    index: Index, prompt: str, jev: ScriptedJev
) -> None:
    propose = proposer_by_authoring(
        "classifier", typed=refining(jev), prose=prose_answer
    )
    assert propose is not None

    result = decompose(index, prompt, propose=propose)

    assert result == decompose(index, prompt, propose=prose_answer)
    assert [c.task for c in result.contracts] == ["from prose"]


# -- the prose path and the wiring ---------------------------------------------


def test_the_prose_path_never_asks_jev_and_emits_what_prose_proposed(
    index: Index,
) -> None:
    jev = ScriptedJev()
    propose = proposer_by_authoring("prose", typed=refining(jev), prose=prose_answer)
    assert propose is prose_answer

    result = decompose(index, "document listing", propose=propose)

    assert [c.task for c in result.contracts] == ["from prose"]
    assert jev.asked == []


def test_a_proposers_refusal_is_reported_beside_what_it_proposed(
    index: Index,
) -> None:
    refused = Refusal("listing.py", "too wide", field="task", what_to_change="narrow")

    alone = decompose(index, "document listing", propose=prose_answer)
    beside = decompose(
        index,
        "document listing",
        propose=lambda evidence: (*prose_answer(evidence), refused),
    )

    assert beside.contracts == alone.contracts
    assert alone.refusals == ()
    assert beside.refusals == (refused,)


UNITS = """\
units:
  fast:
    address: http://localhost:18001
    model: example-coder:3b
    rig: local
  orch:
    address: http://localhost:18003
    model: example-planner:7b
    rig: local
  judge:
    address: http://localhost:18009
    model: example-judge:1b
    rig: local
ladder:
- fast
orchestrator:
  unit: orch
  authoring: classifier
"""


def _typed_for(monkeypatch: pytest.MonkeyPatch, text: str) -> Any:
    """The typed proposer `mcgyvr delegate` puts in front of prose for `text`."""
    from mcgyvr import delegate
    from mcgyvr.cli.commands.delegate import _proposer_for_delegate

    seen: list[Any] = []
    real = delegate.proposer_by_authoring

    def spy(strategy: str | None, **kwargs: Any) -> Any:
        seen.append(kwargs["typed"])
        return real(strategy, **kwargs)

    monkeypatch.setattr(delegate, "proposer_by_authoring", spy)
    config = parse(text)
    _proposer_for_delegate(config, source_map(config))
    (typed,) = seen
    return typed


def test_delegate_refines_with_the_configured_bounds_when_jev_is_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = UNITS + "jev:\n  unit: judge\nmax_refine_depth: 2\nmax_refine_fanout: 4\n"
    typed = _typed_for(monkeypatch, text)
    assert isinstance(typed, RefiningProposer)
    assert (typed.max_depth, typed.max_fanout) == (2, 4)
    assert isinstance(typed.classifier, ClassifierProposer)
    assert typed.classifier.model == "example-judge:1b"


def test_without_jev_delegate_keeps_the_rank0_collapse_unrefined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    typed = _typed_for(monkeypatch, UNITS)
    assert typed is not None
    assert not isinstance(typed, RefiningProposer)


def test_the_bounds_have_defaults_and_refuse_what_cannot_bound() -> None:
    config = parse(UNITS)
    assert (max_depth(config), max_fanout(config)) == (3, 8)
    with pytest.raises(ConfigSchemaError):
        parse(UNITS + "max_refine_depth: 0\n")
    with pytest.raises(ConfigSchemaError):
        parse(UNITS + "max_refine_fanout: 1\n")


# -- what the review found ------------------------------------------------------


@pytest.mark.parametrize(
    "words",
    [
        # A heading and bare list numbers are fragments, not parts.
        "In listing.py:\n1. Add type hints to paginate.\n2. Document listing.",
        # A sentence that ends in a word or two of courtesy.
        "Add type hints to paginate. Document listing. Thanks!",
    ],
)
def test_words_with_a_fragment_are_not_split_by_sentence(
    index: Index, words: str
) -> None:
    evidence = evidence_for(index, words)
    kinds = [p.kind for p in survey(evidence, proposal(words), words)]
    assert "sentence" not in kinds


def test_sentences_end_at_a_capital_never_at_an_abbreviation(index: Index) -> None:
    words = "Make paginate accept e.g. a size of zero. Document listing."
    evidence = evidence_for(index, words)
    (sentence, *_) = survey(evidence, proposal(words), words)
    assert [p.task for p in sentence.parts] == [
        "Make paginate accept e.g. a size of zero.",
        "Document listing.",
    ]
    listed = "- Add type hints to paginate.\n- Document the listing function."
    (by_line, *_) = survey(evidence_for(index, listed), proposal(listed), listed)
    assert [p.task for p in by_line.parts] == [
        "Add type hints to paginate.",
        "Document the listing function.",
    ]


def test_only_failing_tests_that_name_the_target_split_it(index: Index) -> None:
    prompt = "Add type hints to listing and paginate."
    elsewhere = BaselineObservation(
        runner=("pytest",),
        red=("tests/test_report.py::test_a", "tests/test_report.py::test_b"),
        green=("tests/test_report.py::test_ok",),
    )
    evidence = evidence_for(index, prompt, baseline=elsewhere)
    assert survey(evidence, proposal(prompt), prompt) == ()
    # A test that names one of the target's definitions counts as its own.
    mixed = replace(
        elsewhere,
        red=(
            "tests/test_report.py::test_a",
            "tests/test_pages.py::test_paginate_negative",
            "tests/test_listing.py::test_doc",
        ),
    )
    (by_test,) = survey(
        evidence_for(index, prompt, baseline=mixed), proposal(prompt), prompt
    )
    assert [p.subject for p in by_test.parts] == [
        "tests/test_pages.py::test_paginate_negative",
        "tests/test_listing.py::test_doc",
    ]


def test_each_file_is_given_the_sentences_that_name_its_definitions(
    index: Index,
) -> None:
    prompt = "Document render. Make paginate reject a negative size."
    jev = ScriptedJev(picks={"allow": "every evidence path"})

    result = decompose(index, prompt, propose=refining(jev))

    by_target = {c.target: c.task for c in result.contracts}
    assert by_target == {
        "report.py": "Document render.",
        "listing.py": "Make paginate reject a negative size.",
    }


def test_an_inferred_edge_that_would_close_a_cycle_is_left_out(
    index: Index,
) -> None:
    """Each part spells the name the other's rename creates: one edge, not two."""
    prompt = (
        "Rename paginate to page and keep items working. "
        "Rename listing to items and keep page working."
    )
    jev = ScriptedJev(split=tasks(prompt))

    result = decompose(index, prompt, propose=refining(jev))

    assert result.refusals == ()
    first, second = result.contracts
    assert first.depends_on == ()
    assert second.depends_on == (first.id,)


def test_with_prose_or_unset_authoring_delegate_builds_no_typed_proposer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with_jev = "jev:\n  unit: judge\n"
    for authoring in ("  authoring: prose\n", ""):
        text = UNITS.replace("  authoring: classifier\n", authoring) + with_jev
        assert _typed_for(monkeypatch, text) is None
