"""Go symbol extraction on the shared tree-sitter engine.

- DEFINITION: functions (``"function"``), methods and interface method specs
  (``"method"``), and type specs and aliases (``"struct"``, ``"interface"`` or
  ``"type"`` from the declared type). The signature of a type is ``type`` plus the
  spec up to its field list or method set.
- EXPORT: what the Go spec calls exported, an identifier whose first character is an
  upper-case letter (Unicode class Lu) that is declared in the package block or is a
  method name. Package-level ``const`` and ``var`` names are EXPORT-only, as
  module-level assignments are in Python: they are never a DEFINITION.
- FIELD: each named struct field, capitalised or not, and never also an EXPORT, as
  Python's class attributes and JavaScript's class fields are FIELD only. An
  embedded field is skipped.
- IMPORT: one per import spec, named by its alias, ``"*"`` for a dot import, the
  import path for a blank (``_``) import, and otherwise the path's last element with
  a major-version suffix (``/v2`` and up, ``.v3``) dropped. The binding of an unaliased
  import is the imported package's own ``package`` clause, which this file cannot
  see, so that name is the convention, not a resolution. The detail is the import
  path; the signature is ``import`` plus the spec.
- REFERENCE: a call's callee identifier, or the selected field of ``x.f(...)``.

A file with syntax errors yields what parsed around them (see
:mod:`mcgyvr.orchestrator.languages.engine`).
"""

from __future__ import annotations

import re
import unicodedata

from tree_sitter import Language, Node
from tree_sitter_go import language as _go_language

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
    text_before,
)
from mcgyvr.orchestrator.languages.model import Symbol, SymbolKind

_GO = Language(_go_language())

SUFFIXES = (".go",)

#: A module major-version path element: ``v2`` and above, never ``v1``.
_MAJOR_VERSION_ELEMENT = re.compile(r"v(?:[2-9]|[1-9][0-9]+)")

#: A gopkg.in-style version suffix on the last element (``yaml.v3``).
_MAJOR_VERSION = re.compile(r"(?:^|\.)v[0-9]+$")


def _exported(name: str) -> bool:
    return bool(name) and unicodedata.category(name[0]) == "Lu"


def _package_level(declaration: Node | None) -> bool:
    """True when ``declaration`` (a const, var or type declaration) sits directly in
    the file, i.e. in the package block rather than in a function body."""
    return declaration is not None and (
        declaration.parent is not None and declaration.parent.type == "source_file"
    )


def _names(node: Node) -> list[Node]:
    return node.children_by_field_name("name")


def _function(path: str, node: Node) -> list[Symbol]:
    name = field_text(node, "name")
    if name is None:
        return []
    detail = "function" if node.type == "function_declaration" else "method"
    symbols = [definition(path, node, name, detail, header(node))]
    if _exported(name):
        symbols.append(export(path, node, name))
    return symbols


def _method_elem(path: str, node: Node) -> list[Symbol]:
    name = field_text(node, "name")
    if name is None:
        return []
    symbols = [definition(path, node, name, "method", text_before(node, None))]
    if _exported(name):
        symbols.append(export(path, node, name))
    return symbols


_TYPE_DETAIL = {"struct_type": "struct", "interface_type": "interface"}


def _type_spec(path: str, node: Node) -> list[Symbol]:
    name = field_text(node, "name")
    if name is None:
        return []
    type_ = node.child_by_field_name("type")
    detail = _TYPE_DETAIL.get(type_.type, "type") if type_ is not None else "type"
    symbols = [definition(path, node, name, detail, "type " + _type_header(node))]
    if _exported(name) and _package_level(node.parent):
        symbols.append(export(path, node, name))
    return symbols


def _type_header(spec: Node) -> str:
    """The spec cut where a struct's field list or an interface's ``{`` starts."""
    type_ = spec.child_by_field_name("type")
    stop: Node | None = None
    if type_ is not None and type_.type in _TYPE_DETAIL:
        stop = next(
            (
                child
                for child in type_.children
                if child.type in ("field_declaration_list", "{")
            ),
            None,
        )
    return text_before(spec, stop)


def _value_spec(path: str, node: Node) -> list[Symbol]:
    """EXPORT the capitalised names of a package-level const or var spec."""
    declaration = node.parent
    if declaration is not None and declaration.type == "var_spec_list":
        declaration = declaration.parent
    if not _package_level(declaration):
        return []
    return [
        export(path, name, text)
        for name in _names(node)
        if (text := node_text(name)) is not None and _exported(text)
    ]


def _field(path: str, node: Node) -> list[Symbol]:
    """A FIELD per name of a struct field declaration, exported or not; an
    embedded field names no field of its own and is skipped."""
    signature = text_before(node, None)
    return [
        field(path, node, text, signature)
        for name in _names(node)
        if (text := node_text(name)) is not None
    ]


def _import(path: str, node: Node) -> list[Symbol]:
    module = _import_path(node)
    alias = node.child_by_field_name("name")
    if alias is None:
        name = _package_name(module)
    elif alias.type == "dot":
        name = "*"
    elif alias.type == "blank_identifier":
        name = module
    else:
        name = node_text(alias) or module
    statement = "import " + (node_text(node) or "")
    return [Symbol(name, SymbolKind.IMPORT, path, line(node), module, statement)]


def _import_path(spec: Node) -> str:
    literal = spec.child_by_field_name("path")
    if literal is None:
        return ""
    for child in literal.children:
        if child.type in (
            "interpreted_string_literal_content",
            "raw_string_literal_content",
        ):
            return node_text(child) or ""
    return ""


def _package_name(module: str) -> str:
    """The conventional package name of an import path: its last element, with a
    major-version element or suffix dropped (``chi/v5`` and ``yaml.v3`` name
    ``chi`` and ``yaml``). Module major-version elements start at ``/v2``, so a
    ``/v1`` element is the package's own name (``k8s.io/api/core/v1`` is ``v1``)."""
    elements = [element for element in module.split("/") if element]
    if len(elements) > 1 and _MAJOR_VERSION_ELEMENT.fullmatch(elements[-1]):
        elements.pop()
    if not elements:
        return module
    stripped = _MAJOR_VERSION.sub("", elements[-1])
    return stripped or elements[-1]


def _call(path: str, node: Node) -> list[Symbol]:
    callee = node.child_by_field_name("function")
    if callee is None:
        return []
    if callee.type == "identifier":
        return reference(path, node, node_text(callee))
    if callee.type == "selector_expression":
        return reference(path, node, field_text(callee, "field"))
    return []


LANGUAGE = TreeSitterLanguage(
    grammar=lambda _path: _GO,
    handlers={
        "function_declaration": _function,
        "method_declaration": _function,
        "method_elem": _method_elem,
        "type_spec": _type_spec,
        "type_alias": _type_spec,
        "const_spec": _value_spec,
        "var_spec": _value_spec,
        "field_declaration": _field,
        "import_spec": _import,
        "call_expression": _call,
    },
)
extract = LANGUAGE.extract
