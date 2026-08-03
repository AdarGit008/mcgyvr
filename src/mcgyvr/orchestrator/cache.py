"""The index cache — exploration cost amortized across tasks (#52).

Building the index is cheap next to a model reading a repository, but it is not
free: every file is read, decoded and parsed. Paying that on every task throws
away work that was valid the moment it finished, because between two tasks on
the same repository almost nothing has changed. This module persists a build
and reuses the parts of it that still hold.

Three properties shape the design, and each is structural rather than a rule
someone has to remember:

* **The file list is never cached.** Every build re-enumerates through
  :func:`~mcgyvr.orchestrator.index.enumerate_files`, and only per-file content
  is looked up. A deleted path is therefore absent from the enumeration and
  nothing ever asks the cache about it — a stale index *cannot* serve a file
  that no longer exists, rather than merely being expected not to.
* **Invalidation is per file.** Each entry carries its own validity stamp, so a
  change to one file rebuilds that file and leaves every other entry standing.
  There is no whole-index generation number to invalidate the world.
* **The cache is an accelerator, never load-bearing.** Every failure to read,
  parse or write it degrades to a full build. A corrupt or unreadable cache
  makes a task slower; it can never make it wrong, and it can never make it
  fail.

Validity is decided in two steps, cheapest first. A file whose size and
modification time match the stamp is reused without being opened at all — the
fast path that makes a second task on an unchanged repository skip essentially
all of the build. A file whose stamp moved is read and fingerprinted; if the
content is identical the indexed result is reused anyway and only the stamp is
refreshed, so a checkout that rewrites mtimes without changing bytes does not
force a reparse. Only genuinely new content is parsed again.
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

# The on-disk format's version. Bump this whenever what a cached entry means
# changes — a new field, a different stamp, or any change to symbol extraction
# that would make yesterday's symbols wrong for today's code. A mismatched
# version is discarded wholesale rather than migrated: the cache is
# reconstructible from the repository, so rebuilding is always cheaper than
# being subtly wrong about what a stale entry contains.
CACHE_VERSION = 2

# Bound on how much disk the cache may occupy across all repositories. Beyond
# it, whole repository caches are evicted least-recently-used first. A default,
# not a law: a real ceiling belongs in config, and this is only what an
# unconfigured install falls back to. Evicting only ever costs a rebuild, so an
# over-eager bound is a performance choice, never a correctness one.
DEFAULT_MAX_CACHE_BYTES = 256 << 20

# A modification time no real file can carry, used to mark an entry whose stamp
# must not be trusted. It compares unequal to every genuine stat, so the entry
# falls through to content validation without needing a second field to check.
_NO_STAMP = -1


@dataclass(frozen=True)
class CacheStats:
    """What the cache did for one build — reported so its value is visible.

    A cache that silently does nothing looks exactly like a cache that works,
    which is why these numbers are returned rather than logged. ``reused`` is
    the fast path (stamp matched, file never opened), ``restamped`` counts
    files that were read but whose content was unchanged, and ``rebuilt`` is
    the work that actually had to happen.
    """

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
        """Share of indexed files that cost no parsing this build."""
        total = self.reused + self.restamped + self.rebuilt
        return (self.reused + self.restamped) / total if total else 0.0


@dataclass(frozen=True)
class CachedBuild:
    """An index plus the account of how much of it came from cache."""

    index: Index
    cache: CacheStats


@dataclass(frozen=True)
class _Entry:
    """One file's cached index content, with the stamp that validates it."""

    size: int
    mtime_ns: int
    digest: str
    language: str | None
    lines: tuple[str, ...]
    symbols: tuple[Symbol, ...]

    def as_file_index(self, path: str) -> FileIndex:
        """Rebuild the in-memory result this entry stands for.

        ``path`` comes from the caller because it is the cache's key — storing
        it in the value too would let the two disagree.
        """
        return FileIndex(
            file=IndexedFile(path=path, language=self.language, lines=self.lines),
            symbols=tuple(replace(s, path=path) for s in self.symbols),
            size_bytes=self.size,
            digest=self.digest,
        )


def cache_dir() -> Path:
    """Where index caches live: ``$XDG_CACHE_HOME/mcgyvr/index``.

    Follows the same resolution :func:`mcgyvr.config.config_path` uses for
    config, one directory over — cached data is regenerable and belongs under
    the cache root, not beside the user's settings.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "mcgyvr" / "index"


def cache_path(root: Path, *, directory: Path | None = None) -> Path:
    """The cache file for the repository at ``root``.

    Keyed by the absolute path, not the repository name: two worktrees of the
    same repository are different working trees at different revisions, and
    sharing one cache between them would hand each the other's files. The
    readable prefix is there so the directory can be understood by looking at
    it; the hash is what actually distinguishes.
    """
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
    """Build the index of ``root``, reusing everything that has not changed.

    Behaves exactly like :func:`~mcgyvr.orchestrator.index.build_index` — same
    enumeration, same bounds, same resulting :class:`Index` — but reads each
    file's text and symbols from the previous build when the file is unchanged.
    The result is persisted for the next call, and the cache directory is pruned
    to ``max_cache_bytes`` afterwards.

    ``refresh`` ignores any existing cache and rebuilds from source, then writes
    the fresh result. It is the escape hatch for the one thing a content stamp
    cannot see: a change in what indexing a file *means*, such as an upgraded
    grammar. Routine correctness does not depend on it.

    Raises :class:`~mcgyvr.orchestrator.index.IndexBuildError` when ``root`` is
    not a usable git repository, exactly as the uncached build does. No cache
    failure is ever raised: an unreadable or unwritable cache degrades to a
    full build and is reported on :attr:`CachedBuild.cache`.
    """
    path = cache_path(root, directory=directory)
    # Captured before the first stat: any file whose recorded mtime is at or
    # after this could have been modified after we looked at it, and its stamp
    # is not evidence of anything. See _load, which distrusts exactly those.
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
            # No entry is recorded, so a file that grew past the cap or turned
            # binary drops out of the cache rather than lingering as a ghost.
            assembler.skipped(raw)
            continue

        # Re-stamp from after the read: a file written between the stat above
        # and the read here would otherwise be recorded under the older stamp
        # and never re-read. Losing the fast path once is the safe direction.
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
            # Entries the new cache does not carry forward: the file was
            # deleted, ignored, or is no longer indexable. A file that was
            # merely rebuilt is still an entry, so it is not a drop.
            dropped=len(entries.keys() - fresh.keys()),
            written=written,
            # Both halves can fail independently — an unreadable cache that is
            # also unwritable is two different things to fix, so report both
            # rather than letting the first one mask the second.
            note="; ".join(part for part in (note, write_note) if part),
        ),
    )


def clear(
    root: Path | None = None, *, directory: Path | None = None
) -> tuple[Path, ...]:
    """Remove cached indexes — one repository's, or all of them.

    The documented way to reset, for when a cache is suspected rather than
    proven wrong. Returns what was removed. Scoped to mcgyvr's own cache
    directory and its own file naming, so it can never reach a file it did not
    write.
    """
    if root is not None:
        path = cache_path(root, directory=directory)
        return (path,) if _unlink(path) else ()
    return tuple(sorted(p for p in _cache_files(directory) if _unlink(p)))


def prune(
    max_bytes: int = DEFAULT_MAX_CACHE_BYTES, *, directory: Path | None = None
) -> tuple[Path, ...]:
    """Evict whole repository caches until the directory fits ``max_bytes``.

    Least-recently-used first, where "used" is the file's modification time —
    every build rewrites its own cache, so that is exactly the last time the
    repository was indexed. Eviction is per repository rather than per entry:
    a half-evicted repository would be indistinguishable from one whose files
    all changed, and would cost the same rebuild anyway.
    """
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
    for _, size, path in sorted(sized):  # oldest first
        if total <= max_bytes:
            break
        if _unlink(path):
            removed.append(path)
            total -= size
    return tuple(removed)


# --- persistence ---------------------------------------------------------


def _load(
    path: Path, *, root: Path, max_file_bytes: int
) -> tuple[dict[str, _Entry], str]:
    """Read a cache file, or explain why it cannot be used.

    Every rejection returns empty entries and a note rather than raising. The
    checks beyond "does it parse" are the ones that would otherwise serve
    plausible-looking wrong answers: a different format version, a cache
    written for a different repository, or one built under a different size cap
    (whose skipped files are missing for a reason that no longer applies).
    """
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
    """Strip the stamp from an entry that could have changed under the build.

    A file modified in the same clock tick it was read keeps the modification
    time we recorded, so on a filesystem with coarse timestamp granularity its
    stamp would still "match" while its content had moved on. Git calls these
    entries racily clean and rechecks their content; so does this. Blanking the
    stamp forces the read-and-fingerprint path, which still avoids reparsing
    when the content really is unchanged — the cost of the guard is one read,
    and never a wrong answer.
    """
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
    """Persist entries atomically. Returns whether it happened, and why not.

    The write goes to a temporary file in the same directory and is renamed
    into place, so a reader — another lane indexing the same repository — sees
    either the old cache or the new one, never a half-written one. Failing to
    write is not an error: the build already succeeded, and the only cost is
    that the next one pays full price.
    """
    payload = {
        "version": CACHE_VERSION,
        "root": str(root.resolve()),
        "max_file_bytes": max_file_bytes,
        "built_ns": built_ns,
        "entries": {rel: _encode(entry) for rel, entry in entries.items()},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        return False, f"cache not written ({type(exc).__name__})"
    return True, ""


def _encode(entry: _Entry) -> dict[str, Any]:
    """One entry as JSON. Symbols are positional and carry no path.

    A symbol's path is always its entry's key, so storing it per symbol would
    repeat the path once per occurrence — the single largest avoidable cost in
    a file this shape. Positional tuples over objects for the same reason.
    """
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
    """One entry from JSON, strictly — a malformed field raises, never guesses.

    The caller turns any raise into "rebuild this repository", so being strict
    here costs a rebuild and buys the guarantee that a mangled cache cannot
    become a mangled index.
    """
    return _Entry(
        size=int(raw["size"]),
        mtime_ns=int(raw["mtime_ns"]),
        digest=str(raw["digest"]),
        language=None if raw["language"] is None else str(raw["language"]),
        lines=tuple(str(line) for line in raw["lines"]),
        symbols=tuple(
            # The path is filled in from the cache key by _Entry.as_file_index.
            Symbol(str(name), SymbolKind(kind), "", int(line), str(detail), str(sig))
            for name, kind, line, detail, sig in raw["symbols"]
        ),
    )


# --- helpers -------------------------------------------------------------


def _stamp(absolute: Path) -> tuple[int, int] | None:
    """A file's ``(size, mtime_ns)``, or None if it cannot be stat'd."""
    try:
        stat = absolute.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _matches(entry: _Entry, stamp: tuple[int, int]) -> bool:
    """Whether a stamp says the file is byte-identical to what was indexed."""
    return (entry.size, entry.mtime_ns) == stamp


def _cache_files(directory: Path | None) -> tuple[Path, ...]:
    """Every cache file in the directory, ignoring anything else living there."""
    target = directory or cache_dir()
    try:
        return tuple(p for p in target.iterdir() if p.is_file() and p.suffix == ".json")
    except OSError:
        return ()


def _unlink(path: Path) -> bool:
    """Remove ``path``, reporting whether it was there to remove."""
    try:
        path.unlink()
    except OSError:
        return False
    return True
