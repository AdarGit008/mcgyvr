"""Symbol extraction — definitions, references, exports and imports, per language.

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

One exception earns its keep: a definition also carries its **signature**, and an
import is a kind of its own (#115). ADR-0007 puts ``deps[].signature`` on a
contract in the parser's hands rather than a model's — the decomposer names which
symbols a contract depends on, the index states what they look like. Both come
out of the passes already running here, so neither costs a second parse: the
Python signature is unparsed from the ``ast`` node the collector already visits,
and the JS/TS one is that node's own text with the body field sliced off.
"""

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
    """What a symbol occurrence is. A name can appear under more than one."""

    DEFINITION = "definition"
    REFERENCE = "reference"
    EXPORT = "export"
    IMPORT = "import"


@dataclass(frozen=True)
class Symbol:
    """One named occurrence the index can point at.

    ``line`` is 1-based, matching every other line number in the system (the
    change set, findings). ``detail`` carries a coarse category for a
    definition — ``"function"``, ``"class"``, ``"method"`` — and for an import
    the module the name comes from; it is empty for a reference or an export.

    ``signature`` is the declaration without its body: the text ADR-0007 sends
    to a worker as ``deps[].signature``. It is populated for a definition and,
    for an import, holds the whole import statement — which is where an alias
    survives, since ``name`` records the name as depended upon rather than as
    locally bound. It is empty for a reference or an export, both of which are
    occurrences of a name declared elsewhere.
    """

    name: str
    kind: SymbolKind
    path: str
    line: int
    detail: str = ""
    signature: str = ""


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
        """``import a.b as c`` — the dotted module is the name depended upon."""
        statement = ast.unparse(node)
        for alias in node.names:
            self._add(alias.name, SymbolKind.IMPORT, node.lineno, alias.name, statement)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """``from .m import b`` — ``b`` is the dependency, ``.m`` is where from.

        A relative import keeps its leading dots in ``detail``, because that is
        the only thing distinguishing ``from .config import load`` from the
        top-level ``config``. A star import is recorded under the name ``*``:
        a wildcard dependency is still a dependency, and dropping it would make
        the file look as though it depended on nothing.
        """
        module = "." * node.level + (node.module or "")
        statement = ast.unparse(node)
        for alias in node.names:
            self._add(alias.name, SymbolKind.IMPORT, node.lineno, module, statement)
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


def _python_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> str:
    """The declaration without its body: decorators, header, and the docstring.

    Built by unparsing a shallow copy of the node whose body has been replaced —
    by the docstring when there is one, by ``...`` when there is not. The copy is
    what keeps this a statement of fact rather than a mutation: the tree the
    collector is still walking is untouched.

    Decorators are kept because they change how a caller may use the name —
    ``@property`` and ``@staticmethod`` are part of the interface, not of the
    implementation. The docstring is kept whole; deciding how much of it a
    prompt can afford is the decomposer's budget question (#50), not the
    index's, and a signature that quietly truncated would no longer be
    diffable against the file it came from.

    The text is normalised by :func:`ast.unparse` rather than sliced verbatim
    from the source — locating where a header ends in text means finding the
    colon that terminates it, which annotations, lambdas and multi-line
    parameter lists make a parsing problem in its own right. Normalisation is
    reproducible for a given interpreter, and makes a signature stable against
    reformatting of the file it describes.
    """
    docstring = ast.get_docstring(node, clean=False)
    body: ast.expr = (
        ast.Constant(docstring) if docstring is not None else ast.Constant(Ellipsis)
    )
    stub = copy.copy(node)
    stub.body = [ast.Expr(body)]
    return ast.unparse(stub)


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
    return Symbol(
        name,
        SymbolKind.DEFINITION,
        path,
        _line(node),
        "function",
        _declaration_keyword(node) + _js_signature(node, value),
    )


def _declaration_keyword(declarator: Node) -> str:
    """``"const "`` and friends — the keyword the declarator's parent carries.

    A declarator's own text begins at its name, so a verbatim slice would read
    ``f = () =>`` and lose whether the binding is reassignable. The keyword lives
    one node up, on the declaration. When that declaration binds several names at
    once the keyword is repeated onto each, which is the one place this text is
    assembled rather than sliced — and it says of each binding exactly what the
    declaration says of all of them.
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


def _js_imports(path: str, node: Node) -> list[Symbol]:
    """Names an ``import`` statement brings in, and the module they come from.

    Four shapes: ``import {a, b as c} from "m"`` (specifiers — recorded under
    the *source* name, since that is what the index holds a definition for),
    ``import x from "m"`` (a default, whose only name is the local one),
    ``import * as ns from "m"`` (a namespace), and ``import "m"`` (side effects
    only, recorded under the module — a dependency with no name is still a
    dependency).

    A re-export — ``export {x} from "./x"`` — is deliberately not an import
    here. It is already recorded as an EXPORT, and ADR-0007 puts the barrel
    file in the "the index cannot name this" bucket rather than pretending to
    resolve it.
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
            # A default import is a bare identifier directly under the clause;
            # the braced and starred forms are their own node types above.
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
    """The module an import names, with its quotes removed."""
    source = node.child_by_field_name("source")
    if source is None:
        return ""
    for child in source.children:
        if child.type == "string_fragment":
            return _node_text(child) or ""
    return ""


def _last_identifier(node: Node) -> str | None:
    """The final ``identifier`` child of ``node`` — the bound name of ``* as ns``."""
    for child in reversed(node.children):
        if child.type == "identifier":
            return _node_text(child)
    return None


def _js_signature(node: Node, body_owner: Node | None = None) -> str:
    """``node``'s own text up to where its body starts, trailing space removed.

    The body field is what the grammar already separates out, so "signature, not
    body" is a slice rather than a reconstruction — and the text is verbatim,
    which is what makes it diffable against the file. ``body_owner`` names the
    node that actually carries the body when it is not ``node`` itself: a
    ``const f = () => …`` binding is a declarator whose value holds the body, so
    the slice runs from the declarator's name to the arrow function's body.

    A node with no body field — a shape the grammar did not resolve — yields its
    whole text rather than nothing, and it is the caller's job not to ask for a
    signature from a node that has one.
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
