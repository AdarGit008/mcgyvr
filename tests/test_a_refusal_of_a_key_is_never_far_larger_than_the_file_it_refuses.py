"""A small file never makes a refusal far larger than itself, whatever position.

YAML lets one anchored value be named again by an alias, and an alias inside
another anchored value, so a few lines of text can stand for a value many
times their size. A key of a mapping is a position like any other: when the
strict loader refuses a key that is not a plain name, it spells only the start
of it, so the refusal stays about the size of the file and comes as quickly as
any other. The loader is tried directly, with a key built from nested lists
and from nested mappings, at the top of the file and inside a mapping, and
once through the reader of the user's numbers file.
"""

from __future__ import annotations

import pytest
import yaml

from mcgyvr import derived
from mcgyvr.strict_yaml import strict_loader
from tests import numbers_fixture as nf

#: How deep the aliases nest: few enough that the test is quick even where
#: the refusal would spell the whole value, enough that the value dwarfs the
#: text it is written in.
LEVELS = 4
#: How many times each level names the one below it.
WIDTH = 9
#: How much longer than the file a refusal may be: room for its own words.
ROOM = 1_000


class _RefusedError(Exception):
    """The error the loader is given to raise, as a schema gives its own."""


def _anchors(shape: str) -> str:
    """A flow list of anchors, each naming the one before it ``WIDTH`` times."""
    if shape == "list":
        items = ["&a0 [" + ", ".join(["1"] * WIDTH) + "]"]
        items += [
            f"&a{n} [" + ", ".join([f"*a{n - 1}"] * WIDTH) + "]"
            for n in range(1, LEVELS)
        ]
    else:
        items = ["&a0 {" + ", ".join(f"k{i}: 1" for i in range(WIDTH)) + "}"]
        items += [
            f"&a{n} {{" + ", ".join(f"k{i}: *a{n - 1}" for i in range(WIDTH)) + "}"
            for n in range(1, LEVELS)
        ]
    return "[" + ", ".join(items) + "]"


def _text(shape: str, where: str) -> str:
    """A file whose one hostile key names the deepest anchor."""
    deepest = f"*a{LEVELS - 1}"
    if where == "top":
        return f"anchors: {_anchors(shape)}\n? {deepest}\n: 1\n"
    return f"anchors: {_anchors(shape)}\nnested:\n  ? {deepest}\n  : 1\n"


@pytest.mark.parametrize("where", ["top", "nested"])
@pytest.mark.parametrize("shape", ["list", "mapping"])
def test_the_loader_refuses_a_key_in_about_the_size_of_the_file(
    shape: str, where: str
) -> None:
    text = _text(shape, where)
    with pytest.raises(_RefusedError) as was:
        yaml.load(text, Loader=strict_loader(_RefusedError))
    assert len(str(was.value)) < len(text) + ROOM


def test_a_short_key_is_still_spelled_in_full() -> None:
    key = "a_plain_key_of_ordinary_length"
    with pytest.raises(_RefusedError) as was:
        yaml.load(f"{key}: 1\n{key}: 2\n", Loader=strict_loader(_RefusedError))
    assert repr(key) in str(was.value)


@pytest.mark.parametrize("where", ["top", "under a number"])
def test_the_numbers_reader_refuses_a_key_in_about_the_size_of_the_file(
    where: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    number = next(iter(derived.CLASS_PCT_ENTRIES.values()))
    if where == "top":
        text = _text("list", "top")
    else:
        text = f"{number}:\n  anchors: {_anchors('list')}\n  ? *a{LEVELS - 1}\n  : 1\n"
    path = nf.write_user_file(tmp_path_factory, text)
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.class_tolerances()
    assert str(path) in str(was.value)
    assert len(str(was.value)) < len(text) + ROOM
