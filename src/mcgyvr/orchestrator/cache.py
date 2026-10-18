"""A per-repository index cache on disk, so repeat builds skip the parsing.

One JSON file is written per repository, named from the repository directory
plus a hash of its resolved absolute path. It records, for every indexed file,
the size and mtime used to recognise it, a content digest, the decoded lines,
and the extracted symbols.

A later build always re-enumerates the working tree (``git ls-files`` decides
what exists and what is ignored) and then takes the cheapest path per file: an
entry whose size and mtime still match is reused without opening the file at
all; otherwise the bytes are read and hashed, and a matching digest means the
entry is reused with a refreshed stamp; only when both checks fail is the file
parsed again. Files that are gone, binary, or over the size cap are skipped and
left out of the rewritten cache, so their old entries disappear with them.

The cache never carries correctness. A missing, unreadable, malformed,
version-mismatched, root-mismatched, or unwritable file degrades to a full
build and says why in the returned stats, and a build that reads the cache
returns the same index a fresh build would produce.
"""

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

# Bumped whenever the persisted format changes: _load compares the "version"
# recorded inside the file against this number and discards the whole cache on
# any mismatch, so a file written by a build with a different entry layout, key
# set, or symbol encoding is never decoded under the wrong assumptions. Nothing
# migrates between versions, so an equal version is read and anything else is
# rebuilt from the working tree.
CACHE_VERSION = 2

# Budget for the combined size of every cache file in the cache directory, not
# for one repository's file on its own. prune() adds up the .json files it finds
# there and unlinks them oldest-first until the total fits; build_index_cached
# runs that same prune after each successful write, so this one number bounds
# the disk the cache may cost all repositories sharing the area.
DEFAULT_MAX_CACHE_BYTES = 256 << 20

# Sentinel mtime that no real stat produces, so an entry carrying it fails
# _matches and is read back. _derace assigns it to entries not older than the
# build that wrote the cache, whose stamp could hide a same-tick rewrite.
_NO_STAMP = -1


@dataclass(frozen=True)
class CacheStats:
    """What one cache-aware build did, in counts callers can report."""

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
        """Share of enumerated files that avoided parsing: reused plus restamped
        over all three outcomes, and 0.0 when no file was counted at all."""
        total = self.reused + self.restamped + self.rebuilt
        return (self.reused + self.restamped) / total if total else 0.0


@dataclass(frozen=True)
class CachedBuild:
    """The index a cache-aware build assembled, with the stats saying how much
    of it came from the cache and whether it was saved for the next build."""

    index: Index
    cache: CacheStats


@dataclass(frozen=True)
class _Entry:
    """One file's cached state: the stamp that makes the fast path possible, the
    digest that decides whether a re-read needs a reparse, and the parsed result
    itself (language, lines, symbols) ready to be served without touching disk."""

    size: int
    mtime_ns: int
    digest: str
    language: str | None
    lines: tuple[str, ...]
    symbols: tuple[Symbol, ...]

    def as_file_index(self, path: str) -> FileIndex:
        """Rebuild the FileIndex for `path` from this entry. The path is the
        cache key and is not stored with each symbol, so it is stamped onto
        every symbol here; size and digest come from the entry as recorded."""
        return FileIndex(
            file=IndexedFile(path=path, language=self.language, lines=self.lines),
            symbols=tuple(replace(s, path=path) for s in self.symbols),
            size_bytes=self.size,
            digest=self.digest,
        )


def cache_dir() -> Path:
    """The directory holding every cache file: $XDG_CACHE_HOME/mcgyvr/index,
    or ~/.cache/mcgyvr/index when that variable is unset or empty."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "mcgyvr" / "index"


def cache_path(root: Path, *, directory: Path | None = None) -> Path:
    """The JSON file that holds this repository's cache: the repository
    directory name reduced to filesystem-safe characters, plus an 8-byte blake2b
    of the resolved absolute path, so two checkouts with the same basename get
    different files. `directory` overrides the default cache directory."""
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
    """Build the index for `root`, reusing whatever the cache can vouch for.

    Files come from a fresh `enumerate_files` walk every time, so additions,
    deletions, and ignore rules always apply. Each enumerated path is resolved
    by matching its size and mtime against the cached entry (reused, not read),
    else by comparing the digest of its bytes with the cached digest (restamped,
    read but not parsed), else by parsing it (rebuilt). Paths that read as a
    SkipReason are counted as skipped and get no entry, which is how large,
    binary, and vanished files also fall out of the cache.

    The result is written back unless `refresh` was passed or the write fails,
    and a successful write is followed by a prune against `max_cache_bytes`.
    `max_file_bytes` is part of the cache identity: a cache built under a
    different cap is ignored rather than trusted for a different subset of
    files. Cache trouble of any kind is reported in the returned stats instead
    of raised; a failure to enumerate the repository still propagates.
    """
    path = cache_path(root, directory=directory)
    # Recorded before any file is read, so every entry stored by this build has
    # an mtime at or before it. _load gives that number to _derace, which strips
    # the stamp from entries not strictly older than the build that wrote them.
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
            # Gone, binary, or over the cap: counted as a skip and given no entry,
            # so a cached copy of this path does not survive into the rewrite.
            assembler.skipped(raw)
            continue

        # Stat again, since the file may have been rewritten between the first
        # stat and this read; this stamp is the one paired with these bytes. With
        # no stat at all, (len(raw), 0) is stored and matches no real file.
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
            # Loaded entries that did not make it into fresh: the path is no longer
            # enumerated, or it now reads as a skip. A restamped entry is kept in
            # fresh, so a rewritten-but-identical file is not counted as dropped.
            dropped=len(entries.keys() - fresh.keys()),
            written=written,
            # Load reason and write reason joined, when either exists: the first
            # comes from _load (why the cache was not used) and the second from
            # _write (why it was not saved), so an empty note means both worked.
            note="; ".join(part for part in (note, write_note) if part),
        ),
    )


def clear(
    root: Path | None = None, *, directory: Path | None = None
) -> tuple[Path, ...]:
    """Delete cache files and return the ones actually removed. With `root`,
    only that repository's file is a candidate; with no root, every .json file in
    the cache directory goes. Missing or undeletable files are not an error."""
    if root is not None:
        path = cache_path(root, directory=directory)
        return (path,) if _unlink(path) else ()
    return tuple(sorted(p for p in _cache_files(directory) if _unlink(p)))


def prune(
    max_bytes: int = DEFAULT_MAX_CACHE_BYTES, *, directory: Path | None = None
) -> tuple[Path, ...]:
    """Shrink the cache directory to at most `max_bytes` by deleting files, oldest
    mtime first, and return the paths removed. The bound covers all cache files in
    the directory together; files that cannot be stat'ed are left out of the total
    and never removed. A negative bound raises ValueError."""
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
    for _, size, path in sorted(sized):  # oldest mtime first
        if total <= max_bytes:
            break
        if _unlink(path):
            removed.append(path)
            total -= size
    return tuple(removed)


# Reading a stored cache back into entries.


def _load(
    path: Path, *, root: Path, max_file_bytes: int
) -> tuple[dict[str, _Entry], str]:
    """Read the cache at `path` and return its entries keyed by relative path,
    paired with a note saying why it was not used ("" when it was).

    The file is only believed when it parses as a dict whose version, resolved
    root, and size cap all match this build and whose entries decode; anything
    else yields no entries and a note, leaving the caller to rebuild. Decoded
    entries are deraced against the stored build time first."""
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
    """Drop the stamp of an entry whose mtime was not strictly older than the
    build that wrote the cache, since the file could have changed again within
    the same timestamp tick. A stampless entry is always read back instead."""
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
    """Persist `entries` as the cache for `root` at `path`, creating the parent
    directory and replacing the file atomically. Returns whether it was written
    and, when it was not, a note naming the failure; an unwritable cache is never
    an error for the build."""
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
    """Flatten an entry into JSON-ready data: tuples become lists and each symbol
    becomes a positional row of name, kind, line, detail, and signature."""
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
    """Rebuild an entry from the data _encode wrote. Symbols come back with an
    empty path, since the relative path is the cache key and is reattached when
    the entry is turned into a FileIndex; a bad row raises rather than guessing."""
    return _Entry(
        size=int(raw["size"]),
        mtime_ns=int(raw["mtime_ns"]),
        digest=str(raw["digest"]),
        language=None if raw["language"] is None else str(raw["language"]),
        lines=tuple(str(line) for line in raw["lines"]),
        symbols=tuple(
            # Path left blank on purpose: the key restores it, not the file.
            Symbol(str(name), SymbolKind(kind), "", int(line), str(detail), str(sig))
            for name, kind, line, detail, sig in raw["symbols"]
        ),
    )


# Comparing stored entries against what the working tree holds now.


def _stamp(absolute: Path) -> tuple[int, int] | None:
    """The (size, mtime_ns) pair used to recognise a file without reading it, or
    None when it cannot be stat'ed (deleted, unreadable) and must be read."""
    try:
        stat = absolute.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _matches(entry: _Entry, stamp: tuple[int, int]) -> bool:
    """Whether an entry's recorded size and mtime are exactly the current ones,
    which is what allows the file to be served without being opened."""
    return (entry.size, entry.mtime_ns) == stamp


def _cache_files(directory: Path | None) -> tuple[Path, ...]:
    """Every regular .json file in the cache directory (`directory` or the
    default one), or nothing if the directory cannot be listed."""
    target = directory or cache_dir()
    try:
        return tuple(p for p in target.iterdir() if p.is_file() and p.suffix == ".json")
    except OSError:
        return ()


def _unlink(path: Path) -> bool:
    """Delete a cache file and report whether it actually went away; a missing or
    undeletable file is reported as False rather than raising."""
    try:
        path.unlink()
    except OSError:
        return False
    return True
