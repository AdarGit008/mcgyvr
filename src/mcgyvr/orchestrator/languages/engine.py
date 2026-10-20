"""The tree-sitter engine every tree-sitter language extractor runs on.

A language is a :class:`TreeSitterLanguage`: the grammar a path is parsed with, and
a table from node type to the handler that turns one node of that type into
symbols. :meth:`TreeSitterLanguage.extract` parses once, walks the tree once, and
hands each node to the handler its type names; a node type with no handler yields
nothing of its own, and its children are still walked. A language may also name the
subtrees it skips (Rust's test-only modules): a skipped node is neither handled nor
descended into.

tree-sitter does not refuse a file with a syntax error. It returns a tree with
``ERROR`` and missing nodes where the source did not parse, and the walk extracts
whatever did parse around them, so a broken file yields partial symbols rather than
none (unlike Python's ``ast``, where a syntax error yields none).

The helpers below are the ones every language shares: the walk, the text, field and
line of a node, and the declaration header used as a definition's signature.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass

from tree_sitter import Language, Node, Parser

from mcgyvr.orchestrator.languages.model import Symbol, SymbolKind

#: Turns one node into the symbols it contributes, given the file's path.
Handler = Callable[[str, Node], Iterable[Symbol]]


@dataclass(frozen=True)
class TreeSitterLanguage:
    """One tree-sitter language: how a path picks its grammar, which handler each
    node type goes to, and which subtrees are skipped."""

    grammar: Callable[[str], Language]
    handlers: Mapping[str, Handler]
    skip: Callable[[Node], bool] | None = None

    def extract(self, path: str, source: bytes) -> list[Symbol]:
        """Parse ``source`` and return every symbol the handlers emit, in walk order."""
        root = Parser(self.grammar(path)).parse(source).root_node
        symbols: list[Symbol] = []
        for node in walk(root, self.skip):
            handler = self.handlers.get(node.type)
            if handler is not None:
                symbols.extend(handler(path, node))
        return symbols


def walk(root: Node, skip: Callable[[Node], bool] | None = None) -> Iterator[Node]:
    """Yield ``root`` and all its descendants depth-first.

    An explicit stack is used instead of recursion so deep trees cannot hit the
    interpreter's recursion limit. A node ``skip`` answers true for is not yielded
    and its descendants are not visited.
    """
    stack = [root]
    while stack:
        node = stack.pop()
        if skip is not None and skip(node):
            continue
        yield node
        stack.extend(node.children)


def header(node: Node, body_owner: Node | None = None) -> str:
    """Return the declaration header of ``node`` as decoded source text.

    The text is cut at the body of ``body_owner`` (defaulting to ``node``) and
    trailing whitespace is stripped, so the body is excluded. A node with no body
    field is returned whole.
    """
    owner = body_owner if body_owner is not None else node
    return text_before(node, owner.child_by_field_name("body"))


def text_before(node: Node, stop: Node | None) -> str:
    """Return the text of ``node`` up to where ``stop`` starts (all of it when
    ``stop`` is None), decoded, with trailing whitespace stripped."""
    text = node.text
    if text is None:
        return ""
    if stop is not None:
        text = text[: stop.start_byte - node.start_byte]
    return text.decode("utf-8", "surrogateescape").rstrip()


def definition(path: str, node: Node, name: str, detail: str, signature: str) -> Symbol:
    """A DEFINITION of ``name`` at the line ``node`` starts on."""
    return Symbol(name, SymbolKind.DEFINITION, path, line(node), detail, signature)


def field(path: str, node: Node, name: str, signature: str) -> Symbol:
    """A FIELD named ``name`` at the line ``node`` starts on: a field a type
    declares, whatever its visibility. It is never also an EXPORT."""
    return Symbol(name, SymbolKind.FIELD, path, line(node), "field", signature)


def export(path: str, node: Node, name: str) -> Symbol:
    """An EXPORT of ``name`` at the line ``node`` starts on."""
    return Symbol(name, SymbolKind.EXPORT, path, line(node))


def reference(path: str, node: Node, name: str | None) -> list[Symbol]:
    """A REFERENCE to ``name`` at the line ``node`` starts on; none for no name."""
    if name is None:
        return []
    return [Symbol(name, SymbolKind.REFERENCE, path, line(node))]


def has_child(node: Node, type_: str) -> bool:
    return any(child.type == type_ for child in node.children)


def field_text(node: Node, field: str) -> str | None:
    child = node.child_by_field_name(field)
    return node_text(child) if child is not None else None


def node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    text = node.text
    return text.decode("utf-8", "surrogateescape") if text is not None else None


def line(node: Node) -> int:
    return node.start_point[0] + 1
