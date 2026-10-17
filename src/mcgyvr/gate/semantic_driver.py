""

from __future__ import annotations

import ast
import json
import os
import sys
from importlib import import_module
from typing import Any

#
#
#
#
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

#
#
TYPE_CHECKING_NAMES = frozenset({"TYPE_CHECKING"})

#
IMPORT_ERRORS = frozenset({"ImportError", "ModuleNotFoundError"})

#
DYNAMIC_ROOTS = frozenset({"sys.stdout", "sys.stderr", "sys.stdin"})

#
#
REASON_PLATFORM = "platform-guarded"
REASON_IMPORT_GUARD = "import-guarded"
REASON_TYPE_CHECKING = "type-checking-only"
REASON_DYNAMIC_ROOT = "runtime-rebound-root"


#


def dotted(node: ast.AST) -> str | None:
    ""
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
    ""
    found: set[str] = set()
    for child in ast.walk(node):
        #
        #
        if isinstance(child, (ast.Name, ast.Attribute)):
            name = dotted(child)
            if name is not None:
                found.add(name)
    return found


def _is_platform_expr(node: ast.AST, platform_names: set[str]) -> bool:
    ""
    for name in _names_in(node):
        if name in platform_names:
            return True
        for predicate in PLATFORM_PREDICATES:
            if name == predicate or name.startswith(predicate + "."):
                return True
    return False


def _assigned_names(statement: ast.stmt) -> list[str]:
    ""
    if isinstance(statement, ast.Assign):
        return [t.id for t in statement.targets if isinstance(t, ast.Name)]
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return [statement.target.id]
    return []


def _platform_constants(tree: ast.Module) -> set[str]:
    ""
    names: set[str] = set()
    for statement in tree.body:
        value = getattr(statement, "value", None)
        if value is None:
            continue
        if _is_platform_expr(value, set()):
            names.update(_assigned_names(statement))
    return names


def _relative_source(path: str, level: int, module: str | None) -> str | None:
    ""
    parts = path.split("/")[:-1]  #
    for _ in range(level - 1):  #
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
    ""
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
    ""
    try:
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        return _platform_constants(ast.parse(text))
    except (OSError, SyntaxError, ValueError):
        return set()


def suppressed_spans(
    path: str, tree: ast.Module, cache: dict[str, set[str]]
) -> list[tuple[int, int, str]]:
    ""
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
    ""
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
    ""
    for start, end, reason in spans:
        if start <= line <= end:
            return reason
    return None


#


def resolve_file(
    path: str, lines: set[int], cache: dict[str, set[str]]
) -> dict[str, Any]:
    ""
    parse = import_module("ghostcall.parser").parse
    check = import_module("ghostcall.checker").check

    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        # a
        #
        #`,
        #
        #
        #
        #
        return {"path": path, "error": f"unreadable: {exc}"}
    try:
        tree = ast.parse(source)
        parsed = parse(source)
    except (SyntaxError, ValueError) as exc:
        #
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
    ""
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
