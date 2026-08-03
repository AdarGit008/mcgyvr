"""Resolve a change's calls against the environment the code will run in.

**This module is never imported by mcgyvr.** It is read as text and staged
into the sandbox by :mod:`mcgyvr.gate.semantic`, where it runs under the
*target's* interpreter with the target's own packages importable. That is the
whole point of ADR-0010: resolution by import is not an implementation detail
of the check, it is the check, and the only environment in which its answer is
true is the one the code declared. Nothing here may be imported into the
orchestrator process — doing so would import target code on the host, which
ADR-0005 forbids and which ADR-0010 explicitly carried forward.

It is written to run under an *old* interpreter as well as a new one: the base
image is ``python:3.12-slim`` today, but ``sandbox.image`` can be overridden
with anything the repository actually runs on. Annotations are deferred
(:pep:`563`), so nothing here needs a runtime subscript, and no syntax newer
than 3.8 is used.

The engine is ghostcall's (CLM-0006, vendored and digest-pinned); this module
supplies what the gate needs around it:

**Only added lines are resolved.** The job carries the line numbers
:class:`~mcgyvr.gate.changeset.FileChange` attributed to the worker, and a
call on any other line is never looked at. Pre-existing state in a file does
not fail a worker's change.

**Suppression, which is the mitigation Count 3 obliged.** ``check()``
introspects the *live* interpreter, so correctly-guarded foreign-platform code
is indistinguishable from an invented API — every distinct flag the #129
measurement produced over three repositories was of that kind, and none was a
bug. Three rules answer it, and between them they cover all four observed
sites:

1. An ``if`` whose test depends on the platform is skipped whole — both
   branches, because deciding which branch is foreign means evaluating the
   test, and a static pass that evaluates tests is a different and much worse
   tool. One hop of indirection is followed: ``if WIN:`` where ``WIN`` came
   from a relative import is the exact shape click's ``os.startfile`` sites
   have, and it is the reason a bare-name rule is not enough.
2. A ``try`` whose handler catches ``ImportError``/``ModuleNotFoundError`` is
   skipped whole — that is a module the code already knows may be absent.
3. Chains rooted at ``sys.stdout``/``stderr``/``stdin`` are never flagged.
   Those objects are rebound at runtime by design (click's own test shim is
   what the measurement caught, reading ``sys.stdout._original_fd``), and in a
   container the streams are pipes, so introspecting them answers a different
   question from the one the code is asking.

``if TYPE_CHECKING:`` is skipped for a different reason: its body never runs,
so the live interpreter has no view of it at all.

Every suppression is *counted* and returned. A rung that quietly stopped
looking at half a file would report a clean pass it did not earn.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from importlib import import_module
from typing import Any

# Dotted expressions whose value is a property of the machine the code runs
# on. A test mentioning one of these guards a branch that is not universally
# live, so what the live interpreter can resolve inside it says nothing about
# whether the code is right.
PLATFORM_PREDICATES = (
    "sys.platform",
    "sys.getwindowsversion",
    "sys.implementation",
    "os.name",
    "os.uname",
    "platform.system",
    "platform.machine",
    "platform.uname",
    "platform.python_implementation",
    "platform.win32_ver",
    "platform.mac_ver",
)

# `if TYPE_CHECKING:` bodies never execute, so no verdict about the live
# interpreter applies to them.
TYPE_CHECKING_NAMES = frozenset({"TYPE_CHECKING"})

# A handler catching one of these says the module may legitimately be absent.
IMPORT_ERRORS = frozenset({"ImportError", "ModuleNotFoundError"})

# Module attributes that are rebound at runtime as a matter of course.
DYNAMIC_ROOTS = frozenset({"sys.stdout", "sys.stderr", "sys.stdin"})

# Why a call on an added line was not resolved. Returned per file so a caller
# can see the shape of what was skipped rather than only what was flagged.
REASON_PLATFORM = "platform-guarded"
REASON_IMPORT_GUARD = "import-guarded"
REASON_TYPE_CHECKING = "type-checking-only"
REASON_DYNAMIC_ROOT = "runtime-rebound-root"


# --- static suppression ---------------------------------------------------


def dotted(node: ast.AST) -> str | None:
    """The dotted name a Name/Attribute chain spells, or ``None`` if it is not one."""
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _names_in(node: ast.AST) -> set[str]:
    """Every dotted name mentioned anywhere in ``node``."""
    found: set[str] = set()
    for child in ast.walk(node):
        # Tuple form, not `X | Y`: this file runs under the target's
        # interpreter, which may be older than 3.10.
        if isinstance(child, (ast.Name, ast.Attribute)):
            name = dotted(child)
            if name is not None:
                found.add(name)
    return found


def _is_platform_expr(node: ast.AST, platform_names: set[str]) -> bool:
    """Whether ``node`` depends on the platform, directly or via a known constant."""
    for name in _names_in(node):
        if name in platform_names:
            return True
        for predicate in PLATFORM_PREDICATES:
            if name == predicate or name.startswith(predicate + "."):
                return True
    return False


def _assigned_names(statement: ast.stmt) -> list[str]:
    """The plain module-level names a statement assigns to."""
    if isinstance(statement, ast.Assign):
        return [t.id for t in statement.targets if isinstance(t, ast.Name)]
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return [statement.target.id]
    return []


def _platform_constants(tree: ast.Module) -> set[str]:
    """Module-level names bound to a platform-dependent value, in one module."""
    names: set[str] = set()
    for statement in tree.body:
        value = getattr(statement, "value", None)
        if value is None:
            continue
        if _is_platform_expr(value, set()):
            names.update(_assigned_names(statement))
    return names


def _relative_source(path: str, level: int, module: str | None) -> str | None:
    """The file a ``from . import x`` in ``path`` refers to, if it is on disk.

    Only *relative* imports are followed, and only one hop. An absolute import
    would mean searching ``sys.path`` and reasoning about namespace packages —
    a resolver of its own, for a rule whose whole job is to be conservative.
    The relative form is what a package's own platform constant is imported
    with, which is the case the measurement produced.
    """
    parts = path.split("/")[:-1]  # the importing file's directory
    for _ in range(level - 1):  # each extra dot climbs one package
        if not parts:
            return None
        parts.pop()
    if module:
        parts.extend(module.split("."))
    for candidate in ("/".join(parts) + ".py", "/".join([*parts, "__init__.py"])):
        if os.path.isfile(candidate):
            return candidate
    return None


def platform_names(path: str, tree: ast.Module, cache: dict[str, set[str]]) -> set[str]:
    """Names in ``path`` that stand for a platform test.

    Both the constants assigned in this module and those imported from a
    sibling module by a relative import — ``from ._compat import WIN`` and then
    ``if WIN:`` is how the real false positives were guarded, and a rule that
    only looked at this file would miss every one of them.
    """
    names = _platform_constants(tree)
    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom) or statement.level < 1:
            continue
        source = _relative_source(path, statement.level, statement.module)
        if source is None:
            continue
        if source not in cache:
            cache[source] = _read_platform_constants(source)
        exported = cache[source]
        for alias in statement.names:
            if alias.name in exported:
                names.add(alias.asname or alias.name)
    return names


def _read_platform_constants(source: str) -> set[str]:
    """Parse a sibling module and return its platform-dependent constants."""
    try:
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        return _platform_constants(ast.parse(text))
    except (OSError, SyntaxError, ValueError):
        return set()


def suppressed_spans(
    path: str, tree: ast.Module, cache: dict[str, set[str]]
) -> list[tuple[int, int, str]]:
    """Line ranges whose calls carry no verdict, each with the reason why."""
    guards = platform_names(path, tree, cache)
    spans: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        end = getattr(node, "end_lineno", None)
        if end is None:
            continue
        if isinstance(node, ast.If):
            mentioned = _names_in(node.test)
            if mentioned & TYPE_CHECKING_NAMES or "typing.TYPE_CHECKING" in mentioned:
                spans.append((node.lineno, end, REASON_TYPE_CHECKING))
            elif _is_platform_expr(node.test, guards):
                spans.append((node.lineno, end, REASON_PLATFORM))
        elif isinstance(node, ast.Try) and _catches_import_error(node):
            spans.append((node.lineno, end, REASON_IMPORT_GUARD))
    return spans


def _catches_import_error(node: ast.Try) -> bool:
    """Whether any handler on ``node`` catches an import failure."""
    for handler in node.handlers:
        caught = handler.type
        if caught is None:
            continue
        candidates = caught.elts if isinstance(caught, ast.Tuple) else [caught]
        for candidate in candidates:
            name = dotted(candidate)
            if name is not None and name.split(".")[-1] in IMPORT_ERRORS:
                return True
    return False


def _suppression(line: int, spans: list[tuple[int, int, str]]) -> str | None:
    """The reason ``line`` is suppressed, or ``None`` if it carries a verdict."""
    for start, end, reason in spans:
        if start <= line <= end:
            return reason
    return None


# --- resolution -----------------------------------------------------------


def resolve_file(
    path: str, lines: set[int], cache: dict[str, set[str]]
) -> dict[str, Any]:
    """Resolve every call on ``lines`` in ``path``. Never raises."""
    parse = import_module("ghostcall.parser").parse
    check = import_module("ghostcall.checker").check

    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except OSError as exc:
        return {"path": path, "error": f"unreadable: {exc}"}
    try:
        tree = ast.parse(source)
        parsed = parse(source)
    except (SyntaxError, ValueError) as exc:
        # The syntax rung owns this file; it is not this check's to judge.
        return {"path": path, "error": f"unparsed: {exc}"}

    spans = suppressed_spans(path, tree, cache)
    flags: list[dict[str, Any]] = []
    missing_roots: set[str] = set()
    resolved = 0
    suppressed: dict[str, int] = {}

    for call in parsed.calls:
        if call.lineno not in lines:
            continue
        chain = list(call.resolved_chain)
        reason = _suppression(call.lineno, spans)
        if reason is None and ".".join(chain[:2]) in DYNAMIC_ROOTS:
            reason = REASON_DYNAMIC_ROOT
        if reason is not None:
            suppressed[reason] = suppressed.get(reason, 0) + 1
            continue

        result = check(call)
        status = result.status
        if status == "hallucinated":
            resolved += 1
            flags.append(
                {
                    "line": call.lineno,
                    "chain": call.resolved_display,
                    "missing_attr": result.missing_attr,
                    "parent": result.parent_display,
                    "suggestions": list(result.suggestions or []),
                }
            )
        elif status == "module_missing":
            missing_roots.add(result.missing_attr or chain[0])
        else:
            resolved += 1

    return {
        "path": path,
        "flags": flags,
        "resolved": resolved,
        "missing_roots": sorted(missing_roots),
        "suppressed": suppressed,
    }


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    """Resolve every target in ``job`` and return the whole report."""
    cache: dict[str, set[str]] = {}
    files: list[dict[str, Any]] = []
    for path, lines in sorted(job["targets"].items()):
        files.append(resolve_file(path, set(lines), cache))
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "files": files,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write("usage: semantic_driver.py <job.json> <out.json>\n")
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        job: Any = json.load(handle)
    report = run_job(job)
    with open(argv[2], "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
