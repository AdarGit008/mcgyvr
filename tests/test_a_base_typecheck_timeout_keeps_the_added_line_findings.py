"""I-57 — a base re-run that times out must not throw away what the diff was charged.

:class:`~mcgyvr.gate.typecheck.TypeCheck` charges a diagnostic on a line the worker
added to the change outright, and re-runs the checker on the base tree only for
the diagnostics elsewhere in the touched files. When that base re-run runs out of
time, the off-diff diagnostics cannot be compared and are left out, with an
environment note, but the added-line ones still reject: they never needed the base.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.gate import ChangeSet, Gate, GateResult
from mcgyvr.gate.adapter import HostRunner
from mcgyvr.gate.typecheck import TypeCheck
from tests._helpers import git

#: A fault already at the base commit, on line 2: off the lines the worker adds.
INHERITED = """def count(rows: list[int]) -> int:
    return rows
"""

#: The worker's lines, appended below the inherited fault: line 6 is mistyped.
ADDED_MISTYPED = """

def total(rows: list[int]) -> str:
    return sum(rows)
"""

#: Appended lines that type-check, so only the inherited fault is reported.
ADDED_CLEAN = """

def total(rows: list[int]) -> int:
    return sum(rows)
"""


class _BaseRunOutOfTime(HostRunner):
    """Runs the checker over the worker's tree; the re-run on the base never ends."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def run(
        self,
        tool: str,
        args: Sequence[str],
        cwd: Path,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if cwd != self.repo:
            raise subprocess.TimeoutExpired([tool, *args], timeout or 0.0)
        return super().run(tool, args, cwd, timeout=timeout)


def _with_inherited_fault(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[tool.mypy]\npython_version = "3.12"\n', encoding="utf-8"
    )
    (repo / "src" / "pkg" / "count.py").write_text(INHERITED, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "declare mypy, with a fault already in count.py")


def _worker_appended(repo: Path, lines: str) -> ChangeSet:
    path = repo / "src" / "pkg" / "count.py"
    path.write_text(INHERITED + lines, encoding="utf-8")
    return ChangeSet.detect(repo, git(repo, "rev-parse", "HEAD").strip())


def _gate(repo: Path, changed: ChangeSet) -> GateResult:
    return Gate().run(
        changed, typecheck=TypeCheck(repo=repo, runner=_BaseRunOutOfTime(repo))
    )


def test_a_type_error_on_an_added_line_rejects_when_the_base_rerun_times_out(
    repo: Path,
) -> None:
    _with_inherited_fault(repo)
    changed = _worker_appended(repo, ADDED_MISTYPED)

    result = _gate(repo, changed)

    assert not result.accepted, (
        "a type error on a line the worker added was accepted because the base "
        "re-run timed out"
    )
    assert [(f.path, f.line) for f in result.findings] == [("src/pkg/count.py", 6)], (
        "only the added line's fault is charged: the inherited one on line 2 could "
        f"not be compared with the base and must not be: {result.findings}"
    )
    assert any(
        "typecheck base re-run" in issue for issue in result.environment_issues
    ), (
        "the base re-run's timeout was not reported, so the skipped comparison "
        f"looks complete: {result.environment_issues}"
    )


def test_an_inherited_fault_alone_is_not_charged_when_the_base_rerun_times_out(
    repo: Path,
) -> None:
    _with_inherited_fault(repo)
    changed = _worker_appended(repo, ADDED_CLEAN)

    result = _gate(repo, changed)

    assert result.accepted, (
        "a fault the worker did not write was charged to them because the base "
        f"re-run that would have cleared it timed out: {result.findings}"
    )
    assert any(
        "typecheck base re-run" in issue for issue in result.environment_issues
    ), f"the base re-run's timeout was not reported: {result.environment_issues}"
