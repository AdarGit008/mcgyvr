"""The user's own setting answers before the shipped estimate.

For any number and key: a value the user sets in their own settings file is
the answer; where they set none, the estimate shipped with mcgyvr is; where
neither states one, the ask is refused. Every answer says which of the two
layers it came from and which file, so a reader can always tell a starting
value from their own. The numbers are invented by ``tests/numbers_fixture.py``.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
import yaml

from mcgyvr import derived
from tests import numbers_fixture as nf


@pytest.mark.parametrize("seed", nf.SEEDS)
def test_each_answer_comes_from_the_first_layer_that_states_it(
    seed: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    nf.use_invented_spaces(monkeypatch)
    made = nf.entries(seed)
    shipped = nf.write_json(tmp_path / "shipped.json", nf.document(made))
    rng = random.Random(seed + 10_000)
    settings: dict[str, dict[str, float]] = {}
    for entry in made:
        for key in nf.KEY_SPACES[entry.key]:
            if rng.random() < 0.5:
                settings.setdefault(entry.id, {})[key] = nf.a_value(
                    entry.unit, rng, unlike=entry.values.get(key)
                )
    user = nf.write_user_file(tmp_path_factory, settings)

    for entry in made:
        for key in nf.KEY_SPACES[entry.key]:
            if key in settings.get(entry.id, {}):
                number = derived.lookup(entry.id, key, path=shipped)
                assert number.value == settings[entry.id][key]
                assert number.source == "override"
                assert number.where == user
            elif key in entry.values:
                number = derived.lookup(entry.id, key, path=shipped)
                assert number.value == entry.values[key]
                assert number.source == "estimate"
                assert number.where == shipped
            else:
                with pytest.raises(derived.DerivedNumbersError):
                    derived.lookup(entry.id, key, path=shipped)
                continue
            assert (number.id, number.key, number.unit) == (entry.id, key, entry.unit)
            assert str(number.where) in number.says()
            assert str(derived.overrides_path()) in number.says()


@pytest.mark.parametrize("seed", nf.SEEDS)
def test_with_no_settings_file_every_stated_number_is_the_shipped_estimate(
    seed: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    made = nf.entries(seed)
    shipped = nf.write_json(tmp_path / "shipped.json", nf.document(made))
    assert not derived.overrides_path().exists()
    asked = [(e.id, k) for e in made for k in e.values]
    answered = derived.lookup_all(asked, path=shipped)
    assert set(answered) == set(asked)
    for entry in made:
        for key, value in entry.values.items():
            number = answered[(entry.id, key)]
            assert (number.value, number.source, number.where) == (
                value,
                "estimate",
                shipped,
            )


def test_the_two_layers_say_different_things_about_themselves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    nf.use_invented_spaces(monkeypatch)
    made = nf.entries(0)
    shipped = nf.write_json(tmp_path / "shipped.json", nf.document(made))
    entry = made[0]
    key = next(iter(entry.values))
    estimate = derived.lookup(entry.id, key, path=shipped)
    nf.write_user_file(
        tmp_path_factory,
        {
            entry.id: {
                key: nf.a_value(entry.unit, random.Random(1), unlike=estimate.value)
            }
        },
    )
    override = derived.lookup(entry.id, key, path=shipped)
    assert estimate.source != override.source
    assert estimate.says() != override.says()

    # Each ends in the setting as it is written in the user's file: valid YAML,
    # the number's name, then its key and value indented below it.
    for number in (estimate, override):
        setting = number.says().split("\n\n")[-1]
        assert yaml.safe_load(setting) == {entry.id: {key: number.value}}
        assert setting.splitlines()[0] == f"{entry.id}:"
        assert setting.splitlines()[1].startswith("  ")
    assert str(shipped) in estimate.says()
    assert str(derived.overrides_path()) in estimate.says()
    assert "To use your own value" in estimate.says()
    assert str(derived.overrides_path()) in override.says()
    assert "To use your own value" not in override.says()


#: Values whose shortest spelling is long, whole, tiny or inexact, by unit.
_SPELLINGS: dict[str, tuple[float, ...]] = {
    "GiB": (123456789.123, 48.0, 1e-07, 0.1 + 0.2, 1e20),
    "percent": (48.0, 99.99999999, 1e-07, 0.1 + 0.2),
}


@pytest.mark.parametrize(
    ("unit", "value"),
    [(unit, value) for unit, values in _SPELLINGS.items() for value in values],
)
def test_an_answer_states_its_value_as_its_setting_does(
    unit: str,
    value: float,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    nf.use_invented_spaces(monkeypatch)
    space = sorted(nf.KEY_SPACES)[0]
    key = nf.KEY_SPACES[space][0]
    entry = nf.Entry(id="invented_spelling", unit=unit, key=space, values={key: value})
    shipped = nf.write_json(tmp_path / "shipped.json", nf.document([entry]))
    estimate = derived.lookup(entry.id, key, path=shipped)
    nf.write_user_file(tmp_path_factory, {entry.id: {key: value}})
    override = derived.lookup(entry.id, key, path=shipped)

    for number in (estimate, override):
        says = number.says()
        setting = says.split("\n\n")[-1]
        spelled = setting.splitlines()[1].split(": ", 1)[1]
        assert yaml.safe_load(spelled) == value
        assert f" is {spelled} {unit}," in says
    assert f"in place of {spelled}:" in estimate.says()
