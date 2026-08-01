"""Symbol extraction — definitions, references and exports, per language.

The index (#47) needs to answer "where is ``fetch`` defined" and "who calls it"
without a model reading a file. That is a parsing problem, and the answer per
language reuses the investment the gate already made: Python parses with the
standard library's :mod:`ast` (no new dependency, and more precise about
scope than a grammar), and JS/TS parses with **tree-sitter** — the same three
grammars the gate's JS adapter builds (#36). A language with neither is not an
error: :func:`extract` returns nothing and the file is still text-searchable,
which is the "degrades to text-only" guarantee stated once here.

A symbol is deliberately shallow — a name, a kind, and where it sits. The index
is a shortlist, not a semantic model: it points the expensive reader at a few
files, and precise understanding is the reader's job, not the index's.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from tree_sitter import Language, Node, Parser
from tree_sitter_javascript import language as _js_language
from tree_sitter_typescript import language_tsx as _tsx_language
from tree_sitter_typescript import language_typescript as _ts_language

# Grammars build once at import — hard dependencies, cheap to construct, and
# immutable, so a fresh Parser per file is all a parse needs (as the gate does).
_JS = Language(_js_language())
_TS = Language(_ts_language())
_TSX = Language(_tsx_language())

# Extension → language name and, for the JS family, the grammar. The names match
# the gate adapters ("python", "js/ts") so one vocabulary describes the whole
# system. ``.jsx`` rides the JavaScript grammar; ``.tsx`` needs its own.
_PYTHON_EXTENSIONS = (".py", ".pyi")
_TSX_EXTENSIONS = (".tsx",)
_TS_EXTENSIONS = (".ts", ".mts", ".cts")
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")


class SymbolKind(StrEnum):
    """What a symbol occurrence is. A name can appear under all three."""

    DEFINITION = "definition"
    REFERENCE = "reference"
    EXPORT = "export"


@dataclass(frozen=True)
class Symbol:
    """One named occurrence the index can point at.

    ``line`` is 1-based, matching every other line number in the system (the
    change set, findings). ``detail`` carries a coarse category for a
    definition — ``"function"``, ``"class"``, ``"method"`` — and is empty for a
    reference or an export.
    """

    name: str
    kind: SymbolKind
    path: str
    line: int
    detail: str = ""


def language_of(path: str) -> str | None:
    """The language name for a path by extension, or ``None`` if unindexed.

    ``None`` is the "no grammar" signal the index reports as a degraded
    language and still text-searches.
    """
    if path.endswith(_PYTHON_EXTENSIONS):
        return "python"
    if path.endswith(_TSX_EXTENSIONS + _TS_EXTENSIONS + _JS_EXTENSIONS):
        return "js/ts"
    return None


def extract(path: str, source: bytes) -> list[Symbol]:
    """Symbols in ``source`` for ``path``, or ``[]`` when the language has none.

    ``source`` is bytes: tree-sitter works on bytes and its line numbers index
    the bytes handed to it, and Python's parser is fed the decoded text. A file
    that does not parse yields no symbols rather than raising — the text index
    still covers it, so a syntax error degrades precision, not availability.
    """
    language = language_of(path)
    if language == "python":
        return _python_symbols(path, source)
    if language == "js/ts":
        return _js_symbols(path, source)
    return []


# --- Python: the standard library's own parser ---------------------------


def _python_symbols(path: str, source: bytes) -> list[Symbol]:
    try:
        tree = ast.parse(source.decode("utf-8", "surrogateescape"), filename=path)
    except (SyntaxError, ValueError):
        # ValueError covers source with embedded NULs; either way the file is
        # left to the text index rather than aborting the whole build.
        return []
    collector = _PythonCollector(path)
    collector.visit(tree)
    collector.collect_exports(tree)
    return collector.symbols


class _PythonCollector(ast.NodeVisitor):
    """One walk for definitions and references; a separate pass for exports.

    Definitions track class nesting so a ``def`` inside a ``class`` is recorded
    as a method rather than a free function — the distinction a resolver uses to
    tell ``Client.fetch`` from a module-level ``fetch``.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.symbols: list[Symbol] = []
        self._class_depth = 0

    def _add(self, name: str, kind: SymbolKind, line: int, detail: str = "") -> None:
        self.symbols.append(Symbol(name, kind, self.path, line, detail))

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        detail = "method" if self._class_depth else "function"
        self._add(node.name, SymbolKind.DEFINITION, node.lineno, detail)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node.name, SymbolKind.DEFINITION, node.lineno, "class")
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        name = _called_name(node.func)
        if name is not None:
            self._add(name, SymbolKind.REFERENCE, node.func.lineno)
        self.generic_visit(node)

    def collect_exports(self, tree: ast.Module) -> None:
        """Emit an EXPORT per module-level public name.

        An explicit ``__all__`` is authoritative — it is the module's stated
        surface. Absent one, the convention holds: module-level names not
        beginning with an underscore are the public surface. Each export points
        at the definition line when one is known, else at the module start.
        """
        definitions = _module_level_definitions(tree)
        declared = _dunder_all(tree)
        names = (
            declared
            if declared is not None
            else [name for name in definitions if not name.startswith("_")]
        )
        for name in names:
            self._add(name, SymbolKind.EXPORT, definitions.get(name, 1))


def _called_name(func: ast.expr) -> str | None:
    """The callable's name at a call site: ``f()`` -> ``f``, ``a.f()`` -> ``f``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _module_level_definitions(tree: ast.Module) -> dict[str, int]:
    """Module-level defined names -> their line, for pointing exports at a def."""
    lines: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            lines.setdefault(node.name, node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    lines.setdefault(target.id, target.lineno)
    return lines


def _dunder_all(tree: ast.Module) -> list[str] | None:
    """The string names in a module-level ``__all__``, or ``None`` if absent."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if isinstance(node.value, ast.List | ast.Tuple):
            return [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    return None


# --- JS/TS: tree-sitter --------------------------------------------------


def _grammar_for(path: str) -> Language:
    if path.endswith(_TSX_EXTENSIONS):
        return _TSX
    if path.endswith(_TS_EXTENSIONS):
        return _TS
    return _JS


def _js_symbols(path: str, source: bytes) -> list[Symbol]:
    root = Parser(_grammar_for(path)).parse(source).root_node
    symbols: list[Symbol] = []
    for node in _walk(root):
        if node.type in _DEFINITION_TYPES:
            symbol = _js_definition(path, node)
            if symbol is not None:
                symbols.append(symbol)
        elif node.type == "variable_declarator":
            symbol = _js_declarator_definition(path, node)
            if symbol is not None:
                symbols.append(symbol)
        elif node.type == "export_statement":
            symbols.extend(_js_exports(path, node))
        elif node.type == "call_expression":
            symbol = _js_reference(path, node)
            if symbol is not None:
                symbols.append(symbol)
    return symbols


_DEFINITION_TYPES = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
}


def _js_definition(path: str, node: Node) -> Symbol | None:
    name = _field_text(node, "name")
    if name is None:
        return None
    return Symbol(
        name, SymbolKind.DEFINITION, path, _line(node), _DEFINITION_TYPES[node.type]
    )


def _js_declarator_definition(path: str, node: Node) -> Symbol | None:
    """A ``const f = () => …`` or ``const f = function …`` binding is a definition.

    A declarator whose value is a function is how JS names most of its helpers;
    treating only ``function`` statements as definitions would miss them. A
    declarator bound to anything else is a variable, not a symbol worth indexing.
    """
    value = node.child_by_field_name("value")
    if value is None or value.type not in ("arrow_function", "function_expression"):
        return None
    name = _field_text(node, "name")
    if name is None:
        return None
    return Symbol(name, SymbolKind.DEFINITION, path, _line(node), "function")


def _js_exports(path: str, node: Node) -> list[Symbol]:
    """Names an ``export`` statement makes public.

    Three shapes cover the ground: ``export function foo`` / ``export const x``
    (a declaration to read names out of), ``export { a, b }`` (an export clause
    of specifiers), and ``export default …`` (recorded under the name
    ``default``). Each yields an EXPORT; the matching DEFINITION, if any, is
    emitted independently by the walk.
    """
    exports: list[Symbol] = []
    line = _line(node)
    if _has_child(node, "default"):
        exports.append(Symbol("default", SymbolKind.EXPORT, path, line))
    for descendant in _walk(node):
        if (
            descendant.type == "export_specifier"
            or descendant.type in _DEFINITION_TYPES
            or descendant.type == "variable_declarator"
        ):
            name = _field_text(descendant, "name")
            if name is not None:
                exports.append(Symbol(name, SymbolKind.EXPORT, path, _line(descendant)))
    return exports


def _js_reference(path: str, node: Node) -> Symbol | None:
    """The callee name at a call site: ``f()`` -> ``f``, ``a.f()`` -> ``f``."""
    callee = node.child_by_field_name("function")
    if callee is None:
        return None
    if callee.type == "identifier":
        name = _node_text(callee)
    elif callee.type == "member_expression":
        name = _field_text(callee, "property")
    else:
        name = None
    if name is None:
        return None
    return Symbol(name, SymbolKind.REFERENCE, path, _line(node))


def _walk(root: Node) -> Iterator[Node]:
    """Every node in the tree, iteratively — no recursion limit on a deep file."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


def _has_child(node: Node, type_: str) -> bool:
    return any(child.type == type_ for child in node.children)


def _field_text(node: Node, field: str) -> str | None:
    child = node.child_by_field_name(field)
    return _node_text(child) if child is not None else None


def _node_text(node: Node) -> str | None:
    text = node.text
    return text.decode("utf-8", "surrogateescape") if text is not None else None


def _line(node: Node) -> int:
    return node.start_point[0] + 1
