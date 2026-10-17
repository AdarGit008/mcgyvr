""

from __future__ import annotations

import ast
import json
import subprocess
import tomllib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.gate.adapter import (
    LanguageAdapter,
    ToolFailedError,
    added_by_resolved_path,
    plain_env,
    require_tool,
    trusted_stdout,
)
from mcgyvr.gate.changeset import FileChange, read_text_at
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.typecheck import (
    STYLE,
    STYLE_LINT_CODES,
    ParamMutation,
    compliance_findings,
    deprecated_typing_import_lines,
    unimportable_lines,
)
from mcgyvr.sandbox.declared import declared_type_checker
from mcgyvr.sandbox.declared import has_toml_table as _has_toml_table

_EXTENSIONS = (".py", ".pyi")

#
#
#
#
RUFF = "ruff"

#
#
#€”
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
# a
#
#so
#
#
#
#
#
#
#
#
#
#he
#e.
#
#
#
#
#
#
#
#he
#
DEFAULT_RUFF_SELECT: tuple[str, ...] = (
    "E4",
    "E7",
    "E9",
    "F",
    "W",
    "I",
    "N",
    "UP",
    "B",
    "SIM",
    "RUF",
)
DEFAULT_RUFF_LINE_LENGTH = 88
_RUFF_CONFIG_FILES = ("ruff.toml", ".ruff.toml")


def declares_ruff_config(repo: Path) -> bool:
    ""
    if any((repo / name).is_file() for name in _RUFF_CONFIG_FILES):
        return True
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        with pyproject.open("rb") as handle:
            tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return True
    return _has_toml_table(pyproject, "ruff")


def ruff_config_args(repo: Path) -> list[str]:
    ""
    if declares_ruff_config(repo):
        return []
    select = ", ".join(f'"{family}"' for family in DEFAULT_RUFF_SELECT)
    return [
        "--isolated",
        "--config",
        f"line-length = {DEFAULT_RUFF_LINE_LENGTH}",
        "--config",
        f"lint.select = [{select}]",
        "--config",
        'format.quote-style = "double"',
    ]


class PythonAdapter(LanguageAdapter):
    ""

    def __init__(
        self, *, param_mutation: ParamMutation | str = ParamMutation.REFUSE
    ) -> None:
        try:
            self._param_mutation = ParamMutation(param_mutation)
        except ValueError:
            valid = ", ".join(mode.value for mode in ParamMutation)
            raise ValueError(
                f"param_mutation {param_mutation!r} is not a mode the gate "
                f"implements. Valid: {valid}"
            ) from None

    @property
    def param_mutation(self) -> ParamMutation:
        return self._param_mutation

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
            #
            #
            #
            return [
                Finding(
                    check="syntax",
                    path=change.path,
                    line=exc.lineno,
                    message=exc.msg,
                )
            ]
        except UnicodeEncodeError as exc:
            return [_not_utf8(change.path, source, exc)]
        return []

    def structural_checks(
        self, change: FileChange, repo: Path, *, contract_text: str = ""
    ) -> list[Finding]:
        source = _read(repo / change.path)
        if source is None:
            return []
        try:
            tree = ast.parse(source, filename=change.path)
        except (SyntaxError, UnicodeEncodeError):
            return []  #
        visitor = _HazardVisitor(change.path, change.added_lines)
        visitor.visit(tree)
        return visitor.findings + compliance_findings(
            tree,
            change.path,
            change.added_lines,
            contract_text=contract_text,
            param_mutation=self._param_mutation,
        )

    def lint(
        self, changes: Sequence[FileChange], repo: Path, *, base: str | None = None
    ) -> list[Finding]:
        files = self.owned(changes)
        if not files:
            return []
        ruff = require_tool(RUFF)
        #
        #
        #
        config_args = ruff_config_args(repo)
        proc = subprocess.run(
            [
                ruff,
                "check",
                *config_args,
                "--output-format=json",
                "--force-exclude",
                "--",
                *_paths(files),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            env=plain_env(),
        )
        #
        #
        # a
        #
        #
        stdout = trusted_stdout(RUFF, proc, expected=(0, 1))
        try:
            diagnostics = json.loads(stdout or "[]")
        except json.JSONDecodeError as exc:
            #
            #
            raise ToolFailedError(
                RUFF, proc.returncode, f"stdout is not JSON: {exc}"
            ) from exc
        added = added_by_resolved_path(files, repo)
        if base is not None:
            diagnostics = _without_pre_existing(
                diagnostics, added, repo, base, [ruff, "check", *config_args]
            )
        #
        #
        #
        #
        shipped_default = bool(config_args)
        unimportable = _Unimportable(repo)
        deprecated_typing = _DeprecatedTyping(repo)
        findings: list[Finding] = []
        for diag in diagnostics:
            resolved = Path(diag["filename"]).resolve()
            row = (diag.get("location") or {}).get("row")
            rel = added.get(resolved)
            if rel is None or row is None:
                continue
            path, added_lines = rel
            if row in added_lines:
                code = diag.get("code")
                #
                #
                #€”
                #at
                #
                #
                #
                #ot
                #
                #
                #
                #
                #
                #
                #
                #
                #
                #
                #
                demoted = shipped_default and (
                    (code in STYLE_LINT_CODES and row not in unimportable.at(path))
                    or (code == "I001" and row in deprecated_typing.at(path))
                )
                findings.append(
                    Finding(
                        check=STYLE if demoted else "lint",
                        path=path,
                        line=row,
                        code=code,
                        message=diag.get("message", "").strip(),
                    )
                )
        return findings

    def format_check(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        files = self.owned(changes)
        if not files:
            return []
        ruff = require_tool(RUFF)
        proc = subprocess.run(
            [
                ruff,
                "format",
                *ruff_config_args(repo),
                "--diff",
                "--force-exclude",
                "--",
                *_paths(files),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            env=plain_env(),
        )
        #
        #y,
        #
        stdout = trusted_stdout(RUFF, proc, expected=(0, 1))
        if not stdout.strip():
            return []
        touched = _format_touched_lines(stdout)
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

    def locate_type_check_command(self, repo: Path) -> list[str] | None:
        ""
        checker = declared_type_checker(repo)
        return [checker] if checker is not None else None


class _HazardVisitor(ast.NodeVisitor):
    ""

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


class _Unimportable:
    ""

    def __init__(self, repo: Path) -> None:
        self._repo = repo
        self._seen: dict[str, frozenset[int]] = {}

    def at(self, path: str) -> frozenset[int]:
        if path not in self._seen:
            self._seen[path] = frozenset(unimportable_lines(_read(self._repo / path)))
        return self._seen[path]


class _DeprecatedTyping:
    ""

    def __init__(self, repo: Path) -> None:
        self._repo = repo
        self._seen: dict[str, frozenset[int]] = {}

    def at(self, path: str) -> frozenset[int]:
        if path not in self._seen:
            self._seen[path] = deprecated_typing_import_lines(_read(self._repo / path))
        return self._seen[path]


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return None


def _read_or_empty(path: Path) -> str:
    return _read(path) or ""


#
#
#
_SURROGATE_BASE = 0xDC00


def _not_utf8(path: str, source: str, exc: UnicodeEncodeError) -> Finding:
    ""
    offending = ord(exc.object[exc.start])
    detail = (
        f"byte 0x{offending - _SURROGATE_BASE:02x}"
        if 0xDC80 <= offending <= 0xDCFF
        else f"the lone surrogate U+{offending:04X}"
    )
    return Finding(
        check="syntax",
        path=path,
        #
        #
        #
        line=source.count("\n", 0, exc.start) + 1,
        message=f"{detail} is not valid utf-8, which Python source must be",
    )


def _paths(changes: Sequence[FileChange]) -> list[str]:
    return [c.path for c in changes]


def _diagnostic_key(diag: dict[str, object]) -> tuple[object, str]:
    ""
    return diag.get("code"), str(diag.get("message") or "").strip()


def _without_pre_existing(
    diagnostics: list[dict[str, object]],
    added: dict[Path, tuple[str, frozenset[int]]],
    repo: Path,
    base: str,
    check: list[str],
) -> list[dict[str, object]]:
    ""
    by_file: dict[Path, list[dict[str, object]]] = {}
    for diag in diagnostics:
        by_file.setdefault(Path(str(diag["filename"])).resolve(), []).append(diag)
    kept: list[dict[str, object]] = []
    for resolved, diags in by_file.items():
        rel = added.get(resolved)
        if rel is None:
            kept.extend(diags)
            continue
        path, added_lines = rel
        if not any(_row(d) in added_lines for d in diags):
            kept.extend(diags)
            continue
        excused = _base_diagnostics(repo, base, path, check)
        excused.subtract(
            _diagnostic_key(d) for d in diags if _row(d) not in added_lines
        )
        for diag in diags:  #
            key = _diagnostic_key(diag)
            if _row(diag) in added_lines and excused[key] > 0:
                excused[key] -= 1
                continue
            kept.append(diag)
    return kept


def _row(diag: dict[str, object]) -> object:
    location = diag.get("location")
    return location.get("row") if isinstance(location, dict) else None


def _base_diagnostics(
    repo: Path, base: str, path: str, check: list[str]
) -> Counter[tuple[object, str]]:
    ""
    text = read_text_at(repo, base, path)
    if text is None:
        return Counter()
    proc = subprocess.run(
        [*check, "--output-format=json", "--stdin-filename", path, "-"],
        cwd=repo,
        input=text,
        capture_output=True,
        text=True,
        env=plain_env(),
    )
    if proc.returncode not in (0, 1):
        return Counter()
    try:
        found = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return Counter()
    return Counter(_diagnostic_key(d) for d in found)


def _format_touched_lines(diff: str) -> dict[str, set[int]]:
    ""
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
            continue  #
        else:
            old_ln += 1  #
    return touched


def _strip_diff_path(raw: str) -> str:
    ""
    return raw.strip().split("\t", 1)[0]


def _hunk_old_range(header: str) -> tuple[int, int]:
    ""
    minus = header.split("-", 1)[1].split(" ", 1)[0]
    if "," in minus:
        start_s, count_s = minus.split(",", 1)
        return int(start_s), int(count_s)
    return int(minus), 1
