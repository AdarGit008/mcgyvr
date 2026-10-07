"""Where model knowledge is kept, and the order it is read in.

Two places hold records of :mod:`mcgyvr.knowledge.record`:

* the **cache**, ``$MCGYVR_HOME/knowledge/`` (default ``~/.mcgyvr/knowledge``):
  what an online run read from the Hub and the boards, one file per model at
  one quantisation, written by :func:`write`;
* the **shipped catalog**, ``data/model-catalog.json`` in the package: the
  fallback a machine with no network and no cache still has.

:func:`offline` reads the cache first, then the shipped catalog: a model the
cache holds is taken from the cache, every other model from the catalog, and
each says which (:attr:`Known.origin`). A cache file that cannot be read, or
that is of another format version, is not read; it is named in
:attr:`Knowledge.skipped` with why, and the catalog still answers. The cache
is a cache: losing a file costs a lookup, never a plan.

Nothing here opens a socket. The online half implements :class:`Lookup` and
files what it answers with :func:`write`.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Protocol

from mcgyvr.fleet import roots
from mcgyvr.knowledge.record import (
    KnowledgeError,
    ModelRecord,
    dump_document,
    parse_document,
)

#: The shipped catalog's file name, in the package's data folder.
MODEL_CATALOG_FILENAME = "model-catalog.json"
#: The cache's folder under the config folder.
CACHE_DIR = "knowledge"
#: What a cache file's name is made of; anything else in a model id or a
#: quantisation becomes ``_``.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
#: Where a record came from, as :attr:`Known.origin` says it.
CACHE = "cache"
SHIPPED = "shipped"


class Lookup(Protocol):
    """An online source of records: the Hub, a header read, a board.

    Asked for a model, it answers the records it could read, every number with
    its source and the day it was read. It never writes; the caller files what
    it answered with :func:`write`. The online half implements it, over a
    transport a test injects.
    """

    def __call__(self, model_id: str) -> Sequence[ModelRecord]: ...


@dataclass(frozen=True)
class Known:
    """One record, and where it was read: :data:`CACHE` or :data:`SHIPPED`."""

    record: ModelRecord
    origin: str


@dataclass(frozen=True)
class Knowledge:
    """What is known offline: the cache first, then the shipped catalog.

    ``skipped`` names each cache file that was not read, with why.
    ``oldest_read_at`` is the oldest day any number of ``known`` was read, or
    ``None`` when nothing is known.
    """

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
    """The shipped catalog, from a wheel or a source checkout."""
    packaged = resources.files("mcgyvr") / "data" / MODEL_CATALOG_FILENAME
    if Path(str(packaged)).is_file():
        return Path(str(packaged))
    # Running from a source checkout: data/ sits at the repo root.
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
    """The shipped catalog's records. A catalog that does not read is refused."""
    path = catalog_path()
    records = _read(path, shipped=True)
    if not records:
        raise KnowledgeError(f"{path} declares no models")
    return records


def cache_dir() -> Path:
    """``$MCGYVR_HOME/knowledge`` (default ``~/.mcgyvr/knowledge``)."""
    try:
        return roots.home() / CACHE_DIR
    except roots.FolderError as exc:
        raise KnowledgeError(str(exc)) from exc


def cache_file(model_id: str, quant: str) -> Path:
    """The cache file :func:`write` files the record of ``model_id`` at
    ``quant`` in. The reader does not trust the name: it reads each file's own
    records."""
    stem = _UNSAFE.sub("_", f"{model_id.replace('/', '--')}--{quant}")
    return cache_dir() / f"{stem}.json"


def write(record: ModelRecord) -> Path:
    """File ``record`` in the cache, replacing what the cache held for it.

    Through a staging name and :func:`os.replace`, so a reader sees the old
    file or the new one, never half of one. The record is read back before it
    is filed, so the cache cannot hold what :func:`offline` would refuse.
    """
    document = dump_document((record,))
    parse_document(document, f"the record of {record.model_id}", shipped=False)
    target = cache_file(record.model_id, record.quant)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    staging.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, target)
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
    """What is known with no network: the cache first, then the shipped catalog.

    In the shipped catalog's order, each model taken from the cache when the
    cache holds it; then the models only the cache knows, in cache-file order.
    """
    cached, skipped = _cached()
    known: list[Known] = []
    for one in shipped():
        if one.key in cached:
            known.append(Known(record=cached.pop(one.key), origin=CACHE))
        else:
            known.append(Known(record=one, origin=SHIPPED))
    known.extend(Known(record=one, origin=CACHE) for one in cached.values())
    return Knowledge(known=tuple(known), skipped=tuple(skipped))
