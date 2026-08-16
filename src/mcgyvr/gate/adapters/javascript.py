"""The JavaScript/TypeScript adapter — the second language (#36).

This is what proves the adapter interface is real rather than Python-shaped:
it satisfies the very same :class:`~mcgyvr.gate.adapter.LanguageAdapter`
contract with none of Python's tools or concepts.

Syntax and structural checks use **tree-sitter** — the same grammar investment
the orchestrator's index needs, which is what makes a second language
affordable rather than a rewrite. One error-tolerant parse per file gives both
a fast syntax verdict (``root.has_error``) and a walkable tree for hazards, at
no subprocess cost, exactly as the standard-library parser does for Python.

Lint and format defer to the JS ecosystem's own tools — **eslint** and
**prettier** — batched over all changed files and filtered to worker-added
lines, so a file's pre-existing style can never fail the change. When a tool is
absent that is an *environment* fault, surfaced as
:class:`~mcgyvr.gate.adapter.ToolUnavailableError`, not a rejection — the same
distinction the Python adapter and the acceptance rung (#38) draw. When a tool
is present but its run cannot be read, that is
:class:`~mcgyvr.gate.adapter.ToolFailedError` and the change is refused
(ADR-0032): eslint and prettier both answer a fatal config error with exit 2
and an empty stdout, which every reader here would otherwise score as clean.

The three grammars (JavaScript, TypeScript, TSX) are selected by extension.
JSX rides on the JavaScript grammar, which parses it; ``.tsx`` needs its own
grammar because the type syntax and the angle brackets are otherwise ambiguous.
"""

from __future__ import annotations

import difflib
import json
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

from tree_sitter import Language, Node, Parser
from tree_sitter_javascript import language as _js_language
from tree_sitter_typescript import (
    language_tsx as _tsx_language,
)
from tree_sitter_typescript import (
    language_typescript as _ts_language,
)

from mcgyvr.gate.adapter import (
    LanguageAdapter,
    ToolFailedError,
    plain_env,
    require_tool,
    trusted_stdout,
)
from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding

_ESLINT = "eslint"
_PRETTIER = "prettier"

# Grammars are built once at import — they are hard dependencies, cheap to
# construct, and immutable, so a fresh Parser per parse is all a call needs.
_JS = Language(_js_language())
_TS = Language(_ts_language())
_TSX = Language(_tsx_language())

# Extension → grammar. ``.tsx`` is its own grammar; ``.jsx`` is not — the
# JavaScript grammar already parses JSX. TypeScript's module variants (``.mts``,
# ``.cts``) share the plain TypeScript grammar.
_TS_EXTENSIONS = (".ts", ".mts", ".cts")
_TSX_EXTENSIONS = (".tsx",)
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")
_EXTENSIONS = _TS_EXTENSIONS + _TSX_EXTENSIONS + _JS_EXTENSIONS

# eslint marks a real error with severity 2 and an advisory with 1. Only an
# error rejects a change: a warning is, by the project's own config, not
# fatal, so charging the worker for one would contradict the project's intent.
#
# This has no ruff counterpart — the Python adapter counts every diagnostic it
# is given — and the asymmetry is deliberate rather than an oversight, because
# the two tools do not mean the same thing by a non-fatal finding. ADR-0025's
# 2026-08-16 amendment is where that is argued and where it must be changed;
# this constant is the implementation of a decision, not the decision. Under
# the current `eslint.config.mjs` all 66 enabled rules are severity `error`, so
# the filter drops nothing today (#261).
_ESLINT_ERROR = 2


class JavaScriptAdapter(LanguageAdapter):
    """One adapter for the JS/TS family: ``.js/.jsx/.mjs/.cjs/.ts/.tsx/.mts/.cts``."""

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
        if node is None:  # has_error with no locatable node — nothing to point at
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

    def structural_checks(self, change: FileChange, repo: Path) -> list[Finding]:
        root = self._parse(repo / change.path)
        if root is None or root.has_error:
            return []  # the syntax pass owns a broken file; do not double-report
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

    def lint(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        files = self.owned(changes)
        if not files:
            return []
        eslint = require_tool(_ESLINT)
        proc = subprocess.run(
            [eslint, "--format", "json", "--", *_paths(files)],
            cwd=repo,
            capture_output=True,
            text=True,
            env=plain_env(),
        )
        # eslint reports on 0 (nothing to say) and 1 (problems found); 2 is a
        # fatal error — no config, an unloadable config, an internal failure —
        # and it writes **no stdout at all**, which the JSON read below turns
        # into zero results. That is a clean pass under a linter that never ran
        # (#261), and only the exit code distinguishes it.
        stdout = trusted_stdout(_ESLINT, proc, expected=(0, 1))
        try:
            results = json.loads(stdout or "[]")
        except json.JSONDecodeError as exc:
            raise ToolFailedError(
                _ESLINT, proc.returncode, f"stdout is not JSON: {exc}"
            ) from exc
        added = _added_by_resolved_path(files, repo)
        findings: list[Finding] = []
        for result in results:
            resolved = Path(result.get("filePath", "")).resolve()
            rel = added.get(resolved)
            if rel is None:
                continue
            path, added_lines = rel
            for message in result.get("messages", []):
                line = message.get("line")
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
        prettier = require_tool(_PRETTIER)
        # One batched call finds which files differ at all; in the common case
        # (the worker's code is already formatted) it finds none and this is the
        # only prettier invocation. Only a file that both differs and gained
        # worker lines is then diffed to attribute the change to a line —
        # prettier has no batched per-line diff, so the precise attribution
        # that keeps a pre-existing reflow off the worker is done per such file.
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
        """``tsc --noEmit`` when the repository carries a ``tsconfig.json``.

        The presence of the file *is* the declaration: a repository with a
        ``tsconfig.json`` has said how its TypeScript should be checked, and
        every option that shapes the check — ``strict``, ``lib``, ``target``,
        ``paths`` — is read from it by ``tsc`` itself. Nothing is added here.

        ``--noEmit`` is the one argument, and it is not a strictness flag: it
        says *check without writing output*, which is the difference between
        running a check and running a build. A repository whose config already
        sets ``noEmit`` is unaffected, and one that emits to an ``outDir`` is
        spared having a gate step scatter build artefacts through its tree.

        Deliberately not read: ``package.json`` scripts. A repository that
        declares its own ``typecheck`` script has declared an acceptance
        command, and that belongs in the contract, which outranks this. Measured
        while sizing #133: ``immerjs/immer`` carries a ``tsconfig.json`` and
        pins ``typescript`` at all 27 commits of the pinned corpus while
        declaring **no** type-check script at any of them, which is why script
        detection alone would find nothing on a repository written entirely in
        TypeScript.
        """
        return ["tsc", "--noEmit"] if (repo / "tsconfig.json").is_file() else None

    def locate_test_command(self, repo: Path) -> list[str] | None:
        package = repo / "package.json"
        if not package.is_file():
            return None
        try:
            manifest = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        scripts = manifest.get("scripts")
        if not isinstance(scripts, dict) or "test" not in scripts:
            return None
        return [_package_manager(repo), "test"]

    def _parse(self, path: Path) -> Node | None:
        """Parse ``path`` with the grammar its extension names; ``None`` if unread.

        Bytes, not text: tree-sitter works on bytes and its line numbers index
        the bytes we hand it, which keeps attribution aligned with the change
        set's own line numbering.
        """
        language = _language_for(path.name)
        if language is None:
            return None
        try:
            source = path.read_bytes()
        except OSError:
            return None
        return Parser(language).parse(source).root_node


# --- structural hazards --------------------------------------------------
#
# Each entry maps a tree-sitter node type to a function returning the finding's
# (code, message), or (None, "") when a node of that type is not in fact a
# hazard (a `==` inside a `===` shares no type, but loose vs strict equality is
# told apart by the operator token, so the check lives in the function).


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
    """Every node in the tree, iteratively — no recursion limit on deep files."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


def _first_error(root: Node) -> Node | None:
    """The earliest error or missing node, so a syntax finding points at the cause."""
    errors = [n for n in _walk(root) if n.is_error or n.is_missing]
    return min(errors, key=lambda n: n.start_point) if errors else None


# --- prettier ------------------------------------------------------------


def _prettier_differing(prettier: str, paths: Sequence[str], repo: Path) -> set[str]:
    """The owned files prettier would reformat, from one batched call.

    ``--list-different`` prints, one per line, the paths (as passed) that are
    not already formatted, and exits 1 when there are any — an expected outcome
    here, not a failure. Exit 2 is prettier failing (an invalid config, an
    unresolvable plugin), and it prints nothing, so an unguarded read of stdout
    would say every file is already formatted (#261).
    """
    proc = subprocess.run(
        [prettier, "--list-different", "--", *paths],
        cwd=repo,
        capture_output=True,
        text=True,
        env=plain_env(),
    )
    stdout = trusted_stdout(_PRETTIER, proc, expected=(0, 1))
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def _prettier_reflowed_lines(prettier: str, path: str, repo: Path) -> set[int]:
    """Current-file line numbers prettier would change in ``path``.

    Prettier emits no diff, so we take its formatted output for the one file and
    diff it against the file on disk ourselves, recording the lines on the
    *current* side of a change. Intersected with the worker's added lines by the
    caller, this is what keeps a reflow of pre-existing code off the worker.
    """
    proc = subprocess.run(
        [prettier, "--", path],
        cwd=repo,
        capture_output=True,
        text=True,
        env=plain_env(),
    )
    # Printing a file's formatted output is a 0-or-nothing operation: prettier
    # is not reporting a count here, so 1 is a failure like any other. This
    # runs only for a file prettier has *already* said differs, so returning an
    # empty set on a bad exit would silently unsay it (#261).
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
            touched.update(range(i1 + 1, i2 + 1))  # 1-based current-file lines
    return touched


# --- package manager -----------------------------------------------------


def _package_manager(repo: Path) -> str:
    """The runner that fronts ``<pm> test`` for this repo, by its lockfile."""
    if (repo / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (repo / "yarn.lock").is_file():
        return "yarn"
    if (repo / "bun.lockb").is_file():
        return "bun"
    return "npm"


def _paths(changes: Sequence[FileChange]) -> list[str]:
    return [c.path for c in changes]


def _added_by_resolved_path(
    changes: Sequence[FileChange], repo: Path
) -> dict[Path, tuple[str, frozenset[int]]]:
    """Map each file's resolved absolute path to its relative path and added lines.

    eslint reports absolute filenames; the change set carries repo-relative
    ones. Resolving both sides is what lets a diagnostic be matched back to the
    right file's added-line set.
    """
    return {(repo / c.path).resolve(): (c.path, c.added_lines) for c in changes}
