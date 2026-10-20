"""Python symbol extraction, built on the standard library :mod:`ast`.

A file that does not parse (a syntax error, or a ValueError such as embedded null
bytes) yields no symbols at all rather than aborting the scan. Class attributes are
FIELD symbols; module-level assignments are not.
"""

from __future__ import annotations

import ast
import copy
import warnings

from mcgyvr.orchestrator.languages.model import Symbol, SymbolKind

SUFFIXES = (".py", ".pyi")


def extract(path: str, source: bytes) -> list[Symbol]:
    """Return the symbols of one Python file."""
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
