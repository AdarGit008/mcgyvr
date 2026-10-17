""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from mcgyvr import atomic
from mcgyvr.orchestrator.index import (
    DEFAULT_MAX_FILE_BYTES,
    FileIndex,
    Index,
    IndexAssembler,
    IndexedFile,
    SkipReason,
    digest_of,
    enumerate_files,
    index_source,
    read_source,
)
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind

#
#on
#
#
#
#
CACHE_VERSION = 2

#
#
#
#
#
DEFAULT_MAX_CACHE_BYTES = 256 << 20

#
#
#
_NO_STAMP = -1


@dataclass(frozen=True)
class CacheStats:
    ""

    path: Path
    """The cache file for this repository, whether or not it existed."""

    loaded: bool
    """Whether a usable cache was found and read for this build."""

    reused: int
    """Files served from cache without being opened."""

    restamped: int
    """Files read but not reparsed — content identical, stamp refreshed."""

    rebuilt: int
    """Files read and parsed: new, changed, or absent from the cache."""

    dropped: int
    """Cached entries discarded because the file is gone or no longer indexable."""

    written: bool
    """Whether this build's result was persisted for the next one."""

    note: str = ""
    """Why the cache was not loaded or not written, when that happened."""

    @property
    def hit_ratio(self) -> float:
        ""
        total = self.reused + self.restamped + self.rebuilt
        return (self.reused + self.restamped) / total if total else 0.0


@dataclass(frozen=True)
class CachedBuild:
    ""

    index: Index
    cache: CacheStats


@dataclass(frozen=True)
class _Entry:
    ""

    size: int
    mtime_ns: int
    digest: str
    language: str | None
    lines: tuple[str, ...]
    symbols: tuple[Symbol, ...]

    def as_file_index(self, path: str) -> FileIndex:
        ""
        return FileIndex(
            file=IndexedFile(path=path, language=self.language, lines=self.lines),
            symbols=tuple(replace(s, path=path) for s in self.symbols),
            size_bytes=self.size,
            digest=self.digest,
        )


def cache_dir() -> Path:
    ""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "mcgyvr" / "index"


def cache_path(root: Path, *, directory: Path | None = None) -> Path:
    ""
    absolute = root.resolve()
    stamp = hashlib.blake2b(
        str(absolute).encode("utf-8", "surrogateescape"), digest_size=8
    ).hexdigest()
    name = re.sub(r"[^A-Za-z0-9._-]", "-", absolute.name) or "repo"
    return (directory or cache_dir()) / f"{name}-{stamp}.json"


def build_index_cached(
    root: Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    directory: Path | None = None,
    max_cache_bytes: int = DEFAULT_MAX_CACHE_BYTES,
    refresh: bool = False,
) -> CachedBuild:
    ""
    path = cache_path(root, directory=directory)
    #
    #
    #
    built_ns = time.time_ns()
    entries: dict[str, _Entry] = {}
    note = ""
    loaded = False
    if refresh:
        note = "refresh requested — cache ignored"
    else:
        entries, note = _load(path, root=root, max_file_bytes=max_file_bytes)
        loaded = not note

    assembler = IndexAssembler()
    fresh: dict[str, _Entry] = {}
    reused = restamped = rebuilt = 0

    for rel in enumerate_files(root):
        cached = entries.get(rel)
        stamp = _stamp(root / rel)

        if cached is not None and stamp is not None and _matches(cached, stamp):
            assembler.add(cached.as_file_index(rel))
            fresh[rel] = cached
            reused += 1
            continue

        raw = read_source(root, rel, max_file_bytes=max_file_bytes)
        if isinstance(raw, SkipReason):
            #
            #
            assembler.skipped(raw)
            continue

        #
        #
        #
        stamp = _stamp(root / rel) or stamp
        size, mtime_ns = stamp if stamp is not None else (len(raw), 0)
        content = digest_of(raw)

        if cached is not None and cached.digest == content:
            entry = replace(cached, size=size, mtime_ns=mtime_ns)
            assembler.add(entry.as_file_index(rel))
            fresh[rel] = entry
            restamped += 1
            continue

        result = index_source(rel, raw)
        assembler.add(result)
        fresh[rel] = _Entry(
            size=size,
            mtime_ns=mtime_ns,
            digest=result.digest,
            language=result.file.language,
            lines=result.file.lines,
            symbols=result.symbols,
        )
        rebuilt += 1

    index = assembler.finish(root)
    written, write_note = _write(
        path,
        root=root,
        max_file_bytes=max_file_bytes,
        entries=fresh,
        built_ns=built_ns,
    )
    if written:
        prune(max_cache_bytes, directory=directory)

    return CachedBuild(
        index=index,
        cache=CacheStats(
            path=path,
            loaded=loaded,
            reused=reused,
            restamped=restamped,
            rebuilt=rebuilt,
            #
            #
            #
            dropped=len(entries.keys() - fresh.keys()),
            written=written,
            #is
            #
            #
            note="; ".join(part for part in (note, write_note) if part),
        ),
    )


def clear(
    root: Path | None = None, *, directory: Path | None = None
) -> tuple[Path, ...]:
    ""
    if root is not None:
        path = cache_path(root, directory=directory)
        return (path,) if _unlink(path) else ()
    return tuple(sorted(p for p in _cache_files(directory) if _unlink(p)))


def prune(
    max_bytes: int = DEFAULT_MAX_CACHE_BYTES, *, directory: Path | None = None
) -> tuple[Path, ...]:
    ""
    if max_bytes < 0:
        raise ValueError("max_bytes cannot be negative")
    sized: list[tuple[float, int, Path]] = []
    for path in _cache_files(directory):
        try:
            stat = path.stat()
        except OSError:
            continue
        sized.append((stat.st_mtime, stat.st_size, path))

    total = sum(size for _, size, _ in sized)
    removed: list[Path] = []
    for _, size, path in sorted(sized):  #
        if total <= max_bytes:
            break
        if _unlink(path):
            removed.append(path)
            total -= size
    return tuple(removed)


#


def _load(
    path: Path, *, root: Path, max_file_bytes: int
) -> tuple[dict[str, _Entry], str]:
    ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "no cache yet"
    except (OSError, ValueError) as exc:
        return {}, f"cache unreadable ({type(exc).__name__}) — rebuilding"

    if not isinstance(raw, dict):
        return {}, "cache malformed — rebuilding"
    if raw.get("version") != CACHE_VERSION:
        return {}, f"cache version {raw.get('version')!r} — rebuilding"
    if raw.get("root") != str(root.resolve()):
        return {}, "cache belongs to another repository — rebuilding"
    if raw.get("max_file_bytes") != max_file_bytes:
        return {}, "cache built under a different size cap — rebuilding"

    stored = raw.get("entries")
    if not isinstance(stored, dict):
        return {}, "cache malformed — rebuilding"
    try:
        built_ns = int(raw["built_ns"])
        entries = {str(k): _decode(v) for k, v in stored.items()}
    except (KeyError, TypeError, ValueError):
        return {}, "cache entries malformed — rebuilding"
    return {rel: _derace(entry, built_ns) for rel, entry in entries.items()}, ""


def _derace(entry: _Entry, built_ns: int) -> _Entry:
    ""
    if entry.mtime_ns < built_ns:
        return entry
    return replace(entry, mtime_ns=_NO_STAMP)


def _write(
    path: Path,
    *,
    root: Path,
    max_file_bytes: int,
    entries: dict[str, _Entry],
    built_ns: int,
) -> tuple[bool, str]:
    ""
    payload = {
        "version": CACHE_VERSION,
        "root": str(root.resolve()),
        "max_file_bytes": max_file_bytes,
        "built_ns": built_ns,
        "entries": {rel: _encode(entry) for rel, entry in entries.items()},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic.write(path, json.dumps(payload))
    except OSError as exc:
        return False, f"cache not written ({type(exc).__name__})"
    return True, ""


def _encode(entry: _Entry) -> dict[str, Any]:
    ""
    return {
        "size": entry.size,
        "mtime_ns": entry.mtime_ns,
        "digest": entry.digest,
        "language": entry.language,
        "lines": list(entry.lines),
        "symbols": [
            [s.name, str(s.kind), s.line, s.detail, s.signature] for s in entry.symbols
        ],
    }


def _decode(raw: Any) -> _Entry:
    ""
    return _Entry(
        size=int(raw["size"]),
        mtime_ns=int(raw["mtime_ns"]),
        digest=str(raw["digest"]),
        language=None if raw["language"] is None else str(raw["language"]),
        lines=tuple(str(line) for line in raw["lines"]),
        symbols=tuple(
            #
            Symbol(str(name), SymbolKind(kind), "", int(line), str(detail), str(sig))
            for name, kind, line, detail, sig in raw["symbols"]
        ),
    )


#


def _stamp(absolute: Path) -> tuple[int, int] | None:
    ""
    try:
        stat = absolute.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _matches(entry: _Entry, stamp: tuple[int, int]) -> bool:
    ""
    return (entry.size, entry.mtime_ns) == stamp


def _cache_files(directory: Path | None) -> tuple[Path, ...]:
    ""
    target = directory or cache_dir()
    try:
        return tuple(p for p in target.iterdir() if p.is_file() and p.suffix == ".json")
    except OSError:
        return ()


def _unlink(path: Path) -> bool:
    ""
    try:
        path.unlink()
    except OSError:
        return False
    return True
