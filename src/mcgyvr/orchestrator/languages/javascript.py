"""JavaScript, TypeScript and TSX symbol extraction on the shared tree-sitter engine.

``.tsx`` is parsed with the TSX grammar, ``.ts``/``.mts``/``.cts`` with the
TypeScript grammar and the rest with the JavaScript grammar; :func:`grammar_for`
makes that choice, and the rename resolver uses it too.

- DEFINITION: function and generator declarations, classes, methods, and a
  ``const``/``let``/``var`` declarator whose value is an arrow function or a function
  expression. A declarator holding any other value is not a definition.
- EXPORT: every name an ``export`` statement exports, plus ``"default"`` for
  ``export default``.
- IMPORT: one per named, namespace or default import; a side-effect import is named
  after its module. The module string is the detail, the statement the signature.
- REFERENCE: a call's callee identifier, or the property of a member call.

A file with syntax errors yields what parsed around them (see
:mod:`mcgyvr.orchestrator.languages.engine`).
"""

from __future__ import annotations

from tree_sitter import Language, Node
from tree_sitter_javascript import language as _js_language
from tree_sitter_typescript import language_tsx as _tsx_language
from tree_sitter_typescript import language_typescript as _ts_language

from mcgyvr.orchestrator.languages.engine import (
    TreeSitterLanguage,
    definition,
    field_text,
    has_child,
    header,
    line,
    node_text,
    reference,
    walk,
)
from mcgyvr.orchestrator.languages.model import Symbol, SymbolKind

# One tree-sitter grammar per language distribution, built once at import time.
_JS = Language(_js_language())
_TS = Language(_ts_language())
_TSX = Language(_tsx_language())

_TSX_SUFFIXES = (".tsx",)
_TS_SUFFIXES = (".ts", ".mts", ".cts")
_JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs")
SUFFIXES = _TSX_SUFFIXES + _TS_SUFFIXES + _JS_SUFFIXES


def grammar_for(path: str) -> Language:
    """The grammar ``path`` is parsed with, picked by its suffix."""
    if path.endswith(_TSX_SUFFIXES):
        return _TSX
    if path.endswith(_TS_SUFFIXES):
        return _TS
    return _JS


_DEFINITION_TYPES = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
}


def _definition(path: str, node: Node) -> list[Symbol]:
    name = field_text(node, "name")
    if name is None:
        return []
    return [definition(path, node, name, _DEFINITION_TYPES[node.type], header(node))]


def _declarator_definition(path: str, node: Node) -> list[Symbol]:
    """Record a DEFINITION for ``const f = () => ...`` / ``= function () {}``.

    Declarators holding any other kind of value are ignored.
    """
    value = node.child_by_field_name("value")
    if value is None or value.type not in ("arrow_function", "function_expression"):
        return []
    name = field_text(node, "name")
    if name is None:
        return []
    signature = _declaration_keyword(node) + header(node, value)
    return [definition(path, node, name, "function", signature)]


def _declaration_keyword(declarator: Node) -> str:
    """Return the declaring keyword of a declarator, e.g. ``"const "``.

    An empty string is returned when the parent is not a lexical or variable
    declaration or the first child is not ``const``/``let``/``var``.
    """
    parent = declarator.parent
    if parent is None or parent.type not in (
        "lexical_declaration",
        "variable_declaration",
    ):
        return ""
    keyword = parent.children[0] if parent.children else None
    if keyword is None or keyword.type not in ("const", "let", "var"):
        return ""
    return f"{node_text(keyword) or ''} "


def _exports(path: str, node: Node) -> list[Symbol]:
    """Collect the EXPORT symbols of one ``export`` statement.

    A ``default`` keyword yields an EXPORT named ``"default"``; every exported
    specifier, definition or declarator inside the statement yields one EXPORT
    per name, each at its own line.
    """
    exports: list[Symbol] = []
    line_ = line(node)
    if has_child(node, "default"):
        exports.append(Symbol("default", SymbolKind.EXPORT, path, line_))
    for descendant in walk(node):
        if (
            descendant.type == "export_specifier"
            or descendant.type in _DEFINITION_TYPES
            or descendant.type == "variable_declarator"
        ):
            name = field_text(descendant, "name")
            if name is not None:
                exports.append(Symbol(name, SymbolKind.EXPORT, path, line(descendant)))
    return exports


def _imports(path: str, node: Node) -> list[Symbol]:
    """Collect the IMPORT symbols of one ``import`` statement.

    Named specifiers, namespace imports and default imports each become one
    symbol; the module string is stored as the detail and the statement text as
    the signature. A side-effect import (``import "mod"``) contributes a single
    symbol named after the module.
    """
    module = _import_source(node)
    statement = node_text(node) or ""
    names: list[tuple[str, int]] = []
    for descendant in walk(node):
        if descendant.type == "import_specifier":
            name = field_text(descendant, "name")
            if name is not None:
                names.append((name, line(descendant)))
        elif descendant.type == "namespace_import":
            local = _last_identifier(descendant)
            if local is not None:
                names.append((local, line(descendant)))
        elif descendant.type == "import_clause":
            # A default import is a bare identifier directly inside the import
            # clause, so it is picked up here rather than by the specifier or
            # namespace branches above.
            for child in descendant.children:
                if child.type == "identifier":
                    text = node_text(child)
                    if text is not None:
                        names.append((text, line(child)))
    if not names and module:
        names.append((module, line(node)))
    return [
        Symbol(name, SymbolKind.IMPORT, path, line_, module, statement)
        for name, line_ in names
    ]


def _import_source(node: Node) -> str:
    """Return the module string of an import node, or ``""`` if it has none."""
    source = node.child_by_field_name("source")
    if source is None:
        return ""
    for child in source.children:
        if child.type == "string_fragment":
            return node_text(child) or ""
    return ""


def _last_identifier(node: Node) -> str | None:
    """Return the text of the last identifier child, i.e. the local binding
    introduced by a namespace import (``* as ns``)."""
    for child in reversed(node.children):
        if child.type == "identifier":
            return node_text(child)
    return None


def _reference(path: str, node: Node) -> list[Symbol]:
    """Record a REFERENCE for a call expression's callee.

    The callee is named by its identifier (``f(...)``) or, for member calls, by
    its property (``a.b(...)`` gives ``"b"``); other callee shapes are skipped.
    """
    callee = node.child_by_field_name("function")
    if callee is None:
        return []
    if callee.type == "identifier":
        return reference(path, node, node_text(callee))
    if callee.type == "member_expression":
        return reference(path, node, field_text(callee, "property"))
    return []


LANGUAGE = TreeSitterLanguage(
    grammar=grammar_for,
    handlers={
        **dict.fromkeys(_DEFINITION_TYPES, _definition),
        "variable_declarator": _declarator_definition,
        "export_statement": _exports,
        "import_statement": _imports,
        "call_expression": _reference,
    },
)
extract = LANGUAGE.extract
