"""Extract definitions, references, exports and imports from source files.

Python files are parsed with :mod:`ast`; JavaScript, TypeScript and TSX files
are parsed with the bundled tree-sitter grammars. Every extracted item is
returned as a :class:`Symbol` carrying its :class:`SymbolKind` and the file
path plus 1-based line where it was found.
"""

from __future__ import annotations

import ast
import copy
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from tree_sitter import Language, Node, Parser
from tree_sitter_javascript import language as _js_language
from tree_sitter_typescript import language_tsx as _tsx_language
from tree_sitter_typescript import language_typescript as _ts_language

# One tree-sitter grammar per language distribution, built once at import time.
_JS = Language(_js_language())
_TS = Language(_ts_language())
_TSX = Language(_tsx_language())

# Suffix tuples are grouped per language because str.endswith() takes a tuple;
# they drive the extension-to-language dispatch in language_of().
_PYTHON_EXTENSIONS = (".py", ".pyi")
_TSX_EXTENSIONS = (".tsx",)
_TS_EXTENSIONS = (".ts", ".mts", ".cts")
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")


class SymbolKind(StrEnum):
    """What a :class:`Symbol` represents: a definition site, a call site, an
    export site, an import site, a field on a class, or a property of an object
    shape."""

    DEFINITION = "definition"
    REFERENCE = "reference"
    EXPORT = "export"
    IMPORT = "import"
    FIELD = "field"
    PROPERTY = "property"


@dataclass(frozen=True)
class Symbol:
    """One symbol occurrence.

    ``line`` is 1-based. ``detail`` holds a kind-specific label (``"function"``,
    ``"method"``, ``"class"`` for definitions; the module path for imports) and
    ``signature`` holds the source text of the declaration header or, for
    imports, the whole unparsed statement.
    """

    name: str
    kind: SymbolKind
    path: str
    line: int
    detail: str = ""
    signature: str = ""


def language_of(path: str) -> str | None:
    """Return ``"python"`` or ``"js/ts"`` from the file extension, else None."""
    if path.endswith(_PYTHON_EXTENSIONS):
        return "python"
    if path.endswith(_TSX_EXTENSIONS + _TS_EXTENSIONS + _JS_EXTENSIONS):
        return "js/ts"
    return None


def extract(path: str, source: bytes) -> list[Symbol]:
    """Extract the symbols of ``source``, dispatching on :func:`language_of`.

    Files with an unrecognised extension yield an empty list.
    """
    language = language_of(path)
    if language == "python":
        return _python_symbols(path, source)
    if language == "js/ts":
        return _js_symbols(path, source)
    return []


# Python extraction, built on the standard library AST.


def _python_symbols(path: str, source: bytes) -> list[Symbol]:
    try:
        # Legacy syntax (invalid escapes, old octal/decimal literals) makes the
        # parser emit a SyntaxWarning. Suppress it so a build never leaks
        # warnings to stderr, and so a caller running under ``-W error`` cannot
        # turn the warning into an exception that would discard the whole
        # file's symbols.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source.decode("utf-8", "surrogateescape"), filename=path)
    except (SyntaxError, ValueError):
        # Undecodable bytes already became lone surrogates above, so this is a
        # real syntax error (or a ValueError such as embedded null bytes): the
        # file is skipped rather than aborting the whole scan.
        return []
    collector = _PythonCollector(path)
    collector.visit(tree)
    collector.collect_exports(tree)
    return collector.symbols


class _PythonCollector(ast.NodeVisitor):
    """Collect :class:`Symbol` records while walking a Python module."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.symbols: list[Symbol] = []
        self._class_depth = 0

    def _add(
        self,
        name: str,
        kind: SymbolKind,
        line: int,
        detail: str = "",
        signature: str = "",
    ) -> None:
        self.symbols.append(Symbol(name, kind, self.path, line, detail, signature))

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        detail = "method" if self._class_depth else "function"
        self._add(
            node.name,
            SymbolKind.DEFINITION,
            node.lineno,
            detail,
            _python_signature(node),
        )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(
            node.name,
            SymbolKind.DEFINITION,
            node.lineno,
            "class",
            _python_signature(node),
        )
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        """Record class attributes as FIELD symbols, never module assignments."""
        if self._class_depth > 0:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._add(
                        target.id,
                        SymbolKind.FIELD,
                        node.lineno,
                        "field",
                        ast.unparse(node),
                    )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Record annotated class attributes as FIELD symbols."""
        if self._class_depth > 0 and isinstance(node.target, ast.Name):
            self._add(
                node.target.id,
                SymbolKind.FIELD,
                node.lineno,
                "field",
                ast.unparse(node),
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _called_name(node.func)
        if name is not None:
            self._add(name, SymbolKind.REFERENCE, node.func.lineno)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Record one IMPORT symbol per alias of a plain ``import`` statement."""
        statement = ast.unparse(node)
        for alias in node.names:
            self._add(alias.name, SymbolKind.IMPORT, node.lineno, alias.name, statement)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record one IMPORT symbol per alias of a ``from ... import ...``.

        The detail is the module path rebuilt from ``node.level`` dots and
        ``node.module``, so relative imports keep their leading dots.
        """
        module = "." * node.level + (node.module or "")
        statement = ast.unparse(node)
        for alias in node.names:
            self._add(alias.name, SymbolKind.IMPORT, node.lineno, module, statement)
        self.generic_visit(node)

    def collect_exports(self, tree: ast.Module) -> None:
        """Record EXPORT symbols for the module's public surface.

        Declared names from ``__all__`` are used when present, otherwise the
        module-level definitions that do not start with an underscore. A name
        with no known definition line defaults to line 1.
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


def _python_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> str:
    """Render a definition header as source text, without its body.

    A shallow copy of ``node`` is unparsed with the body replaced by the
    docstring (kept verbatim) or ``...``, which drops nested code while
    preserving decorators, name, parameters and return annotation.
    """
    docstring = ast.get_docstring(node, clean=False)
    body: ast.expr = (
        ast.Constant(docstring) if docstring is not None else ast.Constant(Ellipsis)
    )
    stub = copy.copy(node)
    stub.body = [ast.Expr(body)]
    return ast.unparse(stub)


def _called_name(func: ast.expr) -> str | None:
    """Return the name a call refers to: ``f()`` gives ``"f"``, ``a.b()`` gives
    ``"b"``; any other callee expression gives None."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _module_level_definitions(tree: ast.Module) -> dict[str, int]:
    """Map module-level function names, class names and simple assignment
    targets to their line numbers, keeping the first binding seen."""
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
    """Return the string elements of a module-level ``__all__`` list or tuple.

    Returns None when the module assigns ``__all__`` to something else or does
    not define it at all.
    """
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


# JavaScript/TypeScript extraction, built on tree-sitter.


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
        elif node.type == "import_statement":
            symbols.extend(_js_imports(path, node))
        elif node.type == "assignment_expression":
            symbols.extend(_js_commonjs_exports(path, node))
            prototype = _js_prototype_method(path, node)
            if prototype is not None:
                symbols.append(prototype)
        elif node.type == "call_expression":
            symbol = _js_reference(path, node)
            if symbol is not None:
                symbols.append(symbol)
        elif node.type in ("field_definition", "public_field_definition"):
            symbol = _js_field(path, node)
            if symbol is not None:
                symbols.append(symbol)
        elif node.type == "pair":
            symbol = _js_pair(path, node)
            if symbol is not None:
                symbols.append(symbol)
        elif node.type == "property_signature":
            symbol = _js_property_signature(path, node)
            if symbol is not None:
                symbols.append(symbol)
    return symbols


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


def _js_definition(path: str, node: Node) -> Symbol | None:
    name = _field_text(node, "name")
    if name is None:
        return None
    return Symbol(
        name,
        SymbolKind.DEFINITION,
        path,
        _line(node),
        _DEFINITION_TYPES[node.type],
        _js_signature(node),
    )


def _js_declarator_definition(path: str, node: Node) -> Symbol | None:
    """Record a DEFINITION for ``const f = () => ...`` / ``= function () {}``.

    Declarators holding any other kind of value are ignored.
    """
    value = node.child_by_field_name("value")
    if value is None or value.type not in ("arrow_function", "function_expression"):
        return None
    name = _field_text(node, "name")
    if name is None:
        return None
    return Symbol(
        name,
        SymbolKind.DEFINITION,
        path,
        _line(node),
        "function",
        _declaration_keyword(node) + _js_signature(node, value),
    )


def _js_field(path: str, node: Node) -> Symbol | None:
    """Record a class field as a FIELD symbol."""
    name = _js_declared_name(node)
    if name is None:
        return None
    return Symbol(
        name,
        SymbolKind.FIELD,
        path,
        _line(node),
        "field",
        _js_signature(node),
    )


def _js_pair(path: str, node: Node) -> Symbol | None:
    """Record a plain object-literal key as a PROPERTY symbol.

    A computed key (``[expr]``) names nothing literal, so it is skipped.
    """
    key = node.child_by_field_name("key")
    if key is None or key.type not in ("property_identifier", "identifier"):
        return None
    name = _node_text(key)
    if name is None:
        return None
    return Symbol(name, SymbolKind.PROPERTY, path, _line(node), "property")


def _js_property_signature(path: str, node: Node) -> Symbol | None:
    """Record a TypeScript property signature as a PROPERTY symbol."""
    name = _field_text(node, "name")
    if name is None:
        return None
    return Symbol(name, SymbolKind.PROPERTY, path, _line(node), "property")


def _js_declared_name(node: Node) -> str | None:
    """Return a node's declared name from its ``name`` field, falling back to a
    ``property_identifier`` child (JavaScript class fields carry no name field)."""
    name = _field_text(node, "name")
    if name is not None:
        return name
    for child in node.children:
        if child.type in ("property_identifier", "identifier"):
            return _node_text(child)
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
    return f"{_node_text(keyword) or ''} "


def _js_exports(path: str, node: Node) -> list[Symbol]:
    """Collect the EXPORT symbols of one ``export`` statement.

    A ``default`` keyword yields an EXPORT named ``"default"``; every exported
    specifier, definition or declarator inside the statement yields one EXPORT
    per name, each at its own line.
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


def _js_prototype_method(path: str, node: Node) -> Symbol | None:
    """Record a DEFINITION for a ``Klass.prototype.method = function () {}``
    assignment, the CommonJS-era spelling of a class method."""
    left = node.child_by_field_name("left")
    if left is None or left.type != "member_expression":
        return None
    obj = left.child_by_field_name("object")
    prop = left.child_by_field_name("property")
    if obj is None or prop is None or obj.type != "member_expression":
        return None
    proto = obj.child_by_field_name("property")
    if proto is None or _node_text(proto) != "prototype":
        return None
    name = _node_text(prop) if prop.type == "property_identifier" else None
    if name is None:
        return None
    right = node.child_by_field_name("right")
    if right is None or right.type not in ("function_expression", "arrow_function"):
        return None
    return Symbol(
        name,
        SymbolKind.DEFINITION,
        path,
        _line(node),
        "method",
        _js_signature(right, right),
    )


def _js_commonjs_exports(path: str, node: Node) -> list[Symbol]:
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
    obj_text = _node_text(obj)
    prop_text = _node_text(prop)

    # exports.<name> = ...
    if (
        obj.type == "identifier"
        and obj_text == "exports"
        and prop.type == "property_identifier"
        and prop_text is not None
    ):
        return [Symbol(prop_text, SymbolKind.EXPORT, path, _line(node))]

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
            and _node_text(inner_obj) == "module"
            and _node_text(inner_prop) == "exports"
        ):
            return [Symbol(prop_text, SymbolKind.EXPORT, path, _line(node))]

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
            name = _node_text(key)
            if name is not None:
                exports.append(Symbol(name, SymbolKind.EXPORT, path, _line(child)))
    return exports


def _js_imports(path: str, node: Node) -> list[Symbol]:
    """Collect the IMPORT symbols of one ``import`` statement.

    Named specifiers, namespace imports and default imports each become one
    symbol; the module string is stored as the detail and the statement text as
    the signature. A side-effect import (``import "mod"``) contributes a single
    symbol named after the module.
    """
    module = _import_source(node)
    statement = _node_text(node) or ""
    names: list[tuple[str, int]] = []
    for descendant in _walk(node):
        if descendant.type == "import_specifier":
            name = _field_text(descendant, "name")
            if name is not None:
                names.append((name, _line(descendant)))
        elif descendant.type == "namespace_import":
            local = _last_identifier(descendant)
            if local is not None:
                names.append((local, _line(descendant)))
        elif descendant.type == "import_clause":
            # A default import is a bare identifier directly inside the import
            # clause, so it is picked up here rather than by the specifier or
            # namespace branches above.
            for child in descendant.children:
                if child.type == "identifier":
                    text = _node_text(child)
                    if text is not None:
                        names.append((text, _line(child)))
    if not names and module:
        names.append((module, _line(node)))
    return [
        Symbol(name, SymbolKind.IMPORT, path, line, module, statement)
        for name, line in names
    ]


def _import_source(node: Node) -> str:
    """Return the module string of an import node, or ``""`` if it has none."""
    source = node.child_by_field_name("source")
    if source is None:
        return ""
    for child in source.children:
        if child.type == "string_fragment":
            return _node_text(child) or ""
    return ""


def _last_identifier(node: Node) -> str | None:
    """Return the text of the last identifier child, i.e. the local binding
    introduced by a namespace import (``* as ns``)."""
    for child in reversed(node.children):
        if child.type == "identifier":
            return _node_text(child)
    return None


def _js_signature(node: Node, body_owner: Node | None = None) -> str:
    """Return the declaration header of ``node`` as decoded source text.

    The text is cut at the body of ``body_owner`` (defaulting to ``node``) and
    trailing whitespace is stripped, so the body is excluded.
    """
    owner = body_owner if body_owner is not None else node
    text = node.text
    if text is None:
        return ""
    body = owner.child_by_field_name("body")
    if body is not None:
        text = text[: body.start_byte - node.start_byte]
    return text.decode("utf-8", "surrogateescape").rstrip()


def _js_reference(path: str, node: Node) -> Symbol | None:
    """Record a REFERENCE for a call expression's callee.

    The callee is named by its identifier (``f(...)``) or, for member calls, by
    its property (``a.b(...)`` gives ``"b"``); other callee shapes are skipped.
    """
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
    """Yield ``root`` and all its descendants depth-first.

    An explicit stack is used instead of recursion so deep trees cannot hit the
    interpreter's recursion limit.
    """
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
