"""Every shipped number says what it estimates, and is keyed by what any machine has.

The file of shipped numbers is read by strangers on machines nobody here has
seen, so each entry says in words that it is an estimate, what quantity it
estimates, what the product does with it, its unit and its key, and carries no
other field. Its keys come from a closed key space of the module (an engine, a
tolerance class), never from a machine's name, so any machine has one. Every
key the code can ask for is stated, and every value is a finite number inside
its unit's bounds. A value outside them, in any shipped-shaped file, is refused
by name. Nothing here restates a shipped value: the file is read.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import config, derived
from mcgyvr.fleet.tolerance import CLASSES
from tests import numbers_fixture as nf

#: The fields an entry of the shipped file may carry, and no others.
ENTRY_FIELDS = {"kind", "estimates", "used_for", "unit", "key", "values", "note"}


def _refuse_constant(name: str) -> float:
    raise AssertionError(f"the shipped file holds {name}, which is not a number")


def _shipped() -> dict[str, Any]:
    loaded = json.loads(
        derived.shipped_path().read_text(encoding="utf-8"),
        parse_constant=_refuse_constant,
    )
    assert isinstance(loaded, dict)
    return loaded


def _numbers() -> dict[str, dict[str, Any]]:
    numbers = _shipped()["numbers"]
    assert isinstance(numbers, dict) and numbers
    return numbers


def test_the_file_says_what_it_is() -> None:
    document = _shipped()
    assert set(document) == {"_doc", "schema", "numbers", "constants", "covered"}
    assert isinstance(document["_doc"], str) and document["_doc"].strip()
    assert document["schema"] == 1


def test_every_entry_says_it_is_an_estimate_what_of_what_for_its_unit_and_key() -> None:
    for number, entry in _numbers().items():
        assert set(entry) == ENTRY_FIELDS, number
        assert entry["kind"] == "estimate", number
        for words in ("estimates", "used_for", "note"):
            assert isinstance(entry[words], str) and entry[words].strip(), (
                number,
                words,
            )
        assert entry["unit"] in derived.UNITS, number
        assert entry["key"] in derived.KEY_SPACES, number


def test_every_key_comes_from_its_named_key_space() -> None:
    for number, entry in _numbers().items():
        values = entry["values"]
        assert isinstance(values, dict) and values, number
        space = derived.KEY_SPACES[entry["key"]]
        assert set(values) <= set(space), (number, sorted(set(values) - set(space)))


def test_every_value_is_a_finite_number_inside_its_units_bounds() -> None:
    for number, entry in _numbers().items():
        for key, value in entry["values"].items():
            assert not isinstance(value, bool), (number, key)
            assert isinstance(value, (int, float)), (number, key)
            assert math.isfinite(value), (number, key)
            answered = derived.lookup(number, key)
            assert answered.value == float(value)
            assert answered.source == "estimate"
            assert answered.unit == entry["unit"]


def test_every_number_the_code_asks_for_is_stated_and_nothing_else_is() -> None:
    numbers = _numbers()
    asked = {*derived.CLASS_PCT_ENTRIES.values(), derived.RUNTIME_RESIDENT}
    assert set(numbers) == asked
    for entry in derived.CLASS_PCT_ENTRIES.values():
        assert numbers[entry]["key"] == "tolerance_class"
        assert set(numbers[entry]["values"]) == set(CLASSES), entry
    runtime = numbers[derived.RUNTIME_RESIDENT]
    assert derived.RUNTIME_RESIDENT_KEY in runtime["values"]
    assert derived.RUNTIME_RESIDENT_KEY in derived.KEY_SPACES[runtime["key"]]
    derived.class_tolerances()
    derived.runtime_resident_gb()


def test_the_key_spaces_are_the_ones_the_product_already_names() -> None:
    engine = next(field for field in config.UNIT_FIELDS if field.name == "engine")
    assert derived.KEY_SPACES["engine"] == engine.choices
    assert derived.KEY_SPACES["tolerance_class"] == CLASSES


#: A whole number too large to be a float: refused as outside its bounds.
_TOO_LARGE = "1" + "0" * 400

_OUT_OF_BOUNDS: list[tuple[str, str]] = [
    ("percent", _TOO_LARGE),
    ("GiB", _TOO_LARGE),
    ("percent", "0"),
    ("percent", "100"),
    ("percent", "250.5"),
    ("percent", "-4"),
    ("GiB", "-0.5"),
    ("percent", "NaN"),
    ("GiB", "Infinity"),
    ("GiB", "-Infinity"),
    ("percent", "true"),
    ("GiB", '"3"'),
    ("GiB", "null"),
]


@pytest.mark.parametrize(("unit", "literal"), _OUT_OF_BOUNDS)
def test_a_shipped_value_outside_its_bounds_is_refused_by_name(
    unit: str, literal: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    entry = nf.Entry(id="invented_bound", unit=unit, key="lone", values={"only": 1.0})
    text = json.dumps(nf.document([entry])).replace('"only": 1.0', f'"only": {literal}')
    path = tmp_path / "shipped.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup("invented_bound", "only", path=path)
    assert "invented_bound" in str(was.value)
    assert str(path) in str(was.value)


@pytest.mark.parametrize(("unit", "value"), [("GiB", 0.0), ("percent", 99.5)])
def test_a_shipped_value_on_the_open_side_of_its_bounds_is_answered(
    unit: str, value: float, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    entry = nf.Entry(id="invented_edge", unit=unit, key="lone", values={"only": value})
    path = nf.write_json(tmp_path / "shipped.json", nf.document([entry]))
    assert derived.lookup("invented_edge", "only", path=path).value == value


def test_a_shipped_entry_in_a_unit_without_bounds_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    entry = nf.Entry(
        id="invented_unit", unit="furlongs", key="lone", values={"only": 1.0}
    )
    path = nf.write_json(tmp_path / "shipped.json", nf.document([entry]))
    with pytest.raises(derived.DerivedNumbersError, match="invented_unit"):
        derived.lookup("invented_unit", "only", path=path)


@pytest.mark.parametrize("schema", [2, 0, "1", True, None])
def test_a_shipped_file_of_another_schema_is_refused_by_name(
    schema: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    entry = nf.Entry(id="invented_schema", unit="GiB", key="lone", values={"only": 1.0})
    document = nf.document([entry])
    if schema is None:
        del document["schema"]
    else:
        document["schema"] = schema
    path = nf.write_json(tmp_path / "shipped.json", document)
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup("invented_schema", "only", path=path)
    text = str(was.value)
    assert str(path) in text
    assert f"schema {derived.NUMBERS_SCHEMA}" in text
    if schema is not None:
        assert repr(schema) in text


def test_a_document_with_no_numbers_is_not_judged_by_its_schema(
    tmp_path: Path,
) -> None:
    other = nf.write_json(tmp_path / "other.json", {"schema": 99, "a": {}})
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.class_tolerances(path=other)
    assert "schema" not in str(was.value)
    for entry in derived.CLASS_PCT_ENTRIES.values():
        assert entry in str(was.value)


@pytest.mark.parametrize(
    ("key", "values", "named"),
    [
        ("no_such_space", {"only": 1.0}, "no_such_space"),
        ("lone", {"only": 1.0, "elsewhere": 2.0}, "elsewhere"),
        ("lone", [1.0], "values"),
    ],
)
def test_a_shipped_entry_keyed_outside_its_key_space_is_refused_by_name(
    key: str,
    values: object,
    named: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nf.use_invented_spaces(monkeypatch)
    good = nf.Entry(id="invented_good", unit="GiB", key="pace", values={"slow": 1.0})
    bad = nf.Entry(id="invented_keyed", unit="GiB", key="lone", values={"only": 1.0})
    document = nf.document([good, bad])
    document["numbers"]["invented_keyed"].update(key=key, values=values)
    path = nf.write_json(tmp_path / "shipped.json", document)
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup("invented_good", "slow", path=path)
    text = str(was.value)
    assert str(path) in text
    assert "invented_keyed" in text and named in text


def test_a_shipped_entry_that_is_not_an_object_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    good = nf.Entry(id="invented_good", unit="GiB", key="pace", values={"slow": 1.0})
    document = nf.document([good])
    document["numbers"]["invented_flat"] = 3.0
    path = nf.write_json(tmp_path / "shipped.json", document)
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup("invented_good", "slow", path=path)
    assert str(path) in str(was.value) and "invented_flat" in str(was.value)


def test_a_broken_shipped_unit_is_reported_against_the_shipped_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The user setting a number whose shipped unit is broken is not their fault."""
    nf.use_invented_spaces(monkeypatch)
    entry = nf.Entry(
        id="invented_unit", unit="furlongs", key="lone", values={"only": 1.0}
    )
    path = nf.write_json(tmp_path / "shipped.json", nf.document([entry]))
    user = nf.write_user_file(tmp_path_factory, {"invented_unit": {"only": 2.0}})
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup("invented_unit", "only", path=path)
    text = str(was.value)
    assert "invented_unit" in text and "furlongs" in text
    assert str(path) in text
    assert str(user) not in text
