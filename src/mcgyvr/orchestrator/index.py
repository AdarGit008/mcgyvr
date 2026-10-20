"""In-memory index of a repository working tree.

The index lists the files git reports for a root directory, skips oversized and
binary ones, decodes the rest into lines, and extracts their symbols.  A built
:class:`Index` answers symbol lookups through its :class:`SymbolTable` and
line-oriented literal or regex searches through :meth:`Index.search`.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mcgyvr.orchestrator.symbols import Symbol, SymbolKind, extract, language_of

# Files above this many bytes are skipped and counted as LARGE, so that large
# generated or vendored blobs never reach the line and symbol extraction steps.
DEFAULT_MAX_FILE_BYTES = 1 << 20

# Only this leading prefix is scanned for NUL bytes; binary detection is a
# heuristic on the head of the file, not a full read.
_BINARY_SNIFF_BYTES = 8192


class IndexBuildError(Exception):
    """Raised when the file list for a root cannot be obtained from git."""


class SkipReason(StrEnum):
    """Why an enumerated file was left out of the index."""

    LARGE = "large"
    BINARY = "binary"
    GONE = "gone"


@dataclass(frozen=True)
class Match:
    """One matching line: repository-relative path, 1-based line number, text."""

    path: str
    line: int
    text: str


@dataclass(frozen=True)
class IndexedFile:
    """A decoded file: contents split on newlines, and its detected language.

    ``language`` is ``None`` for extensions the symbol extractor does not know.
    """

    path: str
    language: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True)
class FileIndex:
    """Indexing result for a single file: contents, symbols, size and digest."""

    file: IndexedFile
    symbols: tuple[Symbol, ...]
    size_bytes: int
    digest: str


@dataclass(frozen=True)
class BuildStats:
    """Counters and timings gathered while a single index was built.

    ``languages`` maps detected language to the number of files indexed in it.
    ``degraded_extensions`` holds the sorted extensions (or bare file names when
    there is no suffix) of indexed files whose language was unrecognised.
    """

    elapsed_seconds: float
    files_indexed: int
    files_skipped_large: int
    files_skipped_binary: int
    files_skipped_gone: int
    bytes_indexed: int
    symbol_count: int
    languages: Mapping[str, int]
    degraded_extensions: tuple[str, ...]


class SymbolTable:
    """Lookup structure over a fixed tuple of symbols.

    Definitions and references are bucketed by name for fast lookup; exports and
    imports are kept as flat lists in extraction order.
    """

    def __init__(self, symbols: tuple[Symbol, ...]) -> None:
        self._all = symbols
        self._by_definition: dict[str, list[Symbol]] = defaultdict(list)
        self._by_reference: dict[str, list[Symbol]] = defaultdict(list)
        self._exports: list[Symbol] = []
        self._imports: list[Symbol] = []
        for symbol in symbols:
            if symbol.kind is SymbolKind.DEFINITION:
                self._by_definition[symbol.name].append(symbol)
            elif symbol.kind is SymbolKind.REFERENCE:
                self._by_reference[symbol.name].append(symbol)
            elif symbol.kind is SymbolKind.EXPORT:
                self._exports.append(symbol)
            elif symbol.kind is SymbolKind.IMPORT:
                self._imports.append(symbol)

    def __len__(self) -> int:
        return len(self._all)

    def all(self) -> tuple[Symbol, ...]:
        return self._all

    def definitions(self, name: str) -> tuple[Symbol, ...]:
        """Definition symbols named ``name``; empty when there are none."""
        return tuple(self._by_definition.get(name, ()))

    def references(self, name: str) -> tuple[Symbol, ...]:
        """Reference symbols named ``name``; empty when there are none."""
        return tuple(self._by_reference.get(name, ()))

    def exports(self) -> tuple[Symbol, ...]:
        """All export symbols, in extraction order."""
        return tuple(self._exports)

    def imports(self, path: str | None = None) -> tuple[Symbol, ...]:
        """All import symbols, or only those in file ``path`` when given."""
        if path is None:
            return tuple(self._imports)
        return tuple(symbol for symbol in self._imports if symbol.path == path)


@dataclass(frozen=True)
class Index:
    """A built index: the root it came from, its files, symbols and stats."""

    root: Path
    files: tuple[IndexedFile, ...]
    symbols: SymbolTable
    stats: BuildStats

    def search(
        self,
        term: str,
        *,
        regex: bool = False,
        ignore_case: bool = True,
        limit: int | None = None,
    ) -> tuple[Match, ...]:
        """Find indexed lines containing ``term``, in file and line order.

        ``term`` is escaped unless ``regex`` is set.  Scanning stops once
        ``limit`` matches are collected; ``None`` scans every file.
        """
        pattern = _compile(term, regex=regex, ignore_case=ignore_case)
        matches: list[Match] = []
        for file in self.files:
            for number, text in enumerate(file.lines, start=1):
                if pattern.search(text):
                    matches.append(Match(file.path, number, text))
                    if limit is not None and len(matches) >= limit:
                        return tuple(matches)
        return tuple(matches)


def build_index(root: Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> Index:
    """Enumerate, read and index every file git reports for ``root``.

    Files that are too large, binary or unreadable are skipped and only counted
    in the resulting stats.  Raises :class:`IndexBuildError` when enumeration
    fails.
    """
    assembler = IndexAssembler()
    for rel in enumerate_files(root):
        raw = read_source(root, rel, max_file_bytes=max_file_bytes)
        if isinstance(raw, SkipReason):
            assembler.skipped(raw)
            continue
        assembler.add(index_source(rel, raw))
    return assembler.finish(root)


def digest_of(raw: bytes) -> str:
    """Hex blake2b digest (128-bit) of ``raw``, used to fingerprint file bytes."""
    return hashlib.blake2b(raw, digest_size=16).hexdigest()


def read_source(
    root: Path, rel: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
) -> bytes | SkipReason:
    """Read ``rel`` under ``root``, or report why it was skipped.

    Returns LARGE when the file exceeds ``max_file_bytes``, GONE when its size or
    contents cannot be read, and BINARY when the head of the file looks binary.
    """
    absolute = root / rel
    try:
        if absolute.stat().st_size > max_file_bytes:
            return SkipReason.LARGE
        raw = absolute.read_bytes()
    except OSError:
        return SkipReason.GONE
    if _is_binary(raw):
        return SkipReason.BINARY
    return raw


def index_source(rel: str, raw: bytes) -> FileIndex:
    """Build the :class:`FileIndex` for one file's path and raw bytes."""
    language = language_of(rel)
    text = raw.decode("utf-8", "surrogateescape")
    return FileIndex(
        file=IndexedFile(path=rel, language=language, lines=tuple(text.split("\n"))),
        symbols=tuple(extract(rel, raw)),
        size_bytes=len(raw),
        digest=digest_of(raw),
    )


class IndexAssembler:
    """Accumulates per-file results and skip counts until ``finish`` is called."""

    def __init__(self) -> None:
        self._started = time.perf_counter()
        self._files: list[IndexedFile] = []
        self._symbols: list[Symbol] = []
        self._skipped_large = 0
        self._skipped_binary = 0
        self._skipped_gone = 0
        self._bytes_indexed = 0
        self._languages: dict[str, int] = defaultdict(int)
        self._degraded: set[str] = set()

    def add(self, result: FileIndex) -> None:
        """Record one indexed file, counting its language or its degraded kind."""
        if result.file.language is None:
            _record_degraded(result.file.path, self._degraded)
        else:
            self._languages[result.file.language] += 1
        self._files.append(result.file)
        self._symbols.extend(result.symbols)
        self._bytes_indexed += result.size_bytes

    def skipped(self, reason: SkipReason) -> None:
        """Count a skipped file against its reason's counter."""
        if reason is SkipReason.LARGE:
            self._skipped_large += 1
        elif reason is SkipReason.BINARY:
            self._skipped_binary += 1
        elif reason is SkipReason.GONE:
            self._skipped_gone += 1

    def finish(self, root: Path) -> Index:
        """Build the symbol table and stats snapshot and return the frozen index."""
        table = SymbolTable(tuple(self._symbols))
        stats = BuildStats(
            elapsed_seconds=time.perf_counter() - self._started,
            files_indexed=len(self._files),
            files_skipped_large=self._skipped_large,
            files_skipped_binary=self._skipped_binary,
            files_skipped_gone=self._skipped_gone,
            bytes_indexed=self._bytes_indexed,
            symbol_count=len(table),
            languages=dict(self._languages),
            degraded_extensions=tuple(sorted(self._degraded)),
        )
        return Index(root=root, files=tuple(self._files), symbols=table, stats=stats)


def enumerate_files(root: Path) -> Iterator[str]:
    """Yield each git-listed path under ``root`` once, relative to that root.

    Runs ``git ls-files`` for tracked plus untracked-but-not-ignored files, so
    the result honours ``.gitignore``.  Raises :class:`IndexBuildError` when git
    exits non-zero, for example outside a repository.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise IndexBuildError(
            f"cannot enumerate {root}: {detail or 'not a git repository'}"
        )
    seen: set[str] = set()
    for token in proc.stdout.split(b"\x00"):
        if not token:
            continue
        path = token.decode("utf-8", "surrogateescape")
        if path not in seen:  # --cached and --others can both report one path
            seen.add(path)
            yield path


def _is_binary(raw: bytes) -> bool:
    """Heuristic: a NUL byte in the sniffed prefix marks the content binary."""
    return b"\x00" in raw[:_BINARY_SNIFF_BYTES]


def _record_degraded(path: str, degraded: set[str]) -> None:
    """Add the file's extension, or its bare name if it has none, to ``degraded``."""
    suffix = Path(path).suffix
    degraded.add(suffix if suffix else Path(path).name)


def _compile(term: str, *, regex: bool, ignore_case: bool) -> re.Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(term if regex else re.escape(term), flags)
