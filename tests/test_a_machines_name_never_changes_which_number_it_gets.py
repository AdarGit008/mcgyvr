"""A machine's name never changes which number it gets.

The numbers are keyed by what any machine has (its engine, a unit's tolerance
class), never by what a machine is called: a machine nobody has named before
gets the same number as every other, from the same layer, and is never refused
for its name. The sizing still passes the machine's name, so a refusal can say
which machine was being sized; it is never a key. The names here are generated.
"""

from __future__ import annotations

import random
import string
from pathlib import Path

import pytest

from mcgyvr import derived
from tests import numbers_fixture as nf


def _names(seed: int) -> list[str | None]:
    """Invented machine names, plus names that look like keys and ids."""
    rng = random.Random(seed)
    made: list[str | None] = [None, ""]
    for _ in range(6):
        stem = "".join(
            rng.choice(string.ascii_lowercase) for _ in range(rng.randint(1, 9))
        )
        made.append(f"{stem}-{rng.randint(0, 99)}")
    for space in derived.KEY_SPACES.values():
        made.extend(space)
    made.append(derived.RUNTIME_RESIDENT)
    return made


@pytest.mark.parametrize("seed", range(4))
def test_every_name_gets_the_shipped_estimate(seed: int) -> None:
    expected = derived.lookup(derived.RUNTIME_RESIDENT, derived.RUNTIME_RESIDENT_KEY)
    assert expected.source == "estimate"
    for name in _names(seed):
        assert derived.runtime_resident_gb(name) == expected.value, name


@pytest.mark.parametrize("seed", range(4))
def test_every_name_gets_the_users_own_setting(seed: int) -> None:
    shipped = derived.lookup(derived.RUNTIME_RESIDENT, derived.RUNTIME_RESIDENT_KEY)
    mine = nf.a_value(shipped.unit, random.Random(seed), unlike=shipped.value)
    nf.write_user_file({derived.RUNTIME_RESIDENT: {derived.RUNTIME_RESIDENT_KEY: mine}})
    assert (
        derived.lookup(derived.RUNTIME_RESIDENT, derived.RUNTIME_RESIDENT_KEY).source
        == "override"
    )
    for name in _names(seed):
        assert derived.runtime_resident_gb(name) == mine, name


def test_no_name_is_refused_for_being_unknown(tmp_path: Path) -> None:
    """Where nothing states the number, every name is refused for the number alone."""
    empty = nf.write_json(tmp_path / "empty.json", {"_doc": "states nothing"})
    for name in _names(0):
        with pytest.raises(derived.DerivedNumbersError) as was:
            derived.runtime_resident_gb(name, path=empty)
        assert derived.RUNTIME_RESIDENT in str(was.value), name


def test_a_machines_name_cannot_be_a_key_of_the_users_file() -> None:
    name = _names(1)[2]
    assert name is not None
    path = nf.write_user_file({derived.RUNTIME_RESIDENT: {name: 1.0}})
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.runtime_resident_gb(name)
    assert name in str(was.value)
    assert str(path) in str(was.value)
