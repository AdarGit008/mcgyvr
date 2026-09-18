"""R9 — a type-check timeout must not be a verdict on the worker.

A checker that times out on a loaded machine and finishes on a quiet one would make
the verdict a verdict on the machine, not on the change.
:class:`~mcgyvr.gate.typecheck.TypeCheck` treats a timeout as an environment issue:
the rung is skipped and the skip is reported, the way a missing checker is, rather
than turned into a rejection of the worker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.gate import ChangeSet, Gate
from tests.red_port.conftest import git, required

TYPECHECK = "run the type checker a repository declared, over the lines a worker added"

MISTYPED = """def count(rows: list[int]) -> int:
    return rows
"""


def _typecheck() -> Any:
    return required(
        TYPECHECK,
        lambda: __import__("mcgyvr.gate.typecheck", fromlist=["TypeCheck"]).TypeCheck,
    )


def _declare_mypy(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[tool.mypy]\npython_version = "3.12"\n', encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "declare mypy")


def _worker_wrote(repo: Path, source: str) -> ChangeSet:
    (repo / "src" / "pkg" / "count.py").write_text(source, encoding="utf-8")
    return ChangeSet.detect(repo, git(repo, "rev-parse", "HEAD").strip())


def test_a_typecheck_timeout_does_not_reject_the_change(repo: Path) -> None:
    """A checker that runs out of budget skips the rung; it does not fail the worker."""
    _declare_mypy(repo)
    changed = _worker_wrote(repo, MISTYPED)

    # A timeout so short the real mypy cannot finish: the rung is forced onto
    # its timeout path without a mock, so what is asserted is the path itself.
    result = Gate().run(changed, typecheck=_typecheck()(repo, timeout=0.001))

    assert result.accepted, (
        f"a type-check timeout rejected the change: {result.inconclusive}"
    )
    assert any("typecheck" in issue.lower() for issue in result.environment_issues), (
        "the timeout was not reported as an environment issue, so a skipped "
        f"rung looks clean: {result.environment_issues}"
    )
