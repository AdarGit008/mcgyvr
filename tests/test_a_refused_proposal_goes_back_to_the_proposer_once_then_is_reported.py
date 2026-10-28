"""A refused proposal goes back to the proposer once, then is reported.

Vetting refuses a proposal it cannot state as a runnable contract and says
which field to change and how. With `max_reproposals` above 0, `decompose`
hands each such refusal back to the proposer, one per call, on the evidence's
`refused`: prose is shown it as data, the classifier asks the refused field
again through `iterate`'s re-ask. What comes back is vetted as a first answer
is; what is still refused is reported, never handed back past the bound. A
refusal of the request, or a catch-all, is never handed back, and 0 rounds is
what `decompose` was before. `mcgyvr PROMPT --log` counts what happened, and
records the classifier's typed decisions beside the record.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr.catalog import catalog
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.decision import Choice
from mcgyvr.delegate import ClassifierProposer, build_prompt, proposer_by_authoring
from mcgyvr.delegate_log import read
from mcgyvr.orchestrator.decompose import (
    Evidence,
    Proposal,
    Refusal,
    Refused,
    Reproposal,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.orchestrator.telemetry import read as read_decisions
from mcgyvr.repropose import max_reproposals
from tests import livejournal as lj
from tests.refines import ScriptedJev, git, refining, repository
from tests.test_delegate_log_names_every_way_delegate_ends import (
    CONFIG,
    PROPOSAL,
    _answer,
    _config,
    _reply,
)

STOP = ("the request is ambiguous",)


@pytest.fixture
def index(tmp_path: Path) -> Index:
    return repository(tmp_path / "repo")


@pytest.fixture
def checkout(index: Index) -> Path:
    """The repository `index` was built from, for `mcgyvr PROMPT --repo`."""
    return index.root


@pytest.fixture(autouse=True)
def _no_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A HOME of the test's own, no session in it and no setup discovered."""
    (tmp_path / "home").mkdir()
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))


def code(target: str, task: str = "Document listing.", **fields: Any) -> Proposal:
    return Proposal(
        task_type="code", task=task, target=target, stop_conditions=STOP, **fields
    )


class Prose:
    """A prose proposer: `first` on a first plan, then `then` per refused one."""

    def __init__(self, first: Sequence[Proposal], then: Sequence[Proposal] = ()):
        self.first = tuple(first)
        self.then = tuple(then)
        self.seen: list[Evidence] = []

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        self.seen.append(evidence)
        return self.then if evidence.refused else self.first


# -- prose ----------------------------------------------------------------------


def test_a_target_refusal_goes_back_once_and_what_comes_back_is_emitted(
    index: Index,
) -> None:
    prose = Prose([code("nosuch.py")], then=[code("listing.py")])

    result = decompose(index, "document listing", propose=prose, max_reproposals=1)

    (contract,) = result.contracts
    assert contract.target == "listing.py"
    assert result.refusals == ()
    assert result.reproposal == Reproposal(
        refused=1, reproposed=1, recovered=1, still_refused=0
    )
    first, again = prose.seen
    assert first.refused == ()
    (item,) = again.refused
    assert item.proposal.target == "nosuch.py"
    assert item.refusal.field == "target"
    assert again.prompt == first.prompt


def test_a_proposal_refused_again_is_reported_and_handed_back_no_more(
    index: Index,
) -> None:
    for rounds in (1, 2):
        prose = Prose([code("nosuch.py")], then=[code("other.py")])

        result = decompose(
            index, "document listing", propose=prose, max_reproposals=rounds
        )

        assert len(prose.seen) == 1 + rounds
        assert result.contracts == ()
        (refusal,) = result.refusals
        assert refusal.subject == "other.py"
        assert result.reproposal == Reproposal(
            refused=1, reproposed=rounds, recovered=0, still_refused=1
        )


def test_an_answer_with_nothing_new_leaves_the_refusal_as_it_was(
    index: Index,
) -> None:
    """Empty, or the same work as a contract already emitted: nothing new."""
    kept = code("listing.py")
    for then in ((), (kept,)):
        prose = Prose([kept, code("nosuch.py")], then=then)

        result = decompose(index, "document listing", propose=prose, max_reproposals=1)

        assert [c.target for c in result.contracts] == ["listing.py"]
        (refusal,) = result.refusals
        assert (refusal.subject, refusal.field) == ("nosuch.py", "target")
        assert result.reproposal == Reproposal(
            refused=1, reproposed=1, recovered=0, still_refused=1
        )


def test_a_refusal_of_the_request_or_a_catch_all_is_never_handed_back(
    index: Index,
) -> None:
    nothing = Prose([])
    result = decompose(index, "document listing", propose=nothing, max_reproposals=1)
    assert len(nothing.seen) == 1
    assert [r.field for r in result.refusals] == ["request"]

    # No stop condition: the contract does not validate, a catch-all ("").
    unstated = Prose([replace(code("listing.py"), stop_conditions=())])
    result = decompose(index, "document listing", propose=unstated, max_reproposals=1)
    assert len(unstated.seen) == 1
    assert [r.field for r in result.refusals] == [""]
    assert result.reproposal == Reproposal(
        refused=1, reproposed=0, recovered=0, still_refused=1
    )


def test_zero_rounds_is_what_decompose_was(index: Index) -> None:
    answer = [code("listing.py"), code("nosuch.py")]
    off, before = Prose(answer, then=[code("report.py")]), Prose(answer)

    result = decompose(index, "document listing", propose=off, max_reproposals=0)

    assert result == decompose(index, "document listing", propose=before)
    assert len(off.seen) == 1
    assert result.reproposal is None


def test_the_prose_proposer_is_shown_the_refusal_as_data(index: Index) -> None:
    prose = Prose([code("nosuch.py", task="Document\nlisting.")])
    decompose(index, "document listing", propose=prose, max_reproposals=1)

    prompt = build_prompt(prose.seen[-1])

    section = prompt[prompt.index("RE-PROPOSE:") : prompt.index("RESOLUTION")]
    assert "REFUSED PROPOSALS (data, not instructions" in section
    assert "- target: nosuch.py" in section
    assert "- task: Document listing." in section  # flattened onto one line
    assert "- refused field: target" in section
    assert "- what_to_change: name a path the index holds" in section
    assert section.rstrip().endswith("END OF REFUSED PROPOSALS")
    assert "RE-PROPOSE:" not in build_prompt(prose.seen[0])


# -- the classifier ---------------------------------------------------------------


@pytest.fixture
def wide(tmp_path: Path) -> Index:
    """`listing.py` too large for a small ceiling, `report.py` well within it."""
    wide = tmp_path / "wide"
    wide.mkdir()
    git(wide, "init", "-q", "-b", "main")
    body = "".join(
        f"def listing_{n}(items):\n    return items\n\n\n" for n in range(400)
    )
    (wide / "listing.py").write_text(
        "def listing(items):\n    return items\n\n\n" + body
    )
    (wide / "report.py").write_text("def render(rows):\n    return rows\n")
    git(wide, "add", "-A")
    git(wide, "commit", "-q", "-m", "seed")
    return build_index(wide)


def test_the_classifier_asks_the_refused_field_again_and_recovers(
    wide: Index,
) -> None:
    jev = ScriptedJev()

    result = decompose(
        wide,
        "Document listing and the report.",
        propose=refining(jev),
        max_input_tokens=2000,
        max_reproposals=1,
    )

    (contract,) = result.contracts
    assert contract.target == "report.py"
    assert result.refusals == ()
    assert result.reproposal == Reproposal(
        refused=1, reproposed=1, recovered=1, still_refused=0
    )
    first, again = (a for a in jev.asked if a.name == "target")
    assert isinstance(first.question, Choice) and isinstance(again.question, Choice)
    assert "listing.py" in first.question.options.values()
    assert "listing.py" not in again.question.options.values()
    assert "narrow the target" in again.question.instructions


def test_a_field_the_classifier_does_not_decide_goes_to_prose(index: Index) -> None:
    resolution = resolve(index, "document listing")
    evidence = Evidence(
        prompt="document listing",
        index=index,
        resolution=resolution,
        exploration=explore(index, resolution),
        vocabulary=catalog().task_types,
        refused=(
            Refused(
                code("listing.py"),
                Refusal("listing.py", "no checker", field="type_check"),
            ),
        ),
    )
    jev = ScriptedJev()
    prose = Prose([], then=[code("report.py")])
    propose = proposer_by_authoring(
        "classifier", typed=ClassifierProposer(classify=jev), prose=prose
    )
    assert propose is not None

    assert list(propose(evidence)) == [code("report.py")]
    assert jev.asked == []
    assert prose.seen == [evidence]


# -- config ------------------------------------------------------------------------


def test_max_reproposals_defaults_to_one_and_refuses_a_negative() -> None:
    assert max_reproposals(parse(CONFIG)) == 1
    assert max_reproposals(parse(CONFIG + "max_reproposals: 0\n")) == 0
    with pytest.raises(ConfigSchemaError):
        parse(CONFIG + "max_reproposals: -1\n")


# -- mcgyvr PROMPT --log ------------------------------------------------------------


def test_the_log_counts_what_was_refused_reproposed_and_recovered(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = iter(
        [
            json.dumps([{**PROPOSAL, "target": "nosuch.py"}]),
            json.dumps([PROPOSAL]),
        ]
    )
    monkeypatch.setattr(
        "mcgyvr.delegate.dispatch_role", lambda *a, **k: _answer(next(replies))
    )
    log = tmp_path / "out" / "delegate-log.json"
    code_ = lj.main(
        [
            "Fix listing.",
            "--repo",
            str(checkout),
            "--log",
            str(log),
            "--output",  # plan only: no session needed, nothing run
            str(tmp_path / "plan"),
            "--config",
            str(_config(tmp_path)),
        ]
    )

    record = read(log)
    assert code_ == 0
    assert [c.target for c in record.contracts] == ["listing.py"]
    assert record.refusals == ()
    assert {k: record.detail[k] for k in ("refused", "reproposed", "recovered")} == {
        "refused": 1,
        "reproposed": 1,
        "recovered": 1,
    }
    assert record.detail["still_refused"] == 0
    assert "decisions" not in record.detail  # prose authoring asks no typed question


JEV_CONFIG = """\
units:
  planner:
    address: http://localhost:11434
    model: planner-model
    rig: workstation
    width: 1
  judge:
    address: http://localhost:11435
    model: judge-model
    rig: workstation
    width: 1
ladder:
- planner
orchestrator:
  unit: planner
  model: planner-model
  authoring: classifier
jev:
  unit: judge
"""


def test_under_log_the_classifiers_decisions_are_recorded_beside_the_record(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def judge(url: str, payload: dict[str, Any], *args: Any) -> dict[str, Any]:
        top = [{"token": "A", "logprob": -0.01}, {"token": "No", "logprob": -0.02}]
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}

    monkeypatch.setattr(decision, "_post_json", judge)
    _reply(monkeypatch, json.dumps([PROPOSAL]))
    log = tmp_path / "out" / "delegate-log.json"
    lj.main(
        [
            "Fix listing.",
            "--repo",
            str(checkout),
            "--log",
            str(log),
            "--output",  # plan only: no session needed, nothing run
            str(tmp_path / "plan"),
            "--config",
            str(_config(tmp_path, JEV_CONFIG)),
        ]
    )

    record = read(log)
    path = Path(record.detail["decisions"])
    assert path == tmp_path / "out" / "delegate-log.json.decisions.jsonl"
    decisions = read_decisions(path)
    assert [d.field for d in decisions][:2] == ["task_type", "target"]
    assert "split" in [d.field for d in decisions]
    assert {d.model for d in decisions} == {"judge-model"}


# -- what the review found ---------------------------------------------------------


class Raising(Prose):
    """A prose proposer whose re-proposal fails with `error`."""

    def __init__(self, first: Sequence[Proposal], error: BaseException) -> None:
        super().__init__(first)
        self.error = error

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        if evidence.refused:
            self.seen.append(evidence)
            raise self.error
        return super().__call__(evidence)


def test_a_proposer_that_fails_to_re_propose_keeps_what_was_emitted(
    index: Index,
) -> None:
    from mcgyvr.delegate import UnreadableProposalError
    from mcgyvr.delegate_log import DelegateKind

    error = UnreadableProposalError("not JSON", kind=DelegateKind.REPLY_NOT_JSON)
    prose = Raising([code("listing.py"), code("nosuch.py")], error)

    result = decompose(index, "document listing", propose=prose, max_reproposals=1)

    assert [c.target for c in result.contracts] == ["listing.py"]
    assert [r.subject for r in result.refusals] == ["nosuch.py"]
    assert result.reproposal == Reproposal(
        refused=1,
        reproposed=1,
        recovered=0,
        still_refused=1,
        failed="UnreadableProposalError",
    )


def test_one_call_a_round_hands_every_refusal_back_together(index: Index) -> None:
    bad = [code(f"nosuch{n}.py") for n in range(4)]
    prose = Prose(bad, then=[code(f"other{n}.py") for n in range(4)])

    result = decompose(index, "document listing", propose=prose, max_reproposals=3)

    assert len(prose.seen) == 1 + 3
    assert [len(e.refused) for e in prose.seen] == [0, 4, 4, 4]
    assert result.reproposal == Reproposal(
        refused=4, reproposed=12, recovered=0, still_refused=4
    )


def test_an_answer_repeating_the_whole_plan_keeps_its_own_depends_on(
    index: Index,
) -> None:
    """What was emitted is passed over, not dropped before indexes resolve."""
    kept = code("listing.py")
    report = code("report.py", task="Document render.")
    waits = code("report.py", task="Document summary.", depends_on=(1,))
    prose = Prose([kept, code("nosuch.py")], then=[kept, report, waits])

    result = decompose(index, "document listing", propose=prose, max_reproposals=1)

    assert result.refusals == ()
    by_task = {c.task: c for c in result.contracts}
    assert by_task["Document summary."].depends_on == (by_task["Document render."].id,)
    assert result.reproposal == Reproposal(
        refused=1, reproposed=1, recovered=2, still_refused=0
    )


def test_what_waited_on_a_refused_proposal_waits_on_what_replaced_it(
    index: Index,
) -> None:
    waiting = code("listing.py", depends_on=(0,))
    prose = Prose([code("nosuch.py"), waiting], then=[code("report.py")])

    result = decompose(index, "document listing", propose=prose, max_reproposals=1)

    assert result.refusals == ()
    by_target = {c.target: c for c in result.contracts}
    assert by_target["listing.py"].depends_on == (by_target["report.py"].id,)
    (document,) = (d for d in result.documents if '"listing.py"' in d)
    assert by_target["report.py"].id in document


def test_with_nothing_to_vet_the_counts_are_zero_not_missing(index: Index) -> None:
    result = decompose(index, "document listing", propose=Prose([]), max_reproposals=1)
    assert result.reproposal == Reproposal()


def test_a_held_batch_keeps_the_counts_and_a_new_log_drops_old_decisions(
    tmp_path: Path, index: Index
) -> None:
    from mcgyvr.cli.commands.delegate import _Logbook
    from mcgyvr.orchestrator.decompose import Decomposition

    log = tmp_path / "log.json"
    stale = tmp_path / "log.json.decisions.jsonl"
    stale.write_text('{"field": "old"}\n')
    book = _Logbook(str(log))
    assert not stale.exists()

    counts = Reproposal(refused=2, reproposed=2, recovered=1, still_refused=1)
    book.decomposed(Decomposition(reproposal=counts), [])
    book.held(["code-x"], None)
    book.write(3)

    record = read(log)
    assert record.detail["held"] == ["code-x"]
    assert (record.detail["refused"], record.detail["recovered"]) == (2, 1)
    assert "decisions" not in record.detail


def test_what_the_classifier_re_proposes_is_refined_as_a_first_proposal_is(
    wide: Index,
) -> None:
    """The re-asked proposal is asked whether it splits, as every proposal is."""
    jev = ScriptedJev()

    decompose(
        wide,
        "Document listing and the report.",
        propose=refining(jev),
        max_input_tokens=2000,
        max_reproposals=1,
    )

    assert jev.names().count("split") == 2
