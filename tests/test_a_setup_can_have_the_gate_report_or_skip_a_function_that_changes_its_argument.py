"""A setup can have the gate report or skip a function that changes its argument.

``param-mutation`` (:mod:`mcgyvr.gate.typecheck`) rejects a Python function that
changes an object its caller passed in, and that stays the default.
``gate.param_mutation`` in ``policy.yaml`` lets the user turn it to ``report`` —
the finding is listed among the gate's observations and does not fail the
change — or to ``skip`` — the check does not run.

Every case goes through the driver's own gate call with a setup parsed from
text, because what could be missing is not the policy but the path from the
file to the rung. Three things hold under every setting: no other check is
relaxed, a contract that asks for in-place work stands the check down, and
``refuse`` judges exactly as a setup that says nothing.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest

from mcgyvr.config import Config, parse
from mcgyvr.contract import loads
from mcgyvr.gate import GateResult
from mcgyvr.gate.findings import Finding
from mcgyvr.sandbox.tempdir import TempDirSandbox

TARGET = "src/pkg/rows.py"
PARAM_MUTATION = "PARAM-MUTATION"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

#: An invented unit: nothing is dispatched, the gate only needs a setup to read.
FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
"""

PLACEHOLDER = "def placeholder():\n    return None\n"

#: A contract that asks for the rows back with one more, and does not say how.
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

#: The same shape of work, ordered in place in the contract's own words.
SORTS_IN_PLACE = """
id: sort-rows
task_type: function_implementation
task: Sort the rows in place.
interface: tidy(rows) sorts rows in place and returns None.
target: src/pkg/rows.py
stop_conditions:
  - The rows are not comparable to each other.
acceptance: ["true"]
scope:
  allow: ["src/**"]
"""

MUTATES = "def merge_into(rows, extra):\n    rows.append(extra)\n    return rows\n"

SORTS = "def tidy(rows):\n    rows.sort()\n"

#: The mutation beside a fault no setting speaks to: an import that cannot load.
MUTATES_AND_UNIMPORTABLE = (
    "from collections import Mapping\n"
    "\n"
    "\n"
    "def merge_into(rows, extra):\n"
    "    rows.append(extra)\n"
    "    return isinstance(rows, Mapping)\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository whose committed target changes nothing, so every line the
    worker writes is an added line the gate judges."""
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / TARGET).write_text(PLACEHOLDER, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _setup(mode: str | None) -> Config:
    policy = "ladder: [cheap]\n"
    if mode is not None:
        policy += f"gate:\n  param_mutation: {mode}\n"
    return parse(FLEET, policy)


def _judged(repo: Path, contract: str, source: str, mode: str | None) -> GateResult:
    from mcgyvr.drive import gate_in_sandbox

    config = _setup(mode)
    with TempDirSandbox(repo) as sandbox:
        return gate_in_sandbox(loads(contract), sandbox, source, config=config)


def _codes(findings: Iterable[Finding]) -> list[str | None]:
    return [f.code for f in findings]


@pytest.mark.parametrize("mode", [None, "refuse"], ids=["unset", "refuse"])
def test_a_setup_that_says_nothing_or_refuse_rejects_the_change(
    repo: Path, mode: str | None
) -> None:
    """The owner's default: the change is rejected, for the mutation."""
    result = _judged(repo, APPENDS, MUTATES, mode)

    assert not result.accepted, (
        "a function that appends to the list its caller passed in was accepted "
        "with the setting unset or at refuse"
    )
    assert PARAM_MUTATION in _codes(result.findings), result.findings


def test_report_accepts_the_change_and_lists_the_finding_among_observations(
    repo: Path,
) -> None:
    """Said out loud and not fatal: accepted, and the finding is still there."""
    result = _judged(repo, APPENDS, MUTATES, "report")

    assert result.accepted, (
        f"the setup said report and the gate still refused: {result.findings}"
    )
    assert PARAM_MUTATION not in _codes(result.findings), result.findings
    assert PARAM_MUTATION in _codes(result.observations), (
        f"the setup said report and the finding was not reported anywhere: "
        f"{result.observations}"
    )


def test_skip_accepts_the_change_and_lists_the_finding_nowhere(repo: Path) -> None:
    """Not checked: no finding and no observation for this family."""
    result = _judged(repo, APPENDS, MUTATES, "skip")

    assert result.accepted, f"the setup said skip and the gate refused: {result}"
    assert PARAM_MUTATION not in _codes(result.findings), result.findings
    assert PARAM_MUTATION not in _codes(result.observations), result.observations


@pytest.mark.parametrize("mode", ["report", "skip"])
def test_no_setting_relaxes_any_other_check(repo: Path, mode: str) -> None:
    """The setting speaks to one family; an import that cannot load still rejects."""
    result = _judged(repo, APPENDS, MUTATES_AND_UNIMPORTABLE, mode)

    assert not result.accepted, (
        f"under {mode}, a module that cannot be imported was accepted: {result}"
    )
    assert "UNIMPORTABLE" in _codes(result.findings), result.findings
    assert PARAM_MUTATION not in _codes(result.findings), result.findings


@pytest.mark.parametrize("mode", [None, "refuse", "report", "skip"])
def test_a_contract_asking_for_in_place_work_stands_the_check_down_in_every_mode(
    repo: Path, mode: str | None
) -> None:
    """A contract that ordered in-place work is satisfiable under every setting,
    and under report it is not reported either: nothing was done wrong."""
    result = _judged(repo, SORTS_IN_PLACE, SORTS, mode)

    assert result.accepted, (
        f"the contract ordered the sort in place and the gate refused it under "
        f"{mode}: {result.findings}"
    )
    assert PARAM_MUTATION not in _codes(result.observations), result.observations


def test_refuse_judges_exactly_as_a_setup_that_says_nothing(repo: Path) -> None:
    """Writing the default out changes nothing about the verdict or its words."""
    unset = _judged(repo, APPENDS, MUTATES, None)
    refuse = _judged(repo, APPENDS, MUTATES, "refuse")

    assert unset.accepted == refuse.accepted
    assert [str(f) for f in unset.findings] == [str(f) for f in refuse.findings]
    assert [str(f) for f in unset.observations] == [str(f) for f in refuse.observations]
