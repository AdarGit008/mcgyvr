""

from __future__ import annotations

import ast
import copy
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from tree_sitter import Language, Node, Parser
from tree_sitter_javascript import language as _js_language
from tree_sitter_typescript import language_tsx as _tsx_language
from tree_sitter_typescript import language_typescript as _ts_language

#nd
#
_JS = Language(_js_language())
_TS = Language(_ts_language())
_TSX = Language(_tsx_language())

#ch
#
#
_PYTHON_EXTENSIONS = (".py", ".pyi")
_TSX_EXTENSIONS = (".tsx",)
_TS_EXTENSIONS = (".ts", ".mts", ".cts")
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs")


class SymbolKind(StrEnum):
    ""

    DEFINITION = "definition"
    REFERENCE = "reference"
    EXPORT = "export"
    IMPORT = "import"


@dataclass(frozen=True)
class Symbol:
    ""

    name: str
    kind: SymbolKind
    path: str
    line: int
    detail: str = ""
    signature: str = ""


def language_of(path: str) -> str | None:
    ""
    if path.endswith(_PYTHON_EXTENSIONS):
        return "python"
    if path.endswith(_TSX_EXTENSIONS + _TS_EXTENSIONS + _JS_EXTENSIONS):
        return "js/ts"
    return None


def extract(path: str, source: bytes) -> list[Symbol]:
    ""
    language = language_of(path)
    if language == "python":
        return _python_symbols(path, source)
    if language == "js/ts":
        return _js_symbols(path, source)
    return []


#


def _python_symbols(path: str, source: bytes) -> list[Symbol]:
    try:
        tree = ast.parse(source.decode("utf-8", "surrogateescape"), filename=path)
    except (SyntaxError, ValueError):
        #
        #
        #
        return []
    collector = _PythonCollector(path)
    collector.visit(tree)
    collector.collect_exports(tree)
    return collector.symbols


class _PythonCollector(ast.NodeVisitor):
    ""

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

    def visit_Call(self, node: ast.Call) -> None:
        name = _called_name(node.func)
        if name is not None:
            self._add(name, SymbolKind.REFERENCE, node.func.lineno)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        ""
        statement = ast.unparse(node)
        for alias in node.names:
            self._add(alias.name, SymbolKind.IMPORT, node.lineno, alias.name, statement)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        ""
        module = "." * node.level + (node.module or "")
        statement = ast.unparse(node)
        for alias in node.names:
            self._add(alias.name, SymbolKind.IMPORT, node.lineno, module, statement)
        self.generic_visit(node)

    def collect_exports(self, tree: ast.Module) -> None:
        ""
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
    ""
    docstring = ast.get_docstring(node, clean=False)
    body: ast.expr = (
        ast.Constant(docstring) if docstring is not None else ast.Constant(Ellipsis)
    )
    stub = copy.copy(node)
    stub.body = [ast.Expr(body)]
    return ast.unparse(stub)


def _called_name(func: ast.expr) -> str | None:
    ""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _module_level_definitions(tree: ast.Module) -> dict[str, int]:
    ""
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
    ""
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


#


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
        name,
        SymbolKind.DEFINITION,
        path,
        _line(node),
        _DEFINITION_TYPES[node.type],
        _js_signature(node),
    )


def _js_declarator_definition(path: str, node: Node) -> Symbol | None:
    ""
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


def _declaration_keyword(declarator: Node) -> str:
    ""
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
    ""
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


def _js_imports(path: str, node: Node) -> list[Symbol]:
    ""
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
            #
            #
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
    ""
    source = node.child_by_field_name("source")
    if source is None:
        return ""
    for child in source.children:
        if child.type == "string_fragment":
            return _node_text(child) or ""
    return ""


def _last_identifier(node: Node) -> str | None:
    ""
    for child in reversed(node.children):
        if child.type == "identifier":
            return _node_text(child)
    return None


def _js_signature(node: Node, body_owner: Node | None = None) -> str:
    ""
    owner = body_owner if body_owner is not None else node
    text = node.text
    if text is None:
        return ""
    body = owner.child_by_field_name("body")
    if body is not None:
        text = text[: body.start_byte - node.start_byte]
    return text.decode("utf-8", "surrogateescape").rstrip()


def _js_reference(path: str, node: Node) -> Symbol | None:
    ""
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
    ""
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
