"""Rust symbol extraction on the shared tree-sitter engine.

- DEFINITION: functions (``"method"`` inside an ``impl`` or ``trait`` block, else
  ``"function"``, bodiless trait signatures included), structs, enums, unions,
  traits, type aliases, ``macro_rules!`` macros and modules (``mod m;`` as well as
  inline ``mod m { ... }``). An ``impl`` block has no name of its own and is not a
  definition; its methods are.
- EXPORT: an item, ``const`` or ``static`` whose visibility is exactly
  ``pub`` and is reachable from outside the file's module: every module, struct,
  enum, union or trait around it in the file is exactly ``pub`` too, and it is not
  inside a function body. ``pub(crate)``, ``pub(super)``, ``pub(self)`` and
  ``pub(in path)`` are not exports, on the item or around it. An ``impl`` block has
  no visibility of its own: its ``pub`` methods are exported when the modules
  around the block are, whether or not its self type is ``pub`` (that type may be
  declared in another file). ``const`` and ``static`` items are EXPORT-only, as
  module-level assignments are in Python. A ``pub use`` exports
  each name it re-exports, under its alias when it has one, by the same rule; a
  glob re-export (``pub use m::*``) names nothing and exports nothing, and a
  restricted ``pub(...) use`` exports nothing. A ``#[macro_export]`` macro is
  exported wherever it is defined, since that attribute places it at the crate
  root; any other ``macro_rules!`` is not. Enum variants and trait members carry no
  visibility and are never exported.
- FIELD: each named field of a struct or union, whatever its visibility and never
  also an EXPORT, as Python's class attributes and JavaScript's class fields are
  FIELD only. Tuple-struct fields have no name and enum-variant fields belong to
  the variant, so neither is recorded.
- IMPORT: one per name a ``use`` declaration brings in (its own name, not the
  alias, as Python's ``from m import a as b`` records ``a``), ``"*"`` for a glob, the
  bound module for ``self`` in a list; the detail is the ``::`` path it comes from.
  ``extern crate`` is an import of the crate, and ``pub extern crate c as a``
  re-exports it as ``a``, as ``pub use`` would. A re-export under ``as _`` binds no
  name and exports nothing.
- REFERENCE: a call's callee identifier, a method call's field, a path call's last
  segment (``Self::make()`` gives ``make``, ``f::<T>()`` gives ``f``), and a macro
  invocation's macro name (``println!`` gives ``println``).
- Test code is skipped: a module attributed ``#[cfg(test)]`` and a function
  attributed ``#[test]`` (or a ``...::test`` attribute such as ``#[tokio::test]``)
  contribute no symbols, because no path rule can tell them from the code they sit
  beside.

A macro invocation's body is an opaque token tree to the grammar, so calls and
definitions written inside one (``vec![f(x)]``, an item-generating macro) are not
seen. A file with syntax errors yields what parsed around them (see
:mod:`mcgyvr.orchestrator.languages.engine`).
"""

from __future__ import annotations

from collections.abc import Iterator

from tree_sitter import Language, Node
from tree_sitter_rust import language as _rust_language

from mcgyvr.orchestrator.languages.engine import (
    TreeSitterLanguage,
    definition,
    export,
    field,
    field_text,
    header,
    line,
    node_text,
    reference,
)
from mcgyvr.orchestrator.languages.model import Symbol, SymbolKind

_RUST = Language(_rust_language())

SUFFIXES = (".rs",)

_DEFINITION_TYPES = {
    "function_item": "function",
    "function_signature_item": "function",
    "struct_item": "struct",
    "enum_item": "enum",
    "union_item": "union",
    "trait_item": "trait",
    "type_item": "type",
    "macro_definition": "macro",
    "mod_item": "module",
}

_FUNCTIONS = ("function_item", "function_signature_item")


def _visibility(node: Node) -> str | None:
    """The text of ``node``'s visibility modifier with whitespace removed, if any."""
    for child in node.children:
        if child.type == "visibility_modifier":
            return "".join((node_text(child) or "").split())
    return None


def _is_pub(node: Node) -> bool:
    return _visibility(node) == "pub"


#: The items whose own visibility gates what is declared inside them.
_ENCLOSING = ("mod_item", "struct_item", "enum_item", "union_item", "trait_item")


def _exported(node: Node) -> bool:
    """Exactly ``pub``, inside nothing in this file that is less than ``pub``.

    Every enclosing module, struct, enum, union or trait must be exactly ``pub``; an
    ``impl`` block is passed through to the modules around it; anything inside a
    function body is unreachable and never exported.
    """
    if not _is_pub(node):
        return False
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type in _ENCLOSING and not _is_pub(ancestor):
            return False
        if ancestor.type in ("block", "function_item"):
            return False
        ancestor = ancestor.parent
    return True


def _definition(path: str, node: Node) -> list[Symbol]:
    name_node = node.child_by_field_name("name")
    name = node_text(name_node)
    if name_node is None or name is None:
        return []
    detail = _DEFINITION_TYPES[node.type]
    if node.type in _FUNCTIONS and _in_impl_or_trait(node):
        detail = "method"
    if node.type == "macro_definition":
        # `macro_rules! name`: the rules that follow are the macro's body.
        text = (node.text or b"")[: name_node.end_byte - node.start_byte]
        signature = text.decode("utf-8", "surrogateescape")
    else:
        signature = header(node)
    symbols = [definition(path, node, name, detail, signature)]
    if _exported(node) or (
        node.type == "macro_definition"
        and any(_attribute_text(a) == "macro_export" for a in _outer_attributes(node))
    ):
        symbols.append(export(path, node, name))
    return symbols


def _in_impl_or_trait(node: Node) -> bool:
    block = node.parent
    return (
        block is not None
        and block.type == "declaration_list"
        and block.parent is not None
        and block.parent.type in ("impl_item", "trait_item")
    )


def _field(path: str, node: Node) -> list[Symbol]:
    """A FIELD for a named field of a struct or union, whatever its visibility.

    A tuple struct's positional fields have no name, and the fields of an enum
    variant belong to the variant, so neither is recorded.
    """
    name = field_text(node, "name")
    fields = node.parent
    owner = fields.parent if fields is not None else None
    if name is None or owner is None or owner.type not in ("struct_item", "union_item"):
        return []
    return [field(path, node, name, header(node))]


def _value_item(path: str, node: Node) -> list[Symbol]:
    """EXPORT a ``pub`` const or static; never a DEFINITION."""
    name = field_text(node, "name")
    if name is None or not _exported(node):
        return []
    return [export(path, node, name)]


def _use(path: str, node: Node) -> list[Symbol]:
    statement = node_text(node) or ""
    leaves = list(_use_leaves(node.child_by_field_name("argument"), ""))
    symbols = [
        Symbol(name, SymbolKind.IMPORT, path, line(leaf), module, statement)
        for leaf, name, _alias, module in leaves
    ]
    if _exported(node):
        symbols.extend(
            export(path, leaf, alias or name)
            for leaf, name, alias, _module in leaves
            if name != "*" and alias != "_"
        )
    return symbols


def _use_leaves(
    node: Node | None, prefix: str
) -> Iterator[tuple[Node, str, str | None, str]]:
    """Flatten a ``use`` tree into ``(leaf, name, alias, module)`` per imported name.

    ``prefix`` is the ``::`` path of the enclosing ``a::{...}`` lists.
    """
    if node is None:
        return
    if node.type in ("identifier", "crate", "super", "self"):
        name = node_text(node) or ""
        if node.type == "self" and prefix:
            # `use a::b::{self}` binds the module `b` itself.
            module, _, name = prefix.rpartition("::")
            yield node, name, None, module
        else:
            yield node, name, None, prefix
    elif node.type == "scoped_identifier":
        module = _join(prefix, field_text(node, "path") or "")
        yield node, field_text(node, "name") or "", None, module
    elif node.type == "use_as_clause":
        alias = field_text(node, "alias")
        for leaf, name, _alias, module in _use_leaves(
            node.child_by_field_name("path"), prefix
        ):
            yield leaf, name, alias, module
    elif node.type == "use_wildcard":
        inner = node.named_children[0] if node.named_children else None
        yield node, "*", None, _join(prefix, node_text(inner) or "")
    elif node.type == "scoped_use_list":
        inner_prefix = _join(prefix, field_text(node, "path") or "")
        yield from _use_leaves(node.child_by_field_name("list"), inner_prefix)
    elif node.type == "use_list":
        for child in node.named_children:
            yield from _use_leaves(child, prefix)


def _join(prefix: str, path: str) -> str:
    return f"{prefix}::{path}" if prefix and path else prefix or path


def _extern_crate(path: str, node: Node) -> list[Symbol]:
    name = field_text(node, "name")
    if name is None:
        return []
    statement = node_text(node) or ""
    symbols = [Symbol(name, SymbolKind.IMPORT, path, line(node), name, statement)]
    alias = field_text(node, "alias")
    if _exported(node) and alias != "_":
        symbols.append(export(path, node, alias or name))
    return symbols


def _call(path: str, node: Node) -> list[Symbol]:
    callee = node.child_by_field_name("function")
    if callee is not None and callee.type == "generic_function":
        callee = callee.child_by_field_name("function")
    if callee is None:
        return []
    if callee.type == "identifier":
        return reference(path, node, node_text(callee))
    if callee.type == "field_expression":
        return reference(path, node, field_text(callee, "field"))
    if callee.type == "scoped_identifier":
        return reference(path, node, field_text(callee, "name"))
    return []


def _macro_invocation(path: str, node: Node) -> list[Symbol]:
    macro = node.child_by_field_name("macro")
    if macro is not None and macro.type == "scoped_identifier":
        macro = macro.child_by_field_name("name")
    return reference(path, node, node_text(macro))


def _is_test_code(node: Node) -> bool:
    """True for a ``#[cfg(test)]`` module or a ``#[test]`` function."""
    if node.type not in ("mod_item", "function_item"):
        return False
    wanted = _is_cfg_test if node.type == "mod_item" else _is_test_attribute
    return any(wanted(attribute) for attribute in _outer_attributes(node))


def _outer_attributes(node: Node) -> Iterator[Node]:
    """The ``attribute_item`` siblings right before ``node``, comments allowed
    in between."""
    sibling = node.prev_sibling
    while sibling is not None and sibling.type in (
        "attribute_item",
        "line_comment",
        "block_comment",
    ):
        if sibling.type == "attribute_item":
            yield sibling
        sibling = sibling.prev_sibling


def _attribute_text(item: Node) -> str:
    """``#[cfg(test)]`` as ``cfg(test)``, whitespace removed."""
    attribute = next((c for c in item.named_children if c.type == "attribute"), None)
    return "".join((node_text(attribute) or "").split())


def _is_cfg_test(item: Node) -> bool:
    return _attribute_text(item) == "cfg(test)"


def _is_test_attribute(item: Node) -> bool:
    text = _attribute_text(item)
    return text == "test" or text.endswith("::test")


LANGUAGE = TreeSitterLanguage(
    grammar=lambda _path: _RUST,
    handlers={
        **dict.fromkeys(_DEFINITION_TYPES, _definition),
        "const_item": _value_item,
        "static_item": _value_item,
        "field_declaration": _field,
        "use_declaration": _use,
        "extern_crate_declaration": _extern_crate,
        "call_expression": _call,
        "macro_invocation": _macro_invocation,
    },
    skip=_is_test_code,
)
extract = LANGUAGE.extract
