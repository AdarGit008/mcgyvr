"""The numbers mcgyvr sizes and judges a machine with, and where each one comes from.

Some numbers cannot be read off the machine or the model: how far a healthy
unit's speed varies between starts, how much host memory a llama.cpp server
holds beyond the experts it keeps there. mcgyvr ships an estimate of each in
``data/numbers.json`` (inside the installed package, :func:`shipped_path`),
keyed by something every machine has (a tolerance class, an engine) and never
by a machine's name. The user may set their own value for any of them in
``numbers.yaml`` in mcgyvr's own folder (:func:`overrides_path`); their value
answers first.

Nothing here falls back to a literal in code. A number that neither layer
states is a named refusal (:class:`DerivedNumbersError`) naming every missing
number and key and the file where a value can be set, because a silent inline
default is a number nobody stated for the machine in hand.
"""

from __future__ import annotations

import json
import math
import reprlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml

from mcgyvr.config import UNIT_FIELDS
from mcgyvr.fleet import roots
from mcgyvr.fleet.tolerance import CLASSES
from mcgyvr.strict_yaml import strict_loader

#: The shipped estimates' file name, in the package's ``data`` folder.
NUMBERS_FILENAME = "numbers.json"
#: The user's own settings' file name, in mcgyvr's own folder.
OVERRIDES_FILENAME = "numbers.yaml"
#: The shape of the shipped file this code reads, stated as its ``schema``.
NUMBERS_SCHEMA = 1
#: Where a checkout keeps the shipped file, for a mcgyvr run from its source.
CHECKOUT_DATA = Path(__file__).resolve().parents[2] / "data"

#: Which layer answered a number: the user's own setting, or the shipped estimate.
Source = Literal["override", "estimate"]


def _engine_choices() -> tuple[str, ...]:
    """The engines a unit may name, spelled as the config's ``engine`` field is."""
    for field in UNIT_FIELDS:
        if field.name == "engine":
            return field.choices
    raise AssertionError("the config schema names no engine field")


#: The closed spaces a number may be keyed by, each read from the code that
#: owns it. Every key of the shipped file and of the user's file is a member
#: of its number's space, so a machine's name can never become a key.
KEY_SPACES: dict[str, tuple[str, ...]] = {
    "tolerance_class": CLASSES,
    "engine": _engine_choices(),
}

#: The units a number may be stated in: each one's bound, and the bound in words.
_BOUNDS: dict[str, tuple[Callable[[float], bool], str]] = {
    "percent": (lambda value: 0.0 < value < 100.0, "above 0 and below 100"),
    "GiB": (lambda value: value >= 0.0, "0 or more"),
}
UNITS: tuple[str, ...] = tuple(_BOUNDS)


#: The number for the host memory a llama.cpp server holds beyond the experts
#: it keeps on the host, and its one key: llama.cpp, the engine whose expert
#: offload the sizing prices.
RUNTIME_RESIDENT = "runtime_resident_gb"
RUNTIME_RESIDENT_KEY = "llama.cpp"


#: How a refusal spells a value it was given: a few levels, items and characters
#: of it, never all of it, so a value the YAML reader builds far larger than its
#: text (one alias repeated inside another) is refused as fast as any other.
_SHOWN = reprlib.Repr(
    maxlevel=2, maxdict=4, maxlist=4, maxset=4, maxstring=60, maxlong=60, maxother=60
)


def _shown(value: object) -> str:
    """``value`` as a refusal spells it: its ``repr``, cut short when it is long."""
    return _SHOWN.repr(value)


class DerivedNumbersError(Exception):
    """A number was asked for and no layer states it, or a layer cannot be read."""


@dataclass(frozen=True)
class Number:
    """One number's answer for one key, and the layer and file that gave it."""

    id: str
    key: str
    value: float
    unit: str
    source: Source
    where: Path

    def says(self) -> str:
        """The answer: value, unit, the layer and file, then the setting as YAML.

        The setting after the blank line is what the user's file holds, or
        would hold, for this number and key (its name, then the key and value
        indented below it), so it can be copied into that file as it is. An
        estimate adds where to write your own; your own setting does not. The
        value is stated once, as the setting spells it, and the head repeats
        that same text, so the two never differ by a rounding.
        """
        setting = yaml.safe_dump(
            {self.id: {self.key: self.value}}, default_flow_style=False
        ).rstrip("\n")
        spelled = setting.rsplit(": ", 1)[1]
        head = f"{self.id}[{self.key!r}] is {spelled} {self.unit}"
        if self.source == "override":
            return f"{head}, your own setting in {self.where}:\n\n{setting}"
        return (
            f"{head}, the shipped estimate in {self.where}. To use your own "
            f"value, write this in {overrides_path()} with your value in place "
            f"of {spelled}:"
            f"\n\n{setting}"
        )


def shipped_path() -> Path:
    """The shipped estimates: the package's own copy first, a checkout's second.

    An installed mcgyvr finds the file inside the package; one run from its
    source finds it in the checkout's ``data`` folder. With neither, the
    numbers are refused by name and read from nowhere else.
    """
    packaged = resources.files("mcgyvr") / "data" / NUMBERS_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    checkout = CHECKOUT_DATA / NUMBERS_FILENAME
    if checkout.is_file():
        return checkout
    raise DerivedNumbersError(
        f"shipped numbers not found: neither {packaged} (the package's own copy) "
        f"nor {checkout} (a checkout's) is a file; none of its numbers "
        "has a default in code"
    )


def overrides_path() -> Path:
    """The user's own settings file: ``numbers.yaml`` in mcgyvr's own folder.

    The one place that says where it is. It depends on no config, working
    folder, command line flag or live fleet, so every command reads the same
    file. A HOME that cannot be resolved raises ``RuntimeError`` before there
    is a path to name, as it does for every reader of mcgyvr's own folder.
    """
    return roots.home() / OVERRIDES_FILENAME


#: What reading the shipped JSON raises for text it cannot read: ``ValueError``
#: for invalid JSON or a number too long to read, ``RecursionError`` for
#: nesting deeper than the reader goes.
_UNREADABLE_JSON: tuple[type[Exception], ...] = (ValueError, RecursionError)

#: What reading the user's YAML raises for text it cannot build into values:
#: ``yaml.YAMLError`` for YAML that does not parse and ``ValueError`` for a
#: number too long to read, and, from PyYAML's own constructors, ``LookupError``
#: (``!!int ''``, ``!!bool 'maybe'``), ``AttributeError`` (``!!timestamp 'abc'``)
#: and ``TypeError`` (``!!map [1]``) for an explicit tag on text it cannot mean,
#: and ``RecursionError`` for nesting deeper than the reader goes.
_UNREADABLE_YAML: tuple[type[Exception], ...] = (
    yaml.YAMLError,
    ValueError,
    LookupError,
    AttributeError,
    TypeError,
    RecursionError,
)


@dataclass(frozen=True)
class _NotANumber:
    """What JSON's ``NaN``, ``Infinity`` or ``-Infinity`` is read as: never a float."""

    spelled: str

    def __repr__(self) -> str:
        return self.spelled


def _once_each(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A JSON object's pairs as a dict, refused when a key is stated twice.

    JSON would keep the last of a repeated key silently, so the file would not
    mean what it looks like it means; the user's YAML is refused the same way.
    """
    made: dict[str, Any] = {}
    for key, value in pairs:
        if key in made:
            raise DerivedNumbersError(
                f"key {_shown(key)} is stated twice in one object; JSON would "
                "silently keep only the last one"
            )
        made[key] = value
    return made


def _load_shipped(path: Path | None) -> tuple[Path, dict[str, Any]]:
    """The shipped layer's ``numbers`` object, refused by name when unreadable.

    A JSON object with no ``numbers`` object states no number: every ask is
    then refused per number, not as a schema error. One that has a ``numbers``
    object is read only when its ``schema`` is :data:`NUMBERS_SCHEMA`.
    """
    where = shipped_path() if path is None else path
    try:
        text = where.read_text(encoding="utf-8")
    except OSError as exc:
        raise DerivedNumbersError(
            f"cannot read the shipped numbers from {where}: {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise DerivedNumbersError(
            f"{where} is not UTF-8 text, so its numbers cannot be read: {exc}"
        ) from exc
    try:
        document = json.loads(
            text, parse_constant=_NotANumber, object_pairs_hook=_once_each
        )
    except DerivedNumbersError as exc:
        raise DerivedNumbersError(f"{where}: {exc}") from exc
    except _UNREADABLE_JSON as exc:
        raise DerivedNumbersError(f"{where} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise DerivedNumbersError(f"{where} is not a JSON object")
    numbers = document.get("numbers")
    if not isinstance(numbers, dict):
        return where, {}
    schema = document.get("schema")
    if isinstance(schema, bool) or schema != NUMBERS_SCHEMA:
        has = "states no schema" if schema is None else f"is schema {_shown(schema)}"
        raise DerivedNumbersError(
            f"{where} {has}; this mcgyvr reads numbers of schema {NUMBERS_SCHEMA} only"
        )
    for number, entry in numbers.items():
        _check_entry(number, entry, where)
    return where, numbers


def _check_entry(number: str, entry: object, where: Path) -> None:
    """Refuse, by name, a shipped entry with no known unit or keyed outside its space.

    Its ``unit`` must be one of :data:`UNITS`, its ``key`` must name a space of
    :data:`KEY_SPACES`, and every key of its ``values`` must be a member of that
    space, so no entry can be keyed by a machine's name. Every entry is checked
    on every read, asked for or not, and a broken one is reported against the
    shipped file, even when the user's file sets it.
    """
    if not isinstance(entry, dict):
        raise DerivedNumbersError(f"{number} in {where} is not an object")
    unit = entry.get("unit")
    if not isinstance(unit, str) or unit not in _BOUNDS:
        raise DerivedNumbersError(
            f"{number} in {where} is stated in {_shown(unit)}, which is not a unit "
            f"mcgyvr knows ({', '.join(UNITS)})"
        )
    space_name = entry.get("key")
    space = KEY_SPACES.get(space_name) if isinstance(space_name, str) else None
    if space is None:
        raise DerivedNumbersError(
            f"{number} in {where} is keyed by {_shown(space_name)}, which is not a key "
            f"space mcgyvr knows ({', '.join(KEY_SPACES)})"
        )
    values = entry.get("values")
    if not isinstance(values, dict):
        raise DerivedNumbersError(
            f"{number} in {where} states its values as {_shown(values)}; they must be "
            "an object of keys to values"
        )
    outside = [key for key in values if key not in space]
    if outside:
        raise DerivedNumbersError(
            f"{number} in {where} states {', '.join(map(_shown, outside))}, not "
            f"keys of {space_name} (its keys are {', '.join(space)})"
        )


def _checked(value: object, unit: str, what: str, where: Path) -> float:
    """``value`` as a float when it is a finite number inside ``unit``'s bounds.

    ``unit`` is one of :data:`UNITS`: every shipped entry's unit is checked
    when the file is read (:func:`_check_entry`), before any value is.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DerivedNumbersError(
            f"{what} in {where} is {_shown(value)}, which is not a number"
        )
    within, bound = _BOUNDS[unit]
    try:
        number = float(value)
    except OverflowError:
        raise DerivedNumbersError(
            f"{what} in {where} is a whole number too large to be a float; a "
            f"number in {unit} must be finite and {bound}"
        ) from None
    if not math.isfinite(number) or not within(number):
        raise DerivedNumbersError(
            f"{what} in {where} is {_shown(value)}; a number in {unit} must be "
            f"finite and {bound}"
        )
    return number


def _load_overrides(
    shipped: Mapping[str, Any],
) -> tuple[Path, dict[tuple[str, str], float]]:
    """The user's own settings, every one checked, keyed by (number, key).

    A file that is not there sets nothing. Every other failure is refused by
    name with the file's path: unreadable, not UTF-8 text, not YAML, not a
    mapping of numbers to mappings of keys to values, a number the shipped file
    does not know, a key outside that number's key space, or a value that is
    not a finite number inside its unit's bounds. The whole file is checked on
    every read, so a typo in a number nobody asked for is refused too, never
    silently ignored.
    """
    where = overrides_path()
    try:
        text = where.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return where, {}
    except OSError as exc:
        raise DerivedNumbersError(
            f"cannot read your numbers from {where}: {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise DerivedNumbersError(
            f"{where} is not UTF-8 text, so your numbers cannot be read: {exc}"
        ) from exc
    loader = strict_loader(DerivedNumbersError)
    try:
        document = yaml.load(text, Loader=loader)
    except DerivedNumbersError as exc:
        raise DerivedNumbersError(f"{where}: {exc}") from exc
    except _UNREADABLE_YAML as exc:
        raise DerivedNumbersError(f"{where} is not valid YAML: {exc}") from exc
    if document is None:
        return where, {}
    if not isinstance(document, dict):
        raise DerivedNumbersError(
            f"{where} is not a mapping of number names to their keys and values"
        )
    settings: dict[tuple[str, str], float] = {}
    for number, by_key in document.items():
        entry = shipped.get(number) if isinstance(number, str) else None
        if not isinstance(entry, dict):
            raise DerivedNumbersError(
                f"{where} sets {_shown(number)}, which is not a number mcgyvr ships "
                f"(it knows {', '.join(sorted(shipped)) or 'none'})"
            )
        if not isinstance(by_key, dict):
            raise DerivedNumbersError(
                f"{where} sets {number} to {_shown(by_key)}; it must be a mapping of "
                "keys to values"
            )
        space = KEY_SPACES.get(str(entry.get("key")), ())
        for key, value in by_key.items():
            if not isinstance(key, str) or key not in space:
                shown = _shown(key)
                raise DerivedNumbersError(
                    f"{where} sets {number}[{shown}], and {shown} is not a key "
                    f"of {number} (its keys are {', '.join(space) or 'none'})"
                )
            settings[(number, key)] = _checked(
                value, entry["unit"], f"{number}[{key!r}]", where
            )
    return where, settings


def _resolve(
    asked: Sequence[tuple[str, str]],
    path: Path | None,
    *,
    sizing: str | None = None,
) -> dict[tuple[str, str], Number]:
    """Every ask answered by the first layer that states it, or one refusal."""
    shipped_where, shipped = _load_shipped(path)
    user_where, settings = _load_overrides(shipped)
    answered: dict[tuple[str, str], Number] = {}
    missing: list[tuple[str, str]] = []
    for number, key in asked:
        entry = shipped.get(number)
        unit = entry.get("unit") if isinstance(entry, dict) else None
        if (number, key) in settings:
            answered[(number, key)] = Number(
                id=number,
                key=key,
                value=settings[(number, key)],
                unit=str(unit),
                source="override",
                where=user_where,
            )
            continue
        values = entry.get("values") if isinstance(entry, dict) else None
        if not isinstance(values, dict) or key not in values:
            missing.append((number, key))
            continue
        answered[(number, key)] = Number(
            id=number,
            key=key,
            value=_checked(values[key], str(unit), f"{number}[{key!r}]", shipped_where),
            unit=str(unit),
            source="estimate",
            where=shipped_where,
        )
    if missing:
        named = ", ".join(f"{number}[{key!r}]" for number, key in missing)
        context = f" while sizing {sizing}" if sizing else ""
        raise DerivedNumbersError(
            f"no number for {named}{context}: the shipped estimates "
            f"({shipped_where}) state none and your own numbers ({user_where}) "
            f"set none; set each under its name and key in {user_where}. "
            "None of these numbers has a default in code"
        )
    return answered


def lookup_all(
    asked: Sequence[tuple[str, str]], *, path: Path | None = None
) -> dict[tuple[str, str], Number]:
    """Every (number, key) asked, each from the first layer that states it.

    The user's own setting answers first, the shipped estimate second. When
    any ask is stated by neither, one refusal names every missing number and
    key, the shipped file, and the user's file where a value can be set.
    ``path`` replaces the shipped file only; the user's file applies either
    way. Each layer is read once per call.
    """
    return _resolve(asked, path)


def lookup(number: str, key: str, *, path: Path | None = None) -> Number:
    """One number for one key, from the first layer that states it."""
    return _resolve([(number, key)], path)[(number, key)]


def runtime_resident_gb(host: str | None = None, *, path: Path | None = None) -> float:
    """The host memory, in GiB, a llama.cpp server holds beyond its host-side experts.

    What a sizing adds to the spilled experts when a model keeps expert blocks
    in host memory. The number is keyed by the engine, never by the machine:
    ``host`` only names, in a refusal, the machine that was being sized, and
    never changes the answer.
    """
    asked = (RUNTIME_RESIDENT, RUNTIME_RESIDENT_KEY)
    return _resolve([asked], path, sizing=host)[asked].value


#: A judged field -> the number that states its percent per tolerance class.
#: Each field has its own: prefill is not judged by warm decode's.
CLASS_PCT_ENTRIES: dict[str, str] = {
    "warm_decode_tok_s": "warm_decode_class_pct",
    "prefill_tok_s": "prefill_class_pct",
}


def class_tolerance_numbers(
    *, path: Path | None = None
) -> dict[str, dict[str, Number]]:
    """Judged field -> tolerance class -> its number, with the layer that gave it.

    Every class of :data:`mcgyvr.fleet.tolerance.CLASSES` is asked for each
    judged field of :data:`CLASS_PCT_ENTRIES`; any that no layer states is
    refused by name, all of them in one refusal, so no judge guesses a number
    or borrows another field's.
    """
    asked = [(entry, name) for entry in CLASS_PCT_ENTRIES.values() for name in CLASSES]
    answered = _resolve(asked, path)
    return {
        field: {name: answered[(entry, name)] for name in CLASSES}
        for field, entry in CLASS_PCT_ENTRIES.items()
    }


def class_tolerances(*, path: Path | None = None) -> dict[str, dict[str, float]]:
    """Judged field -> tolerance class -> the percent that field may fall.

    ``warm_decode_tok_s`` is what a live probe judges a unit's warm decode
    against, and what locking a fleet allows a unit's warm decode to fall
    below the baseline its evidence states. ``prefill_tok_s`` is what a live
    probe judges its prefill against. The values of
    :func:`class_tolerance_numbers`, without their layers.
    """
    return {
        field: {name: number.value for name, number in by_class.items()}
        for field, by_class in class_tolerance_numbers(path=path).items()
    }
