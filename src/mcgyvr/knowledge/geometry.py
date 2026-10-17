"""One GGUF header row per weights file, each with one source and one day.

A geometry is a header a scan read from one file at one revision: a mapping of
the header's values, filed under the weights file it was read from. A row is
kept whole, so every number in it shares one kind (a fact), one source
(``gguf-header-range:<repo>@<revision>/<file>``, the header of that very file)
and the one day on which it was read.

Rows come from two places. `write` files a row as its own JSON document under
``$MCGYVR_HOME/knowledge/geometry/``; `shipped` reads the rows that travel with
the package in ``data/model-geometry.json``. `load` merges both, a cached row
standing in front of a shipped row of the same file, and names — rather than
raises on — a cache document it cannot use, so a bad file never hides the
others.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

from mcgyvr import atomic
from mcgyvr.knowledge import store
from mcgyvr.knowledge.record import KnowledgeError, Weights, _text

#: The geometry document format this code reads and writes; a document of any
#: other version is refused rather than read.
SCHEMA_VERSION = 1
#: The folder, under the knowledge cache, holding one document per weights file.
GEOMETRY_DIR = "geometry"
#: The data file shipping the catalog's own rows, looked for in the package and
#: then in the checkout's data directory.
SHIPPED_FILENAME = "model-geometry.json"
#: The reading every row is: a GGUF header fetched by byte ranges, which is what
#: a row's source starts with and what its source must say.
SOURCE = "gguf-header-range"
# A geometry is a reading of the file rather than an estimate, so its one kind
# is a fact.
KIND = "fact"
#: Characters a document's name may not hold: repo slashes become ``--``, and
#: every other one becomes ``_``.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_FILE_KEYS = ("repo", "revision", "file")
_DOCUMENT_KEYS = frozenset({"schema_version", "weights", "geometry"})
_SHIPPED_KEYS = frozenset({"schema_version", "geometries", "_purpose"})
_NUMBER_KEYS = frozenset({"value", "kind", "source", "read_at"})


@dataclass(frozen=True)
class Geometry:
    """The header row of one weights file, with where it came from and when.

    `key` is the (repo, revision, file) triple naming that file, `row` the
    header as read, `source` which reading this is, `read_at` the day it was
    read, and `origin` whether the row was cached or shipped.
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
    """Every row `load` found, and the cache documents it had to leave out.

    `rows` is keyed by (repo, revision, file); `skipped` pairs each unusable
    cache path with the reason it was not read.
    """

    rows: Mapping[tuple[str, str, str], Geometry]
    skipped: tuple[tuple[Path, str], ...]

    def of(self, weights: Weights | None) -> Geometry | None:
        """The row for these weights, or None when there are none or no row."""
        if weights is None:
            return None
        return self.rows.get((weights.repo, weights.revision, weights.file))


def locator(repo: str, revision: str, file: str) -> str:
    """Name a file at a revision as ``repo@revision/file``."""
    return f"{repo}@{revision}/{file}"


def cache_dir() -> Path:
    """The directory holding the cached geometry documents, inside the cache."""
    return store.cache_dir() / GEOMETRY_DIR


def cache_file(repo: str, revision: str, file: str) -> Path:
    """The cache document for one weights file.

    The name is ``repo@revision--file.json``, with slashes in the repo turned
    into ``--`` and any other character a name cannot hold turned into ``_``.
    """
    stem = _UNSAFE.sub("_", f"{repo.replace('/', '--')}@{revision}--{file}")
    return cache_dir() / f"{stem}.json"


def shipped_path() -> Path:
    """The shipped geometry file: the packaged data file, else the checkout's."""
    packaged = resources.files("mcgyvr") / "data" / SHIPPED_FILENAME
    if Path(str(packaged)).is_file():
        return Path(str(packaged))
    checkout = Path(__file__).resolve().parents[3] / "data" / SHIPPED_FILENAME
    if checkout.is_file():
        return checkout
    raise KnowledgeError(f"model geometry not found (looked for {SHIPPED_FILENAME})")


def parse(raw: Any, where: str, *, origin: str) -> Geometry:
    """Read one geometry document, or refuse it by naming the rule it broke.

    `raw` must be a document of `SCHEMA_VERSION` with no keys beyond
    ``schema_version``, ``weights`` and ``geometry``. ``weights`` must name
    ``repo``, ``revision`` and ``file`` and nothing else; ``geometry`` must hold
    one row of exactly ``value``, ``kind``, ``source`` and ``read_at``, where
    the kind is `KIND`, the source is ``SOURCE`` and that same locator, and
    ``read_at`` is a bare ``YYYY-MM-DD`` day. The value must be a header row
    without an ``error`` in it, read from a file of the same name, and stating a
    positive whole ``size_bytes``. `where` names the document in every refusal,
    and `origin` is carried onto the row as where it came from.
    """
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
    """The document for one row: its version, the file it is for, and the row."""
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
    """File one header row for a file under the cache, returning its document.

    The row is dated `today`, given the source of that file's header, checked by
    `parse` before anything is written, and then written whole and atomically as
    indented JSON, making the geometry directory if it is not there yet.
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
    atomic.write(target, json.dumps(document, indent=1) + "\n")
    return target


def shipped() -> tuple[Geometry, ...]:
    """Every row of the shipped geometry file, in the order it lists them.

    The file must read as JSON and be a document of `SCHEMA_VERSION` with no
    keys beyond ``schema_version``, ``geometries`` and ``_purpose``, listing its
    rows in a ``geometries`` array. Each row is read by `parse` as shipped, and
    one file at one revision may not appear twice.
    """
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
    """Read the cached rows, then add shipped rows for files the cache lacks.

    The cache documents are read in path order; one that cannot be read or that
    `parse` refuses goes into `skipped` with its reason instead of raising, so
    one bad file does not hide the rest. The first row for a file wins among the
    cache documents, and a cached row stands in front of a shipped row of the
    same file.
    """
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
