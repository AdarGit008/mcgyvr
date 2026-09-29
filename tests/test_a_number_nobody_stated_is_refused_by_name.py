"""A number that no layer states for the key asked is refused by name.

Nothing is sized or judged from a default in code. When a number is asked for
and neither the user's own settings file nor the shipped estimates state it for
the key asked, the ask is refused, and the one refusal names every missing
number and key together, the shipped file it looked in, and the file where the
user can set a value. The numbers here are invented by a generator
(``tests/numbers_fixture.py``); the product's own ids and classes are read from
the module.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from mcgyvr import derived
from tests import numbers_fixture as nf


def _named(number: str, key: str) -> str:
    return f"{number}[{key!r}]"


@pytest.mark.parametrize("seed", nf.SEEDS)
def test_every_unstated_number_and_key_is_named_in_one_refusal(
    seed: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    made = nf.entries(seed)
    shipped = nf.write_json(tmp_path / "shipped.json", nf.document(made))
    stated = {(e.id, k) for e in made for k in e.values}
    never_shipped = (f"never_shipped_{seed}", "slow")
    asked = [*nf.every_ask(made), never_shipped]
    missing = [ask for ask in asked if ask not in stated]

    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup_all(asked, path=shipped)

    text = str(was.value)
    for number, key in missing:
        assert _named(number, key) in text, text
    for number, key in stated:
        assert _named(number, key) not in text, text
    assert str(shipped) in text
    assert str(derived.overrides_path()) in text


@pytest.mark.parametrize("seed", nf.SEEDS)
def test_each_unstated_number_asked_alone_is_refused_by_name(
    seed: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nf.use_invented_spaces(monkeypatch)
    made = nf.entries(seed)
    shipped = nf.write_json(tmp_path / "shipped.json", nf.document(made))
    stated = {(e.id, k) for e in made for k in e.values}
    for number, key in nf.every_ask(made):
        if (number, key) in stated:
            continue
        with pytest.raises(derived.DerivedNumbersError) as was:
            derived.lookup(number, key, path=shipped)
        assert _named(number, key) in str(was.value)
        assert str(derived.overrides_path()) in str(was.value)


@pytest.mark.parametrize("seed", nf.SEEDS)
def test_a_number_the_user_sets_is_no_longer_missing(
    seed: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    nf.use_invented_spaces(monkeypatch)
    made = nf.entries(seed)
    shipped = nf.write_json(tmp_path / "shipped.json", nf.document(made))
    stated = {(e.id, k) for e in made for k in e.values}
    missing = [ask for ask in nf.every_ask(made) if ask not in stated]
    assert missing, "the generator leaves at least one key unstated"
    number, key = missing[0]
    unit = next(e.unit for e in made if e.id == number)
    nf.write_user_file(
        tmp_path_factory, {number: {key: nf.a_value(unit, random.Random(seed))}}
    )

    rest = missing[1:]
    if rest:
        with pytest.raises(derived.DerivedNumbersError) as was:
            derived.lookup_all(nf.every_ask(made), path=shipped)
        assert _named(number, key) not in str(was.value)
        for other in rest:
            assert _named(*other) in str(was.value)
    else:
        answered = derived.lookup_all(nf.every_ask(made), path=shipped)
        assert answered[(number, key)].source == "override"


def test_a_document_with_no_numbers_states_none_of_them(tmp_path: Path) -> None:
    """A JSON object of another shape is not a schema error: it states nothing."""
    other = nf.write_json(tmp_path / "other.json", {"_doc": "another shape", "a": {}})
    asked = [
        (entry, name)
        for entry in derived.CLASS_PCT_ENTRIES.values()
        for name in derived.KEY_SPACES["tolerance_class"]
    ]
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.class_tolerances(path=other)
    for number, key in asked:
        assert _named(number, key) in str(was.value)

    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.runtime_resident_gb(path=other)
    assert derived.RUNTIME_RESIDENT in str(was.value)
    assert str(derived.overrides_path()) in str(was.value)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("not-there.json", None),
        ("broken.json", '{"numbers": '),
        ("a-list.json", json.dumps([1, 2])),
        pytest.param(
            "too-deep.json", "[" * 100_000 + "]" * 100_000, id="too-deep.json"
        ),
        ("not-utf8.json", '{"_doc": "caf\xe9", "numbers": {}}'.encode("latin-1")),
    ],
)
def test_a_shipped_file_that_cannot_be_read_as_an_object_is_refused_by_name(
    tmp_path: Path, name: str, content: str | bytes | None
) -> None:
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    elif content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.class_tolerances(path=path)
    assert str(path) in str(was.value)
