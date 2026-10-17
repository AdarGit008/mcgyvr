"""The Python language adapter for the gate.

``PythonAdapter`` answers the gate's questions about a Python change set: does it
parse (``ast``), does the new code carry structural hazards, what does ``ruff``
report about it, and which test and type-check commands apply to the repo. Every
finding is attributed to a line the worker added, so code it did not touch is
never charged against it.
"""

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

# The adapter shells out to ``ruff`` for both lint and format. The binary is
# resolved through ``require_tool``, so a missing one is an environment fault
# rather than a finding against the change. The constants below pin the
# configuration used when the repo declares none of its own.
RUFF = "ruff"

# The fallback rule set, used only when the repo says nothing about ruff (see
# ``declares_ruff_config``). Families are named instead of individual rules so
# the adapter picks up the ones ruff grows inside them: E4, E7 and E9 for import
# and statement layout plus runtime errors; F for the names pyflakes finds unused
# or undefined, and W for the warnings it carries; I for import order and
# grouping; N for pep8-naming; UP for spellings the language has since absorbed;
# B for the constructs bugbear treats as mistakes; SIM for simplify; and RUF for
# ruff's own rules. Width and quote style are pinned to ruff's defaults, so a
# repo that declares nothing is judged against this stated selection — wider than
# ruff's own default of E4/E7/E9/F — not left to ruff. ``_RUFF_CONFIG_FILES``
# names the files ruff searches
# for itself: when one of them is present, or a ``[tool.ruff]`` table exists in
# ``pyproject.toml``, the gate runs ruff unconfigured and lets the repo's
# settings stand.
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
    """Return whether ``repo`` carries a ruff configuration of its own.

    A ``ruff.toml`` or ``.ruff.toml`` at the repo root counts, as does a
    ``[tool.ruff]`` table in ``pyproject.toml``. A ``pyproject.toml`` that cannot
    be read or parsed also counts: the gate defers to a config it cannot inspect
    instead of overriding it with the pinned defaults.
    """
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
    """Return the ruff arguments that select the configuration for ``repo``.

    A repo that declares its own config gets no extra arguments, so ruff
    resolves the same settings a developer running it there would get. Otherwise
    the returned arguments put ruff in ``--isolated`` mode and rebuild the
    default config inline, keeping the project's own ``pyproject.toml`` out of
    the run.
    """
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
    """The gate's adapter for ``.py`` and ``.pyi`` files.

    Syntax is decided by ``ast``, structure by an ``ast`` visitor plus the shared
    compliance rules, lint and format by ``ruff``. ``param_mutation`` chooses
    where the shared parameter-mutation rule lands: rejecting, observational, or
    off.
    """

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
            # The parser's own line and message are reported verbatim, since they
            # name the token that broke the file. ``lineno`` is None for a fault
            # detected before any line is known, and a finding without a line is
            # still well formed.
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
            return []  # a file that does not parse is the syntax check's finding
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
        # A missing binary raises out of ``require_tool`` as an environment
        # fault. The config arguments pin the rule set when the repo declares
        # none, and stay empty when it does.
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
        # Exit 0 means ruff found nothing and exit 1 means it printed a report;
        # both carry JSON on stdout and either is trusted. Any other exit code is
        # a ruff that did not run to completion, and ``trusted_stdout`` raises
        # ``ToolFailedError`` carrying ruff's first stderr line instead of
        # reading a verdict out of output that means nothing.
        stdout = trusted_stdout(RUFF, proc, expected=(0, 1))
        try:
            diagnostics = json.loads(stdout or "[]")
        except json.JSONDecodeError as exc:
            # The exit code was one ruff reports with, but the payload is not the
            # JSON it promises, so the tool is broken in a way the gate cannot
            # read and there is no finding to attribute.
            raise ToolFailedError(
                RUFF, proc.returncode, f"stdout is not JSON: {exc}"
            ) from exc
        added = added_by_resolved_path(files, repo)
        if base is not None:
            diagnostics = _without_pre_existing(
                diagnostics, added, repo, base, [ruff, "check", *config_args]
            )
        # ``shipped_default`` records that the rule set came from the gate rather
        # than from the repo's own ruff config, which is what makes the
        # demotion below appropriate: a repo that configures ruff has already made
        # its choice about those codes.
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
                # Two ruff codes are moved from the rejecting ``lint`` axis to
                # the observational ``style`` one, and only under the gate's own
                # default rule set. ``STYLE_LINT_CODES`` are the deprecated typing
                # spellings: they describe code that runs, so they are
                # observations — except on a line that cannot import at all, which
                # is a real fault the compliance pass reports as ``UNIMPORTABLE``
                # on the rejecting axis, and demoting it here would bury it.
                # ``I001`` is isort's complaint about an unsorted import block,
                # filed on the block's first line. When that line imports a
                # deprecated typing name the block reads as unsorted only because
                # ruff would rewrite that import, so charging the worker for the
                # ordering would undo the excusal above.
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
        # ``--diff`` makes ruff format report instead of rewrite: exit 0 with no
        # output when nothing would change, exit 1 with a unified diff of what it
        # would touch.
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
        """Return the declared type checker as a command, or None if there is none.

        ``declared_type_checker`` finds mypy or pyright from the repo's own
        configuration, preferring mypy when both are declared; a repo declaring
        neither gets no type-check rung.
        """
        checker = declared_type_checker(repo)
        return [checker] if checker is not None else None


class _HazardVisitor(ast.NodeVisitor):
    """Flag hand-written hazards on the worker's added lines.

    Three shapes are reported, all on the rejecting ``structure`` axis: mutable
    default arguments, which are shared across calls; bare ``except``, which
    swallows ``KeyboardInterrupt``; and wildcard imports, which hide the names
    they bind. A hazard whose line is not in ``added_lines`` is dropped, so code
    the worker did not touch is never re-reported.
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


class _Unimportable:
    """Cache :func:`unimportable_lines` per file for the length of one lint pass.

    The lint loop asks about the same paths repeatedly, so each file's source is
    read and parsed at most once; ``at`` answers with the ``{line: message}`` map
    of imports that cannot import.
    """

    def __init__(self, repo: Path) -> None:
        self._repo = repo
        self._seen: dict[str, frozenset[int]] = {}

    def at(self, path: str) -> frozenset[int]:
        if path not in self._seen:
            self._seen[path] = frozenset(unimportable_lines(_read(self._repo / path)))
        return self._seen[path]


class _DeprecatedTyping:
    """Cache :func:`deprecated_typing_import_lines` per file for one lint pass.

    Lazily filled on the first query for a path and answered from memory after
    that, so the lint loop parses each file at most once.
    """

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


# Source is read with ``errors="surrogateescape"``, which turns each undecodable
# byte into the lone surrogate U+DC80..U+DCFF (the byte plus 0xDC00). Subtracting
# this base recovers the original byte value for the error message.
_SURROGATE_BASE = 0xDC00


def _not_utf8(path: str, source: str, exc: UnicodeEncodeError) -> Finding:
    """Return the ``syntax`` finding for Python source that is not valid utf-8.

    ``ast.parse`` raises ``UnicodeEncodeError`` on a surrogate the reader let
    through; the message names the offending byte, or the lone surrogate itself
    when the character did not come from the escaped range.
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
        # The parser reports a character offset rather than a line, so the
        # newlines before that offset are counted to place the finding on the
        # line the offending character sits on.
        line=source.count("\n", 0, exc.start) + 1,
        message=f"{detail} is not valid utf-8, which Python source must be",
    )


def _paths(changes: Sequence[FileChange]) -> list[str]:
    return [c.path for c in changes]


def _diagnostic_key(diag: dict[str, object]) -> tuple[object, str]:
    """Return the ``(code, message)`` pair that identifies a diagnostic.

    The pair is what gets compared between a base-revision run and the current
    one, so the location is deliberately left out of it: the same complaint
    about the same code is the same complaint even if it moved.
    """
    return diag.get("code"), str(diag.get("message") or "").strip()


def _without_pre_existing(
    diagnostics: list[dict[str, object]],
    added: dict[Path, tuple[str, frozenset[int]]],
    repo: Path,
    base: str,
    check: list[str],
) -> list[dict[str, object]]:
    """Drop the diagnostics that the base revision already produced.

    Diagnostics for files the change does not touch, and diagnostics for a file
    with nothing on its added lines, pass through untouched. Every other file is
    re-checked at ``base`` by piping its old text to the same ``check`` command,
    and each ``(code, message)`` is excused once per report of it in that run.
    The base's reports on lines the change did not add are removed from the tally
    first, so untouched code cannot excuse a new complaint. A diagnostic that
    still finds an excuse when its turn comes existed before the change and is
    dropped; the rest are kept.
    """
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
        for diag in diags:  # one base report excuses one matching diagnostic
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
    """Return the ``(code, message)`` counts of the base revision's report.

    The old file text is piped to the same tool invocation on stdin, so the run
    needs no checkout of the base tree. A file absent at ``base``, an exit code
    the tool does not report with, and unreadable JSON all yield an empty tally:
    the caller then has nothing to excuse and keeps every diagnostic.
    """
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
    """Return the old-side line numbers a format diff would rewrite.

    Keys are the paths named by the diff's ``---`` headers, values are the lines
    its hunks remove, which is where the formatter's changes land. Added lines
    start nothing, because the question asked of this map is whether a line the
    worker added would be reflowed.
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
            continue  # an added line consumes no old-side line number
        else:
            old_ln += 1  # a context line is present on both sides
    return touched


def _strip_diff_path(raw: str) -> str:
    """Return the path from a diff header, dropping any trailing timestamp."""
    return raw.strip().split("\t", 1)[0]


def _hunk_old_range(header: str) -> tuple[int, int]:
    """Return the ``(start, count)`` old-side range of a unified diff hunk header.

    ``@@ -12,7 +12,8 @@`` gives the line the hunk starts on at the old side and
    how many old lines it covers; the count is written as one when it is omitted.
    """
    minus = header.split("-", 1)[1].split(" ", 1)[0]
    if "," in minus:
        start_s, count_s = minus.split(",", 1)
        return int(start_s), int(count_s)
    return int(minus), 1
