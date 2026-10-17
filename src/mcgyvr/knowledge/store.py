""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.fleet import roots
from mcgyvr.knowledge.record import (
    KnowledgeError,
    ModelRecord,
    dump_document,
    parse_document,
)

#
MODEL_CATALOG_FILENAME = "model-catalog.json"
#
CACHE_DIR = "knowledge"
#
#
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
#
CACHE = "cache"
SHIPPED = "shipped"


@dataclass(frozen=True)
class Known:
    ""

    record: ModelRecord
    origin: str


@dataclass(frozen=True)
class Knowledge:
    ""

    known: tuple[Known, ...]
    skipped: tuple[tuple[Path, str], ...]

    @property
    def records(self) -> tuple[ModelRecord, ...]:
        return tuple(k.record for k in self.known)

    @property
    def oldest_read_at(self) -> date | None:
        days = [n.read_at for k in self.known for _name, n in k.record.numbers()]
        return min(days) if days else None


def catalog_path() -> Path:
    ""
    packaged = resources.files("mcgyvr") / "data" / MODEL_CATALOG_FILENAME
    if Path(str(packaged)).is_file():
        return Path(str(packaged))
    #
    checkout = Path(__file__).resolve().parents[3] / "data" / MODEL_CATALOG_FILENAME
    if checkout.is_file():
        return checkout
    raise KnowledgeError(
        f"model catalog not found (looked for {MODEL_CATALOG_FILENAME})"
    )


def _read(path: Path, *, shipped: bool) -> tuple[ModelRecord, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise KnowledgeError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise KnowledgeError(f"{path} is not valid JSON: {exc}") from exc
    return parse_document(raw, str(path), shipped=shipped)


def shipped() -> tuple[ModelRecord, ...]:
    ""
    path = catalog_path()
    records = _read(path, shipped=True)
    if not records:
        raise KnowledgeError(f"{path} declares no models")
    return records


def cache_dir() -> Path:
    ""
    try:
        return roots.home() / CACHE_DIR
    except roots.FolderError as exc:
        raise KnowledgeError(str(exc)) from exc


def cache_file(model_id: str, quant: str) -> Path:
    ""
    stem = _UNSAFE.sub("_", f"{model_id.replace('/', '--')}--{quant}")
    return cache_dir() / f"{stem}.json"


def write(record: ModelRecord) -> Path:
    ""
    document = dump_document((record,))
    parse_document(document, f"the record of {record.model_id}", shipped=False)
    target = cache_file(record.model_id, record.quant)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(target, json.dumps(document, indent=2) + "\n")
    return target


def _cached() -> tuple[dict[tuple[str, str], ModelRecord], list[tuple[Path, str]]]:
    folder = cache_dir()
    found: dict[tuple[str, str], ModelRecord] = {}
    skipped: list[tuple[Path, str]] = []
    if not folder.is_dir():
        return found, skipped
    for path in sorted(folder.glob("*.json")):
        try:
            records = _read(path, shipped=False)
        except KnowledgeError as exc:
            skipped.append((path, str(exc)))
            continue
        again = [one.key for one in records if one.key in found]
        if again:
            skipped.append((path, f"another cache file already holds {again}"))
            continue
        found.update((one.key, one) for one in records)
    return found, skipped


def offline() -> Knowledge:
    ""
    cached, skipped = _cached()
    known: list[Known] = []
    for one in shipped():
        if one.key in cached:
            known.append(Known(record=cached.pop(one.key), origin=CACHE))
        else:
            known.append(Known(record=one, origin=SHIPPED))
    known.extend(Known(record=one, origin=CACHE) for one in cached.values())
    return Knowledge(known=tuple(known), skipped=tuple(skipped))
