"""Delivery judges a changed argument by the same setting as the sandbox.

The run command's delivery step does not take the sandbox's word for a change:
:func:`mcgyvr.deliver.place` and :func:`mcgyvr.deliver.deliver` run the gate
again over the bytes they are about to write. A setup that asked the gate to
``report`` or ``skip`` a function that changes its argument has to reach that
second gate too, or every change the sandbox accepted under it is refused where
it lands.

These drive the climb's own report step, :func:`mcgyvr.cli._report_climb`, with
an outcome bound in a real sandbox under the setup's setting, and the adapters
the run settled from the same setup (``args.gate_adapters``, settled once by
``_run`` for both paths). The floor's path is held end to end by
``tests/test_a_run_on_the_floor_leaves_a_change_the_setup_asked_the_gate_to_report.py``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract, loads
from mcgyvr.result import RunResult
from mcgyvr.sandbox.tempdir import TempDirSandbox

TARGET = "src/pkg/rows.py"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
"""

PLACEHOLDER = "def placeholder():\n    return None\n"

APPENDS = """
id: merge-rows
task_type: function_implementation
task: Add the extra row to the rows and return them.
interface: merge_into(rows, extra) returns the rows with extra at the end.
target: src/pkg/rows.py
stop_conditions:
  - The rows cannot hold the extra row.
acceptance: ["true"]
scope:
  allow: ["src/**"]
"""

MUTATES = "def merge_into(rows, extra):\n    rows.append(extra)\n    return rows\n"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_IDENTITY},
    )
    return done.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / TARGET).write_text(PLACEHOLDER, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _setup(mode: str) -> Config:
    return parse(FLEET, f"ladder: [cheap]\ngate:\n  param_mutation: {mode}\n")


def _report(contract: Contract) -> RunResult:
    return RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        target=contract.target,
        orchestrator="t",
    )


def _climb_and_report(
    repo: Path, mode: str, args: argparse.Namespace
) -> tuple[int, RunResult]:
    """Gate the change in a sandbox under ``mode``, then hand the accepted
    climb to the report step, as the run command does."""
    from mcgyvr import cli
    from mcgyvr.catalog import catalog
    from mcgyvr.deliver import Accepted
    from mcgyvr.drive import gate_in_sandbox
    from mcgyvr.escalate import Assurance, Delivered, Judgement
    from mcgyvr.route import Attempted, Verdict

    contract = loads(APPENDS)
    report = _report(contract)
    with TempDirSandbox(repo) as sandbox:
        result = gate_in_sandbox(contract, sandbox, MUTATES, config=_setup(mode))
        assert result.accepted, f"the sandbox refused under {mode}: {result}"
        bound = Accepted.read(repo=sandbox.workspace, contract=contract, result=result)
        outcome = Delivered(
            family=catalog().family("local"),
            rung="cheap",
            assurance=Assurance.UNVERIFIED,
            judgement=Judgement(verdict=Verdict.PASSED, accepted=bound),
            entered=(),
            history=(Attempted(rung="cheap", attempt=1, verdict=Verdict.PASSED),),
            attempts_spent=1,
            escalations=0,
        )
        code = cli._report_climb(args, contract, sandbox, repo, outcome, None, report)
    return code, report


def _settled(mode: str, *, commit: bool) -> argparse.Namespace:
    from mcgyvr.drive import gate_adapters

    return argparse.Namespace(commit=commit, gate_adapters=gate_adapters(_setup(mode)))


def _reported_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if "[PARAM-MUTATION]" in line]


@pytest.mark.parametrize("commit", [False, True], ids=["left", "committed"])
def test_a_change_accepted_under_report_lands_and_its_finding_is_printed_once(
    repo: Path, commit: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    code, report = _climb_and_report(repo, "report", _settled("report", commit=commit))
    printed = capsys.readouterr().out

    assert code == 0, f"delivery refused a change the setup asked to report: {report}"
    assert (repo / TARGET).read_text(encoding="utf-8") == MUTATES
    if commit:
        assert _git(repo, "show", f"HEAD:{TARGET}") == MUTATES
    lines = _reported_lines(printed)
    assert len(lines) == 1, printed
    assert f"{TARGET}:2" in lines[0], lines[0]
    assert "gate.param_mutation" in lines[0], lines[0]
    assert "report" in lines[0], lines[0]


def test_a_change_accepted_under_skip_lands_and_prints_no_finding(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, report = _climb_and_report(repo, "skip", _settled("skip", commit=False))
    printed = capsys.readouterr().out

    assert code == 0, f"delivery refused a change the setup asked to skip: {report}"
    assert (repo / TARGET).read_text(encoding="utf-8") == MUTATES
    assert _reported_lines(printed) == [], printed


def test_a_delivery_with_no_settled_adapters_is_refused_by_name(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A caller that never settled the gate's adapters is not delivered under a
    guess: the refusal names what is missing, and nothing is written."""
    code, report = _climb_and_report(repo, "report", argparse.Namespace(commit=False))
    capsys.readouterr()

    assert code == 1
    assert report.outcome == "error", report
    assert "gate_adapters" in report.detail, report.detail
    assert (repo / TARGET).read_text(encoding="utf-8") == PLACEHOLDER
