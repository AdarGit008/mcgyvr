"""The capability table: what each model costs to serve.

`load` reads the table from the installed package (or from a path it is given)
and checks it against the shape declared here, refusing a document of another
schema version or one carrying a key this code does not declare. Every figure
is an estimate, not a reading of the machine at hand; `CapabilityTable.fitting`
lists the rows a card's memory holds with a headroom beside them.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mcgyvr.shipped import shipped_file

TABLE_FILENAME = "capability-table.json"

#: The version of the table's format this code reads. A document whose
#: `schema_version` is not this exact integer is refused by name, before its
#: shape or its rows are looked at.
SCHEMA_VERSION = 4

#: Printed above a listing of the table, so that no figure in it is taken as a
#: reading of the card or machine in front of the reader.
ESTIMATES_NOTICE = "Estimates; none is a reading of your machine."

# How many decimal gigabytes make one GiB (1024**3 / 1000**3). The table states
# its memory and weight figures in decimal GB, as card vendors do; sizing
# divides by this to carry them into the GiB it computes in.
GB_PER_GIB = 1.073741824


class CapabilityTableError(Exception):
    """A table that cannot be read, or that is not the shape declared here.

    Every refusal names the file, and what in it was refused.
    """


@dataclass(frozen=True)
class Model:
    """One row of the table: what a model costs to serve.

    Its size, its weights and the memory it takes to work, and the server it
    needs if any.
    """

    id: str
    family: str
    params_b: float
    vram_gb_working: float
    weights_gb: float
    quant: str
    requires_backend: str | None
    notes: str
    not_for_fit: str | None = None
    model_id: str | None = None


@dataclass(frozen=True)
class CapabilityTable:
    models: tuple[Model, ...]

    def get(self, model_id: str) -> Model | None:
        return next((m for m in self.models if m.id == model_id), None)

    def fitting(self, vram_gb: float, headroom_gb: float = 2.0) -> list[Model]:
        """Rows that fit `vram_gb` with `headroom_gb` to spare, in table order.

        A row is left out when it carries `not_for_fit`, or when its working
        footprint plus the headroom is more than the memory available. The
        headroom is an absolute figure, not a share of the card. For a unified
        GPU `vram_gb` is the memory it may use (`estimate.usable_unified_mb`),
        never the machine's whole memory.
        """
        return [
            m
            for m in self.models
            if m.not_for_fit is None and m.vram_gb_working + headroom_gb <= vram_gb
        ]


#: Every key the table may carry, by the level of the document it sits at: the
#: table, a row of `models`, the `backends` block, and each backend's block.
#: A level is closed: a key it does not declare is refused by name, and the
#: refusal lists the keys declared for it. So no figure — a quality score, a
#: benchmark reading, a reading of a card — enters the table without first
#: being declared here, where a reviewer reads it. A row states what a model
#: costs to serve, and these keys are the only terms it can state that in.
#: The `backends block` level declares only `_doc`, the block's own prose:
#: what sits under `backends` is a mapping whose keys name servers, not facts,
#: so that level is open where each backend under it is closed.
#: `active_params_b` and `architecture` are declared and checked but not
#: carried into `Model`: `architecture` is read from the raw document by the
#: sizing seam, and `active_params_b` is checked as a number and unread.
#: A declared key that is not a container holds a single value; an object
#: under it would carry keys of no level (see `CONTAINER_KEYS`).
DECLARED_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "table": frozenset(
            {
                "schema_version",
                "_purpose",
                "models",
                "backends",
            }
        ),
        "model row": frozenset(
            {
                "id",
                "model_id",
                "family",
                "params_b",
                "active_params_b",
                "architecture",
                "quant",
                "weights_gb",
                "vram_gb_working",
                "requires_backend",
                "not_for_fit",
                "notes",
            }
        ),
        "backends block": frozenset({"_doc"}),
        "backend": frozenset({"wire_protocol", "strengths", "limits"}),
    }
)


#: The keys whose value holds entries, by level. Every other declared key holds
#: a single value, so an object under it is refused (`_values`).
CONTAINER_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        **{level: frozenset[str]() for level in DECLARED_KEYS},
        "table": frozenset({"models", "backends"}),
    }
)


def _kind(value: Any) -> str:
    """Name one JSON value's kind, so a refusal can say what it found."""
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
    """Refuse a key `entry` carries that `level` does not declare.

    The refusal names the stray keys and those declared for the level; the
    entry's values are then checked too (`_values`).
    """
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
    """Refuse an object under a key of `level` that holds a value, not entries.

    A list is refused as well when anything it holds is an object: keys there
    would be keys no level declares.
    """
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


#: What a row must state or be refused: without these it has no name and no cost.
_MODEL_REQUIRED = ("id", "family", "params_b", "vram_gb_working", "weights_gb")
_MODEL_NUMBERS = (
    "params_b",
    "active_params_b",
    "vram_gb_working",
    "weights_gb",
)


def _required(
    entry: Mapping[str, Any], keys: tuple[str, ...], path: Path, where: str
) -> None:
    for key in keys:
        if key not in entry:
            raise CapabilityTableError(
                f"{path}: {where} is missing required key {key!r}"
            )


def _check_row(index: int, value: Any, path: Path) -> None:
    """Check one row of `models`: its keys, the required ones, its values' shapes."""
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
    if "model_id" in entry and not _text(entry["model_id"]):
        raise CapabilityTableError(
            f"{path}: {row} gives 'model_id' as {entry['model_id']!r}; a model's "
            f"'model_id' is the catalog repository id its weights match, written "
            f"as non-empty text"
        )


def _check_shape(raw: Mapping[str, Any], path: Path) -> None:
    """Check the table's declared keys, every row, and every named backend.

    `backends` is open at its own level: its keys name servers rather than
    facts, so each value under it is checked as a backend instead.
    """
    _closed(raw, "table", path, "the table")
    for index, value in enumerate(_entries(raw.get("models", []), path, "models")):
        _check_row(index, value, path)
    backends = _object(raw.get("backends", {}), path, "backends")
    _values(backends, "backends block", path, "backends")
    for name, value in backends.items():
        if name in DECLARED_KEYS["backends block"]:
            continue
        where = f"backends[{name!r}]"
        backend = _object(value, path, where)
        _closed(backend, "backend", path, where)


def table_path() -> Path:
    """Where the shipped table is: the package's copy, else the checkout's.

    A built wheel carries the file inside the package; a source tree, where
    that copy is absent, is read from the repository's `data/` directory.
    """
    found = shipped_file(TABLE_FILENAME)
    if found is not None:
        return found
    raise CapabilityTableError(
        f"capability table not found (looked for {TABLE_FILENAME})"
    )


def load(path: Path | None = None) -> CapabilityTable:
    """Read and check the table at `path`, defaulting to `table_path()`.

    Every failure is a `CapabilityTableError` naming the file: unreadable or
    non-UTF-8 text, invalid JSON, another schema version, a key or value of a
    shape this code does not declare, no models at all, or a `model_id`
    declared twice.
    """
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

    # The shape is checked before any row is turned into a `Model`, so a
    # refusal names the key rather than failing part-way through construction.
    _check_shape(raw, path)

    models = tuple(
        Model(
            id=str(entry["id"]),
            family=str(entry["family"]),
            params_b=float(entry["params_b"]),
            vram_gb_working=float(entry["vram_gb_working"]),
            weights_gb=float(entry["weights_gb"]),
            quant=str(entry.get("quant", "")),
            requires_backend=entry.get("requires_backend"),
            notes=str(entry.get("notes", "")),
            not_for_fit=str(entry["not_for_fit"]) if "not_for_fit" in entry else None,
            model_id=(str(entry["model_id"]) if "model_id" in entry else None),
        )
        for entry in raw.get("models", [])
    )
    if not models:
        raise CapabilityTableError(f"{path} declares no models")
    mapped = [m.model_id for m in models if m.model_id is not None]
    if len(mapped) != len(set(mapped)):
        raise CapabilityTableError(
            f"{path}: a model_id is declared twice; the shared catalog key must "
            f"name one row, not two"
        )
    return CapabilityTable(models=models)
