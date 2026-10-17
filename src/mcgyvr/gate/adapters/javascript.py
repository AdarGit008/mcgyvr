""

from __future__ import annotations

import difflib
import json
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath

from tree_sitter import Language, Node, Parser
from tree_sitter_javascript import language as _js_language
from tree_sitter_typescript import (
    language_tsx as _tsx_language,
)
from tree_sitter_typescript import (
    language_typescript as _ts_language,
)

from mcgyvr.gate.adapter import (
    HostRunner,
    LanguageAdapter,
    ToolFailedError,
    ToolRunner,
    added_by_resolved_path,
    trusted_stdout,
)
from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.sandbox.declared import CONFIG_MODULES, ESLINT, PRETTIER

_ESLINT = ESLINT
_PRETTIER = PRETTIER

#to
#
_JS = Language(_js_language())
_TS = Language(_ts_language())
_TSX = Language(_tsx_language())

# the
#
#
_TS_EXTENSIONS = (".ts", ".mts", ".cts")
_TSX_EXTENSIONS = (".tsx",)
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")
_EXTENSIONS = _TS_EXTENSIONS + _TSX_EXTENSIONS + _JS_EXTENSIONS

#
#
#
#
#
#
_ESLINT_ERROR = 2


class JavaScriptAdapter(LanguageAdapter):
    ""

    def __init__(self, runner: ToolRunner | None = None) -> None:
        self._runner: ToolRunner = runner if runner is not None else HostRunner()

    def running_in(self, runner: ToolRunner) -> JavaScriptAdapter:
        return JavaScriptAdapter(runner)

    def loads_as_code(self, path: str) -> dict[str, str]:
        name = PurePosixPath(path).name
        rungs = {"lint": _ESLINT, "format": _PRETTIER}
        return {
            rung: tool for rung, tool in rungs.items() if name in CONFIG_MODULES[tool]
        }

    @property
    def name(self) -> str:
        return "js/ts"

    def owns(self, path: str) -> bool:
        return path.endswith(_EXTENSIONS)

    def check_syntax(self, change: FileChange, repo: Path) -> list[Finding]:
        root = self._parse(repo / change.path)
        if root is None or not root.has_error:
            return []
        node = _first_error(root)
        if node is None:  #at
            return []
        detail = f": missing '{node.type}'" if node.is_missing else ""
        return [
            Finding(
                check="syntax",
                path=change.path,
                line=node.start_point[0] + 1,
                message=f"syntax error{detail}",
            )
        ]

    def structural_checks(
        self, change: FileChange, repo: Path, *, contract_text: str = ""
    ) -> list[Finding]:
        #
        #`,
        #nd
        #
        #
        #
        root = self._parse(repo / change.path)
        if root is None or root.has_error:
            return []  #
        findings: list[Finding] = []
        for node in _walk(root):
            hazard = _HAZARDS.get(node.type)
            if hazard is None:
                continue
            code, message = hazard(node)
            if code is None:
                continue
            line = node.start_point[0] + 1
            if line in change.added_lines:
                findings.append(
                    Finding(
                        check="structure",
                        path=change.path,
                        line=line,
                        code=code,
                        message=message,
                    )
                )
        findings.sort(key=lambda f: (f.line or 0, f.code or ""))
        return findings

    def lint(
        self, changes: Sequence[FileChange], repo: Path, *, base: str | None = None
    ) -> list[Finding]:
        #
        #
        files = self.owned(changes)
        if not files:
            return []
        proc = _run(
            self._runner, _ESLINT, ["--format", "json", "--", *_paths(files)], repo
        )
        #
        # â€”
        #
        #
        #
        stdout = trusted_stdout(_ESLINT, proc, expected=(0, 1))
        try:
            results = json.loads(stdout or "[]")
        except json.JSONDecodeError as exc:
            raise ToolFailedError(
                _ESLINT, proc.returncode, f"stdout is not JSON: {exc}"
            ) from exc
        added = added_by_resolved_path(files, repo)
        findings: list[Finding] = []
        for result in results:
            resolved = self._runner.host_path(result.get("filePath", "")).resolve()
            rel = added.get(resolved)
            if rel is None:
                continue
            path, added_lines = rel
            for message in result.get("messages", []):
                line = message.get("line")
                if message.get("fatal") and line not in added_lines:
                    #
                    #
                    #
                    raise ToolFailedError(
                        _ESLINT,
                        proc.returncode,
                        f"{path}: {(message.get('message') or '').strip()}",
                    )
                if message.get("severity") != _ESLINT_ERROR or line not in added_lines:
                    continue
                findings.append(
                    Finding(
                        check="lint",
                        path=path,
                        line=line,
                        code=message.get("ruleId"),
                        message=(message.get("message") or "").strip(),
                    )
                )
        return findings

    def format_check(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        files = self.owned(changes)
        if not files:
            return []
        prettier = self._runner
        #
        #
        #
        #€”
        #
        #
        differing = _prettier_differing(prettier, _paths(files), repo)
        findings: list[Finding] = []
        for change in files:
            if change.path not in differing or not change.added_lines:
                continue
            touched = _prettier_reflowed_lines(prettier, change.path, repo)
            hit = sorted(touched & change.added_lines)
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

    def locate_type_check_command(self, repo: Path) -> list[str] | None:
        ""
        return ["tsc", "--noEmit"] if (repo / "tsconfig.json").is_file() else None

    def locate_test_command(self, repo: Path) -> list[str] | None:
        package = repo / "package.json"
        if not package.is_file():
            return None
        try:
            manifest = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            #
            #
            #
            #
            #as
            #
            return None
        scripts = manifest.get("scripts")
        if not isinstance(scripts, dict) or "test" not in scripts:
            return None
        return [_package_manager(repo), "test"]

    def _parse(self, path: Path) -> Node | None:
        ""
        language = _language_for(path.name)
        if language is None:
            return None
        try:
            source = path.read_bytes()
        except OSError:
            return None
        return Parser(language).parse(source).root_node


#
#
#
#
#
#


def _loose_equality(node: Node) -> tuple[str | None, str]:
    operator = node.child_by_field_name("operator")
    if operator is not None and operator.text in (b"==", b"!="):
        return (
            "LOOSE-EQ",
            "loose equality coerces types; prefer === / !== to compare without "
            "surprises",
        )
    return None, ""


def _var_declaration(_node: Node) -> tuple[str | None, str]:
    return (
        "NO-VAR",
        "`var` is function-scoped and hoisted; prefer `let` or `const`",
    )


def _debugger(_node: Node) -> tuple[str | None, str]:
    return "DEBUGGER", "`debugger` statement left in the code"


_HAZARDS = {
    "binary_expression": _loose_equality,
    "variable_declaration": _var_declaration,
    "debugger_statement": _debugger,
}


def _language_for(filename: str) -> Language | None:
    if filename.endswith(_TSX_EXTENSIONS):
        return _TSX
    if filename.endswith(_TS_EXTENSIONS):
        return _TS
    if filename.endswith(_JS_EXTENSIONS):
        return _JS
    return None


def _walk(root: Node) -> Iterator[Node]:
    ""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


def _first_error(root: Node) -> Node | None:
    ""
    errors = [n for n in _walk(root) if n.is_error or n.is_missing]
    return min(errors, key=lambda n: n.start_point) if errors else None


#


def _run(
    runner: ToolRunner, tool: str, args: Sequence[str], repo: Path
) -> subprocess.CompletedProcess[str]:
    ""
    try:
        return runner.run(tool, args, repo)
    except subprocess.TimeoutExpired as exc:
        raise ToolFailedError(tool, -1, f"timed out after {exc.timeout:g}s") from exc


def _prettier_differing(
    prettier: ToolRunner, paths: Sequence[str], repo: Path
) -> set[str]:
    ""
    proc = _run(prettier, _PRETTIER, ["--list-different", "--", *paths], repo)
    stdout = trusted_stdout(_PRETTIER, proc, expected=(0, 1))
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def _prettier_reflowed_lines(prettier: ToolRunner, path: str, repo: Path) -> set[int]:
    ""
    proc = _run(prettier, _PRETTIER, ["--", path], repo)
    #
    #
    #
    #
    stdout = trusted_stdout(_PRETTIER, proc, expected=(0,))
    try:
        original = (repo / path).read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return set()
    old_lines = original.splitlines()
    new_lines = stdout.splitlines()
    touched: set[int] = set()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            touched.update(range(i1 + 1, i2 + 1))  #
    return touched


#


def _package_manager(repo: Path) -> str:
    ""
    if (repo / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (repo / "yarn.lock").is_file():
        return "yarn"
    if (repo / "bun.lockb").is_file():
        return "bun"
    return "npm"


def _paths(changes: Sequence[FileChange]) -> list[str]:
    return [c.path for c in changes]
