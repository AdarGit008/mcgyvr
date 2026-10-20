"""The numbers mcgyvr sizes and judges a machine with that it cannot read.

Two files answer for a number: the estimates shipped with mcgyvr, and the
user's own settings in ``numbers.yaml`` in the config folder, which answer
first. Each entry is keyed by what every machine has (an engine, a unit's
tolerance class, a class of link) and stated in a unit whose bounds are
checked, so no answer is keyed by a machine's name. A number and key that
neither file states is refused by name: none of them falls back to a default
in code. Every answer carries the file it was read from, so a reader can tell
a starting value from their own.
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
from mcgyvr.fleet.links import LINK_CLASSES
from mcgyvr.fleet.tolerance import CLASSES
from mcgyvr.strict_yaml import strict_loader

#: The shipped estimates' file name, in the package's data folder and a checkout's.
NUMBERS_FILENAME = "numbers.json"
#: The user's own numbers: the layer that answers before the shipped estimates.
OVERRIDES_FILENAME = "numbers.yaml"
#: The schema of the shipped file that this code reads, stated in the file itself.
NUMBERS_SCHEMA = 1
#: Where a checkout keeps the shipped file: the repository root's data folder.
CHECKOUT_DATA = Path(__file__).resolve().parents[2] / "data"

#: Where an answer came from: the user's own setting, or the estimate shipped.
Source = Literal["override", "estimate"]


def _engine_choices() -> tuple[str, ...]:
    """The engines the config schema accepts, for keying the numbers by engine.

    Read off the config schema's own engine field rather than restated here, so
    a number keyed by an engine follows whatever engines the schema accepts. A
    schema with no engine field is a fault of this module, so it asserts.
    """
    for field in UNIT_FIELDS:
        if field.name == "engine":
            return field.choices
    raise AssertionError("the config schema names no engine field")


#: The keys a number may be stated under, named by the ``key`` field of its entry:
#: the tolerance classes, the config schema's engines, and the link classes, each
#: read from the module that defines it rather than spelled again here.
KEY_SPACES: dict[str, tuple[str, ...]] = {
    "tolerance_class": CLASSES,
    "engine": _engine_choices(),
    "link_class": LINK_CLASSES,
}

#: Each unit, with the test a value in it passes and the words a refusal names it by.
_BOUNDS: dict[str, tuple[Callable[[float], bool], str]] = {
    "percent": (lambda value: 0.0 < value < 100.0, "above 0 and below 100"),
    "GiB": (lambda value: value >= 0.0, "0 or more"),
    "GiB/s": (lambda value: value > 0.0, "above 0"),
    "microseconds": (lambda value: value > 0.0, "above 0"),
}
UNITS: tuple[str, ...] = tuple(_BOUNDS)


#: The host memory a llama.cpp server holds beyond the experts it keeps in host
#: memory, and the engine key it is stated under: charged only to such a unit, and
#: never to a unit of another engine.
RUNTIME_RESIDENT = "runtime_resident_gb"
RUNTIME_RESIDENT_KEY = "llama.cpp"

#: The card memory each shard of a tensor split holds beyond its share of the
#: weights and its cache, stated for each engine.
SHARD_ALLOWANCE = "shard_allowance_gib"

#: The two numbers of a link, stated for the class of link the traffic crosses.
LINK_GIB_S = "link_gib_s"
LINK_LATENCY_US = "link_latency_us"

#: The engines whose host memory figure is read off the model's geometry instead
#: of being shipped as a number: their entry of ``RUNTIME_RESIDENT`` is never
#: asked for, so a user's setting of it is reported unused and not priced in.
RUNTIME_RESIDENT_READ: tuple[str, ...] = ("vllm",)


#: How much of a value a refusal spells: ``reprlib`` cut to two levels and a few
#: entries a collection, 60 characters of any one string, number or other value, so
#: a refusal stays about the size of the file that caused it.
_SHOWN = reprlib.Repr(
    maxlevel=2, maxdict=4, maxlist=4, maxset=4, maxstring=60, maxlong=60, maxother=60
)


def _shown(value: object) -> str:
    """``value``'s repr, cut short the way a refusal spells a value."""
    return _SHOWN.repr(value)


class DerivedNumbersError(Exception):
    """A number could not be read, was stated wrongly, or is stated nowhere."""


@dataclass(frozen=True)
class Number:
    """One number answered for one key, and the file that answered it.

    ``source`` is the layer that stated it, the user's own setting or the
    estimate shipped with mcgyvr, and ``where`` is that layer's file.
    """

    id: str
    key: str
    value: float
    unit: str
    source: Source
    where: Path

    def says(self) -> str:
        """The number as a sentence: what it is, the file, and how to set it.

        An answer from the shipped estimate also spells the setting to write in
        the user's own file, with their value in place of the shipped one; an
        answer from that file already is what they wrote, so it does not.
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
    """The shipped numbers file: the package's own copy, else a checkout's.

    The packaged copy is looked for first, so an installed mcgyvr finds the file
    inside itself; a checkout without that copy finds it beside ``src``. With
    neither, the numbers are refused rather than read from anywhere else.
    """
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
    """Where the user's own numbers live: ``numbers.yaml`` in the config folder."""
    return roots.home() / OVERRIDES_FILENAME


#: What ``json.loads`` raises on text it cannot read, besides the refusal this
#: module makes itself through its hooks: a document that is not JSON, and the
#: recursion limit reached on text nested too deep to be built.
_UNREADABLE_JSON: tuple[type[Exception], ...] = (ValueError, RecursionError)

#: What ``yaml.load`` with the strict loader may raise on a file that is not the
#: mapping of number names to keys and values this module reads: a malformed
#: document, an error while building a value the document asks for (a lookup, an
#: attribute or a type that is not there), and the recursion a file of nested
#: aliases runs into. The strict loader's own refusal is a ``DerivedNumbersError``
#: caught on its own, so these are the errors YAML raises around it.
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
    """A JSON constant where a number should be, kept as the spelling it had.

    ``json.loads`` is handed this class as ``parse_constant``, so ``NaN``,
    ``Infinity`` and ``-Infinity`` arrive as an instance rather than a float; a
    value that is one is then refused as not a number, and its repr spells the
    constant so the refusal quotes it.
    """

    spelled: str

    def __repr__(self) -> str:
        return self.spelled


def _once_each(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """``pairs`` as one object, refusing a key stated twice in it.

    Handed to ``json.loads`` as ``object_pairs_hook``, so the duplicate a JSON
    object may hold is refused instead of silently keeping only the last value.
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
    """The shipped numbers: the file read, and the entries of its ``numbers`` block.

    The file is ``path`` if given, else :func:`shipped_path`. Text that is not
    UTF-8, not JSON, not a JSON object, or not of ``NUMBERS_SCHEMA`` is refused
    by its path, and every entry is checked by :func:`_check_entry`. A document
    with no ``numbers`` object states no numbers, and is read without checking
    its schema.
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
    """Refuse an entry of the shipped file that is not one this code can read.

    ``number`` names the entry and ``where`` the file. The unit must be one
    ``_BOUNDS`` knows, the ``key`` must name a space of ``KEY_SPACES``, and the
    ``values`` must be an object keyed only by that space's keys. What each value
    is belongs to :func:`_checked`, which is asked when a value is answered for.
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
    """``value`` as a float in ``unit``, refused by name if it is not one.

    ``what`` names the number and key, and ``where`` the file, so the refusal is
    one sentence about the value it refuses. A bool is not a number here, and the
    value must be finite and inside its unit's bounds.
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
    """The user's own numbers: the file they are read from, and their values.

    A file that is not there states nothing, and is not an error. ``shipped``
    names the numbers, their key spaces and their units, so a number or key the
    shipped file does not state is refused in the path of the user's file, as is
    a value outside its unit's bounds; a key stated twice is refused by the
    strict loader.
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
    """Answer every ``(number, key)`` asked for, refusing those nobody states.

    Each answer is the user's own setting where their file states one, else the
    shipped estimate. ``path`` replaces the shipped file, as a test's own file
    does; ``sizing`` names what is being sized, so a refusal can say what was
    under way. One refusal names every missing number and key together, both
    files it looked in, and where to set a value.
    """
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
    """Answer each ``(number, key)`` of ``asked``, refusing if any is unstated."""
    return _resolve(asked, path)


def lookup(number: str, key: str, *, path: Path | None = None) -> Number:
    """Answer one ``number`` for one ``key``, refusing if no file states it."""
    return _resolve([(number, key)], path)[(number, key)]


def runtime_resident_gb(host: str | None = None, *, path: Path | None = None) -> float:
    """Host memory a llama.cpp server holds beyond the experts held in host memory.

    ``host`` names the machine being sized and is used only in a refusal, since
    the number is keyed by engine and the key asked for is llama.cpp's.
    """
    asked = (RUNTIME_RESIDENT, RUNTIME_RESIDENT_KEY)
    return _resolve([asked], path, sizing=host)[asked].value


def shard_allowance_gib(
    engine: str, *, sizing: str | None = None, path: Path | None = None
) -> float:
    """The card memory, in GiB, each shard of ``engine``'s tensor split holds.

    ``sizing`` names the unit being sized, so a refusal names it too.
    """
    asked = (SHARD_ALLOWANCE, engine)
    return _resolve([asked], path, sizing=sizing)[asked].value


def user_setting(number: str, key: str, *, path: Path | None = None) -> Path | None:
    """The file the user sets ``number`` for ``key`` in, or ``None`` if they set none.

    Both files are read to answer, so a malformed one is refused here as it is
    when a number is asked for.
    """
    _, shipped = _load_shipped(path)
    where, settings = _load_overrides(shipped)
    return where if (number, key) in settings else None


#: The two tolerance numbers, by the unit field each one judges: how far, in percent,
#: a healthy unit's speed of that field may fall from one start of the unit to the next.
CLASS_PCT_ENTRIES: dict[str, str] = {
    "warm_decode_tok_s": "warm_decode_class_pct",
    "prefill_tok_s": "prefill_class_pct",
}


def class_tolerance_numbers(
    *, path: Path | None = None
) -> dict[str, dict[str, Number]]:
    """Both tolerance numbers, by unit field and by tolerance class, with their file.

    Every class of ``CLASSES`` is asked for, so a class that neither the shipped
    file nor the user's states is refused by name.
    """
    asked = [(entry, name) for entry in CLASS_PCT_ENTRIES.values() for name in CLASSES]
    answered = _resolve(asked, path)
    return {
        field: {name: answered[(entry, name)] for name in CLASSES}
        for field, entry in CLASS_PCT_ENTRIES.items()
    }


def class_tolerances(*, path: Path | None = None) -> dict[str, dict[str, float]]:
    """Both tolerance numbers as plain percentages, by unit field and class."""
    return {
        field: {name: number.value for name, number in by_class.items()}
        for field, by_class in class_tolerance_numbers(path=path).items()
    }
