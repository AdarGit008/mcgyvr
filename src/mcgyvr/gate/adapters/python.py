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
import configparser
import json
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.gate.adapter import (
    LanguageAdapter,
    ToolFailedError,
    plain_env,
    require_tool,
    trusted_stdout,
)
from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.typecheck import STYLE, STYLE_LINT_CODES, compliance_findings

_EXTENSIONS = (".py", ".pyi")

#: The Python toolchain binary, named once. Both gate rungs here are the same
#: program, and `mcgyvr.repair` imports this rather than restating it: repairing
#: with a different tool than the one that rejected would be a second opinion,
#: and a second opinion cannot guarantee the re-run gate accepts.
RUFF = "ruff"


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
            # Every other way source can fail to be Python arrives here, null
            # bytes included ("source code string cannot contain null bytes"
            # is a SyntaxError from 3.12, which is this project's floor).
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
            return []  # syntax pass already owns this; do not double-report
        visitor = _HazardVisitor(change.path, change.added_lines)
        visitor.visit(tree)
        return visitor.findings + compliance_findings(
            tree, change.path, change.added_lines, contract_text=contract_text
        )

    def lint(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        files = self.owned(changes)
        if not files:
            return []
        ruff = require_tool(RUFF)
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
            env=plain_env(),
        )
        # ruff reports on 0 (nothing to say) and 1 (diagnostics); 2 is ruff
        # telling us it failed. On 2 it writes an *empty* stdout, so the JSON
        # read below succeeds and yields no diagnostics — a clean pass under a
        # linter that never ran (#261). The exit code is the only thing that
        # separates the two, so it is checked first.
        stdout = trusted_stdout(RUFF, proc, expected=(0, 1))
        try:
            diagnostics = json.loads(stdout or "[]")
        except json.JSONDecodeError as exc:
            # An expected exit code with unreadable output: not a shape ruff
            # produces today, and inconclusive rather than clean if it ever does.
            raise ToolFailedError(
                RUFF, proc.returncode, f"stdout is not JSON: {exc}"
            ) from exc
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
                code = diag.get("code")
                findings.append(
                    Finding(
                        check=STYLE if code in STYLE_LINT_CODES else "lint",
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
            [ruff, "format", "--diff", "--force-exclude", "--", *_paths(files)],
            cwd=repo,
            capture_output=True,
            text=True,
            env=plain_env(),
        )
        # Same shape as lint, same reason: `ruff format --diff` exits 0 already
        # formatted, 1 would reformat, 2 failed — and on 2 the diff is empty,
        # which reads as "nothing to reflow" (#261).
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
        """Whichever checker this repository configured, invoked bare.

        Bare on purpose. ``mypy`` with no arguments reads the repository's own
        ``files``/``exclude`` and checks what the repository said to check;
        adding a path here would substitute mcgyvr's idea of the scope for the
        one the project wrote down, which is the same error as adding a flag.

        This once said that a repository whose ``[tool.mypy]`` sets no ``files``
        would have its target supplied by the decomposer, since only it knows
        what the change touched. **#142 decided otherwise and nothing appends a
        target anywhere**: mypy's ``exclude`` is not applied to a file named on
        the command line, so appending one would check a file the repository
        said to skip. The case that motivated the idea — bare ``mypy`` exiting 2
        with "Missing target module, package, files, or command" — is caught by
        :meth:`~mcgyvr.gate.acceptance.Acceptance.precondition` against the
        unchanged tree, before an attempt is spent and without charging a
        worker. See :func:`mcgyvr.orchestrator.decompose._acceptance_for`.

        Detection reads the files each checker itself reads, rather than only
        ``pyproject.toml``: a project with ``mypy.ini`` has declared mypy every
        bit as much as one with ``[tool.mypy]``, and ADR-0006 turns on what the
        repository declared, not on where it chose to write it down.
        """
        for command, declared in (
            (["mypy"], _declares_mypy(repo)),
            (["pyright"], _declares_pyright(repo)),
        ):
            if declared:
                return command
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


#: Where ``surrogateescape`` parks a byte it could not decode: bytes ``0x80``
#: to ``0xff`` land on ``U+DC80`` to ``U+DCFF``, so subtracting this base from
#: the surrogate recovers the byte the file actually holds.
_SURROGATE_BASE = 0xDC00


def _not_utf8(path: str, source: str, exc: UnicodeEncodeError) -> Finding:
    """The finding for source the parser will not even be handed.

    :func:`_read` decodes with ``surrogateescape`` deliberately — that is the
    byte convention the rest of mcgyvr is written to (:mod:`mcgyvr.pending`),
    and it is what lets a file with an undecodable byte reach the gate at all
    instead of raising on the way in. ``compile()`` refuses such a string:
    ``ast.parse`` answers a lone surrogate with ``UnicodeEncodeError``, which is
    not a ``SyntaxError``, so it used to leave this adapter and take the whole
    gate run down with it — a crash where a verdict was owed.

    A *syntax* finding, for the same reason a stray brace is one: Python source
    is UTF-8 by definition (:pep:`3120`), so this is a file the parser cannot
    accept — which is precisely what this rung reports, and precisely what has
    to stop the file reaching lint, the type checker and the sandboxed rungs
    below. Returning nothing would let a file no checker ever read pass clean.

    The offending byte is named rather than the codec's message quoted. The
    codec counts characters from the top of the file and a reviewer needs a
    line, and its wording is about a *character* the file does not contain: the
    surrogate is this decoder's placeholder for the byte, so the byte is what is
    reported.
    """
    offending = ord(exc.object[exc.start])
    detail = (
        f"byte 0x{offending - _SURROGATE_BASE:02x}"
        if 0xDC80 <= offending <= 0xDCFF
        else f"the lone surrogate U+{offending:04X}"
    )
    return Finding(
        check="syntax",
        path=path,
        # Characters up to the offending one, counted in newlines. `exc.start`
        # indexes the very string handed to the parser, so this is the line the
        # byte is on in the file as it is on disk.
        line=source.count("\n", 0, exc.start) + 1,
        message=f"{detail} is not valid utf-8, which Python source must be",
    )


# --- type-checker declarations (#114) --------------------------------------
#
# Each checker is looked for in the files it reads its own configuration from,
# so "declared" means what it means to the tool. The order mypy appears in
# before pyright is ARBITRARY and must stay that way: ADR-0004 found the
# benchmark #97 used to rank them traced to a single self-contradicting blog
# post, and ADR-0006 concluded that the choice "leaves this project". A
# repository configuring both is telling us it runs both; this returns one, and
# a repository that cares which declares the command in its contract, which
# always wins over a sniff.


def _declares_mypy(repo: Path) -> bool:
    """Whether mypy is configured here, in any of the four places it looks."""
    if _has_toml_table(repo / "pyproject.toml", "mypy"):
        return True
    if (repo / "mypy.ini").is_file() or (repo / ".mypy.ini").is_file():
        return True
    # setup.cfg is INI, and a bare substring would match a comment or a
    # `[mypy-somepackage.*]` per-module override in a file that never
    # configures mypy itself. The section header is the declaration.
    return _has_ini_section(repo / "setup.cfg", "mypy")


def _declares_pyright(repo: Path) -> bool:
    if (repo / "pyrightconfig.json").is_file():
        return True
    return _has_toml_table(repo / "pyproject.toml", "pyright")


def _has_toml_table(path: Path, name: str) -> bool:
    """Whether ``[tool.<name>]`` is really present — parsed, not grepped.

    A substring test would fire on a comment, on a dependency pin naming the
    tool, or on ``[tool.ruff.lint.mypy-init-return]``. Getting this wrong
    fabricates a type-check command for a repository that runs none, which
    under ADR-0006 is precisely the thing not to do.
    """
    if not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        # An unparseable manifest is not a declaration. Nothing here raises:
        # a malformed file is the target's business, and the honest answer to
        # "does it declare a checker" is no. `UnicodeDecodeError` is named
        # separately because `tomllib` decodes the bytes itself and answers a
        # non-UTF-8 manifest with that rather than with `TOMLDecodeError` — and
        # it is a `ValueError`, so it walked straight out of a function whose
        # only vocabulary downstream is a command or a refusal.
        return False
    tool = document.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get(name), dict)


def _has_ini_section(path: Path, name: str) -> bool:
    """Whether an INI file carries a ``[name]`` section, parsed as INI."""
    if not path.is_file():
        return False
    parser = configparser.ConfigParser()
    try:
        parser.read_string(_read_or_empty(path))
    except configparser.Error:
        return False
    return parser.has_section(name)


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
