"""A checker run on the host writes no cache where the workspace points it.

The gate's own checkers and the repair after it — ``ruff check``, ``ruff
format``, ``ruff check --fix``, the declared ``mypy`` — run on the host, over
the workspace, under the workspace's own configuration. That configuration is
part of the tree a task's commands may have written, and both tools take a
cache directory from it (``cache-dir`` for ruff, ``cache_dir`` for mypy), as an
absolute path anywhere. A checker that honoured it would write outside the
workspace — in either sandbox mode, from the host — wherever a contract's
command pointed it.

So a checker run on the host keeps no cache at all. The workspace is thrown
away after the task, so a cache there bought nothing that lasts.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.adapters.python import PythonAdapter
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.typecheck import TypeCheck
from mcgyvr.repair import repair
from tests import livejournal as lj

needs_tools = pytest.mark.skipif(
    shutil.which("ruff") is None or shutil.which("mypy") is None,
    reason="the checkers under test are a real ruff and a real mypy",
)

CONTRACT = """
id: tidy
task_type: function_implementation
task: Give the module a value.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    where = tmp_path / "outside"
    where.mkdir()
    return where


@pytest.fixture
def changed(tmp_path: Path, outside: Path) -> ChangeSet:
    """A workspace whose config points every cache outside it, then a change."""
    repo = lj.make_repo(tmp_path / "workspace")
    (repo / "pyproject.toml").write_text(
        "[tool.ruff]\n"
        f'cache-dir = "{outside / "ruff"}"\n'
        "[tool.mypy]\n"
        f'cache_dir = "{outside / "mypy"}"\n',
        encoding="utf-8",
    )
    lj.git(repo, "add", "-A")
    lj.git(repo, "commit", "-qm", "the workspace's own config")
    (repo / "src" / "pkg" / "messy.py").write_text(
        "import os\nx=1\ny: int = 'a'\n", encoding="utf-8"
    )
    return ChangeSet.detect(repo)


def _written(outside: Path) -> list[str]:
    return sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*"))


@needs_tools
def test_the_gates_lint_and_format_rungs_write_nothing_outside(
    changed: ChangeSet, outside: Path
) -> None:
    adapter = PythonAdapter()
    assert adapter.lint(changed.files, changed.repo)  # it ran, and found the import
    assert adapter.format_check(changed.files, changed.repo)
    assert _written(outside) == []


@needs_tools
def test_the_repair_writes_nothing_outside(changed: ChangeSet, outside: Path) -> None:
    outcome = repair(repo=changed.repo, contract=load_contract(CONTRACT))
    assert outcome.repaired == ("src/pkg/messy.py",)  # it ran, and rewrote
    assert _written(outside) == []


@needs_tools
def test_the_declared_type_checker_writes_nothing_outside(
    changed: ChangeSet, outside: Path
) -> None:
    assert TypeCheck(repo=changed.repo).run(changed)  # it ran, and found the str
    assert _written(outside) == []
