"""The numbers that judge a machine, and the code held to them.

The numbers mcgyvr cannot read off a machine or a model ship as estimates in
the package's own ``data/numbers.json`` and are read through
:mod:`mcgyvr.derived`. This file holds the code to them: a number the shipped
file leaves out is refused by name, never defaulted; no module that reads the
numbers restates one of their values as a literal; and the constant the
runtime figure once lived in is gone.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from mcgyvr import derived

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"


def test_a_number_the_shipped_file_leaves_out_is_refused_by_name(
    tmp_path: Path,
) -> None:
    space, keys = next(iter(derived.KEY_SPACES.items()))
    invented = {
        "_doc": "Invented for a test.",
        "schema": derived.NUMBERS_SCHEMA,
        "numbers": {
            "an_invented_number": {
                "kind": "estimate",
                "estimates": "an invented quantity",
                "used_for": "nothing; a test reads it",
                "unit": derived.UNITS[0],
                "key": space,
                "values": {keys[0]: 1.5},
                "note": "invented for a test",
            }
        },
    }
    path = tmp_path / derived.NUMBERS_FILENAME
    path.write_text(json.dumps(invented), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match=derived.RUNTIME_RESIDENT):
        derived.runtime_resident_gb(path=path)


def _shipped_values() -> dict[str, set[float]]:
    """Every shipped key -> the values the shipped file states for it."""
    numbers = derived.class_tolerance_numbers()
    by_key: dict[str, set[float]] = {}
    for by_class in numbers.values():
        for number in by_class.values():
            by_key.setdefault(number.key, set()).add(number.value)
    runtime = derived.lookup(derived.RUNTIME_RESIDENT, derived.RUNTIME_RESIDENT_KEY)
    by_key.setdefault(runtime.key, set()).add(runtime.value)
    return by_key


def _readers() -> list[Path]:
    """Every module of the package that imports :mod:`mcgyvr.derived`, and it."""
    package = SRC / "mcgyvr"
    found = [package / "derived.py"]
    for module in sorted(package.rglob("*.py")):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            imports_it = (
                isinstance(node, ast.ImportFrom)
                and (
                    node.module == "mcgyvr.derived"
                    or (
                        node.module == "mcgyvr"
                        and any(alias.name == "derived" for alias in node.names)
                    )
                )
            ) or (
                isinstance(node, ast.Import)
                and any(alias.name == "mcgyvr.derived" for alias in node.names)
            )
            if imports_it:
                found.append(module)
                break
    return found


def _number(node: ast.AST) -> float | None:
    """The value of a numeric literal (never a bool), else None."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    return None


def test_the_moved_literals_live_only_in_the_file() -> None:
    """No module that reads the numbers restates a shipped value as a literal.

    Every value is read from the shipped file through :mod:`mcgyvr.derived`,
    none is written here. Whole values (a percent like one or two) are common
    literals with other meanings, so a module is refused for a shipped value
    only where chance is unlikely: a literal with a fractional part equal to
    any shipped value, or a literal equal to a value the shipped file states
    for a key (under any number) paired with that key in a dict literal, or a
    name that spells a number's id. It cannot see a whole value written bare,
    a value computed from others, a value held in a string or in a file that
    is not a module, or a value in a module that is handed the numbers without
    importing :mod:`mcgyvr.derived`.
    """
    shipped = _shipped_values()
    fractional = {v for values in shipped.values() for v in values if v % 1}
    ids = {number.upper() for number in derived.CLASS_PCT_ENTRIES.values()}
    ids.add(derived.RUNTIME_RESIDENT.upper())
    restated: list[str] = []
    for module in _readers():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        name = module.relative_to(SRC)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and _number(node) in fractional:
                restated.append(f"{name}:{node.lineno}: {node.value!r}")
            if isinstance(node, ast.Dict):
                for key, item in zip(node.keys, node.values, strict=True):
                    if not (isinstance(key, ast.Constant) and key.value in shipped):
                        continue
                    if _number(item) in shipped[key.value]:
                        restated.append(f"{name}:{key.lineno}: {key.value}")
            if isinstance(node, ast.Name) and node.id in ids:
                restated.append(f"{name}:{node.lineno}: {node.id}")
    assert not restated, f"shipped values restated in code: {restated}"
    cli = (SRC / "mcgyvr" / "cli.py").read_text(encoding="utf-8")
    assert "class_tolerances()" in cli


def test_the_runtime_resident_constant_is_gone() -> None:
    from mcgyvr import serving

    assert not hasattr(serving, "RUNTIME_RESIDENT_GB")
