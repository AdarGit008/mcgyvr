"""D2 — ``show_absolute_path = true`` must not silently disable the type-check rung.

:class:`~mcgyvr.gate.typecheck.TypeCheck` matched a checker's reported path
against the change set's paths as raw strings. mypy configured with
``show_absolute_path = true`` reports the *absolute* path to each changed file,
which never equals the repository-relative path the change set keys on — so every
diagnostic is dropped and the rung reports clean over a change it actually
rejected. A worker can ship a module that does not type-check and the gate says
nothing asked.

The fix normalises the reported path to the repository-relative form before
matching, so both spellings land on the same line.
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


def _declare_mypy(repo: Path, extra: str = "") -> None:
    (repo / "pyproject.toml").write_text(
        '[tool.mypy]\npython_version = "3.12"\n' + extra,
        encoding="utf-8",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "declare mypy")


def _worker_wrote(repo: Path, source: str) -> ChangeSet:
    (repo / "src" / "pkg" / "count.py").write_text(source, encoding="utf-8")
    return ChangeSet.detect(repo, git(repo, "rev-parse", "HEAD").strip())


def test_an_absolute_path_still_lands_on_the_workers_line(repo: Path) -> None:
    """A checker that reports absolute paths must still reject a mistyped change."""
    _declare_mypy(repo, extra="show_absolute_path = true\n")
    changed = _worker_wrote(repo, MISTYPED)

    result = Gate().run(changed, typecheck=_typecheck()(repo))

    assert not result.accepted, (
        "a mistyped change was accepted: mypy reported absolute paths, and the "
        "type-check rung dropped every one of them as unattributable"
    )
    assert any(f.path.endswith("count.py") for f in result.findings), (
        f"the change was rejected, but nothing points at the mistyped file: "
        f"{result.findings}"
    )
