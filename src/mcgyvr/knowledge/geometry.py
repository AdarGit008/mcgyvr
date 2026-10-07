"""A model file's geometry: its header row, with one source and one date.

A plan sizes a unit with the product's serving sizer (:func:`mcgyvr.serving.fit`),
and that sizer reads one ``ggufscan`` row: the tensor table summed per block,
the cache geometry per layer, the recurrent state, the experts per block (an
MoE) and the multi-token-prediction head (MTP). A model record
(:mod:`mcgyvr.knowledge.record`) says what a file weighs; this says how it is
built, so an MoE can be sized offline, by the same law as a file on a rig.

A row is one reading of one file, so it carries **one** kind, source and date
for all of its numbers (``gguf-header-range:<repo>@<revision>/<file>``, read
over HTTP ``Range``, never a weight). It is kept per file at a revision:

* the **cache**, ``$MCGYVR_HOME/knowledge/geometry/``, one file per
  ``repo@revision/file``, written by :func:`write` when an online run read the
  header;
* the **shipped** rows, ``data/model-geometry.json``, the headers of the
  shipped catalog's files, so a machine with no network and no cache can still
  size them.

:func:`load` reads the cache first, then the shipped rows. A cache file that
cannot be read is not read; it is named in :attr:`Geometries.skipped` with
why, and the shipped rows still answer. Nothing here opens a socket.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

from mcgyvr.knowledge import store
from mcgyvr.knowledge.record import KnowledgeError, Weights

#: The version of a geometry document, the shipped file's and each cache file's.
SCHEMA_VERSION = 1
#: The cache's folder under the knowledge cache.
GEOMETRY_DIR = "geometry"
#: The shipped rows' file name, in the package's data folder.
SHIPPED_FILENAME = "model-geometry.json"
#: The one source a row may come from, and its kind.
SOURCE = "gguf-header-range"
KIND = "fact"
#: What a cache file's name is made of; anything else becomes ``_``.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_FILE_KEYS = ("repo", "revision", "file")
_DOCUMENT_KEYS = frozenset({"schema_version", "weights", "geometry"})
_SHIPPED_KEYS = frozenset({"schema_version", "geometries", "_purpose"})
_NUMBER_KEYS = frozenset({"value", "kind", "source", "read_at"})


@dataclass(frozen=True)
class Geometry:
    """One file's header row, where it was read, when, and where it is kept.

    ``origin`` is :data:`mcgyvr.knowledge.store.CACHE` or
    :data:`mcgyvr.knowledge.store.SHIPPED`.
    """

    repo: str
    revision: str
    file: str
    row: Mapping[str, Any]
    source: str
    read_at: date
    origin: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.repo, self.revision, self.file)


@dataclass(frozen=True)
class Geometries:
    """Every row known offline, the cache's before the shipped ones.

    ``skipped`` names each cache file that was not read, with why.
    """

    rows: Mapping[tuple[str, str, str], Geometry]
    skipped: tuple[tuple[Path, str], ...]

    def of(self, weights: Weights | None) -> Geometry | None:
        """The row of the file ``weights`` names, if one is known."""
        if weights is None:
            return None
        return self.rows.get((weights.repo, weights.revision, weights.file))


def locator(repo: str, revision: str, file: str) -> str:
    """Where a row was read: the file at its revision."""
    return f"{repo}@{revision}/{file}"


def cache_dir() -> Path:
    """``$MCGYVR_HOME/knowledge/geometry``."""
    return store.cache_dir() / GEOMETRY_DIR


def cache_file(repo: str, revision: str, file: str) -> Path:
    """The cache file the row of ``file`` at ``revision`` is filed in."""
    stem = _UNSAFE.sub("_", f"{repo.replace('/', '--')}@{revision}--{file}")
    return cache_dir() / f"{stem}.json"


def shipped_path() -> Path:
    """The shipped rows, from a wheel or a source checkout."""
    packaged = resources.files("mcgyvr") / "data" / SHIPPED_FILENAME
    if Path(str(packaged)).is_file():
        return Path(str(packaged))
    checkout = Path(__file__).resolve().parents[3] / "data" / SHIPPED_FILENAME
    if checkout.is_file():
        return checkout
    raise KnowledgeError(f"model geometry not found (looked for {SHIPPED_FILENAME})")


def _text(raw: Any, where: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise KnowledgeError(f"{where} is not a non-empty string")
    return raw


def parse(raw: Any, where: str, *, origin: str) -> Geometry:
    """One geometry document, validated: one row of one file, with one kind,
    one source naming that file at that revision, and one day."""
    if not isinstance(raw, dict):
        raise KnowledgeError(f"{where}: a geometry document is not an object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise KnowledgeError(
            f"{where} has schema_version {raw.get('schema_version')!r}; this code "
            f"reads geometry version {SCHEMA_VERSION} only"
        )
    unknown = sorted(set(raw) - _DOCUMENT_KEYS)
    if unknown:
        raise KnowledgeError(f"{where} has keys a geometry does not have: {unknown}")
    weights = raw.get("weights")
    if not isinstance(weights, dict) or set(weights) != set(_FILE_KEYS):
        raise KnowledgeError(
            f"{where} weights is not an object of exactly {list(_FILE_KEYS)}"
        )
    repo, revision, file = (
        _text(weights[key], f"{where} weights {key}") for key in _FILE_KEYS
    )
    held = raw.get("geometry")
    if not isinstance(held, dict) or set(held) != _NUMBER_KEYS:
        raise KnowledgeError(
            f"{where} geometry is not an object of exactly {sorted(_NUMBER_KEYS)}: "
            f"one row with its kind, its source and the day it was read"
        )
    if held["kind"] != KIND:
        raise KnowledgeError(f"{where} geometry kind {held['kind']!r} is not {KIND!r}")
    expected = f"{SOURCE}:{locator(repo, revision, file)}"
    if held["source"] != expected:
        raise KnowledgeError(
            f"{where} geometry source {held['source']!r} is not the header of the "
            f"file it is filed for ({expected!r})"
        )
    read_at = held["read_at"]
    try:
        day = date.fromisoformat(read_at) if isinstance(read_at, str) else None
    except ValueError:
        day = None
    if day is None or len(read_at) != len("YYYY-MM-DD"):
        raise KnowledgeError(f"{where} read_at {read_at!r} is not a day (YYYY-MM-DD)")
    row = held["value"]
    if not isinstance(row, dict) or "error" in row:
        raise KnowledgeError(f"{where} geometry value is not a header row")
    if Path(str(row.get("file") or "")).name != Path(file).name:
        raise KnowledgeError(
            f"{where}: the row was read from {row.get('file')!r}, not {file!r}"
        )
    size = row.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise KnowledgeError(f"{where}: the row states no size_bytes")
    return Geometry(
        repo=repo,
        revision=revision,
        file=file,
        row=row,
        source=expected,
        read_at=day,
        origin=origin,
    )


def dump(one: Geometry) -> dict[str, Any]:
    """``one`` as a document, the shape :func:`parse` reads back."""
    return {
        "schema_version": SCHEMA_VERSION,
        "weights": {"repo": one.repo, "revision": one.revision, "file": one.file},
        "geometry": {
            "value": dict(one.row),
            "kind": KIND,
            "source": one.source,
            "read_at": one.read_at.isoformat(),
        },
    }


def write(
    repo: str, revision: str, file: str, row: Mapping[str, Any], *, today: date
) -> Path:
    """File the header row of ``file`` at ``revision`` in the cache.

    Through a staging name and :func:`os.replace`, as the record cache is, and
    read back before it is filed, so the cache cannot hold what :func:`load`
    would refuse.
    """
    one = Geometry(
        repo=repo,
        revision=revision,
        file=file,
        row=dict(row),
        source=f"{SOURCE}:{locator(repo, revision, file)}",
        read_at=today,
        origin=store.CACHE,
    )
    document = dump(one)
    parse(document, f"the header of {locator(repo, revision, file)}", origin="cache")
    target = cache_file(repo, revision, file)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    staging.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    os.replace(staging, target)
    return target


def shipped() -> tuple[Geometry, ...]:
    """The shipped rows. A file that does not read is refused."""
    path = shipped_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise KnowledgeError(f"{path} is not geometry version {SCHEMA_VERSION}")
    unknown = sorted(set(raw) - _SHIPPED_KEYS)
    if unknown:
        raise KnowledgeError(f"{path} has keys it does not have: {unknown}")
    listed = raw.get("geometries")
    if not isinstance(listed, list):
        raise KnowledgeError(f"{path} declares no geometries list")
    rows = tuple(
        parse(one, f"{path} [{index}]", origin=store.SHIPPED)
        for index, one in enumerate(listed)
    )
    if len({one.key for one in rows}) != len(rows):
        raise KnowledgeError(f"{path} holds one file at one revision twice")
    return rows


def load() -> Geometries:
    """Every row known with no network: the cache's, then the shipped ones."""
    rows: dict[tuple[str, str, str], Geometry] = {}
    skipped: list[tuple[Path, str]] = []
    folder = cache_dir()
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                one = parse(
                    json.loads(path.read_text(encoding="utf-8")),
                    str(path),
                    origin=store.CACHE,
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                skipped.append((path, f"cannot read it: {exc}"))
                continue
            except KnowledgeError as exc:
                skipped.append((path, str(exc)))
                continue
            rows.setdefault(one.key, one)
    for one in shipped():
        rows.setdefault(one.key, one)
    return Geometries(rows=rows, skipped=tuple(skipped))
