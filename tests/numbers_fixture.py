"""Invented numbers files for the tests of :mod:`mcgyvr.derived`.

Every number id, key space, key and value here is made up by a small
generator, so a test built on it promises something about how numbers are
found and refused, never about what any shipped number is. The shipped file's
own ids, classes and key spaces are read from the module and the file by the
tests that need them; nothing here restates them.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import derived

#: Key spaces nobody's code asks for: the generator keys its numbers by these.
KEY_SPACES: dict[str, tuple[str, ...]] = {
    "pace": ("slow", "steady", "brisk"),
    "tool": ("hammer", "saw", "rasp", "awl"),
    "lone": ("only",),
}

#: The units an entry may be stated in, and a range well inside each one's bounds.
_RANGES: dict[str, tuple[float, float]] = {
    "percent": (0.5, 99.5),
    "GiB": (0.0, 40.0),
    "GiB/s": (0.5, 40.0),
    "microseconds": (0.5, 900.0),
}

#: How many generated shapes each generated test runs over.
SEEDS = range(8)


@dataclass(frozen=True)
class Entry:
    """One invented number: its id, unit, key space and the keys it states."""

    id: str
    unit: str
    key: str
    values: Mapping[str, float]


def a_value(unit: str, rng: random.Random, *, unlike: float | None = None) -> float:
    """A value inside ``unit``'s bounds, never equal to ``unlike``."""
    low, high = _RANGES[unit]
    while True:
        value = round(rng.uniform(low, high), 2)
        if value != unlike:
            return value


def entries(seed: int) -> list[Entry]:
    """Several invented numbers, each stating some keys of its space and not others.

    Every entry states at least one key, and every shape leaves at least one
    key unstated, so a test of a missing number always has one to ask for.
    """
    rng = random.Random(seed)
    made: list[Entry] = []
    for n in range(rng.randint(1, 5)):
        key = rng.choice(sorted(KEY_SPACES))
        unit = rng.choice(sorted(_RANGES))
        space = KEY_SPACES[key]
        stated = [k for k in space if rng.random() < 0.6] or [rng.choice(space)]
        made.append(
            Entry(
                id=f"invented_{seed}_{n}",
                unit=unit,
                key=key,
                values={k: a_value(unit, rng) for k in stated},
            )
        )
    if all(set(e.values) == set(KEY_SPACES[e.key]) for e in made):
        wide = max(sorted(KEY_SPACES), key=lambda name: len(KEY_SPACES[name]))
        unit = rng.choice(sorted(_RANGES))
        made.append(
            Entry(
                id=f"invented_{seed}_{len(made)}",
                unit=unit,
                key=wide,
                values={KEY_SPACES[wide][0]: a_value(unit, rng)},
            )
        )
    return made


def every_ask(made: list[Entry]) -> list[tuple[str, str]]:
    """Every (number, key) the invented numbers' key spaces allow."""
    return [(e.id, k) for e in made for k in KEY_SPACES[e.key]]


def document(made: list[Entry]) -> dict[str, Any]:
    """A shipped-shaped document stating ``made``."""
    return {
        "_doc": "Invented for a test.",
        "schema": 1,
        "numbers": {
            e.id: {
                "kind": "estimate",
                "estimates": "an invented quantity",
                "used_for": "nothing; a test reads it",
                "unit": e.unit,
                "key": e.key,
                "values": dict(e.values),
                "note": "invented for a test",
            }
            for e in made
        },
    }


def write_json(path: Path, content: Mapping[str, Any]) -> Path:
    """``content`` as JSON at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def users_file(tmp: pytest.TempPathFactory) -> Path:
    """The user's own settings file, only when it lies under pytest's temporary root.

    A test writes the user's file where :func:`mcgyvr.derived.overrides_path`
    says it is, which follows HOME. Were HOME ever a real one, a test would
    overwrite a real user's settings; so nothing is written unless the file
    lies under the temporary root this pytest run made.
    """
    root = tmp.getbasetemp().resolve()
    path = derived.overrides_path()
    assert path.resolve().is_relative_to(root), (
        f"refusing to write the user's numbers file {path}: it is not under "
        f"pytest's temporary root {root}, so it may be a real user's file"
    )
    return path


def write_user_file(
    tmp: pytest.TempPathFactory, content: Mapping[str, Any] | str | bytes
) -> Path:
    """The user's own settings file, holding YAML text, bytes or a mapping."""
    path = users_file(tmp)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
        return path
    text = content if isinstance(content, str) else yaml.safe_dump(dict(content))
    path.write_text(text, encoding="utf-8")
    return path


def use_invented_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module keys numbers by the invented key spaces for one test."""
    monkeypatch.setattr(derived, "KEY_SPACES", dict(KEY_SPACES))
