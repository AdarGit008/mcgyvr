"""Per-rig derived numbers, read from the one file that states them.

``tools/runs/derived.json`` is the source of truth for the numeric values
mcgyvr measures on a rig rather than reads from the rig or from the model.
It is JSON and content-addressable so a reader can digest it the way it
digests ``tools/runs/hosts.json``, and it is a sibling of that file on purpose:
``hosts.json`` declares what each rig IS, read live by the door's gate 2, and
this file declares what was MEASURED on it.

Nothing here falls back to a literal in code. A number that is absent from the
file is a named refusal (:class:`DerivedNumbersError`), because a silent inline
default is exactly the drift this file exists to end.
"""

from __future__ import annotations

import json
import math
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
        """The answer in one sentence: value, unit, layer, and how to set your own."""
        if self.source == "override":
            layer = f"your own setting in {self.where}"
        else:
            layer = f"the estimate shipped with mcgyvr in {self.where}"
        return (
            f"{self.id}[{self.key!r}] is {self.value:g} {self.unit}, {layer}; "
            f"set {self.id}: {self.key}: <value> in {overrides_path()} to use "
            "your own"
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
        f"shipped numbers not found (looked for {NUMBERS_FILENAME} in the "
        "package's data folder and in the checkout's data folder); nothing is "
        "sized or judged from a default in code"
    )


def overrides_path() -> Path:
    """The user's own settings file: ``numbers.yaml`` in mcgyvr's own folder.

    The one place that says where it is. It depends on no config, working
    folder, command line flag or live fleet, so every command reads the same
    file.
    """
    return roots.home() / OVERRIDES_FILENAME


@dataclass(frozen=True)
class _NotANumber:
    """What JSON's ``NaN``, ``Infinity`` or ``-Infinity`` is read as: never a float."""

    spelled: str

    def __repr__(self) -> str:
        return self.spelled


def _load_shipped(path: Path | None) -> tuple[Path, dict[str, Any]]:
    """The shipped layer's ``numbers`` object, refused by name when unreadable.

    A JSON object with no ``numbers`` object states no number: every ask is
    then refused per number, not as a schema error.
    """
    where = shipped_path() if path is None else path
    try:
        text = where.read_text(encoding="utf-8")
    except OSError as exc:
        raise DerivedNumbersError(
            f"cannot read the shipped numbers from {where}: {exc}"
        ) from exc
    try:
        document = json.loads(text, parse_constant=_NotANumber)
    except json.JSONDecodeError as exc:
        raise DerivedNumbersError(f"{where} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise DerivedNumbersError(f"{where} is not a JSON object")
    numbers = document.get("numbers")
    return where, numbers if isinstance(numbers, dict) else {}


def _checked(value: object, unit: object, what: str, where: Path) -> float:
    """``value`` as a float when it is a finite number inside ``unit``'s bounds."""
    if not isinstance(unit, str) or unit not in _BOUNDS:
        raise DerivedNumbersError(
            f"{what} in {where} is stated in {unit!r}, which is not a unit "
            f"mcgyvr knows ({', '.join(UNITS)})"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DerivedNumbersError(
            f"{what} in {where} is {value!r}, which is not a number"
        )
    number = float(value)
    within, bound = _BOUNDS[unit]
    if not math.isfinite(number) or not within(number):
        raise DerivedNumbersError(
            f"{what} in {where} is {value!r}; a number in {unit} must be "
            f"finite and {bound}"
        )
    return number


def _load_overrides(
    shipped: Mapping[str, Any],
) -> tuple[Path, dict[tuple[str, str], float]]:
    """The user's own settings, every one checked, keyed by (number, key).

    A file that is not there sets nothing. Every other failure is refused by
    name with the file's path: unreadable, not YAML, not a mapping of numbers
    to mappings of keys to values, a number the shipped file does not know, a
    key outside that number's key space, or a value that is not a finite
    number inside its unit's bounds. The whole file is checked on every read,
    so a typo in a number nobody asked for is refused too, never silently
    ignored.
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
    try:
        document = yaml.load(text, Loader=strict_loader(DerivedNumbersError))
    except DerivedNumbersError as exc:
        raise DerivedNumbersError(f"{where}: {exc}") from exc
    except yaml.YAMLError as exc:
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
                f"{where} sets {number!r}, which is not a number mcgyvr ships "
                f"(it knows {', '.join(sorted(shipped)) or 'none'})"
            )
        if not isinstance(by_key, dict):
            raise DerivedNumbersError(
                f"{where} sets {number} to {by_key!r}; it must be a mapping of "
                "keys to values"
            )
        space = KEY_SPACES.get(str(entry.get("key")), ())
        for key, value in by_key.items():
            if not isinstance(key, str) or key not in space:
                raise DerivedNumbersError(
                    f"{where} sets {number}[{key!r}], and {key!r} is not a key "
                    f"of {number} (its keys are {', '.join(space) or 'none'})"
                )
            settings[(number, key)] = _checked(
                value, entry.get("unit"), f"{number}[{key!r}]", where
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
            value=_checked(values[key], unit, f"{number}[{key!r}]", shipped_where),
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
            "Nothing is sized or judged from a default in code"
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


#: A judged field -> the ``engine`` entry of ``tools/runs/derived.json`` that
#: states its percent per tolerance class. Each field has its own measured
#: classes (owner, 2026-09-15): prefill is not judged by warm decode's.
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
