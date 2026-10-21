"""JavaScript, TypeScript and TSX symbol extraction on the shared tree-sitter engine.

``.tsx`` is parsed with the TSX grammar, ``.ts``/``.mts``/``.cts`` with the
TypeScript grammar and the rest with the JavaScript grammar; :func:`grammar_for`
makes that choice, and the rename resolver uses it too.

- DEFINITION: function and generator declarations, classes (abstract ones too),
  methods (``Klass.prototype.m = function () {}`` included), TypeScript enums,
  interfaces and type aliases, and a
  ``const``/``let``/``var`` declarator whose value is an arrow function or a function
  expression. A declarator holding any other value is not a definition.
- FIELD: a class field. PROPERTY: a plain object-literal key, and a TypeScript
  property signature.
- EXPORT: every name an ``export`` statement exports, plus ``"default"`` for
  ``export default``; and CommonJS ``exports.x =``, ``module.exports.x =`` and each
  literal key of ``module.exports = {...}``.
- IMPORT: one per named, namespace or default import; a side-effect import is named
  after its module. The module string is the detail, the statement the signature.
- REFERENCE: a call's callee identifier, or the property of a member call.

A file with syntax errors yields what parsed around them; a JavaScript file whose
parse leaves ERROR nodes is re-parsed once with the matching TypeScript grammar
(``.js``/``.mjs``/``.cjs`` as TS, ``.jsx`` as TSX) so Flow-typed generics still
yield their declarations (see :mod:`mcgyvr.orchestrator.languages.engine`).
"""

from __future__ import annotations

from collections.abc import Iterator

from tree_sitter import Language, Node
from tree_sitter_javascript import language as _js_language
from tree_sitter_typescript import language_tsx as _tsx_language
from tree_sitter_typescript import language_typescript as _ts_language

from mcgyvr.orchestrator.languages.engine import (
    TreeSitterLanguage,
    definition,
    export,
    field,
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


def fallback_for(path: str) -> Language | None:
    """The grammar to retry when ``grammar_for``'s parse leaves ERROR nodes.

    ``.js``/``.mjs``/``.cjs`` retry as TypeScript (whose grammar parses Flow
    generics); ``.jsx`` retries as TSX. The TS/TSX grammars need no fallback.
    """
    if path.endswith(".jsx"):
        return _TSX
    if path.endswith(_JS_SUFFIXES):
        return _TS
    return None


_DEFINITION_TYPES = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "enum_declaration": "enum",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "abstract_class_declaration": "class",
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


def _field(path: str, node: Node) -> list[Symbol]:
    """Record a class field as a FIELD symbol."""
    name = _declared_name(node)
    if name is None:
        return []
    return [field(path, node, name, header(node))]


def _pair(path: str, node: Node) -> list[Symbol]:
    """Record a plain object-literal key as a PROPERTY symbol.

    A computed key (``[expr]``) names nothing literal, so it is skipped.
    """
    key = node.child_by_field_name("key")
    if key is None or key.type not in ("property_identifier", "identifier"):
        return []
    name = node_text(key)
    if name is None:
        return []
    return [Symbol(name, SymbolKind.PROPERTY, path, line(node), "property")]


def _property_signature(path: str, node: Node) -> list[Symbol]:
    """Record a TypeScript property signature as a PROPERTY symbol."""
    name = field_text(node, "name")
    if name is None:
        return []
    return [Symbol(name, SymbolKind.PROPERTY, path, line(node), "property")]


def _declared_name(node: Node) -> str | None:
    """Return a node's declared name from its ``name`` field, falling back to a
    ``property_identifier`` child (JavaScript class fields carry no name field)."""
    name = field_text(node, "name")
    if name is not None:
        return name
    for child in node.children:
        if child.type in ("property_identifier", "identifier"):
            return node_text(child)
    return None


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


_EXPORT_BOUNDARIES = {
    "function_declaration",
    "generator_function_declaration",
    "function_expression",
    "generator_function",
    "arrow_function",
    "method_definition",
    "class_declaration",
    "abstract_class_declaration",
    "class",
}


def _walk_exports(root: Node) -> Iterator[Node]:
    """Yield export-relevant descendants, never entering a nested scope.

    Like :func:`walk`, but stops descending at function, arrow, method and
    class boundaries, so a declaration inside an exported function or class body
    is not mistaken for a module export.
    """
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        if node.type in _EXPORT_BOUNDARIES:
            continue
        stack.extend(node.children)


def _exports(path: str, node: Node) -> list[Symbol]:
    """Collect the EXPORT symbols of one ``export`` statement.

    A ``default`` keyword yields an EXPORT named ``"default"``; every exported
    specifier, definition or declarator inside the statement yields one EXPORT
    per name, each at its own line. Nested scopes — the body of an exported
    function or class, or a declarator's arrow/function value — are not entered,
    so a ``const`` or ``method`` inside them is never an export.
    """
    exports: list[Symbol] = []
    line_ = line(node)
    if has_child(node, "default"):
        exports.append(Symbol("default", SymbolKind.EXPORT, path, line_))
    for descendant in _walk_exports(node):
        if (
            descendant.type == "export_specifier"
            or descendant.type in _DEFINITION_TYPES
            or descendant.type == "variable_declarator"
        ):
            name = field_text(descendant, "name")
            if name is not None:
                exports.append(Symbol(name, SymbolKind.EXPORT, path, line(descendant)))
    return exports


def _assignment(path: str, node: Node) -> list[Symbol]:
    """The CommonJS exports and the prototype method one assignment makes."""
    return _commonjs_exports(path, node) + _prototype_method(path, node)


def _prototype_method(path: str, node: Node) -> list[Symbol]:
    """Record a DEFINITION for a ``Klass.prototype.method = function () {}``
    assignment, the CommonJS-era spelling of a class method."""
    left = node.child_by_field_name("left")
    if left is None or left.type != "member_expression":
        return []
    obj = left.child_by_field_name("object")
    prop = left.child_by_field_name("property")
    if obj is None or prop is None or obj.type != "member_expression":
        return []
    proto = obj.child_by_field_name("property")
    if proto is None or node_text(proto) != "prototype":
        return []
    name = node_text(prop) if prop.type == "property_identifier" else None
    if name is None:
        return []
    right = node.child_by_field_name("right")
    if right is None or right.type not in ("function_expression", "arrow_function"):
        return []
    return [definition(path, node, name, "method", header(right, right))]


def _commonjs_exports(path: str, node: Node) -> list[Symbol]:
    """Collect the EXPORT symbols of a CommonJS public-surface assignment.

    ``exports.name = ...`` and ``module.exports.name = ...`` each export one
    name; ``module.exports = { a, b }`` exports every literal key of the object.
    Any other assignment exports nothing.
    """
    left = node.child_by_field_name("left")
    if left is None or left.type != "member_expression":
        return []
    obj = left.child_by_field_name("object")
    prop = left.child_by_field_name("property")
    if obj is None or prop is None:
        return []
    obj_text = node_text(obj)
    prop_text = node_text(prop)

    # exports.<name> = ...
    if (
        obj.type == "identifier"
        and obj_text == "exports"
        and prop.type == "property_identifier"
        and prop_text is not None
    ):
        return [export(path, node, prop_text)]

    # module.exports.<name> = ...
    if (
        obj.type == "member_expression"
        and prop.type == "property_identifier"
        and prop_text is not None
    ):
        inner_obj = obj.child_by_field_name("object")
        inner_prop = obj.child_by_field_name("property")
        if (
            inner_obj is not None
            and inner_prop is not None
            and node_text(inner_obj) == "module"
            and node_text(inner_prop) == "exports"
        ):
            return [export(path, node, prop_text)]

    # module.exports = { a, b, ... }
    if obj.type == "identifier" and obj_text == "module" and prop_text == "exports":
        right = node.child_by_field_name("right")
        if right is not None and right.type == "object":
            return _commonjs_object_exports(path, right)
    return []


def _commonjs_object_exports(path: str, obj: Node) -> list[Symbol]:
    """Build an EXPORT symbol for every literal key of a ``module.exports`` object."""
    exports: list[Symbol] = []
    for child in obj.children:
        if child.type != "pair":
            continue
        key = child.child_by_field_name("key")
        if key is not None and key.type in ("property_identifier", "identifier"):
            name = node_text(key)
            if name is not None:
                exports.append(export(path, child, name))
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
    fallback=fallback_for,
    handlers={
        **dict.fromkeys(_DEFINITION_TYPES, _definition),
        "variable_declarator": _declarator_definition,
        "export_statement": _exports,
        "import_statement": _imports,
        "assignment_expression": _assignment,
        "call_expression": _reference,
        "field_definition": _field,
        "public_field_definition": _field,
        "pair": _pair,
        "property_signature": _property_signature,
    },
)
extract = LANGUAGE.extract
