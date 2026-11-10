"""A refused proposal goes to the top rung once, then is reported (I-30b).

Vetting refuses a proposal it cannot state as a runnable contract and says
which field to change and how. With `max_reproposals` above 0, `decompose`
hands every such refusal to `fix` — on `mcgyvr PROMPT`, the top rung of the
ladder (`delegate.top_rung_proposer_for`) — together, one call a round, on the
evidence's `refused`; the top rung is shown each refused proposal, field by
field, and its refusal as data and asked for it corrected and nothing else.
The proposer that made it — the scaffold, Jev's fill or the prose unit — is
never asked again. What comes back is vetted as a first answer is; what is
still refused is reported, never handed over past the bound. A refusal of the
request, or a catch-all, is never handed over, and 0 rounds is what
`decompose` was before. `mcgyvr PROMPT --log` counts what happened and names
the rung that was asked. `mcgyvr direct` asks nobody: a contract its author
wrote that vetting refuses goes back to the author.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr.cli.commands import delegate as command
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.contract import Contract, dumps
from mcgyvr.decision_log import read as read_decisions
from mcgyvr.decompose.decompose import (
    Decomposition,
    Evidence,
    Proposal,
    Reproposal,
    decompose,
)
from mcgyvr.delegate import build_prompt, deterministic_proposer
from mcgyvr.delegate_log import DelegateKind, read
from mcgyvr.repo.index import Index, build_index
from mcgyvr.repropose import max_reproposals
from mcgyvr.scope import Scope
from tests import livejournal as lj
from tests.refines import ScriptedJev, git, refining, repository
from tests.test_delegate_log_names_every_way_delegate_ends import (
    CONFIG,
    PROPOSAL,
    UNBOUND,
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
    """A proposer that answers `first`, and is never to be handed a refusal."""

    def __init__(self, first: Sequence[Proposal]):
        self.first = tuple(first)
        self.seen: list[Evidence] = []

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        assert not evidence.refused, "a proposer is never asked to redo its refusals"
        self.seen.append(evidence)
        return self.first


class Fixer:
    """The top rung: answers `then` to each round of refusals it is handed."""

    def __init__(self, then: Sequence[Proposal] = ()):
        self.then = tuple(then)
        self.seen: list[Evidence] = []

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        assert evidence.refused, "the top rung is asked only to fix a refusal"
        self.seen.append(evidence)
        return self.then


# -- decompose ------------------------------------------------------------------


def test_a_refusal_goes_to_the_top_rung_once_and_what_comes_back_is_emitted(
    index: Index,
) -> None:
    prose, fixer = Prose([code("nosuch.py")]), Fixer([code("listing.py")])

    result = decompose(
        index, "document listing", propose=prose, fix=fixer, max_reproposals=1
    )

    (contract,) = result.contracts
    assert contract.target == "listing.py"
    assert result.refusals == ()
    assert result.reproposal == Reproposal(
        refused=1, reproposed=1, recovered=1, still_refused=0
    )
    (first,) = prose.seen
    assert first.refused == ()
    (again,) = fixer.seen
    (item,) = again.refused
    assert item.proposal.target == "nosuch.py"
    assert item.refusal.field == "target"
    assert again.prompt == first.prompt


def test_a_proposal_refused_again_is_dropped_with_its_refusal_after_the_bound(
    index: Index,
) -> None:
    for rounds in (1, 2):
        prose, fixer = Prose([code("nosuch.py")]), Fixer([code("other.py")])

        result = decompose(
            index, "document listing", propose=prose, fix=fixer, max_reproposals=rounds
        )

        assert len(prose.seen) == 1
        assert len(fixer.seen) == rounds
        assert result.contracts == ()
        (refusal,) = result.refusals
        assert refusal.subject == "other.py"
        assert refusal.what_to_change
        assert result.reproposal == Reproposal(
            refused=1, reproposed=rounds, recovered=0, still_refused=1
        )


def test_an_answer_with_nothing_new_leaves_the_refusal_as_it_was(
    index: Index,
) -> None:
    """Empty, or the same work as a contract already emitted: nothing new."""
    kept = code("listing.py")
    for then in ((), (kept,)):
        prose, fixer = Prose([kept, code("nosuch.py")]), Fixer(then)

        result = decompose(
            index, "document listing", propose=prose, fix=fixer, max_reproposals=1
        )

        assert [c.target for c in result.contracts] == ["listing.py"]
        (refusal,) = result.refusals
        assert (refusal.subject, refusal.field) == ("nosuch.py", "target")
        assert result.reproposal == Reproposal(
            refused=1, reproposed=1, recovered=0, still_refused=1
        )


def test_a_refusal_of_the_request_or_a_catch_all_is_never_handed_over(
    index: Index,
) -> None:
    fixer = Fixer([code("listing.py")])
    result = decompose(
        index, "document listing", propose=Prose([]), fix=fixer, max_reproposals=1
    )
    assert [r.field for r in result.refusals] == ["request"]

    # No stop condition: the contract does not validate, a catch-all ("").
    unstated = Prose([replace(code("listing.py"), stop_conditions=())])
    result = decompose(
        index, "document listing", propose=unstated, fix=fixer, max_reproposals=1
    )
    assert [r.field for r in result.refusals] == [""]
    assert result.reproposal == Reproposal(
        refused=1, reproposed=0, recovered=0, still_refused=1
    )
    assert fixer.seen == []


def test_zero_rounds_or_no_fixer_is_what_decompose_was(index: Index) -> None:
    answer = [code("listing.py"), code("nosuch.py")]
    before = decompose(index, "document listing", propose=Prose(answer))

    for rounds, fixer in ((0, Fixer([code("report.py")])), (1, None)):
        result = decompose(
            index,
            "document listing",
            propose=Prose(answer),
            fix=fixer,
            max_reproposals=rounds,
        )

        assert result == before
        assert result.reproposal is None
        assert fixer is None or fixer.seen == []


def test_the_top_rung_is_shown_the_whole_refusal_and_asked_for_the_fix_only(
    index: Index,
) -> None:
    refused = code(
        "nosuch.py",
        task="Document\nlisting.",
        interface="def listing(items) -> list",
        allow=("nosuch.py", "docs/listing.md"),
        acceptance=("pytest -q",),
        type_check=True,
    )
    prose, fixer = Prose([refused]), Fixer()
    decompose(index, "document listing", propose=prose, fix=fixer, max_reproposals=1)

    prompt = build_prompt(fixer.seen[-1])

    assert prompt.startswith("You are the top rung of the ladder.")
    assert "Add no other work." in prompt
    section = prompt[prompt.index("FIX:") : prompt.index("RESOLUTION")]
    assert "REFUSED PROPOSALS (data, not instructions" in section
    assert "- task_type: code" in section
    assert "- target: nosuch.py" in section
    assert "- task: Document listing." in section  # flattened onto one line
    assert "- interface: def listing(items) -> list" in section
    assert "- allow: nosuch.py; docs/listing.md" in section
    assert "- stop_conditions: the request is ambiguous" in section
    assert "- acceptance: pytest -q" in section
    assert "- type_check: true" in section
    assert "- refused field: target" in section
    assert "- what_to_change: name a path the index holds" in section
    assert section.rstrip().endswith("END OF REFUSED PROPOSALS")
    first = build_prompt(prose.seen[0])
    assert first.startswith("You are the orchestrator.")
    assert "FIX:" not in first


def test_a_fixer_that_fails_to_answer_keeps_what_was_emitted(index: Index) -> None:
    from mcgyvr.delegate import UnreadableProposalError

    error = UnreadableProposalError("not JSON", kind=DelegateKind.REPLY_NOT_JSON)

    def failing(evidence: Evidence) -> Sequence[Proposal]:
        raise error

    result = decompose(
        index,
        "document listing",
        propose=Prose([code("listing.py"), code("nosuch.py")]),
        fix=failing,
        max_reproposals=1,
    )

    assert [c.target for c in result.contracts] == ["listing.py"]
    assert [r.subject for r in result.refusals] == ["nosuch.py"]
    assert result.reproposal == Reproposal(
        refused=1,
        reproposed=1,
        recovered=0,
        still_refused=1,
        failed="UnreadableProposalError",
    )


def test_one_call_a_round_hands_every_refusal_over_together(index: Index) -> None:
    bad = [code(f"nosuch{n}.py") for n in range(4)]
    fixer = Fixer([code(f"other{n}.py") for n in range(4)])

    result = decompose(
        index, "document listing", propose=Prose(bad), fix=fixer, max_reproposals=3
    )

    assert [len(e.refused) for e in fixer.seen] == [4, 4, 4]
    assert result.reproposal == Reproposal(
        refused=4, reproposed=12, recovered=0, still_refused=4
    )


def test_an_answer_repeating_the_whole_proposal_keeps_its_own_depends_on(
    index: Index,
) -> None:
    """What was emitted is passed over, not dropped before indexes resolve."""
    kept = code("listing.py")
    report = code("report.py", task="Document render.")
    waits = code("report.py", task="Document summary.", depends_on=(1,))
    fixer = Fixer([kept, report, waits])

    result = decompose(
        index,
        "document listing",
        propose=Prose([kept, code("nosuch.py")]),
        fix=fixer,
        max_reproposals=1,
    )

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

    result = decompose(
        index,
        "document listing",
        propose=Prose([code("nosuch.py"), waiting]),
        fix=Fixer([code("report.py")]),
        max_reproposals=1,
    )

    assert result.refusals == ()
    by_target = {c.target: c for c in result.contracts}
    assert by_target["listing.py"].depends_on == (by_target["report.py"].id,)
    (document,) = (d for d in result.documents if '"listing.py"' in d)
    assert by_target["report.py"].id in document


def test_with_nothing_to_vet_the_counts_are_zero_not_missing(index: Index) -> None:
    result = decompose(
        index, "document listing", propose=Prose([]), fix=Fixer(), max_reproposals=1
    )
    assert result.reproposal == Reproposal()


# -- the scaffold and Jev's fill ---------------------------------------------------


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


def test_jev_is_not_asked_again_and_the_top_rung_fixes_its_refusal(
    wide: Index,
) -> None:
    jev = ScriptedJev()
    fixer = Fixer([code("report.py")])

    result = decompose(
        wide,
        "Document listing and the report.",
        propose=refining(jev),
        fix=fixer,
        max_input_tokens=2000,
        max_reproposals=1,
    )

    (contract,) = result.contracts
    assert contract.target == "report.py"
    assert result.refusals == ()
    assert result.reproposal == Reproposal(
        refused=1, reproposed=1, recovered=1, still_refused=0
    )
    assert jev.names().count("target") == 1
    (asked,) = fixer.seen
    (item,) = asked.refused
    assert item.proposal.target == "listing.py"
    # The fix is vetted, not split again: Jev is asked whether to split once.
    assert jev.names().count("split") == 1


def test_with_no_jev_the_scaffold_proposes_and_the_top_rung_fixes_its_refusal(
    wide: Index,
) -> None:
    fixer = Fixer([code("report.py")])

    result = decompose(
        wide,
        "Document listing and the report.",
        propose=deterministic_proposer(),
        fix=fixer,
        max_input_tokens=2000,
        max_reproposals=1,
    )

    assert [c.target for c in result.contracts] == ["report.py"]
    (asked,) = fixer.seen
    (item,) = asked.refused
    assert item.proposal.target == "listing.py"


# -- config ------------------------------------------------------------------------


def test_max_reproposals_defaults_to_one_and_refuses_a_negative() -> None:
    assert max_reproposals(parse(CONFIG)) == 1
    assert max_reproposals(parse(CONFIG + "max_reproposals: 0\n")) == 0
    with pytest.raises(ConfigSchemaError):
        parse(CONFIG + "max_reproposals: -1\n")


# -- mcgyvr PROMPT -----------------------------------------------------------------


def _prompt(tmp_path: Path, checkout: Path, config: Path, *extra: str) -> int:
    return lj.main(
        [
            "Fix listing.",
            "--repo",
            str(checkout),
            "--log",
            str(tmp_path / "out" / "delegate-log.json"),
            "--config",
            str(config),
            *extra,
        ]
    )


def _top_rung_answers(
    monkeypatch: pytest.MonkeyPatch, *replies: str
) -> list[tuple[str, str]]:
    """The top rung answers `replies` in turn; each call's rung and prompt is kept."""
    asked: list[tuple[str, str]] = []
    left = iter(replies)

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        asked.append((rung, request.prompt))
        return _answer(next(left))

    monkeypatch.setattr("mcgyvr.delegate.dispatch", fake_dispatch)
    return asked


def test_the_log_counts_the_fix_and_names_the_top_rung_asked(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([{**PROPOSAL, "target": "nosuch.py"}]))
    asked = _top_rung_answers(monkeypatch, json.dumps([PROPOSAL]))

    code_ = _prompt(
        tmp_path, checkout, _config(tmp_path), "--output", str(tmp_path / "plan")
    )

    record = read(tmp_path / "out" / "delegate-log.json")
    assert code_ == 0
    assert [c.target for c in record.contracts] == ["listing.py"]
    assert record.refusals == ()
    assert {
        k: record.detail[k]
        for k in ("refused", "reproposed", "recovered", "still_refused")
    } == {"refused": 1, "reproposed": 1, "recovered": 1, "still_refused": 0}
    assert (record.detail["fixer"], record.detail["fixer_model"]) == (
        "planner",
        "planner-model",
    )
    ((rung, prompt),) = asked
    assert rung == "planner"
    assert prompt.startswith("You are the top rung of the ladder.")
    assert "- target: nosuch.py" in prompt
    assert "decisions" not in record.detail  # prose authoring asks no typed question


def test_with_nothing_refused_the_top_rung_is_not_asked_or_named(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(monkeypatch, json.dumps([PROPOSAL]))
    asked = _top_rung_answers(monkeypatch)

    code_ = _prompt(
        tmp_path, checkout, _config(tmp_path), "--output", str(tmp_path / "plan")
    )

    record = read(tmp_path / "out" / "delegate-log.json")
    assert code_ == 0
    assert asked == []
    assert "fixer" not in record.detail


def test_no_jev_and_no_authoring_scaffolds_with_no_prose_model(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I-30a: the default needs no prose model; nothing is dispatched to plan."""

    def no_role(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no orchestrator model is asked")

    monkeypatch.setattr("mcgyvr.delegate.dispatch_role", no_role)
    asked = _top_rung_answers(monkeypatch)

    code_ = _prompt(
        tmp_path,
        checkout,
        _config(tmp_path, UNBOUND),
        "--output",
        str(tmp_path / "plan"),
    )

    record = read(tmp_path / "out" / "delegate-log.json")
    assert code_ == 0
    assert record.kind is DelegateKind.EMITTED
    assert [c.target for c in record.contracts] == ["listing.py"]
    assert asked == []


def test_a_refused_proposal_is_fixed_by_the_top_rung_and_dispatched(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Jev, no prose model: refused -> top rung once -> vetted -> dispatched."""

    def scaffold(config: Any, pool: Any, **kwargs: Any) -> Any:
        return lambda evidence: (code("nosuch.py"),)

    monkeypatch.setattr(command, "_proposer_for_delegate", scaffold)
    asked = _top_rung_answers(monkeypatch, json.dumps([PROPOSAL]))
    dispatched: list[Decomposition] = []

    def run_delegated(
        args: argparse.Namespace, root: Path, dec: Decomposition, *rest: Any, **kw: Any
    ) -> int:
        dispatched.append(dec)
        return 0

    monkeypatch.setattr(command, "_run_delegated", run_delegated)

    code_ = _prompt(tmp_path, checkout, _config(tmp_path, UNBOUND), "--session", "t-1")

    assert code_ == 0
    assert len(asked) == 1
    (dec,) = dispatched
    (contract,) = dec.contracts
    assert contract.target == "listing.py"
    assert dec.refusals == ()


def test_under_log_the_classifiers_decisions_are_recorded_beside_the_record(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def judge(url: str, payload: dict[str, Any], *args: Any) -> dict[str, Any]:
        top = [{"token": "A", "logprob": -0.01}, {"token": "No", "logprob": -0.02}]
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}

    monkeypatch.setattr(decision, "_post_json", judge)
    _reply(monkeypatch, json.dumps([PROPOSAL]))
    _prompt(
        tmp_path,
        checkout,
        _config(tmp_path, JEV_CONFIG),
        "--output",
        str(tmp_path / "plan"),
    )

    record = read(tmp_path / "out" / "delegate-log.json")
    path = Path(record.detail["decisions"])
    assert path == tmp_path / "out" / "delegate-log.json.decisions.jsonl"
    decisions = read_decisions(path)
    assert [d.field for d in decisions][:2] == ["task_type", "target"]
    assert "split" in [d.field for d in decisions]
    assert {d.model for d in decisions} == {"judge-model"}


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


def test_a_held_batch_keeps_the_counts_and_a_new_log_drops_old_decisions(
    tmp_path: Path,
) -> None:
    from mcgyvr.cli.commands.delegate import _Logbook

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


# -- mcgyvr direct -----------------------------------------------------------------


def test_direct_hands_a_refused_contract_back_to_its_author_and_asks_nobody(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def nobody(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("mcgyvr direct asks no model to fix a contract")

    monkeypatch.setattr("mcgyvr.delegate.dispatch", nobody)
    monkeypatch.setattr("mcgyvr.delegate.dispatch_role", nobody)
    written = tmp_path / "contracts" / "code-nosuch.json"
    written.parent.mkdir()
    written.write_text(
        dumps(
            Contract(
                id="code-nosuch",
                task_type="code",
                task="Document listing.",
                target="nosuch.py",
                scope=Scope.of(["nosuch.py"], []),
                stop_conditions=STOP,
            )
        )
    )
    log = tmp_path / "out" / "delegate-log.json"

    code_ = lj.main(
        [
            "direct",
            str(written),
            "--repo",
            str(checkout),
            "--log",
            str(log),
            "--config",
            str(_config(tmp_path)),
            "--session",
            "t-1",
        ]
    )

    record = read(log)
    assert code_ == 3
    assert record.kind is DelegateKind.NONE_EMITTED
    (refusal,) = record.refusals
    # The refusal names the author's own file, the field and what to change.
    assert (refusal.subject, refusal.field) == (str(written), "target")
    assert refusal.what_to_change
    assert "reproposed" not in record.detail
    assert "fixer" not in record.detail


# -- the re-plan of a spent contract ------------------------------------------------


def test_with_no_prose_model_the_top_rung_redoes_a_spent_contract(
    checkout: Path,
) -> None:
    """The re-plan needs a prose proposer; with none bound it is the top rung."""
    from mcgyvr.local_pool import source_map
    from mcgyvr.replan import Spent

    config = parse(UNBOUND)
    asked: list[str] = []

    def first(evidence: Evidence) -> Sequence[Proposal]:
        raise AssertionError("the first proposer does not re-plan")

    def top(evidence: Evidence) -> Sequence[Proposal]:
        asked.append("re-plan" if evidence.spent is not None else "fix")
        return (code("report.py", task="Document render."),)

    args = argparse.Namespace(budget=None, jobs=1)
    replan = command._replanner(args, checkout, config, source_map(config), first, top)
    spent = Contract(
        id="code-spent",
        task_type="code",
        task="Document listing.",
        target="listing.py",
        scope=Scope.of(["listing.py"], []),
        stop_conditions=STOP,
    )

    dec = replan(Spent(spent))

    assert asked == ["re-plan"]
    assert [c.target for c in dec.contracts] == ["report.py"]


def test_the_top_rung_is_sent_its_own_timeout_and_a_cut_off_reply_names_it(
    index: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real send path: the unit's own timeout, and a cut-off says who."""
    from mcgyvr.delegate import (
        OrchestratorReplyCutOffError,
        top_rung_proposer_for,
    )
    from mcgyvr.local_pool import source_map
    from mcgyvr.runner import StopReason

    config = parse(UNBOUND)
    pool = source_map(config)
    sent: list[Any] = []

    def cut_off(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append((rung, request))
        return _answer("[", StopReason.TRUNCATED)

    monkeypatch.setattr("mcgyvr.delegate.dispatch", cut_off)
    fixer = top_rung_proposer_for(config, pool)
    assert fixer is not None
    assert (fixer.rung, fixer.model) == ("planner", "planner-model")
    from mcgyvr.decompose.decompose import _evidence

    evidence = _evidence(index, "document listing")

    with pytest.raises(OrchestratorReplyCutOffError, match="the top rung's reply"):
        fixer(evidence)

    ((rung, request),) = sent
    assert rung == "planner"
    assert request.timeout_s == pool.bind("planner").request_timeout_s
    assert request.max_output_tokens is None
