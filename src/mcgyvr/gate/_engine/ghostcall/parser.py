"""Parse Python source: collect imports and dotted attribute chains."""

import ast
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImportRef:
    """How a name in scope maps to a real module path."""
    module: str
    attr: Optional[str] = None


@dataclass
class CallInfo:
    """A dotted attribute chain rooted at a known import."""
    raw_chain: list[str]
    resolved_chain: list[str]
    lineno: int
    col_offset: int

    @property
    def display(self) -> str:
        return ".".join(self.raw_chain)

    @property
    def resolved_display(self) -> str:
        return ".".join(self.resolved_chain)


@dataclass
class ParseResult:
    imports: dict[str, ImportRef] = field(default_factory=dict)
    calls: list[CallInfo] = field(default_factory=list)
    star_imports: list[str] = field(default_factory=list)


class _Collector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: dict[str, ImportRef] = {}
        self.attribute_nodes: list[ast.Attribute] = []
        self.star_imports: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self.imports[alias.asname] = ImportRef(module=alias.name)
            else:
                top = alias.name.split(".")[0]
                self.imports[top] = ImportRef(module=top)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None or node.level > 0:
            return
        for alias in node.names:
            if alias.name == "*":
                self.star_imports.append(node.module)
                continue
            local = alias.asname or alias.name
            self.imports[local] = ImportRef(module=node.module, attr=alias.name)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.attribute_nodes.append(node)
        self.generic_visit(node)


def _extract_chain(node: ast.Attribute) -> Optional[list[str]]:
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return None


def parse(source: str) -> ParseResult:
    tree = ast.parse(source)
    c = _Collector()
    c.visit(tree)

    result = ParseResult(imports=c.imports, star_imports=c.star_imports)

    inner_ids = {id(n.value) for n in c.attribute_nodes if isinstance(n.value, ast.Attribute)}
    seen: set[tuple] = set()

    for node in c.attribute_nodes:
        if id(node) in inner_ids:
            continue
        chain = _extract_chain(node)
        if not chain:
            continue
        root = chain[0]
        if root not in c.imports:
            continue
        ref = c.imports[root]
        if ref.attr is None:
            resolved = [ref.module] + chain[1:]
        else:
            resolved = [ref.module, ref.attr] + chain[1:]

        key = (tuple(resolved), node.lineno, node.col_offset)
        if key in seen:
            continue
        seen.add(key)

        result.calls.append(CallInfo(
            raw_chain=chain,
            resolved_chain=resolved,
            lineno=node.lineno,
            col_offset=node.col_offset,
        ))

    return result
