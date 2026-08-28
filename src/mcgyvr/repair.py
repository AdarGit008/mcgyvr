"""Deterministic repair of a rejected change (D21).

The gate is read-only on purpose: ``ruff format --diff`` reports what the
formatter *would* change, ``ruff check`` runs without ``--fix``, and a
formatting violation becomes a :class:`~mcgyvr.gate.Finding` rather than a
rewrite. A checker that edits what it is checking cannot be trusted to have
checked it, so that separation stays.

What it leaves behind is a bill. Every rejection a *tool* could have fixed for
nothing — an unused import, an unsorted block, a line the formatter would
reflow — is instead paid for with a model call, and on a weak local model the
call is the scarce thing. A 7B that produced correct logic with a blank line in
the wrong place is asked to try again, and it is at least as likely to produce
different logic as the same logic formatted.

So this module is the other half of the separation. The gate judges and never
writes; :func:`repair` writes and never judges. The caller's loop is::

    result = gate.run(changeset, contract.scope)
    if not result.accepted and repair(repo=repo, contract=contract, base=base).changed:
        result = gate.run(ChangeSet.detect(repo, base), contract.scope)

and the point of it is the rung that does *not* appear: on a repaired file the
gate is re-run **on the same rung, with no model retry**. A failed attempt
becomes a free pass.

Three constraints hold the lever honest, and each is a way it could otherwise
buy nothing or cost something:

* **It reports what it did, by the bytes.** ``changed`` is computed by
  comparing each file before and after, not by trusting a tool's exit code. A
  caller told "repaired" re-runs the gate; told that on a file nothing touched,
  it re-runs a gate whose answer it already has, and on a failing attempt that
  is a loop that ends at the attempt ceiling rather than a recovery.
* **It stays inside the contract's scope.** The tools are pointed at an
  explicit file list drawn from the change set and filtered through
  :class:`~mcgyvr.scope.Scope`, never at a directory. A formatter run across a
  tree is exactly how a tidy-up escapes its contract: it rewrites a human's
  unrelated file, and the gate never notices because the gate only looks at the
  change.
* **The one step that adds code may only transcribe.** Auto-import insertion
  writes ``from <module> import <name>`` for an undefined name **only** when
  some ``deps`` entry in the contract already declares that name. The repair is
  writing down something the contract said, not inventing a dependency.

Everything here is best effort. A missing ruff, a ruff that dies, a file that
will not decode: all are recorded as environment issues and none of them
raises. The verdict on the change belongs to the gate, and a tidy-up that could
not run has no standing to overturn one — it just reports that it changed
nothing, and the caller escalates exactly as it would have without this module.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.contract import Contract, Dependency
from mcgyvr.gate.adapter import ToolUnavailableError, plain_env, require_tool
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.adapters.python import RUFF
from mcgyvr.gate.changeset import ChangeSet, ChangeSetError, FileChange

#: ruff reports on 0 (clean) and 1 (diagnostics, or fixes applied with some
#: left); anything else is ruff telling us it did not do the job. Same split
#: the adapters make (:func:`mcgyvr.gate.adapter.trusted_stdout`) — read here
#: rather than reused, because an untrustworthy repair is an environment issue
#: and not, as it is for a gate rung, a reason to refuse the change.
_REPORTING = frozenset({0, 1})

#: Directory prefixes that are a packaging root rather than a package. ``src``
#: carries no ``__init__.py`` and is never importable, so ``src/pkg/x.py`` is
#: the module ``pkg.x``; keeping the prefix would emit an import that does not
#: resolve, which replaces one failure with another.
_SOURCE_ROOTS = ("src/",)

#: The name ruff quotes in ``Undefined name `foo```. Read from the message
#: rather than from the source span, because the span is a byte range and the
#: message already carries the identifier ruff resolved.
_UNDEFINED_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


@dataclass(frozen=True)
class RepairOutcome:
    """What a repair pass actually did.

    ``repaired`` holds the paths whose bytes differ from what the worker left,
    which is the only claim a caller can act on: it is what makes re-running
    the gate worth a second subprocess rather than a guaranteed repeat of the
    verdict already in hand.

    ``environment_issues`` mirror
    :class:`~mcgyvr.gate.acceptance.AcceptanceReport`'s — a step that could not
    run, phrased so an operator knows what to install. They never imply
    anything about the change.
    """

    repaired: tuple[str, ...] = ()
    environment_issues: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """Whether any file on disk is different from what the worker wrote."""
        return bool(self.repaired)


def repair(*, repo: Path, contract: Contract, base: str = "HEAD") -> RepairOutcome:
    """Apply every fix a tool can make to the worker's change, in place.

    ``base`` is the pre-worker tree, the same one the gate measured the change
    against, so the files touched here are exactly the files the gate judged.
    Nothing outside ``contract.scope`` is opened, and no model is reached at any
    point — this module imports nothing from :mod:`mcgyvr.runner` and calls no
    dispatcher, which is the whole economic argument for the lever.

    The order is deliberate: imports are inserted **first**, then the fixer,
    then the formatter. The insertion is the only step that writes new code, so
    running the tools after it means they see the file the re-run gate will see
    and the repair never leaves behind a line it added but did not tidy.
    """
    issues: list[str] = []
    try:
        changeset = ChangeSet.detect(repo, base)
    except ChangeSetError as exc:
        # No change set, no file list: repairing a tree we cannot describe is
        # exactly the unscoped tidy-up this module refuses to be.
        return RepairOutcome(environment_issues=(f"repair: {exc}",))

    targets = _repairable(changeset, contract)
    if not targets:
        return RepairOutcome()

    paths = [change.path for change in targets]
    before = {path: _read_bytes(repo / path) for path in paths}

    ruff = _locate_ruff(issues)
    if ruff is not None:
        _insert_declared_imports(repo, ruff, paths, contract.deps, issues)
        _run_ruff(repo, ruff, ["check", "--fix", "--force-exclude"], paths, issues)
        _run_ruff(repo, ruff, ["format", "--force-exclude"], paths, issues)

    return RepairOutcome(
        repaired=tuple(p for p in paths if _read_bytes(repo / p) != before[p]),
        environment_issues=tuple(issues),
    )


def _repairable(changeset: ChangeSet, contract: Contract) -> list[FileChange]:
    """The changed files a repair may open: Python, in scope, still on disk.

    ``owned`` is the adapter's own answer to "is this a Python file the gate
    scans", already excluding deletions and binaries — asking it rather than
    re-deriving the suffix list keeps the repair pointed at precisely the files
    the gate's Python rungs rejected on.
    """
    return [
        change
        for change in PythonAdapter().owned(changeset.files)
        if contract.scope.permits(change.path)
        and (changeset.repo / change.path).is_file()
    ]


# --- the tools ------------------------------------------------------------


def _locate_ruff(issues: list[str]) -> str | None:
    """ruff's path, or ``None`` with the absence recorded for the operator."""
    try:
        return require_tool(RUFF)
    except ToolUnavailableError as exc:
        issues.append(f"repair: {exc.tool} not installed — no fix could be applied")
        return None


def _run_ruff(
    repo: Path, ruff: str, args: Sequence[str], paths: Sequence[str], issues: list[str]
) -> None:
    """Run one ruff rung over ``paths``, noting a fault instead of raising.

    ``--force-exclude`` because the paths are named explicitly: without it ruff
    edits a file its own configuration excludes, and a repository that excluded
    a path has said not to rewrite it. ``--`` because a worker-created filename
    may begin with a dash.
    """
    proc = subprocess.run(
        [ruff, *args, "--", *paths],
        cwd=repo,
        capture_output=True,
        text=True,
        env=plain_env(),
        check=False,
    )
    if proc.returncode not in _REPORTING:
        issues.append(
            f"repair: {RUFF} {args[0]} exited {proc.returncode} — "
            f"{_first_line(proc.stderr)}"
        )


# --- auto-import insertion ------------------------------------------------


def _insert_declared_imports(
    repo: Path,
    ruff: str,
    paths: Sequence[str],
    deps: Sequence[Dependency],
    issues: list[str],
) -> None:
    """Give every undefined name the contract already declared its import.

    The index is built from the contract's ``deps`` — their *signatures*, which
    are the contract's own statement of what each dependency exposes, and the
    only thing this step is permitted to write down. A name ruff cannot resolve
    and the contract never mentioned is a real failure and stays one: guessing
    a module for it would turn a legible rejection into an import that does not
    resolve.
    """
    index = _declared_modules(deps)
    if not index:
        return
    for path, names in _undefined_names(repo, ruff, paths, issues).items():
        wanted = sorted(
            f"from {index[name]} import {name}" for name in names if name in index
        )
        if wanted:
            _insert_imports(repo / path, wanted, issues)


def _declared_modules(deps: Sequence[Dependency]) -> dict[str, str]:
    """Name → module, over every dependency the contract states.

    First declaration wins, matching the order the contract lists them in: two
    dependencies exporting one name is the contract's ambiguity to resolve, and
    picking the later one would make the repair depend on iteration order.
    """
    index: dict[str, str] = {}
    for dep in deps:
        module = _module_of(dep.path)
        if module is None:
            continue
        for name in _declared_names(dep.signature):
            index.setdefault(name, module)
    return index


def _declared_names(signature: str) -> tuple[str, ...]:
    """The names a declared signature defines, parsed rather than matched.

    A signature is a header without a body, so it is completed with a
    placeholder until it parses — ``def f(x) -> None`` and ``class C(B):`` need
    different endings, and a signature that is already whole needs none. A
    signature that parses under none of them is not a declaration of a name and
    contributes nothing: the contract said something this step cannot read, and
    inventing a name from it is the one thing it must not do.
    """
    for completion in ("", ": ...", " ..."):
        try:
            tree = ast.parse(signature + completion)
        except SyntaxError:
            continue
        names = tuple(
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )
        if names:
            return names
    return ()


def _module_of(path: str) -> str | None:
    """The dotted module a repo-relative ``.py`` path is imported as.

    ``None`` where the path cannot name a module — a suffix that is not
    ``.py``, or a directory segment that is not an identifier (``my-pkg/x.py``).
    An import line that does not resolve is a new failure rather than a repair,
    so an unnameable path is skipped instead of guessed at.
    """
    if not path.endswith(".py"):
        return None
    relative = path
    for root in _SOURCE_ROOTS:
        if relative.startswith(root):
            relative = relative[len(root) :]
            break
    parts = relative.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]  # a package is imported by its directory
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _undefined_names(
    repo: Path, ruff: str, paths: Sequence[str], issues: list[str]
) -> dict[str, set[str]]:
    """Per file, the names ruff says are undefined.

    ``--select F821`` asks ruff one question rather than reading whatever the
    repository happens to have enabled: the repair needs the undefined names
    specifically, and a project that never selected ``F`` still has undefined
    names worth an import. JSON rather than the human format for the same
    reason the lint rung uses it — a message layout is not an interface.
    """
    proc = subprocess.run(
        [
            ruff,
            "check",
            "--select",
            "F821",
            "--output-format=json",
            "--force-exclude",
            "--",
            *paths,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=plain_env(),
        check=False,
    )
    if proc.returncode not in _REPORTING:
        issues.append(
            f"repair: {RUFF} check --select F821 exited {proc.returncode} — "
            f"{_first_line(proc.stderr)}"
        )
        return {}
    try:
        diagnostics = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        # ruff promised JSON on a reporting exit code and did not deliver it.
        # Nothing here is trustworthy enough to write an import from.
        issues.append(f"repair: {RUFF} F821 output is not JSON")
        return {}

    # ruff prints absolute filenames; the change set carries repo-relative
    # ones. Resolving both sides is what maps a diagnostic back to its file.
    by_resolved = {(repo / path).resolve(): path for path in paths}
    undefined: dict[str, set[str]] = {}
    for diagnostic in diagnostics:
        path = by_resolved.get(Path(diagnostic["filename"]).resolve())
        match = _UNDEFINED_NAME.search(diagnostic.get("message", ""))
        if path is not None and match is not None:
            undefined.setdefault(path, set()).add(match.group(1))
    return undefined


def _insert_imports(path: Path, imports: Sequence[str], issues: list[str]) -> None:
    """Splice import lines into a file below whatever already imports there."""
    source = _read_text(path)
    if source is None:
        issues.append(f"repair: {path.name} could not be decoded — no import inserted")
        return
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # A file that does not parse is a syntax rejection, which is the
        # gate's to report and a model's to fix. Editing it blind would only
        # move the error.
        return
    lines = source.splitlines(keepends=True)
    present = {line.strip() for line in lines}
    fresh = [f"{line}\n" for line in imports if line not in present]
    if not fresh:
        return
    anchor = _import_anchor(tree)
    lines[anchor:anchor] = fresh
    path.write_text("".join(lines), encoding="utf-8")


def _import_anchor(tree: ast.Module) -> int:
    """The line index to insert imports at: after the docstring and imports.

    Placing them at line 0 would push a module docstring down a line and demote
    it to a plain string expression — valid Python that has quietly deleted the
    module's documentation. Stopping at the first statement that is neither
    keeps the block where a reader expects it, and where ``__future__`` imports
    (which must come first) already are.
    """
    body = list(tree.body)
    anchor = 0
    if body and _is_docstring(body[0]):
        anchor = body[0].end_lineno or anchor
        body = body[1:]
    for node in body:
        if not isinstance(node, ast.Import | ast.ImportFrom):
            break
        anchor = node.end_lineno or anchor
    return anchor


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


# --- io -------------------------------------------------------------------


def _read_bytes(path: Path) -> bytes | None:
    """The file's exact bytes, or ``None`` if it cannot be read.

    Bytes, not text: "did the repair change this file" has to be answered on
    what is on disk, and a decode step could report two different files as the
    same one.
    """
    try:
        return path.read_bytes()
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _first_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return "no output"
