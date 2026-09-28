"""Every estimate can be set by the user, and a setting that means nothing is refused.

Every number the product ships is an estimate, so every one of them, for every
key it states, can be replaced by the user's own value in their settings file,
and the code that sizes and judges then uses that value. A setting the product
cannot mean (an unknown number, a key outside the number's key space, a value
that is not a finite number inside the unit's bounds, a file that is not a
mapping) is refused by name with the file's path, even when the ask was for
another number: a typo is never silently ignored. A file that is not there sets
nothing. The shipped ids and keys are read from the file; the values set here
are generated.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from mcgyvr import derived
from tests import numbers_fixture as nf


def _shipped() -> dict[str, dict[str, Any]]:
    numbers = json.loads(derived.shipped_path().read_text(encoding="utf-8"))["numbers"]
    assert isinstance(numbers, dict)
    return numbers


def _every_shipped_ask() -> list[tuple[str, str]]:
    return [(n, k) for n, entry in _shipped().items() for k in entry["values"]]


@pytest.mark.parametrize(("number", "key"), _every_shipped_ask())
def test_a_value_the_user_sets_replaces_the_estimate(
    number: str, key: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    estimate = derived.lookup(number, key)
    mine = nf.a_value(
        estimate.unit, random.Random(f"{number}{key}"), unlike=estimate.value
    )
    path = nf.write_user_file(tmp_path_factory, {number: {key: mine}})

    answered = derived.lookup(number, key)
    assert (answered.value, answered.source, answered.where) == (mine, "override", path)
    assert answered.unit == estimate.unit

    for field, entry in derived.CLASS_PCT_ENTRIES.items():
        if entry == number:
            assert derived.class_tolerances()[field][key] == mine
            numbers = derived.class_tolerance_numbers()[field][key]
            assert (numbers.value, numbers.source) == (mine, "override")
    if (number, key) == (derived.RUNTIME_RESIDENT, derived.RUNTIME_RESIDENT_KEY):
        assert derived.runtime_resident_gb() == mine


def test_every_key_of_every_estimate_can_be_set_at_once(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rng = random.Random(7)
    settings: dict[str, dict[str, float]] = {}
    for number, key in _every_shipped_ask():
        unit = derived.lookup(number, key).unit
        settings.setdefault(number, {})[key] = nf.a_value(unit, rng)
    nf.write_user_file(tmp_path_factory, settings)
    answered = derived.lookup_all(_every_shipped_ask())
    for (number, key), got in answered.items():
        assert (got.value, got.source) == (settings[number][key], "override")


def _an_entry_in(unit: str) -> tuple[str, str]:
    for number, entry in _shipped().items():
        if entry["unit"] == unit:
            return number, next(iter(entry["values"]))
    pytest.skip(f"no shipped number is stated in {unit}")


def _another_ask(number: str) -> tuple[str, str]:
    """A shipped ask that is not ``number``, so a typo is found while asking another."""
    for other, key in _every_shipped_ask():
        if other != number:
            return other, key
    return _every_shipped_ask()[0]


_BAD_VALUES: list[tuple[str, str]] = [
    ("percent", "0"),
    ("percent", "100"),
    ("percent", "-3"),
    ("percent", ".nan"),
    ("percent", ".inf"),
    ("GiB", "-1"),
    ("GiB", "-.inf"),
    ("GiB", "true"),
    ("GiB", "'2.5'"),
    ("GiB", "null"),
    ("GiB", "[1, 2]"),
]


@pytest.mark.parametrize(("unit", "literal"), _BAD_VALUES)
def test_a_value_that_is_not_a_finite_number_inside_its_bounds_is_refused(
    unit: str, literal: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    number, key = _an_entry_in(unit)
    path = nf.write_user_file(tmp_path_factory, f"{number}:\n  {key}: {literal}\n")
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup(*_another_ask(number))
    assert str(path) in str(was.value)
    assert number in str(was.value) and key in str(was.value)


def test_an_unknown_number_is_refused_even_when_another_is_asked(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    number, key = _every_shipped_ask()[0]
    path = nf.write_user_file(tmp_path_factory, {"no_such_number": {key: 1.0}})
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup(number, key)
    assert str(path) in str(was.value)
    assert "no_such_number" in str(was.value)


def test_a_key_outside_the_numbers_key_space_is_refused(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    number = _every_shipped_ask()[0][0]
    path = nf.write_user_file(tmp_path_factory, {number: {"no-such-key": 1.0}})
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup(*_another_ask(number))
    assert str(path) in str(was.value)
    assert number in str(was.value) and "no-such-key" in str(was.value)


@pytest.mark.parametrize(
    "text",
    [
        "- a list\n- not a mapping\n",
        "just words\n",
        "a: [unclosed\n",
        "{number}:\n  {key}: 1\n{number}:\n  {key}: 2\n",
        "{number}: 3\n",
        "7:\n  {key}: 1\n",
        "{number}:\n  7: 1\n",
    ],
)
def test_a_settings_file_that_is_not_a_mapping_of_numbers_is_refused(
    text: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    number, key = _every_shipped_ask()[0]
    path = nf.write_user_file(tmp_path_factory, text.format(number=number, key=key))
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup(number, key)
    assert str(path) in str(was.value)


def test_a_settings_path_that_cannot_be_read_is_refused(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = nf.users_file(tmp_path_factory)
    path.mkdir(parents=True)
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup(*_every_shipped_ask()[0])
    assert str(path) in str(was.value)


def test_a_settings_file_that_is_not_there_sets_nothing() -> None:
    assert not derived.overrides_path().exists()
    assert derived.lookup(*_every_shipped_ask()[0]).source == "estimate"


def test_a_settings_folder_that_is_a_file_sets_nothing(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    folder = nf.users_file(tmp_path_factory).parent
    folder.parent.mkdir(parents=True, exist_ok=True)
    folder.write_text("not a folder", encoding="utf-8")
    assert derived.lookup(*_every_shipped_ask()[0]).source == "estimate"


def test_an_empty_settings_file_sets_nothing(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    nf.write_user_file(tmp_path_factory, "# nothing set yet\n")
    assert derived.lookup(*_every_shipped_ask()[0]).source == "estimate"
