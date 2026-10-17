""

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

#
#
#
SCHEMA_VERSION = 4

#
#
ESTIMATES_NOTICE = "Estimates; none is a reading of your machine."

#
#
#
GB_PER_GIB = 1.073741824


class CapabilityTableError(Exception):
    ""


@dataclass(frozen=True)
class Model:
    ""

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
    #
    resolution: str = ""
    steps: float | None = None
    vae_decode_gb: float | None = None
    frames: float | None = None
    temporal_compress: float | None = None
    sample_rate_hz: float | None = None
    rtf: float | None = None
    cpu_only: bool = False


@dataclass(frozen=True)
class CapabilityTable:
    models: tuple[Model, ...]

    def get(self, model_id: str) -> Model | None:
        return next((m for m in self.models if m.id == model_id), None)

    def fitting(self, vram_gb: float, headroom_gb: float = 2.0) -> list[Model]:
        ""
        return [
            m
            for m in self.models
            if m.not_for_fit is None and m.vram_gb_working + headroom_gb <= vram_gb
        ]


#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
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
                #
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
        "backends block": frozenset({"_doc"}),
        "backend": frozenset({"wire_protocol", "strengths", "limits"}),
    }
)


#
#
CONTAINER_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        **{level: frozenset[str]() for level in DECLARED_KEYS},
        "table": frozenset({"models", "backends"}),
    }
)


def _kind(value: Any) -> str:
    ""
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
    ""
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
    ""
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


#
_MODEL_REQUIRED = ("id", "family", "params_b", "vram_gb_working", "weights_gb")
_MODEL_NUMBERS = (
    "params_b",
    "active_params_b",
    "vram_gb_working",
    "weights_gb",
    #
    #
    #
    "steps",
    "vae_decode_gb",
    "frames",
    "temporal_compress",
    "sample_rate_hz",
    "rtf",
)

#
_MODEL_BOOLEANS = ("cpu_only",)


def _required(
    entry: Mapping[str, Any], keys: tuple[str, ...], path: Path, where: str
) -> None:
    for key in keys:
        if key not in entry:
            raise CapabilityTableError(
                f"{path}: {where} is missing required key {key!r}"
            )


def _check_row(index: int, value: Any, path: Path) -> None:
    ""
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


def _check_shape(raw: Mapping[str, Any], path: Path) -> None:
    ""
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
    ""
    packaged = resources.files("mcgyvr") / "data" / TABLE_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    #
    checkout = Path(__file__).resolve().parents[2] / "data" / TABLE_FILENAME
    if checkout.is_file():
        return checkout
    raise CapabilityTableError(
        f"capability table not found (looked for {TABLE_FILENAME})"
    )


def load(path: Path | None = None) -> CapabilityTable:
    ""
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

    #
    #
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
    mapped = [m.model_id for m in models if m.model_id is not None]
    if len(mapped) != len(set(mapped)):
        raise CapabilityTableError(
            f"{path}: a model_id is declared twice; the shared catalog key must "
            f"name one row, not two"
        )
    return CapabilityTable(models=models)
