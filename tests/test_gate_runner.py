"""End-to-end: the gate over a real change set, in the order #32 prescribes.

These exercise the whole pipeline against actual git repositories — the change
is detected once and every check reads from it — and pin the two properties the
epic makes acceptance criteria: a hard failure (scope, secret) stops before the
expensive checks, and the subprocess count stays flat as the change grows.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate.adapter import ToolUnavailableError
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.runner import Gate
from mcgyvr.scope import Scope


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def repo_with_base(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "seed.py").write_text("SEED = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_clean_change_is_accepted(tmp_path: Path) -> None:
    repo = repo_with_base(tmp_path)
    (repo / "good.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    result = Gate().run(ChangeSet.detect(repo))
    assert result.accepted, result.findings
    assert result.environment_issues == ()


def test_secret_stops_before_lint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leaked key is a hard fail; the expensive lint/format never runs."""
    repo = repo_with_base(tmp_path)
    # Poorly formatted AND leaks a key: if lint ran we'd see two checks, but the
    # secret short-circuit means only the secret finding comes back.
    (repo / "bad.py").write_text('KEY="AKIAIOSFODNN7EXAMPLE"\n')

    def explode(*_a: object, **_k: object) -> list[object]:
        raise AssertionError("lint must not run once a secret is found")

    monkeypatch.setattr(PythonAdapter, "lint", explode)
    result = Gate().run(ChangeSet.detect(repo))

    assert not result.accepted
    assert {f.check for f in result.findings} == {"secret"}


def test_scope_violation_fails_by_name(tmp_path: Path) -> None:
    repo = repo_with_base(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "ok.py").write_text("x = 1\n")
    (repo / "forbidden.py").write_text("y = 2\n")

    scope = Scope.of(allow=["src/**"])
    result = Gate().run(ChangeSet.detect(repo), scope=scope)

    assert not result.accepted
    scope_findings = result.by_check()["scope"]
    assert [f.path for f in scope_findings] == ["forbidden.py"]


def test_syntax_error_is_reported_and_skips_lint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = repo_with_base(tmp_path)
    (repo / "broken.py").write_text("def f(:\n    pass\n")

    def explode(*_a: object, **_k: object) -> list[object]:
        raise AssertionError("a file that doesn't parse must not be linted")

    monkeypatch.setattr(PythonAdapter, "lint", explode)
    result = Gate().run(ChangeSet.detect(repo))

    assert {f.check for f in result.findings} == {"syntax"}


def test_structural_hazard_on_added_line_fails(tmp_path: Path) -> None:
    repo = repo_with_base(tmp_path)
    (repo / "h.py").write_text("def f(a=[]):\n    return a\n")

    result = Gate().run(ChangeSet.detect(repo))
    assert not result.accepted
    assert any(f.code == "MUT-DEFAULT" for f in result.findings)


def test_missing_tool_is_an_environment_issue_not_a_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = repo_with_base(tmp_path)
    (repo / "ok.py").write_text("x = 1\n")

    def raise_missing(*_a: object, **_k: object) -> list[object]:
        raise ToolUnavailableError("ruff")

    monkeypatch.setattr(PythonAdapter, "lint", raise_missing)
    monkeypatch.setattr(PythonAdapter, "format_check", raise_missing)
    result = Gate().run(ChangeSet.detect(repo))

    assert result.accepted, "a missing tool must not reject a clean change"
    assert any("ruff" in issue for issue in result.environment_issues)
    assert len(result.environment_issues) == 2  # lint and format both reported


def test_invalid_json_change_is_flagged(tmp_path: Path) -> None:
    repo = repo_with_base(tmp_path)
    (repo / "data.json").write_text('{"a": ,}\n')

    result = Gate().run(ChangeSet.detect(repo))
    assert not result.accepted
    assert any(f.code == "invalid-json" for f in result.findings)


def _add_python_files(repo: Path, n: int) -> None:
    for i in range(n):
        (repo / f"m{i}.py").write_text(
            f"def f{i}(x: int) -> int:\n    return x + {i}\n"
        )


def test_subprocess_count_is_flat_across_change_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1 vs 12 changed files must cost the same number of subprocesses.

    The change set is computed once (outside the counted region) and the
    adapter batches lint and format, so the gate spawns two ruff calls no
    matter how many files the worker touched.
    """
    real_run = subprocess.run
    counts: list[int] = []

    def counting_run(cmd, *a, **k):  # type: ignore[no-untyped-def]
        counting_run.n += 1  # type: ignore[attr-defined]
        return real_run(cmd, *a, **k)

    for n in (1, 12):
        repo = tmp_path / f"r{n}"
        repo.mkdir()
        repo_with_base(repo)
        _add_python_files(repo, n)
        changeset = ChangeSet.detect(repo)  # detected before counting starts

        counting_run.n = 0  # type: ignore[attr-defined]
        monkeypatch.setattr("mcgyvr.gate.adapters.python.subprocess.run", counting_run)
        Gate().run(changeset)
        monkeypatch.undo()
        counts.append(counting_run.n)  # type: ignore[attr-defined]

    assert counts[0] == 2, f"expected exactly two ruff calls, got {counts[0]}"
    assert counts[0] == counts[1], f"gate subprocess count grew with size: {counts}"
