"""A repo that declares no ruff configuration is linted by a basic default,
not by everything ruff knows (owner, 2026-09-05: "set a basic default").

Measured in the first live e2e: a workspace with a ``pyproject.toml`` but no
``[tool.ruff]`` was linted by the gate under 826 rules — ruff 0.16.4 with no
configuration — and TRY004 alone rejected six of nine replies for raising
``ValueError`` where the worker bundle says to. ``tools/bench/score.py``
already writes this project's own selection into every bench workspace for
exactly that reason; the live gate had no such floor. Now it does, and the
floor is the same nine families. A repo that states its own ruff config keeps
it, whatever it selects: the default is for the repo that said nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcgyvr.gate import Gate
from mcgyvr.gate.adapters.python import DEFAULT_RUFF_SELECT, ruff_config_args
from mcgyvr.gate.changeset import ChangeSet

#: Raises ValueError on a type check: TRY004 under a wide rule set, clean under
#: this project's own selection. Formatted, import-sorted, and under 88 wide.
TYPE_CHECK = (
    "def chunk(items: list, size: int) -> list:\n"
    '    """Split items into groups of at most size."""\n'
    "    if not isinstance(size, int):\n"
    '        raise ValueError("size must be an int")\n'
    "    return [items[i : i + size] for i in range(0, len(items), size)]\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )


def repo_with(tmp_path: Path, *, pyproject: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "solution.py").write_text(TYPE_CHECK, encoding="utf-8")
    return repo


def codes(repo: Path) -> set[str]:
    result = Gate().run(ChangeSet.detect(repo, "HEAD"))
    return {f.code for f in result.findings if f.code}


def test_a_repo_that_declares_no_ruff_config_gets_the_basic_default(
    tmp_path: Path,
) -> None:
    repo = repo_with(tmp_path, pyproject='[project]\nname = "x"\nversion = "0"\n')
    args = ruff_config_args(repo)
    assert "--isolated" in args, args
    assert any("lint.select" in a for a in args), args
    assert "TRY004" not in codes(repo)


def test_the_default_is_this_projects_own_nine_families() -> None:
    assert DEFAULT_RUFF_SELECT == ("E", "F", "W", "I", "N", "UP", "B", "SIM", "RUF")


def test_a_repo_with_its_own_ruff_config_keeps_it(tmp_path: Path) -> None:
    own = '[project]\nname = "x"\nversion = "0"\n\n[tool.ruff.lint]\nselect = ["TRY"]\n'
    repo = repo_with(tmp_path, pyproject=own)
    assert ruff_config_args(repo) == []
    assert "TRY004" in codes(repo)


def test_a_ruff_toml_counts_as_a_declared_config(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, pyproject='[project]\nname = "x"\nversion = "0"\n')
    (repo / "ruff.toml").write_text('[lint]\nselect = ["TRY"]\n', encoding="utf-8")
    assert ruff_config_args(repo) == []
    assert "TRY004" in codes(repo)
