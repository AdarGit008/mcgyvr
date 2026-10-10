"""Reader for the shipped capability table.

The table (``data/capability-table.json``) is estimates by card class, not
readings of the user's machine. ``mcgyvr capabilities`` lists it, and
``mcgyvr emit`` sizes a unit from the row whose id equals the unit's model,
unless a unit in fleet.yaml declares that model, for example under ``launch``
or as ``room_mib``. ``mcgyvr setup`` does not read it: init binds the models running
servers list (:mod:`mcgyvr.propose`). See ``data/README.md`` for what a card
class is and for the harness caveats: ways a naive run of a reading or a
benchmark goes wrong.

The table carries no quality figure. It says what a model costs to serve, never
how well it does the work, so nothing read from it ranks one model above
another. No level of it declares a key for such a figure (:data:`DECLARED_KEYS`).

Reading and validating is most of this module.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any

TABLE_FILENAME = "capability-table.json"

#: The one table version this code reads. A table of any other version is
#: refused by name rather than read: a reader that skipped keys it did not know
#: would take an older table's rows to mean what this version's rows mean.
SCHEMA_VERSION = 3

#: What every figure in the shipped table is, in the words the product prints
#: above them.
ESTIMATES_NOTICE = (
    "Estimates by card class, one card read per class; none is a reading of "
    "your machine."
)

# The table's ``*_gb`` figures are decimal gigabytes; the sizing code is in GiB
# (:data:`mcgyvr.detect.MIB_PER_GB` is 1024). Divide by this wherever a table
# figure crosses into the sizing code, and nowhere else.
GB_PER_GIB = 1.073741824


class CapabilityTableError(Exception):
    """The capability table is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class CardClass:
    """A class of card the table's estimates are given for.

    ``memory_gb`` is the class's nominal card memory. A class is a rough guide:
    one card was read for it, and speed depends on the card, not only on its
    memory.
    """

    id: str
    label: str
    memory_gb: float


@dataclass(frozen=True)
class Measurement:
    """One figure of the table: an estimate for a card class.

    ``backend`` is the server program the figure was taken through, and
    ``card_class`` the id of the declared :class:`CardClass` it is given for.
    """

    value: float
    backend: str
    card_class: str


@dataclass(frozen=True)
class Model:
    """A model the table knows about.

    ``params_b`` is the declared parameter count in billions. It is size, not
    footprint: ``vram_gb_working`` says what the weights cost to hold at a
    quantization, while this says how big the model is regardless of how it was
    packed, which is what a *usable context window* scales with.

    ``not_for_fit`` is ``None``, or the table's text saying why this row is
    never listed as fitting a card (:meth:`CapabilityTable.fitting`), for
    example that its memory figure is not the model's own footprint.
    """

    id: str
    family: str
    params_b: float
    vram_gb_working: float
    weights_gb: float
    quant: str
    throughput: tuple[Measurement, ...]
    requires_backend: str | None
    notes: str
    not_for_fit: str | None = None
    # Media cost units, empty on a text row. Image and video are reading
    # lists like ``throughput``; the scalar media fields sit on the row
    # itself, where the shape document puts them.
    seconds_per_image: tuple[Measurement, ...] = ()
    seconds_per_clip: tuple[Measurement, ...] = ()
    resolution: str = ""
    steps: float | None = None
    vae_decode_gb: float | None = None
    frames: float | None = None
    temporal_compress: float | None = None
    sample_rate_hz: float | None = None
    rtf: float | None = None
    cpu_only: bool = False


@dataclass(frozen=True)
class Caveat:
    """A known way of producing wrong numbers for this table."""

    id: str
    severity: str
    summary: str
    consequence: str


@dataclass(frozen=True)
class CapabilityTable:
    models: tuple[Model, ...]
    caveats: tuple[Caveat, ...]
    card_classes: tuple[CardClass, ...] = ()

    def get(self, model_id: str) -> Model | None:
        return next((m for m in self.models if m.id == model_id), None)

    def fitting(self, vram_gb: float, headroom_gb: float = 2.0) -> list[Model]:
        """The rows that fit in ``vram_gb`` with room to work, in table order.

        ``headroom_gb`` guards CAV-04: a marginal fit can run markedly slower
        rather than fail, which makes it look like a working binding.
        The headroom is ABSOLUTE, not a fraction of the card, because what
        it reserves — KV cache for the context window — is sized by tokens,
        not by the card.

        A row that carries ``not_for_fit`` is never listed, whatever its
        memory figure: its text says why. Nothing else is judged here.
        """
        return [
            m
            for m in self.models
            if m.not_for_fit is None and m.vram_gb_working + headroom_gb <= vram_gb
        ]


#: The lists on a model row whose entries are readings, each keyed by a class.
#:
#: Each modality prices its cost in its own unit, but every one of these keeps
#: the same shape: a list of readings, each an estimate for one declared card
#: class. Text is ``throughput_tok_s``; image and video add their own lists.
#: TTS is the exception in shape, not in contract: its ``rtf`` is a scalar on
#: the row (see the model-row keys), because a real-time factor is a ratio of
#: seconds of audio to seconds of compute, stated at the row's sample rate,
#: and a CPU-only rung has no card class to key a reading by.
READING_LISTS = ("throughput_tok_s", "seconds_per_image", "seconds_per_clip")

#: Every key the table may carry, level by level, and no other.
#:
#: The loader refuses a key its level does not declare, by name, rather than
#: skipping it. A key this code does not know is either a misspelling of one it
#: reads, whose value would be lost without a word, or a fact nobody reads, and
#: a fact nobody reads in a table of estimates is how a machine's description,
#: or where and when a figure was taken, would come back in. Refusing it keeps a
#: new kind of fact out until it is declared here, where a reviewer reads it:
#: the same reason a table of another version is refused rather than read.
#:
#: One place holds names that are data rather than keys, and they are not
#: declared: under ``backends`` every key but the block's own notes names a
#: backend.
#:
#: No level declares a quality figure or a benchmark score, so a table that
#: carries one at any level but the backends block's is refused by the key's
#: name.
#:
#: A declared key that is not one of its level's :data:`CONTAINER_KEYS` holds a
#: value, never an object and never a list holding one, and the loader refuses
#: it otherwise: an object there would carry keys no level declares.
DECLARED_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "table": frozenset(
            {
                "schema_version",
                "_purpose",
                "card_classes",
                "harness_caveats",
                "models",
                "backends",
                "concurrency_findings",
            }
        ),
        "card class": frozenset({"id", "label", "memory_gb"}),
        "harness caveat": frozenset(
            {"id", "severity", "summary", "detail", "consequence"}
        ),
        "model row": frozenset(
            {
                "id",
                "family",
                "params_b",
                "active_params_b",
                "architecture",
                "quant",
                "weights_gb",
                "vram_gb_working",
                "requires_backend",
                *READING_LISTS,
                # Media rows keep the same cost-only contract, in the unit
                # their modality is priced in. ``rtf`` is the one media cost
                # unit that is a scalar, not a reading list: see READING_LISTS.
                "resolution",
                "steps",
                "vae_decode_gb",
                "frames",
                "temporal_compress",
                "sample_rate_hz",
                "rtf",
                "cpu_only",
                "not_for_fit",
                "notes",
            }
        ),
        "reading": frozenset({"value", "backend", "card_class", "caveat", "note"}),
        "backends block": frozenset({"_doc"}),
        "backend": frozenset({"wire_protocol", "strengths", "limits", "card_class"}),
        "concurrency finding": frozenset(
            {"id", "summary", "detail", "consequence", "card_class"}
        ),
    }
)


#: The declared keys whose value holds the entries of another level, level by
#: level. Every other declared key holds a value.
CONTAINER_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        **{level: frozenset[str]() for level in DECLARED_KEYS},
        "table": frozenset(
            {
                "card_classes",
                "harness_caveats",
                "models",
                "backends",
                "concurrency_findings",
            }
        ),
        "model row": frozenset(READING_LISTS),
    }
)


def _kind(value: Any) -> str:
    """What a JSON value is, in the words a refusal uses."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    return "an object"


def _object(value: Any, path: Path, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CapabilityTableError(f"{path}: {where} is {_kind(value)}, not an object")
    return value


def _entries(value: Any, path: Path, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise CapabilityTableError(f"{path}: {where} is {_kind(value)}, not a list")
    return value


def _closed(entry: Mapping[str, Any], level: str, path: Path, where: str) -> None:
    """Refuse a key ``level`` does not declare, naming it and what is declared."""
    stray = sorted(str(key) for key in entry if key not in DECLARED_KEYS[level])
    if stray:
        raise CapabilityTableError(
            f"{path}: {where} carries {', '.join(repr(k) for k in stray)}, which "
            f"this code does not declare for a {level} (declared: "
            f"{', '.join(sorted(DECLARED_KEYS[level]))})"
        )
    _values(entry, level, path, where)


def _holds_object(value: Any) -> bool:
    if isinstance(value, dict):
        return True
    return isinstance(value, list) and any(_holds_object(item) for item in value)


def _values(entry: Mapping[str, Any], level: str, path: Path, where: str) -> None:
    """Refuse an object, at any depth, under a key ``level`` gives a value."""
    for key in sorted(DECLARED_KEYS[level] - CONTAINER_KEYS[level]):
        if key in entry and _holds_object(entry[key]):
            raise CapabilityTableError(
                f"{path}: {where} has an object under {key!r}; a {level}'s "
                f"{key!r} holds a value, not entries, and an object there would "
                f"carry keys this code does not declare"
            )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
    )


#: The keys a model row cannot do without, and those of its keys that are numbers.
_MODEL_REQUIRED = ("id", "family", "params_b", "vram_gb_working", "weights_gb")
_MODEL_NUMBERS = (
    "params_b",
    "active_params_b",
    "vram_gb_working",
    "weights_gb",
    # Media row figures. ``steps`` and ``frames`` are counts but are carried
    # as numbers so a whole number and a fraction are both read and printed
    # as written; the loader refuses non-numbers, not fractions.
    "steps",
    "vae_decode_gb",
    "frames",
    "temporal_compress",
    "sample_rate_hz",
    "rtf",
)

#: The keys of a model row that are a true/false fact rather than a number.
_MODEL_BOOLEANS = ("cpu_only",)

#: The keys of a reading that carry its figure.
_READING_FIGURES = ("value",)

#: The keys a harness caveat cannot do without.
_CAVEAT_REQUIRED = ("id", "severity", "summary", "consequence")


def _required(
    entry: Mapping[str, Any], keys: tuple[str, ...], path: Path, where: str
) -> None:
    for key in keys:
        if key not in entry:
            raise CapabilityTableError(
                f"{path}: {where} is missing required key {key!r}"
            )


def _card_classes(raw: Mapping[str, Any], path: Path) -> tuple[CardClass, ...]:
    """The declared classes, each with an id, a label and its nominal memory."""
    declared = raw.get("card_classes")
    if not isinstance(declared, list):
        raise CapabilityTableError(
            f"{path}: the capability table declares no 'card_classes' list, so "
            f"no reading in it can say which card class it is an estimate for"
        )
    classes: list[CardClass] = []
    for index, value in enumerate(declared):
        where = f"card_classes[{index}]"
        entry = _object(value, path, where)
        _closed(entry, "card class", path, where)
        for key in ("id", "label", "memory_gb"):
            if key not in entry:
                raise CapabilityTableError(
                    f"{path}: {where} is missing required key {key!r}"
                )
        for key in ("id", "label"):
            if not _text(entry[key]):
                raise CapabilityTableError(
                    f"{path}: {where} has {key} {entry[key]!r}; a card class's "
                    f"{key} is non-empty text"
                )
        memory = entry["memory_gb"]
        if (
            isinstance(memory, bool)
            or not isinstance(memory, int | float)
            or not math.isfinite(memory)
            or memory <= 0
        ):
            raise CapabilityTableError(
                f"{path}: {where} ({entry['id']!r}) has memory_gb {memory!r}; a "
                f"card class's memory is a positive number of GB"
            )
        card_class = CardClass(
            id=entry["id"], label=entry["label"], memory_gb=float(memory)
        )
        if any(c.id == card_class.id for c in classes):
            raise CapabilityTableError(
                f"{path}: {where}: card class {card_class.id!r} is declared twice"
            )
        classes.append(card_class)
    return tuple(classes)


def _given_for(
    entry: Mapping[str, Any], declared: frozenset[str], path: Path, where: str
) -> None:
    """A ``card_class`` an entry carries is one the table declares."""
    if "card_class" not in entry:
        return
    named = entry["card_class"]
    if not isinstance(named, str) or named not in declared:
        raise CapabilityTableError(
            f"{path}: {where} is keyed by card class {named!r}, which the table "
            f"does not declare (declared: {', '.join(sorted(declared)) or 'none'})"
        )


def _check_readings(
    index: int, value: Any, declared: frozenset[str], path: Path
) -> None:
    """A model row carries only declared keys, and every reading of it names a
    declared card class, or the table is refused."""
    entry = _object(value, path, f"models[{index}]")
    row = f"models[{index}] ({entry.get('id')!r})"
    _closed(entry, "model row", path, row)
    _required(entry, _MODEL_REQUIRED, path, row)
    for key in _MODEL_NUMBERS:
        if key in entry and not _number(entry[key]):
            raise CapabilityTableError(
                f"{path}: {row} gives {key!r} as {entry[key]!r}; a model's "
                f"{key!r} is a number"
            )
    if "not_for_fit" in entry and not _text(entry["not_for_fit"]):
        raise CapabilityTableError(
            f"{path}: {row} gives 'not_for_fit' as {entry['not_for_fit']!r}; it "
            f"is the text saying why the row is never listed as fitting a card"
        )
    if "resolution" in entry and not _text(entry["resolution"]):
        raise CapabilityTableError(
            f"{path}: {row} gives 'resolution' as {entry['resolution']!r}; it "
            f"is the resolution the row was read at, written as non-empty text"
        )
    for key in _MODEL_BOOLEANS:
        if key in entry and not isinstance(entry[key], bool):
            raise CapabilityTableError(
                f"{path}: {row} gives {key!r} as {entry[key]!r}; a model's "
                f"{key!r} is true or false"
            )
    for field_name in READING_LISTS:
        if field_name not in entry:
            continue
        readings = _entries(entry[field_name], path, f"{row} {field_name}")
        for place, reading in enumerate(readings):
            where = f"{row} {field_name}[{place}]"
            reading = _object(reading, path, where)
            _closed(reading, "reading", path, where)
            if "card_class" not in reading:
                raise CapabilityTableError(
                    f"{path}: {where} names no 'card_class'; every figure is an "
                    f"estimate for a declared card class"
                )
            _given_for(reading, declared, path, where)
            for key in _READING_FIGURES:
                if key in reading and not _number(reading[key]):
                    raise CapabilityTableError(
                        f"{path}: {where} gives {key!r} as {reading[key]!r}; a "
                        f"reading's figure is a number"
                    )


def _check_shape(raw: Mapping[str, Any], path: Path) -> tuple[CardClass, ...]:
    """Refuse, by name, every entry of a shape or a key this code does not read.

    Returns the declared card classes, which everything else is keyed by.
    """
    _closed(raw, "table", path, "the table")
    card_classes = _card_classes(raw, path)
    declared = frozenset(c.id for c in card_classes)
    for index, value in enumerate(
        _entries(raw.get("harness_caveats", []), path, "harness_caveats")
    ):
        where = f"harness_caveats[{index}]"
        caveat = _object(value, path, where)
        _closed(caveat, "harness caveat", path, where)
        _required(caveat, _CAVEAT_REQUIRED, path, where)
    for index, value in enumerate(_entries(raw.get("models", []), path, "models")):
        _check_readings(index, value, declared, path)
    backends = _object(raw.get("backends", {}), path, "backends")
    _values(backends, "backends block", path, "backends")
    for name, value in backends.items():
        if name in DECLARED_KEYS["backends block"]:
            continue
        where = f"backends[{name!r}]"
        backend = _object(value, path, where)
        _closed(backend, "backend", path, where)
        _given_for(backend, declared, path, where)
    for index, value in enumerate(
        _entries(raw.get("concurrency_findings", []), path, "concurrency_findings")
    ):
        where = f"concurrency_findings[{index}]"
        finding = _object(value, path, where)
        _closed(finding, "concurrency finding", path, where)
        _given_for(finding, declared, path, where)
    return card_classes


def _measurements(rows: list[dict[str, Any]], key: str) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(
            value=float(row[key]),
            backend=str(row.get("backend", "")),
            card_class=str(row["card_class"]),
        )
        for row in rows
        if key in row
    )


def table_path() -> Path:
    """Locate the shipped table, whether running from a checkout or a wheel."""
    packaged = resources.files("mcgyvr") / "data" / TABLE_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    # Running from a source checkout: data/ sits at the repo root.
    checkout = Path(__file__).resolve().parents[2] / "data" / TABLE_FILENAME
    if checkout.is_file():
        return checkout
    raise CapabilityTableError(
        f"capability table not found (looked for {TABLE_FILENAME})"
    )


def load(path: Path | None = None) -> CapabilityTable:
    """Load and validate the capability table."""
    path = path or table_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CapabilityTableError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise CapabilityTableError(f"{path} is not UTF-8 text: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CapabilityTableError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise CapabilityTableError(f"{path}: the table is {_kind(raw)}, not an object")
    found = raw.get("schema_version")
    if type(found) is not int or found != SCHEMA_VERSION:
        raise CapabilityTableError(
            f"{path} has capability table schema_version {found!r}; this code "
            f"reads version {SCHEMA_VERSION} only"
        )

    # Every shape the parse below relies on (each required key, each number) is
    # refused by name here first, so nothing below raises out of the loader.
    card_classes = _check_shape(raw, path)

    models = tuple(
        Model(
            id=str(entry["id"]),
            family=str(entry["family"]),
            params_b=float(entry["params_b"]),
            vram_gb_working=float(entry["vram_gb_working"]),
            weights_gb=float(entry["weights_gb"]),
            quant=str(entry.get("quant", "")),
            throughput=_measurements(entry.get("throughput_tok_s", []), "value"),
            requires_backend=entry.get("requires_backend"),
            notes=str(entry.get("notes", "")),
            not_for_fit=str(entry["not_for_fit"]) if "not_for_fit" in entry else None,
            seconds_per_image=_measurements(
                entry.get("seconds_per_image", []), "value"
            ),
            seconds_per_clip=_measurements(entry.get("seconds_per_clip", []), "value"),
            resolution=str(entry.get("resolution", "")),
            steps=float(entry["steps"]) if "steps" in entry else None,
            vae_decode_gb=(
                float(entry["vae_decode_gb"]) if "vae_decode_gb" in entry else None
            ),
            frames=float(entry["frames"]) if "frames" in entry else None,
            temporal_compress=(
                float(entry["temporal_compress"])
                if "temporal_compress" in entry
                else None
            ),
            sample_rate_hz=(
                float(entry["sample_rate_hz"]) if "sample_rate_hz" in entry else None
            ),
            rtf=float(entry["rtf"]) if "rtf" in entry else None,
            cpu_only=bool(entry["cpu_only"]) if "cpu_only" in entry else False,
        )
        for entry in raw.get("models", [])
    )
    if not models:
        raise CapabilityTableError(f"{path} declares no models")

    caveats = tuple(
        Caveat(
            id=str(c["id"]),
            severity=str(c["severity"]),
            summary=str(c["summary"]),
            consequence=str(c["consequence"]),
        )
        for c in raw.get("harness_caveats", [])
    )
    return CapabilityTable(models=models, caveats=caveats, card_classes=card_classes)
