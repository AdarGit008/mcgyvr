"""A gate that did not understand its check never reports clean.

Every rung here reads another program's output. When that output is in a form
the rung does not parse, or says the check never ran on the file, the rung must
report a finding or an inconclusive run. Zero findings means "checked and
clean". It must not also mean "could not read the answer".
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from mcgyvr.gate import ToolFailedError
from mcgyvr.gate.adapters.javascript import JavaScriptAdapter
from mcgyvr.gate.adapters.python import PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.typecheck import TypeCheck


def _tool(bin_dir: Path, name: str, script: str) -> None:
    """A stand-in for ``name`` on PATH that runs ``script`` under ``/bin/sh``."""
    bin_dir.mkdir(exist_ok=True)
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _pyright_repo(tmp_path: Path) -> tuple[Path, ChangeSet]:
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "pyrightconfig.json").write_text("{}\n", encoding="utf-8")
    (repo / "src" / "pkg" / "count.py").write_text(
        "def count(rows: list[int]) -> int:\n    return rows\n", encoding="utf-8"
    )
    change = FileChange("src/pkg/count.py", "A", frozenset({1, 2}), False)
    return repo, ChangeSet(repo=repo, base="HEAD", files=(change,))


def test_a_pyright_error_on_a_worker_line_is_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pyright's own report format lands on the worker's line."""
    repo, changes = _pyright_repo(tmp_path)
    _tool(
        tmp_path / "bin",
        "pyright",
        'echo "$PWD/src/pkg/count.py"\n'
        'echo "  $PWD/src/pkg/count.py:2:12 - error: Type \\"list[int]\\" is not '
        'assignable to return type \\"int\\" (reportReturnType)"\n'
        'echo "1 error, 0 warnings, 0 informations "\n'
        "exit 1\n",
    )
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")

    findings = TypeCheck(repo).run(changes)

    assert [(f.path, f.line, f.code) for f in findings] == [
        ("src/pkg/count.py", 2, "reportReturnType")
    ], f"pyright rejected the change and the rung reported {findings}"


def test_a_checker_that_reported_errors_it_cannot_read_is_inconclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 1 means errors were found; none parsed means the report was not read."""
    repo, changes = _pyright_repo(tmp_path)
    _tool(tmp_path / "bin", "pyright", 'echo "{\\"diagnostics\\": [1]}"\nexit 1\n')
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")

    with pytest.raises(ToolFailedError):
        TypeCheck(repo).run(changes)


def test_a_file_under_a_top_level_a_directory_is_format_checked(
    tmp_path: Path,
) -> None:
    """ruff prints bare paths, so ``a/foo.py`` is a path, not a diff prefix."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "foo.py").write_text("x=1\n", encoding="utf-8")

    findings = PythonAdapter().format_check(
        [FileChange("a/foo.py", "A", frozenset({1}), False)], tmp_path
    )

    assert [(f.check, f.path, f.line) for f in findings] == [("format", "a/foo.py", 1)]


def test_an_eslint_parse_failure_off_the_added_lines_is_inconclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fatal message means no rule ran on the file, wherever it points."""
    (tmp_path / "app.ts").write_text(
        "let n: number = 1;\nexport const m = n;\n", encoding="utf-8"
    )
    report = [
        {
            "filePath": str(tmp_path / "app.ts"),
            "messages": [
                {
                    "fatal": True,
                    "severity": 2,
                    "line": 1,
                    "column": 6,
                    "ruleId": None,
                    "message": "Parsing error: Unexpected token :",
                }
            ],
        }
    ]
    _tool(
        tmp_path / "bin",
        "eslint",
        f"cat <<'EOF'\n{json.dumps(report)}\nEOF\nexit 1\n",
    )
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")

    with pytest.raises(ToolFailedError):
        JavaScriptAdapter().lint(
            [FileChange("app.ts", "M", frozenset({2}), False)], tmp_path
        )
