"""Mechanical repair of a change set: bring the Python files a contract permits
up to the toolchain's own standard before anything is reviewed.

`repair` detects the files changed against a base revision (or against the base
of an already-open sandbox), keeps the ones the contract's scope allows, inserts
imports for names the contract declares as dependencies, then runs
`ruff check --fix` and `ruff format` over the survivors. The outcome names the
files the tools actually rewrote and the environment problems — a missing
`ruff`, a timeout, an unexpected exit code — that stopped a fix from happening.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.contract import Contract, Dependency
from mcgyvr.gate.adapter import ToolUnavailableError, plain_env, require_tool
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.adapters.python import RUFF, ruff_config_args
from mcgyvr.gate.changeset import ChangeSet, ChangeSetError, FileChange
from mcgyvr.lines import parser_lines, terminator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.sandbox.base import Sandbox

#: Ruff exit codes that mean "the run itself succeeded": 0 for a clean result,
#: 1 for findings or would-reformat, which is exactly what `--fix` and `format`
#: report when they have work to do.
_REPORTING = frozenset({0, 1})

#: Ceiling on any single ruff invocation; a run that outlives it is abandoned and
#: recorded as an environment issue instead of stalling the repair.
RUFF_TIMEOUT_S = 120.0

#: Path prefixes stripped from a dependency's file path when turning it into an
#: importable module name, so `src/pkg/mod.py` indexes as `pkg.mod`.
_SOURCE_ROOTS = ("src/",)

#: Pulls the offending name out of ruff's F821 message, which quotes it in
#: backticks: "Undefined name `foo`".
_UNDEFINED_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


@dataclass(frozen=True)
class RepairOutcome:
    """What a repair run did: the files it rewrote and the environment problems
    that kept it from doing more."""

    repaired: tuple[str, ...] = ()
    environment_issues: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """True when at least one file's bytes differ from what they were."""
        return bool(self.repaired)


class RepairError(Exception):
    """Raised when `repair` cannot tell which tree to work on: both a sandbox and
    a repo were given, or neither was."""


def repair(
    *,
    repo: Path | None = None,
    sandbox: Sandbox | None = None,
    contract: Contract,
    base: str = "HEAD",
) -> RepairOutcome:
    """Repair the contract-permitted Python files changed against `base`, either
    in `repo` or in `sandbox`'s workspace (where `base` comes from the sandbox).

    Exactly one of `repo` and `sandbox` must be given. A change set that cannot
    be computed is returned as an environment issue rather than raised, because
    the tree has then been left untouched.
    """
    if sandbox is not None and repo is not None:
        raise RepairError(
            "pass `sandbox` or `repo`, not both: a sandbox is a workspace, so "
            "the `repo` beside it would be read by nothing"
        )
    if sandbox is None and repo is None:
        raise RepairError(
            "pass `sandbox` to repair in a caller's own workspace, or `repo` "
            "to repair a tree against a named base"
        )
    if sandbox is not None:
        repo = sandbox.workspace
        base = sandbox.base_changeset_ref()
    assert repo is not None  # narrowing: the checks above leave exactly one source

    issues: list[str] = []
    try:
        changeset = ChangeSet.detect(repo, base)
    except ChangeSetError as exc:
        # Detection needs a usable git tree and a resolvable base. When either is
        # missing nothing can be repaired, but this is the environment's fault
        # rather than the change's, so it is reported instead of raised.
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

    after = {path: _read_bytes(repo / path) for path in paths}
    return RepairOutcome(
        repaired=tuple(path for path in paths if after[path] != before[path]),
        environment_issues=tuple(issues),
    )


def _repairable(changeset: ChangeSet, contract: Contract) -> list[FileChange]:
    """The changed Python files that may be rewritten: owned by the Python
    adapter (so no deletions, binaries or links) and permitted by the contract's
    scope both as named and as resolved."""
    return [
        change
        for change in PythonAdapter().owned(changeset.files)
        if contract.scope.permits(change.path)
        and _writes_where_it_says(changeset.repo, change.path, contract)
    ]


def _writes_where_it_says(repo: Path, path: str, contract: Contract) -> bool:
    """True when `path` is a regular file inside `repo` that resolves to a
    location the scope permits and whose every other name for the same inode is
    permitted too."""
    target = repo / path
    if not target.is_file():
        return False
    anchor = repo.resolve()
    resolved = target.resolve()
    if anchor not in resolved.parents:
        return False
    if not contract.scope.permits(resolved.relative_to(anchor).as_posix()):
        return False
    return _every_name_is_in_scope(anchor, resolved, contract)


def _every_name_is_in_scope(anchor: Path, resolved: Path, contract: Contract) -> bool:
    """For files with more than one hard link, require that every name for the
    inode sits inside the scope, so editing through one name cannot silently
    rewrite a file the contract never granted."""
    try:
        inode = resolved.stat()
    except OSError:
        return False
    if inode.st_nlink <= 1:
        return True
    return _in_scope_names(anchor, inode, contract) >= inode.st_nlink


def _in_scope_names(anchor: Path, inode: os.stat_result, contract: Contract) -> int:
    """Count the in-scope entries under `anchor` that point at `inode`, stopping
    as soon as `st_nlink` is reached; `.git` is skipped."""
    device, number = inode.st_dev, inode.st_ino
    found = 0
    for directory, subdirectories, names in os.walk(anchor):
        subdirectories[:] = [name for name in subdirectories if name != ".git"]
        for name in names:
            candidate = Path(directory) / name
            if not contract.scope.permits(candidate.relative_to(anchor).as_posix()):
                continue
            try:
                entry = candidate.lstat()
            except OSError:
                continue
            if (entry.st_dev, entry.st_ino) == (device, number):
                found += 1
                if found >= inode.st_nlink:
                    return found
    return found


# Locating ruff and running it over the target paths.


def _locate_ruff(issues: list[str]) -> str | None:
    """Path to `ruff`, or None with an environment issue recorded when the tool
    is not installed and therefore no fix at all can be applied."""
    try:
        return require_tool(RUFF)
    except ToolUnavailableError as exc:
        issues.append(f"repair: {exc.tool} not installed — no fix could be applied")
        return None


def _run_ruff(
    repo: Path, ruff: str, args: Sequence[str], paths: Sequence[str], issues: list[str]
) -> None:
    """Run ruff with `args` over `paths` inside `repo`, recording a timeout or an
    exit code outside `_REPORTING` as an environment issue rather than failing."""
    try:
        proc = subprocess.run(
            [ruff, *ruff_config_args(repo), *args, "--", *paths],
            cwd=repo,
            capture_output=True,
            text=True,
            env=plain_env(),
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        issues.append(f"repair: {RUFF} {args[0]} timed out after {RUFF_TIMEOUT_S:g}s")
        return
    if proc.returncode not in _REPORTING:
        issues.append(
            f"repair: {RUFF} {args[0]} exited {proc.returncode} — "
            f"{_first_line(proc.stderr)}"
        )


# Supplying the imports the contract already declares as dependencies.


def _insert_declared_imports(
    repo: Path,
    ruff: str,
    paths: Sequence[str],
    deps: Sequence[Dependency],
    issues: list[str],
) -> None:
    """Insert `from <module> import <name>` for each name ruff reports as
    undefined on `paths`, when the contract's `deps` declare that name."""
    index = _declared_modules(repo, deps)
    if not index:
        return
    for path, names in _undefined_names(repo, ruff, paths, issues).items():
        wanted = sorted(
            f"from {index[name]} import {name}" for name in names if name in index
        )
        if wanted:
            _insert_imports(repo / path, wanted, issues)


def _declared_modules(repo: Path, deps: Sequence[Dependency]) -> dict[str, str]:
    """Map each name declared by a dependency to the module it should be imported
    from, skipping dependencies whose file is absent from `repo`; the first
    declaration of a name wins."""
    index: dict[str, str] = {}
    for dep in deps:
        module = _module_of(dep.path)
        if module is None:
            continue
        if not (repo / dep.path).is_file():
            continue
        for name in _declared_names(dep.signature):
            index.setdefault(name, module)
    return index


def _declared_names(signature: str) -> tuple[str, ...]:
    """Top-level function and class names declared by a dependency signature,
    parsed first as written and then with a trailing `:`/`...` appended so both
    `def f(x)` and `def f(x): ...` yield names."""
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
    """Dotted module name for a repo-relative `.py` path, with any `_SOURCE_ROOTS`
    prefix and a trailing `__init__` removed; None when the remainder is not a run
    of identifiers."""
    if not path.endswith(".py"):
        return None
    relative = path
    for root in _SOURCE_ROOTS:
        if relative.startswith(root):
            relative = relative[len(root) :]
            break
    parts = relative.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]  # a package's `__init__.py` names the package itself
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _undefined_names(
    repo: Path, ruff: str, paths: Sequence[str], issues: list[str]
) -> dict[str, set[str]]:
    """Ask ruff for its F821 diagnostics on `paths` as JSON and group the
    undefined names by file, keyed by the path as the caller spelled it."""
    try:
        proc = subprocess.run(
            [
                ruff,
                *ruff_config_args(repo),
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
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        issues.append(
            f"repair: {RUFF} check --select F821 timed out after {RUFF_TIMEOUT_S:g}s"
        )
        return {}
    if proc.returncode not in _REPORTING:
        issues.append(
            f"repair: {RUFF} check --select F821 exited {proc.returncode} — "
            f"{_first_line(proc.stderr)}"
        )
        return {}
    try:
        diagnostics = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        # Output that is not JSON cannot be trusted to name undefined symbols,
        # so nothing is inserted and the mismatch is reported instead.
        issues.append(f"repair: {RUFF} F821 output is not JSON")
        return {}

    # Ruff prints absolute filenames, so resolve each candidate path once to map
    # a diagnostic back onto the repo-relative path the caller passed.
    by_resolved = {(repo / path).resolve(): path for path in paths}
    undefined: dict[str, set[str]] = {}
    for diagnostic in diagnostics:
        path = by_resolved.get(Path(diagnostic["filename"]).resolve())
        match = _UNDEFINED_NAME.search(diagnostic.get("message", ""))
        if path is not None and match is not None:
            undefined.setdefault(path, set()).add(match.group(1))
    return undefined


def _insert_imports(path: Path, imports: Sequence[str], issues: list[str]) -> None:
    """Write the `imports` that are not already present into `path`, after its
    shebang, docstring and existing import block, using the file's own line
    terminator."""
    source = _read_text(path)
    if source is None:
        issues.append(f"repair: {path.name} could not be decoded — no import inserted")
        return
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Without a parse tree there is no reliable place to put the import, and
        # an unparseable file is ruff's problem to fix first, so skip it here
        # rather than risk writing an import into the middle of broken syntax.
        return
    lines = parser_lines(source)
    present = {line.strip() for line in lines}
    ending = terminator(source)
    fresh = [f"{line}{ending}" for line in imports if line not in present]
    if not fresh:
        return
    anchor = _import_anchor(tree, source)
    lines[anchor:anchor] = fresh
    _write_text(path, "".join(lines))


def _import_anchor(tree: ast.Module, source: str) -> int:
    """Number of lines to insert new imports after: past a shebang, a module
    docstring and any leading `import`/`from` statements."""
    body = list(tree.body)
    anchor = 1 if source.startswith("#!") else 0
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


# File helpers; the readers swallow errors so a caller can record an issue.


def _read_bytes(path: Path) -> bytes | None:
    """File contents for the before/after comparison, or None when the file has
    gone or cannot be read."""
    try:
        return path.read_bytes()
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    """File decoded as UTF-8 with line endings left untouched, or None when it is
    missing or not valid UTF-8."""
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def _write_text(path: Path, source: str) -> None:
    """Write `source` back with `newline=""` so the line endings it already
    carries are written verbatim."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(source)


def _first_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return "no output"
