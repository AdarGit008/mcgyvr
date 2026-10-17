"""The gate's JavaScript/TypeScript adapter.

Owns the .js/.jsx/.mjs/.cjs and .ts/.tsx/.mts/.cts family. Syntax and the
structural hazard checks run on tree-sitter parses, so they need no toolchain;
lint and format shell out to eslint and prettier and then attribute what those
tools say to the lines the change added, so a defect the worker did not
introduce is not counted against it. The adapter also names the repo's type
check and test commands when the repo declares them.
"""

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

# One parser per grammar: TypeScript proper, TSX (the JSX dialect, which has a
# grammar of its own), and JavaScript. _language_for picks between them.
_JS = Language(_js_language())
_TS = Language(_ts_language())
_TSX = Language(_tsx_language())

# The suffixes each grammar covers, kept apart so _language_for can pick one.
# `.tsx` is listed on its own because JSX is not valid in the other TypeScript
# suffixes, and _EXTENSIONS is the whole family that `owns` accepts.
_TS_EXTENSIONS = (".ts", ".mts", ".cts")
_TSX_EXTENSIONS = (".tsx",)
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")
_EXTENSIONS = _TS_EXTENSIONS + _TSX_EXTENSIONS + _JS_EXTENSIONS

# eslint's severity scale: 1 is a warning and 2 is an error. Only errors reject
# a change, so the number is named here rather than spelled inline below. The
# gate looks for problems rather than style opinions, and a warning is an
# opinion; anything eslint cannot grade — a fatal message — is a tool fault.
_ESLINT_ERROR = 2


class JavaScriptAdapter(LanguageAdapter):
    """Check JS/TS changes with tree-sitter, eslint and prettier."""

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
        if node is None:  # has_error is set, yet no node was found to point at
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
        # The hazard rules are fixed rather than contract-driven: contract prose
        # carries nothing JS/TS-specific to interpret, so `contract_text` is
        # unused and _HAZARDS is the whole rule set. A hazard is reported only
        # when it sits on a line the change added, and a file that does not
        # parse is skipped here so check_syntax reports it once.
        root = self._parse(repo / change.path)
        if root is None or root.has_error:
            return []  # unparseable, so no node can be trusted as a hazard
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
        # One eslint run over every owned file; `base` plays no part because the
        # added lines already say which of them the worker touched.
        files = self.owned(changes)
        if not files:
            return []
        proc = _run(
            self._runner, _ESLINT, ["--format", "json", "--", *_paths(files)], repo
        )
        # eslint exits 0 when it has nothing to report and 1 when it reports
        # problems; both carry a JSON report on stdout. Any other exit — an
        # unloadable config, an internal error — prints an empty stdout, which
        # must never read as "nothing found", so trusted_stdout raises
        # ToolFailedError rather than letting the empty string parse as clean.
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
                    # A fatal message is eslint failing to judge the file, not a
                    # rule violation: no line it names can be trusted, so it is
                    # a fault for the whole run instead of a finding.
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
        # --list-different names the files prettier would rewrite, so only those
        # are worth diffing line by line. For each of them prettier's formatted
        # output is diffed against the file on disk, and a finding is raised
        # only when a reflowed line is one the change added — pre-existing
        # formatting is not the worker's doing.
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
        """`tsc --noEmit` when the repo has a tsconfig.json, else no check."""
        return ["tsc", "--noEmit"] if (repo / "tsconfig.json").is_file() else None

    def locate_test_command(self, repo: Path) -> list[str] | None:
        package = repo / "package.json"
        if not package.is_file():
            return None
        try:
            manifest = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            # An unreadable or malformed manifest says only that no test command
            # can be located, so it is reported as absence rather than raised:
            # the caller treats a missing command as no test rung. Raising here
            # would turn a broken package.json into a gate fault before any
            # check of the delivered code had run.
            return None
        scripts = manifest.get("scripts")
        if not isinstance(scripts, dict) or "test" not in scripts:
            return None
        return [_package_manager(repo), "test"]

    def _parse(self, path: Path) -> Node | None:
        """Parse `path` with the grammar its suffix picks, or None if unreadable."""
        language = _language_for(path.name)
        if language is None:
            return None
        try:
            source = path.read_bytes()
        except OSError:
            return None
        return Parser(language).parse(source).root_node


# Structural hazard handlers. Each receives a tree-sitter node and returns
# ``(code, message)`` to report it, or ``(None, "")`` to leave it alone.
# _HAZARDS binds them to the node types that trigger them, so structural_checks
# walks the tree once and consults the table instead of pattern-matching node
# types inline.


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
    """Yield `root` and every node beneath it, each node before its children."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


def _first_error(root: Node) -> Node | None:
    """Return the first error or missing node under `root`, or None."""
    errors = [n for n in _walk(root) if n.is_error or n.is_missing]
    return min(errors, key=lambda n: n.start_point) if errors else None


# Shell out through the adapter's runner, reporting a timeout as a tool fault.


def _run(
    runner: ToolRunner, tool: str, args: Sequence[str], repo: Path
) -> subprocess.CompletedProcess[str]:
    """Run `tool` in `repo`, turning a timeout into a ToolFailedError."""
    try:
        return runner.run(tool, args, repo)
    except subprocess.TimeoutExpired as exc:
        raise ToolFailedError(tool, -1, f"timed out after {exc.timeout:g}s") from exc


def _prettier_differing(
    prettier: ToolRunner, paths: Sequence[str], repo: Path
) -> set[str]:
    """Return the paths prettier's ``--list-different`` says it would rewrite."""
    proc = _run(prettier, _PRETTIER, ["--list-different", "--", *paths], repo)
    stdout = trusted_stdout(_PRETTIER, proc, expected=(0, 1))
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def _prettier_reflowed_lines(prettier: ToolRunner, path: str, repo: Path) -> set[int]:
    """Return the 1-based lines of `path` that prettier's formatting would change."""
    proc = _run(prettier, _PRETTIER, ["--", path], repo)
    # Only exit 0 is accepted here: the file has already been listed as
    # differing, so a prettier that cannot print it is a fault rather than
    # evidence that nothing reflowed. Exit 0 also means stdout carries the
    # formatted file, ready to diff.
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
            touched.update(range(i1 + 1, i2 + 1))  # 0-based diff, 1-based lines
    return touched


# Lockfile detection, so the test command runs under the manager the repo uses.


def _package_manager(repo: Path) -> str:
    """Return the package manager whose lockfile `repo` carries, or npm."""
    if (repo / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (repo / "yarn.lock").is_file():
        return "yarn"
    if (repo / "bun.lockb").is_file():
        return "bun"
    return "npm"


def _paths(changes: Sequence[FileChange]) -> list[str]:
    return [c.path for c in changes]
