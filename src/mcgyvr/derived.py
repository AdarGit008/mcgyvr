""

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
from mcgyvr.fleet.links import LINK_CLASSES
from mcgyvr.fleet.tolerance import CLASSES
from mcgyvr.strict_yaml import strict_loader

#
NUMBERS_FILENAME = "numbers.json"
#
OVERRIDES_FILENAME = "numbers.yaml"
#
NUMBERS_SCHEMA = 1
#
CHECKOUT_DATA = Path(__file__).resolve().parents[2] / "data"

#
Source = Literal["override", "estimate"]


def _engine_choices() -> tuple[str, ...]:
    ""
    for field in UNIT_FIELDS:
        if field.name == "engine":
            return field.choices
    raise AssertionError("the config schema names no engine field")


#
#
#
KEY_SPACES: dict[str, tuple[str, ...]] = {
    "tolerance_class": CLASSES,
    "engine": _engine_choices(),
    "link_class": LINK_CLASSES,
}

#
_BOUNDS: dict[str, tuple[Callable[[float], bool], str]] = {
    "percent": (lambda value: 0.0 < value < 100.0, "above 0 and below 100"),
    "GiB": (lambda value: value >= 0.0, "0 or more"),
    "GiB/s": (lambda value: value > 0.0, "above 0"),
    "microseconds": (lambda value: value > 0.0, "above 0"),
}
UNITS: tuple[str, ...] = tuple(_BOUNDS)


#
#
#
#
#
#
NUMBER_KINDS: tuple[str, ...] = ("fact", "choice", "estimate")

#
#
FACT_REASONS: tuple[str, ...] = (
    "a definition or arithmetic",
    "the specification of a format, protocol or tool",
    "where a count starts",
    "the layout of the package or its checkout",
)

#
#
#
SETTING_SOURCES: tuple[str, ...] = ("config", "contract", "flag")

#
DUPLICATE_REASON = "a duplicate of another entry"

#
#
CHOICE_REASONS: tuple[str, ...] = (
    "a protocol or tool default",
    "a code or version other programs or files read",
    "the method a stored reading was made with",
    "a rule over the product's own shipped data",
    "what a caller that names none gets; the product's callers name one",
    (
        "how much of a text the product itself shows, carries or reads, and at "
        "what width (never a budget for a model's whole reply or whole input)"
    ),
    "a weight, threshold or cut of the product's own ranking of files and symbols",
    "how often or how many times the product tries its own step again",
    DUPLICATE_REASON,
)


#
#
#
RUNTIME_RESIDENT = "runtime_resident_gb"
RUNTIME_RESIDENT_KEY = "llama.cpp"

#
#
SHARD_ALLOWANCE = "shard_allowance_gib"

#
LINK_GIB_S = "link_gib_s"
LINK_LATENCY_US = "link_latency_us"

#
#
#
RUNTIME_RESIDENT_READ: tuple[str, ...] = ("vllm",)


#
#
#
_SHOWN = reprlib.Repr(
    maxlevel=2, maxdict=4, maxlist=4, maxset=4, maxstring=60, maxlong=60, maxother=60
)


def _shown(value: object) -> str:
    ""
    return _SHOWN.repr(value)


class DerivedNumbersError(Exception):
    ""


@dataclass(frozen=True)
class Number:
    ""

    id: str
    key: str
    value: float
    unit: str
    source: Source
    where: Path

    def says(self) -> str:
        ""
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
    ""
    packaged = resources.files("mcgyvr") / "data" / NUMBERS_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    checkout = CHECKOUT_DATA / NUMBERS_FILENAME
    if checkout.is_file():
        return checkout
    raise DerivedNumbersError(
        f"shipped numbers not found: neither {packaged} (the package's own copy) "
        f"nor {checkout} (a checkout's) is a file; no number of its `numbers` "
        "block has a default in code"
    )


def overrides_path() -> Path:
    ""
    return roots.home() / OVERRIDES_FILENAME


#
#
#
_UNREADABLE_JSON: tuple[type[Exception], ...] = (ValueError, RecursionError)

#
#
#
#
#
#
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
    ""

    spelled: str

    def __repr__(self) -> str:
        return self.spelled


def _once_each(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    ""
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
    ""
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
    ""
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
    ""
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
    ""
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
    ""
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
    ""
    return _resolve(asked, path)


def lookup(number: str, key: str, *, path: Path | None = None) -> Number:
    ""
    return _resolve([(number, key)], path)[(number, key)]


def runtime_resident_gb(host: str | None = None, *, path: Path | None = None) -> float:
    ""
    asked = (RUNTIME_RESIDENT, RUNTIME_RESIDENT_KEY)
    return _resolve([asked], path, sizing=host)[asked].value


def shard_allowance_gib(
    engine: str, *, sizing: str | None = None, path: Path | None = None
) -> float:
    ""
    asked = (SHARD_ALLOWANCE, engine)
    return _resolve([asked], path, sizing=sizing)[asked].value


def user_setting(number: str, key: str, *, path: Path | None = None) -> Path | None:
    ""
    _, shipped = _load_shipped(path)
    where, settings = _load_overrides(shipped)
    return where if (number, key) in settings else None


#
#
CLASS_PCT_ENTRIES: dict[str, str] = {
    "warm_decode_tok_s": "warm_decode_class_pct",
    "prefill_tok_s": "prefill_class_pct",
}


def class_tolerance_numbers(
    *, path: Path | None = None
) -> dict[str, dict[str, Number]]:
    ""
    asked = [(entry, name) for entry in CLASS_PCT_ENTRIES.values() for name in CLASSES]
    answered = _resolve(asked, path)
    return {
        field: {name: answered[(entry, name)] for name in CLASSES}
        for field, entry in CLASS_PCT_ENTRIES.items()
    }


def class_tolerances(*, path: Path | None = None) -> dict[str, dict[str, float]]:
    ""
    return {
        field: {name: number.value for name, number in by_class.items()}
        for field, by_class in class_tolerance_numbers(path=path).items()
    }
