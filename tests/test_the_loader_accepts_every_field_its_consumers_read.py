"""Every unit field the lock reads must be one ``files.load_fleet`` accepts.

``mcgyvr.fleet.files`` is the one authoritative parser for ``fleet.yaml``: it
refuses an unknown key rather than ignoring it. The lock
(``mcgyvr.fleet.lock``) and live admission (``mcgyvr.fleet.admit``) then read
named fields off each loaded unit. If a consumer grows a field the loader does
not accept, an operator's ``fleet.yaml`` carrying that field is refused before
the lock ever sees it — the schema addition silently bypasses the parser.

This guard scans the consumers for the unit fields they read, builds a
``fleet.yaml`` document from exactly those fields, and requires ``load_fleet``
to accept it. It does not restate ``_UNIT_KEYS``; it exercises the loader with
the consumers' fields, so the two lists cannot drift apart unnoticed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from mcgyvr.fleet import files

SRC = Path(__file__).resolve().parents[1] / "src" / "mcgyvr" / "fleet"

#: The modules that read a unit block out of a loaded fleet.
CONSUMERS = ("lock.py", "admit.py")


def _name(node: ast.AST) -> str | None:
    """The identifier a bare ``Name`` node holds."""
    return node.id if isinstance(node, ast.Name) else None


def _literal_str(node: ast.AST) -> str | None:
    """The text a string-literal node holds."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_call(node: ast.AST) -> ast.Call | None:
    """The call node when ``node`` is an ``X.get(...)`` expression."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "get":
            return node
    return None


def _is_units_mapping(node: ast.AST, units_names: set[str]) -> bool:
    """Whether ``node`` names the mapping of unit name to unit block."""
    if isinstance(node, ast.Name):
        return node.id in units_names
    call = _get_call(node)
    return bool(
        call is not None and call.args and _literal_str(call.args[0]) == "units"
    )


def _is_items_of_units(node: ast.AST, units_names: set[str]) -> bool:
    """Whether ``node`` is ``<units mapping>.items()``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "items"
    ):
        return _is_units_mapping(node.func.value, units_names)
    return False


def _units_names(tree: ast.AST) -> set[str]:
    """Names bound to the units mapping: the conventional local plus aliases."""
    names = {"units"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            call = _get_call(node.value)
            if call is not None and call.args and _literal_str(call.args[0]) == "units":
                for target in node.targets:
                    name = _name(target)
                    if name is not None:
                        names.add(name)
    return names


def _unit_names(tree: ast.AST, units_names: set[str]) -> set[str]:
    """Names bound to a single unit block, by loop, subscript or get."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Tuple)
            and len(node.target.elts) == 2
            and _is_items_of_units(node.iter, units_names)
        ):
            name = _name(node.target.elts[1])
            if name is not None:
                names.add(name)
        if isinstance(node, ast.Assign):
            value = node.value
            if isinstance(value, ast.Subscript):
                source: ast.AST = value.value
            else:
                call = _get_call(value)
                if call is None or not isinstance(call.func, ast.Attribute):
                    continue
                source = call.func.value
            if not _is_units_mapping(source, units_names):
                continue
            for target in node.targets:
                name = _name(target)
                if name is not None:
                    names.add(name)
    # An alias of a unit block is a unit block too.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Name):
                continue
            if node.value.id not in names:
                continue
            for target in node.targets:
                name = _name(target)
                if name is not None and name not in names:
                    names.add(name)
                    changed = True
    return names


def _unit_fields_read(source: str) -> set[str]:
    """Every string key the source reads from a single unit block."""
    tree = ast.parse(source)
    units_names = _units_names(tree)
    unit_names = _unit_names(tree, units_names)
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and isinstance(func.value, ast.Name)
                and func.value.id in unit_names
                and node.args
            ):
                key = _literal_str(node.args[0])
                if key is not None:
                    fields.add(key)
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in unit_names
        ):
            key = _literal_str(node.slice)
            if key is not None:
                fields.add(key)
        elif (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str)
            and type(node.ops[0]) in (ast.In, ast.NotIn)
        ):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Name) and comparator.id in unit_names:
                    fields.add(node.left.value)
    return fields


def test_the_consumers_read_unit_fields() -> None:
    """The guard's extraction works: a broken scanner would pass vacuously."""
    read: set[str] = set()
    for consumer in CONSUMERS:
        read |= _unit_fields_read((SRC / consumer).read_text(encoding="utf-8"))
    assert read, (
        "the guard found no unit fields at all; its scanner is broken, so it "
        "would no longer catch a field the lock reads but the loader refuses"
    )


def test_load_fleet_accepts_every_field_the_consumers_read() -> None:
    read: set[str] = set()
    for consumer in CONSUMERS:
        read |= _unit_fields_read((SRC / consumer).read_text(encoding="utf-8"))
    document = {
        "units": {"srv2_7b": {field: "pinned" for field in sorted(read)}},
        "rigs": {},
        "fleets": {},
    }
    loaded = files.load_fleet(yaml.safe_dump(document))
    assert set(loaded["units"]["srv2_7b"]) == read, (
        "a field the lock reads was dropped or renamed by files.load_fleet; "
        f"the loader refuses {sorted(read - set(loaded['units']['srv2_7b']))}"
    )


def test_load_fleet_still_refuses_a_unit_field_it_does_not_know() -> None:
    """The guard depends on this refusal: an unknown field must not load."""
    with pytest.raises(files.FleetFileError, match="not_a_unit_field"):
        files.load_fleet("units:\n  srv2_7b:\n    not_a_unit_field: 1\n")
