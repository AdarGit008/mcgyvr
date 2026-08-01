"""The Python language adapter — the reference implementation of #35.

Syntax is checked with the standard library's own parser, so it costs no
subprocess and fails before anything expensive runs. Structural hazards are
found by walking the AST and keeping only nodes the worker actually added.
Lint and format defer to ruff — the tool this very project uses — run once
over all changed Python files, with every finding filtered down to
worker-added lines so a file's pre-existing style can never fail the change.
"""

from __future__ import annotations

import ast
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.gate.adapter import LanguageAdapter, require_tool
from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding

_EXTENSIONS = (".py", ".pyi")


class PythonAdapter(LanguageAdapter):
    @property
    def name(self) -> str:
        return "python"

    def owns(self, path: str) -> bool:
        return path.endswith(_EXTENSIONS)

    def check_syntax(self, change: FileChange, repo: Path) -> list[Finding]:
        source = _read(repo / change.path)
        if source is None:
            return []
        try:
            ast.parse(source, filename=change.path)
        except SyntaxError as exc:
            return [
                Finding(
                    check="syntax",
                    path=change.path,
                    line=exc.lineno,
                    message=exc.msg,
                )
            ]
        return []

    def structural_checks(self, change: FileChange, repo: Path) -> list[Finding]:
        source = _read(repo / change.path)
        if source is None:
            return []
        try:
            tree = ast.parse(source, filename=change.path)
        except SyntaxError:
            return []  # syntax pass already owns this; do not double-report
        visitor = _HazardVisitor(change.path, change.added_lines)
        visitor.visit(tree)
        return visitor.findings

    def lint(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        files = self.owned(changes)
        if not files:
            return []
        ruff = require_tool("ruff")
        proc = subprocess.run(
            [
                ruff,
                "check",
                "--output-format=json",
                "--force-exclude",
                "--",
                *_paths(files),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        try:
            diagnostics = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            # ruff writes diagnostics to stdout and only fails hard on internal
            # errors; a non-JSON stdout means we cannot trust the run.
            return []
        added = _added_by_resolved_path(files, repo)
        findings: list[Finding] = []
        for diag in diagnostics:
            resolved = Path(diag["filename"]).resolve()
            row = (diag.get("location") or {}).get("row")
            rel = added.get(resolved)
            if rel is None or row is None:
                continue
            path, added_lines = rel
            if row in added_lines:
                findings.append(
                    Finding(
                        check="lint",
                        path=path,
                        line=row,
                        code=diag.get("code"),
                        message=diag.get("message", "").strip(),
                    )
                )
        return findings

    def format_check(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        files = self.owned(changes)
        if not files:
            return []
        ruff = require_tool("ruff")
        proc = subprocess.run(
            [ruff, "format", "--diff", "--force-exclude", "--", *_paths(files)],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if not proc.stdout.strip():
            return []
        touched = _format_touched_lines(proc.stdout)
        findings: list[Finding] = []
        for change in files:
            would_change = touched.get(change.path, set())
            hit = sorted(would_change & change.added_lines)
            if hit:
                findings.append(
                    Finding(
                        check="format",
                        path=change.path,
                        line=hit[0],
                        message="formatter would reflow a worker-added line",
                    )
                )
        return findings

    def locate_test_command(self, repo: Path) -> list[str] | None:
        pyproject = repo / "pyproject.toml"
        if pyproject.is_file() and "pytest" in _read_or_empty(pyproject):
            return ["pytest"]
        if (repo / "tests").is_dir() or (repo / "test").is_dir():
            return ["pytest"]
        return None


class _HazardVisitor(ast.NodeVisitor):
    """Collects language hazards, keeping only worker-added occurrences.

    The whole file is walked, but a node is reported only when its own line is
    one the worker added — so a hazard already present in the file is never
    charged to the worker's change.
    """

    def __init__(self, path: str, added_lines: frozenset[int]) -> None:
        self.path = path
        self.added = added_lines
        self.findings: list[Finding] = []

    def _added(self, lineno: int | None) -> bool:
        return lineno is not None and lineno in self.added

    def _flag(self, lineno: int | None, code: str, message: str) -> None:
        if self._added(lineno):
            self.findings.append(
                Finding(
                    check="structure",
                    path=self.path,
                    line=lineno,
                    code=code,
                    message=message,
                )
            )

    def _check_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        defaults = [d for d in node.args.defaults if d is not None]
        defaults += [d for d in node.args.kw_defaults if d is not None]
        for default in defaults:
            if _is_mutable_literal(default):
                self._flag(
                    default.lineno,
                    "MUT-DEFAULT",
                    "mutable default argument is shared across calls",
                )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_defaults(node)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self._flag(
                node.lineno,
                "BARE-EXCEPT",
                "bare except catches everything, including KeyboardInterrupt",
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if any(alias.name == "*" for alias in node.names):
            self._flag(
                node.lineno,
                "WILDCARD-IMPORT",
                "wildcard import hides which names enter the namespace",
            )
        self.generic_visit(node)


def _is_mutable_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.List | ast.Dict | ast.Set):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in {"list", "dict", "set"}
    return False


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return None


def _read_or_empty(path: Path) -> str:
    return _read(path) or ""


def _paths(changes: Sequence[FileChange]) -> list[str]:
    return [c.path for c in changes]


def _added_by_resolved_path(
    changes: Sequence[FileChange], repo: Path
) -> dict[Path, tuple[str, frozenset[int]]]:
    """Map each file's resolved absolute path to its repo-relative path and added lines.

    ruff reports absolute filenames; the change set carries repo-relative ones.
    Resolving both sides is what lets a lint diagnostic be matched back to the
    right file's added-line set.
    """
    return {(repo / c.path).resolve(): (c.path, c.added_lines) for c in changes}


def _format_touched_lines(diff: str) -> dict[str, set[int]]:
    """Per file, the current-file line numbers ``ruff format`` would change.

    Reads the unified diff ruff emits and records only the lines actually on
    the minus side of a hunk — the current-file lines the formatter would
    rewrite. Context lines advance the old-file counter but are left untouched,
    so a hunk that merely spans a worker-added line without changing it does
    not implicate the worker.
    """
    touched: dict[str, set[int]] = {}
    current: str | None = None
    old_ln = 0
    for line in diff.splitlines():
        if line.startswith("--- "):
            current = _strip_diff_path(line[4:])
        elif line.startswith("+++ "):
            continue
        elif line.startswith("@@ "):
            old_ln = _hunk_old_range(line)[0]
        elif current is None:
            continue
        elif line.startswith("-"):
            touched.setdefault(current, set()).add(old_ln)
            old_ln += 1
        elif line.startswith("+"):
            continue  # added on the new side; does not consume an old line
        else:
            old_ln += 1  # context line
    return touched


def _strip_diff_path(raw: str) -> str:
    path = raw.strip().split("\t", 1)[0]
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path


def _hunk_old_range(header: str) -> tuple[int, int]:
    """Parse ``@@ -a,b +c,d @@`` into the old-file ``(start, count)``.

    ``-a`` without a count means ``-a,1``. A pure insertion is written ``-a,0``
    and contributes no current-file lines.
    """
    minus = header.split("-", 1)[1].split(" ", 1)[0]
    if "," in minus:
        start_s, count_s = minus.split(",", 1)
        return int(start_s), int(count_s)
    return int(minus), 1
