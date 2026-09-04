"""A result never says ``accepted`` for a change that was not written.

``_report_run`` set ``outcome = "accepted"`` the moment the gate accepted,
before ``Accepted.read`` bound the bytes; a ``DeliveryError`` there went
through ``_error``, which kept the outcome and set the exit code to 1. The
file then read ``outcome: accepted, exit_code: 1, committed: false`` with
nothing in the target — and the skill tells the agent that ``accepted``
means the change is in ``target``. The climb path's ``bound is None`` branch
had the same shape. ``_error`` now names the outcome it is reporting under,
``error`` unless the caller says otherwise, so a run that ended in
``_error`` is never filed as accepted.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mcgyvr.contract import load
from mcgyvr.deliver import Accepted, DeliveryError
from mcgyvr.gate import GateResult
from mcgyvr.result import RunResult
from mcgyvr.sandbox.base import Sandbox
from tests import livejournal as lj


def _report(contract: Any) -> RunResult:
    return RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        target=contract.target,
        orchestrator="t",
    )


def test_a_gate_that_accepted_but_could_not_bind_is_an_error_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli

    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    report = _report(contract)

    def unbindable(**_: Any) -> Accepted:
        raise DeliveryError("src/pkg/messy.py is a symlink; not read through")

    monkeypatch.setattr(Accepted, "read", unbindable)
    sandbox = cast(
        Sandbox, SimpleNamespace(workspace=repo, source_base_commit=lambda: "HEAD")
    )
    args = argparse.Namespace(commit=False)

    code = cli._report_run(args, contract, sandbox, repo, GateResult(), report)

    assert code == 1
    assert report.outcome == "error", report
    assert "symlink" in report.detail
    assert "error: " in capsys.readouterr().err
    assert (repo / "src/pkg/messy.py").read_text() == "x = 0\n"


def test_a_climb_accepted_without_bound_content_is_an_error_not_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli
    from mcgyvr.catalog import catalog
    from mcgyvr.escalate import Assurance, Delivered, Judgement
    from mcgyvr.route import Attempted, Verdict

    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    report = _report(contract)
    outcome = Delivered(
        family=catalog().family("local"),
        rung="local_qwen-7b",
        assurance=Assurance.UNVERIFIED,
        judgement=Judgement(verdict=Verdict.PASSED, policy="none"),
        entered=(),
        history=(Attempted(rung="local_qwen-7b", attempt=1, verdict=Verdict.PASSED),),
        attempts_spent=1,
        escalations=0,
    )
    sandbox = cast(
        Sandbox, SimpleNamespace(workspace=repo, source_base_commit=lambda: "HEAD")
    )

    code = cli._report_climb(
        argparse.Namespace(commit=False), contract, sandbox, repo, outcome, None, report
    )

    assert code == 1
    assert report.outcome == "error", report
    assert "without bound content" in report.detail
    capsys.readouterr()


def test_error_keeps_a_refusal_word_the_caller_chose() -> None:
    from mcgyvr import cli

    report = RunResult(contract="c", task_type="format", target="t", orchestrator="o")
    assert cli._error(report, "no", outcome=cli.DELIVERY_REFUSED) == 1
    assert report.outcome == cli.DELIVERY_REFUSED
    assert cli._error(report, "no") == 1
    assert report.outcome == "error"
