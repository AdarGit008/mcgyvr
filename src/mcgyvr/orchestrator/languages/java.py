"""Java symbol extraction on the shared tree-sitter engine.

- DEFINITION: classes, interfaces, enums, records and annotation types (each its
  own detail: ``"class"``, ``"interface"``, ``"enum"``, ``"record"``,
  ``"annotation"``), methods and annotation elements (``"method"``), and
  constructors, compact ones included (``"constructor"``). The line is the line of
  the declaration's name, not of an annotation that precedes it; the signature is
  the declaration up to its body, annotations and modifiers included.
- EXPORT: a declaration that is ``public`` or ``protected``, or implicitly public —
  a member of an interface or annotation type that is not ``private``, and an enum
  constant — and whose every enclosing type is exported in turn. A package-private
  member, a ``private`` interface method, and a member of a local or anonymous
  class are not. Enum constants are EXPORT-only, as module-level assignments are in
  Python.
- FIELD: each declarator of a field or an interface or annotation constant, at the
  line of its name, whatever its visibility and never also an EXPORT, as Python's
  class attributes and JavaScript's class fields are FIELD only. A record's
  components are parameters of its header and are not recorded, as JavaScript's
  constructor parameter properties are not.
- IMPORT: one per import declaration, named by its last segment (``"*"`` for a
  wildcard), with the qualifier as the detail (the whole name for a wildcard),
  ``static`` imports alike; the signature is the statement.
- REFERENCE: a method invocation's name, and the class an instance creation
  (``new Foo<>()``) names.

A file with syntax errors yields what parsed around them (see
:mod:`mcgyvr.orchestrator.languages.engine`).
"""

from __future__ import annotations

from tree_sitter import Language, Node
from tree_sitter_java import language as _java_language

from mcgyvr.orchestrator.languages.engine import (
    TreeSitterLanguage,
    definition,
    export,
    field,
    has_child,
    header,
    line,
    node_text,
    reference,
)
from mcgyvr.orchestrator.languages.model import Symbol, SymbolKind

_JAVA = Language(_java_language())

SUFFIXES = (".java",)

_TYPE_DETAIL = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}

_MEMBER_DETAIL = {
    "method_declaration": "method",
    "annotation_type_element_declaration": "method",
    "constructor_declaration": "constructor",
    "compact_constructor_declaration": "constructor",
}

_DEFINITION_DETAIL = _TYPE_DETAIL | _MEMBER_DETAIL

#: The bodies a member is declared in, and those whose members are public unless
#: declared otherwise.
_BODIES = ("class_body", "interface_body", "enum_body", "annotation_type_body")
_IMPLICITLY_PUBLIC = ("interface_body", "annotation_type_body")


def _modifiers(node: Node) -> set[str]:
    """The modifier keywords of a declaration (``public``, ``static``, ...)."""
    for child in node.children:
        if child.type == "modifiers":
            return {modifier.type for modifier in child.children}
    return set()


def _exported(node: Node) -> bool:
    """Whether the declaration ``node`` is visible outside its package.

    A top-level type must be ``public``. A member must sit directly in the body of a
    type that is itself exported, and be ``public``/``protected``, or implicitly
    public (an interface or annotation member that is not ``private``, or an enum
    constant).
    """
    parent = node.parent
    if parent is None:
        return False
    modifiers = _modifiers(node)
    if parent.type == "program":
        return "public" in modifiers
    body = parent.parent if parent.type == "enum_body_declarations" else parent
    owner = body.parent if body is not None else None
    if (
        body is None
        or body.type not in _BODIES
        or owner is None
        or owner.type not in _TYPE_DETAIL
        or not _exported(owner)
    ):
        return False
    if "private" in modifiers:
        return False
    if body.type in _IMPLICITLY_PUBLIC or node.type == "enum_constant":
        return True
    return "public" in modifiers or "protected" in modifiers


def _definition(path: str, node: Node) -> list[Symbol]:
    name_node = node.child_by_field_name("name")
    name = node_text(name_node)
    if name_node is None or name is None:
        return []
    detail = _DEFINITION_DETAIL[node.type]
    symbols = [definition(path, name_node, name, detail, header(node))]
    if _exported(node):
        symbols.append(export(path, name_node, name))
    return symbols


def _fields(path: str, node: Node) -> list[Symbol]:
    """A FIELD per declarator of a field or interface constant, whatever its
    visibility, at the line of its name."""
    signature = header(node)
    symbols: list[Symbol] = []
    for declarator in node.children_by_field_name("declarator"):
        name_node = declarator.child_by_field_name("name")
        name = node_text(name_node)
        if name_node is not None and name is not None:
            symbols.append(field(path, name_node, name, signature))
    return symbols


def _enum_constant(path: str, node: Node) -> list[Symbol]:
    name_node = node.child_by_field_name("name")
    name = node_text(name_node)
    if name_node is None or name is None or not _exported(node):
        return []
    return [export(path, name_node, name)]


def _import(path: str, node: Node) -> list[Symbol]:
    names = ("scoped_identifier", "identifier")
    target = next((c for c in node.named_children if c.type in names), None)
    qualified = node_text(target) or ""
    if has_child(node, "asterisk"):
        name, module = "*", qualified
    else:
        module, _, name = qualified.rpartition(".")
    statement = node_text(node) or ""
    return [Symbol(name, SymbolKind.IMPORT, path, line(node), module, statement)]


def _method_invocation(path: str, node: Node) -> list[Symbol]:
    return reference(path, node, node_text(node.child_by_field_name("name")))


def _object_creation(path: str, node: Node) -> list[Symbol]:
    type_ = node.child_by_field_name("type")
    if type_ is not None and type_.type == "generic_type":
        type_ = type_.named_children[0] if type_.named_children else None
    if type_ is not None and type_.type == "scoped_type_identifier":
        type_ = type_.named_children[-1] if type_.named_children else None
    if type_ is None or type_.type != "type_identifier":
        return []
    return reference(path, node, node_text(type_))


LANGUAGE = TreeSitterLanguage(
    grammar=lambda _path: _JAVA,
    handlers={
        **dict.fromkeys(_DEFINITION_DETAIL, _definition),
        "field_declaration": _fields,
        "constant_declaration": _fields,
        "enum_constant": _enum_constant,
        "import_declaration": _import,
        "method_invocation": _method_invocation,
        "object_creation_expression": _object_creation,
    },
)
extract = LANGUAGE.extract
