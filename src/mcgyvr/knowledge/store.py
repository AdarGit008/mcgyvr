"""
Storage for the knowledge layer: the shipped model catalog, read from the
package's data folder, and the per-user cache of measured records that overrides
it.

Both sources are JSON documents validated by ``mcgyvr.knowledge.record`` as they
are read; a shipped record may not carry a machine reading, a cached one may.
``offline`` merges the two and reports, rather than raises on, cache files it
could not use.
"""

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

#: The catalog file the package ships; every shipped record is read from it.
MODEL_CATALOG_FILENAME = "model-catalog.json"
#: The folder under the mcgyvr home that holds one file per cached record.
CACHE_DIR = "knowledge"
#: A cache file stem keeps these characters as they are; every other one becomes "_".
#: Model ids and quantisations carry spaces and "+", so names are flattened,
#: not used raw.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
#: The origin a Known record reports: CACHE for a cache file, SHIPPED for the catalog.
CACHE = "cache"
SHIPPED = "shipped"


@dataclass(frozen=True)
class Known:
    """A record together with the origin it was read from, CACHE or SHIPPED."""

    record: ModelRecord
    origin: str


@dataclass(frozen=True)
class Knowledge:
    """The merged view ``offline`` returns: the records it will use, in shipped
    order followed by cache-only records, and the cache files it skipped, each
    with the reason it could not be used."""

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
    """The shipped catalog: the packaged data file when the package has one,
    otherwise ``data/`` of a source checkout; raises KnowledgeError when neither
    exists."""
    packaged = resources.files("mcgyvr") / "data" / MODEL_CATALOG_FILENAME
    if Path(str(packaged)).is_file():
        return Path(str(packaged))
    # No packaged data file, so this is a source checkout: data/ sits beside
    # src/, three levels up.
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
    """The catalog's records, validated as shipped so that none of them carries a
    machine reading; raises KnowledgeError when the file is missing, unreadable or
    declares no models."""
    path = catalog_path()
    records = _read(path, shipped=True)
    if not records:
        raise KnowledgeError(f"{path} declares no models")
    return records


def cache_dir() -> Path:
    """The cache folder inside the mcgyvr home; a home that cannot be resolved
    becomes a KnowledgeError."""
    try:
        return roots.home() / CACHE_DIR
    except roots.FolderError as exc:
        raise KnowledgeError(str(exc)) from exc


def cache_file(model_id: str, quant: str) -> Path:
    """Where one model_id at one quantisation is cached: ``/`` in the model id
    becomes ``--``, the pair is joined by ``--``, every character outside the safe
    set becomes ``_``, and the name ends in ``.json``."""
    stem = _UNSAFE.sub("_", f"{model_id.replace('/', '--')}--{quant}")
    return cache_dir() / f"{stem}.json"


def write(record: ModelRecord) -> Path:
    """Cache one record: dump it as a single-model document, parse that document
    back as a cache document to check it, write it atomically to the cache path of
    the record's model and quantisation, and return that path."""
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
    """Merge the cache with the shipped catalog without touching the network: a
    cached record replaces the shipped record with the same model_id and
    quantisation, cache-only records follow the shipped ones, and cache files that
    could not be read or repeat a key already present are reported in
    ``skipped``."""
    cached, skipped = _cached()
    known: list[Known] = []
    for one in shipped():
        if one.key in cached:
            known.append(Known(record=cached.pop(one.key), origin=CACHE))
        else:
            known.append(Known(record=one, origin=SHIPPED))
    known.extend(Known(record=one, origin=CACHE) for one in cached.values())
    return Knowledge(known=tuple(known), skipped=tuple(skipped))
