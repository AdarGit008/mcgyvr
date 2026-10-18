"""Resolve the attribute chains a change adds, inside the sandbox, using ghostcall.

``mcgyvr.gate.semantic`` reads this file as text, stages it beside a copy of the
vendored ghostcall engine, and runs it there as a script, because the host has no
``ghostcall``. It takes a job of ``{"targets": {path: [added line numbers]}}``
and writes ``{"python", "platform", "files": [...]}``, which the calling rung
interprets into findings and environment issues.

Per target file it parses with ``ghostcall.parser.parse``, keeps only the calls
landing on the added lines, and asks ``ghostcall.checker.check`` whether the
chain resolves against the packages this environment really installs. A chain
that does not resolve is reported with the missing attribute, the parent it was
looked up on, and any suggestions.

Calls it cannot judge honestly are counted as suppressed rather than flagged:
lines inside ``TYPE_CHECKING`` or platform guards, inside a ``try`` that catches
an import error, and chains rooted at ``sys.stdout``/``stderr``/``stdin``, which
are rebound at runtime. A file that cannot be read or parsed becomes a per-file
``error`` entry instead of an exception, so one bad path cannot take the rest of
the job down.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from importlib import import_module
from typing import Any

# Dotted prefixes of the names that read the host platform. A test mentioning
# one of these (or an alias imported from one) depends on the machine the code
# runs on, so a chain underneath it is not evidence of a hallucination.
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

# The unqualified name to look for in an ``if`` test; the ``typing.TYPE_CHECKING``
# spelling is matched separately in ``suppressed_spans``.
TYPE_CHECKING_NAMES = frozenset({"TYPE_CHECKING"})

# Handler names, compared after the last dot, that mark a ``try`` as an
# optional-import fallback rather than a real error path.
IMPORT_ERRORS = frozenset({"ImportError", "ModuleNotFoundError"})

# Calls rooted here are answered by whatever the process bound to the standard
# stream, so their chains cannot be resolved against installed packages.
DYNAMIC_ROOTS = frozenset({"sys.stdout", "sys.stderr", "sys.stdin"})

# Why a call was left unflagged. Each span carries one of these, and the job
# reports them as counts per reason under a file's ``suppressed`` map.
REASON_PLATFORM = "platform-guarded"
REASON_IMPORT_GUARD = "import-guarded"
REASON_TYPE_CHECKING = "type-checking-only"
REASON_DYNAMIC_ROOT = "runtime-rebound-root"


# AST helpers: dotted names out of nodes, the guards that make a call
# undecidable statically, and the line lookup that ties a call to a guard.


def dotted(node: ast.AST) -> str | None:
    """Return ``a.b.c`` for an attribute chain rooted at a plain name.

    ``None`` when the chain ends in something other than a ``Name`` — a call
    result, a subscript, a literal — since no static name can be spelled for it.
    """
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
    """Every name spelled out anywhere beneath ``node``, as dotted strings.

    Both the attribute nodes and the plain names inside them are collected, so
    ``sys.platform == "win32"`` yields ``{"sys.platform", "sys"}`` and a guard
    written against either spelling is still recognised by its caller.
    """
    found: set[str] = set()
    for child in ast.walk(node):
        # ``dotted`` already returns ``None`` for a chain it cannot spell, so
        # the filter below keeps every whole attribute chain and every bare
        # ``Name`` without needing to recurse into children itself.
        if isinstance(child, (ast.Name, ast.Attribute)):
            name = dotted(child)
            if name is not None:
                found.add(name)
    return found


def _is_platform_expr(node: ast.AST, platform_names: set[str]) -> bool:
    """True when ``node`` reads the host platform, directly or through an alias.

    ``platform_names`` holds the file's own flag constants (``IS_WINDOWS``);
    ``PLATFORM_PREDICATES`` covers the raw predicates, matched on the whole
    dotted name or as a prefix of a longer chain like ``sys.platform.startswith``.
    """
    for name in _names_in(node):
        if name in platform_names:
            return True
        for predicate in PLATFORM_PREDICATES:
            if name == predicate or name.startswith(predicate + "."):
                return True
    return False


def _assigned_names(statement: ast.stmt) -> list[str]:
    """The names a plain or annotated assignment binds.

    Only single-name targets are returned: unpacking targets are skipped, which
    keeps the caller's set to names that map one-to-one onto one value.
    """
    if isinstance(statement, ast.Assign):
        return [t.id for t in statement.targets if isinstance(t, ast.Name)]
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return [statement.target.id]
    return []


def _platform_constants(tree: ast.Module) -> set[str]:
    """Names this module binds to an expression that reads the platform.

    So ``IS_WINDOWS = sys.platform == "win32"`` makes ``IS_WINDOWS`` count as a
    platform guard wherever it is tested, not just the predicate it wraps.
    """
    names: set[str] = set()
    for statement in tree.body:
        value = getattr(statement, "value", None)
        if value is None:
            continue
        if _is_platform_expr(value, set()):
            names.update(_assigned_names(statement))
    return names


def _relative_source(path: str, level: int, module: str | None) -> str | None:
    """On-disk file that ``from ..module import name`` at ``path`` refers to.

    ``level`` one stays in the importing file's package, and each further dot
    climbs one package up; ``module`` is then appended as path parts. Both the
    ``<pkg>/<mod>.py`` and ``<pkg>/<mod>/__init__.py`` shapes are tried, and
    ``None`` means no such file exists, so the import is not followed.
    """
    parts = path.split("/")[:-1]  # directories of the importing file
    for _ in range(level - 1):  # one more package up per extra dot
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
    """Platform-flag names visible inside ``tree``, own and imported.

    Starts from the constants the file defines, then adds every name imported by
    name from a relative sibling, provided that sibling exports it as a platform
    constant. ``cache`` maps an already-scanned source file to its exports so a
    shared module is read once per job.
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
    """Platform constants exported by ``source``; empty if it is unusable.

    A sibling that cannot be read or parsed simply contributes no extra guard
    names — a missing constant can lose a suppression, never invent a flag.
    """
    try:
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        return _platform_constants(ast.parse(text))
    except (OSError, SyntaxError, ValueError):
        return set()


def suppressed_spans(
    path: str, tree: ast.Module, cache: dict[str, set[str]]
) -> list[tuple[int, int, str]]:
    """Line ranges where a call must not be flagged, each with its reason.

    Three shapes qualify: an ``if`` whose test mentions ``TYPE_CHECKING`` or a
    platform predicate (the whole statement, so its ``else`` branch is covered
    too), and a ``try`` whose handlers catch an import error. Ranges are
    inclusive and taken from the node's own start and end lines.
    """
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
    """True when any handler of ``node`` names an import error.

    The handler type may be a bare name, a dotted name, or a tuple of either;
    only the last dotted component is compared, so ``builtins.ImportError``
    counts the same as ``ImportError``. A bare ``except:`` catches everything
    and therefore says nothing about imports, so it is skipped.
    """
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
    """Reason for the first span containing ``line``, or ``None`` if unflagged."""
    for start, end, reason in spans:
        if start <= line <= end:
            return reason
    return None


# Per-file resolution, and the job and report shapes the sandbox rung calls.


def resolve_file(
    path: str, lines: set[int], cache: dict[str, set[str]]
) -> dict[str, Any]:
    """Resolve the calls on ``lines`` in one file and describe what happened.

    ``lines`` is the set of added line numbers, so untouched calls cost nothing.
    A call is counted in ``suppressed`` and skipped when a guard span covers it
    or when its root is a standard stream; otherwise it is handed to the checker,
    where a hallucinated chain becomes a ``flags`` entry and an unimportable root
    lands in ``missing_roots``. ``resolved`` counts the calls the environment
    could actually answer, hallucinated ones included, which is what tells the
    caller whether a run was blind or merely found nothing.

    Never raises for a bad target: an unreadable or unparsable file returns a
    ``{"path", "error"}`` entry so the rest of the job still reports.
    """
    parse = import_module("ghostcall.parser").parse
    check = import_module("ghostcall.checker").check

    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        # A strict decode is deliberate: the parser below could not take a
        # surrogate anyway. ``UnicodeDecodeError`` is a ``ValueError``, so it
        # has to be caught beside ``OSError`` or one bad byte anywhere in the
        # change would abort the run for every other file in it.
        return {"path": path, "error": f"unreadable: {exc}"}
    try:
        tree = ast.parse(source)
        parsed = parse(source)
    except (SyntaxError, ValueError) as exc:
        # Same per-file contract for a file the parsers reject, including the
        # ``ValueError`` they raise on source containing a null byte.
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
            # The root imported fine and only the attribute was absent, so the
            # environment did resolve this call — it is a finding, not a fault.
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
            # Nothing could be said about this chain; record the root so the
            # caller can report an image that cannot import it.
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
    """Resolve every target in ``job`` and build the report the rung reads.

    Targets are visited in sorted path order and share one platform-constant
    cache. The report names the interpreter and host platform that produced it,
    so a fault can be traced to the image rather than to the change.
    """
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
