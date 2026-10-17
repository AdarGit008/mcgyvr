""

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

if TYPE_CHECKING:  #
    from mcgyvr.sandbox.base import Sandbox

#
#
#re
#
#
_REPORTING = frozenset({0, 1})

#
#
#
RUFF_TIMEOUT_S = 120.0

#
#
#
#
_SOURCE_ROOTS = ("src/",)

#
#
#
_UNDEFINED_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


@dataclass(frozen=True)
class RepairOutcome:
    ""

    repaired: tuple[str, ...] = ()
    environment_issues: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        ""
        return bool(self.repaired)


class RepairError(Exception):
    ""


def repair(
    *,
    repo: Path | None = None,
    sandbox: Sandbox | None = None,
    contract: Contract,
    base: str = "HEAD",
) -> RepairOutcome:
    ""
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
    assert repo is not None  #

    issues: list[str] = []
    try:
        changeset = ChangeSet.detect(repo, base)
    except ChangeSetError as exc:
        #
        #
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
    ""
    return [
        change
        for change in PythonAdapter().owned(changeset.files)
        if contract.scope.permits(change.path)
        and _writes_where_it_says(changeset.repo, change.path, contract)
    ]


def _writes_where_it_says(repo: Path, path: str, contract: Contract) -> bool:
    ""
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
    ""
    try:
        inode = resolved.stat()
    except OSError:
        return False
    if inode.st_nlink <= 1:
        return True
    return _in_scope_names(anchor, inode, contract) >= inode.st_nlink


def _in_scope_names(anchor: Path, inode: os.stat_result, contract: Contract) -> int:
    ""
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


#


def _locate_ruff(issues: list[str]) -> str | None:
    ""
    try:
        return require_tool(RUFF)
    except ToolUnavailableError as exc:
        issues.append(f"repair: {exc.tool} not installed — no fix could be applied")
        return None


def _run_ruff(
    repo: Path, ruff: str, args: Sequence[str], paths: Sequence[str], issues: list[str]
) -> None:
    ""
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


#


def _insert_declared_imports(
    repo: Path,
    ruff: str,
    paths: Sequence[str],
    deps: Sequence[Dependency],
    issues: list[str],
) -> None:
    ""
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
    ""
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
    ""
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
    ""
    if not path.endswith(".py"):
        return None
    relative = path
    for root in _SOURCE_ROOTS:
        if relative.startswith(root):
            relative = relative[len(root) :]
            break
    parts = relative.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]  #
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _undefined_names(
    repo: Path, ruff: str, paths: Sequence[str], issues: list[str]
) -> dict[str, set[str]]:
    ""
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
        #
        #
        issues.append(f"repair: {RUFF} F821 output is not JSON")
        return {}

    #
    #
    by_resolved = {(repo / path).resolve(): path for path in paths}
    undefined: dict[str, set[str]] = {}
    for diagnostic in diagnostics:
        path = by_resolved.get(Path(diagnostic["filename"]).resolve())
        match = _UNDEFINED_NAME.search(diagnostic.get("message", ""))
        if path is not None and match is not None:
            undefined.setdefault(path, set()).add(match.group(1))
    return undefined


def _insert_imports(path: Path, imports: Sequence[str], issues: list[str]) -> None:
    ""
    source = _read_text(path)
    if source is None:
        issues.append(f"repair: {path.name} could not be decoded — no import inserted")
        return
    try:
        tree = ast.parse(source)
    except SyntaxError:
        #
        #
        #
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
    ""
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


#


def _read_bytes(path: Path) -> bytes | None:
    ""
    try:
        return path.read_bytes()
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    ""
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def _write_text(path: Path, source: str) -> None:
    ""
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(source)


def _first_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return "no output"
