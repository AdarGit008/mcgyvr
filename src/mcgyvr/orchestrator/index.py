""

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

#
#
#
#
DEFAULT_MAX_FILE_BYTES = 1 << 20

#
#
_BINARY_SNIFF_BYTES = 8192


class IndexBuildError(Exception):
    ""


class SkipReason(StrEnum):
    ""

    LARGE = "large"
    BINARY = "binary"
    GONE = "gone"


@dataclass(frozen=True)
class Match:
    ""

    path: str
    line: int
    text: str


@dataclass(frozen=True)
class IndexedFile:
    ""

    path: str
    language: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True)
class FileIndex:
    ""

    file: IndexedFile
    symbols: tuple[Symbol, ...]
    size_bytes: int
    digest: str


@dataclass(frozen=True)
class BuildStats:
    ""

    elapsed_seconds: float
    files_indexed: int
    files_skipped_large: int
    files_skipped_binary: int
    bytes_indexed: int
    symbol_count: int
    languages: Mapping[str, int]
    degraded_extensions: tuple[str, ...]


class SymbolTable:
    ""

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
        ""
        return tuple(self._by_definition.get(name, ()))

    def references(self, name: str) -> tuple[Symbol, ...]:
        ""
        return tuple(self._by_reference.get(name, ()))

    def exports(self) -> tuple[Symbol, ...]:
        ""
        return tuple(self._exports)

    def imports(self, path: str | None = None) -> tuple[Symbol, ...]:
        ""
        if path is None:
            return tuple(self._imports)
        return tuple(symbol for symbol in self._imports if symbol.path == path)


@dataclass(frozen=True)
class Index:
    ""

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
        ""
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
    ""
    assembler = IndexAssembler()
    for rel in enumerate_files(root):
        raw = read_source(root, rel, max_file_bytes=max_file_bytes)
        if isinstance(raw, SkipReason):
            assembler.skipped(raw)
            continue
        assembler.add(index_source(rel, raw))
    return assembler.finish(root)


def digest_of(raw: bytes) -> str:
    ""
    return hashlib.blake2b(raw, digest_size=16).hexdigest()


def read_source(
    root: Path, rel: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
) -> bytes | SkipReason:
    ""
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
    ""
    language = language_of(rel)
    text = raw.decode("utf-8", "surrogateescape")
    return FileIndex(
        file=IndexedFile(path=rel, language=language, lines=tuple(text.split("\n"))),
        symbols=tuple(extract(rel, raw)),
        size_bytes=len(raw),
        digest=digest_of(raw),
    )


class IndexAssembler:
    ""

    def __init__(self) -> None:
        self._started = time.perf_counter()
        self._files: list[IndexedFile] = []
        self._symbols: list[Symbol] = []
        self._skipped_large = 0
        self._skipped_binary = 0
        self._bytes_indexed = 0
        self._languages: dict[str, int] = defaultdict(int)
        self._degraded: set[str] = set()

    def add(self, result: FileIndex) -> None:
        ""
        if result.file.language is None:
            _record_degraded(result.file.path, self._degraded)
        else:
            self._languages[result.file.language] += 1
        self._files.append(result.file)
        self._symbols.extend(result.symbols)
        self._bytes_indexed += result.size_bytes

    def skipped(self, reason: SkipReason) -> None:
        ""
        if reason is SkipReason.LARGE:
            self._skipped_large += 1
        elif reason is SkipReason.BINARY:
            self._skipped_binary += 1
        #

    def finish(self, root: Path) -> Index:
        ""
        table = SymbolTable(tuple(self._symbols))
        stats = BuildStats(
            elapsed_seconds=time.perf_counter() - self._started,
            files_indexed=len(self._files),
            files_skipped_large=self._skipped_large,
            files_skipped_binary=self._skipped_binary,
            bytes_indexed=self._bytes_indexed,
            symbol_count=len(table),
            languages=dict(self._languages),
            degraded_extensions=tuple(sorted(self._degraded)),
        )
        return Index(root=root, files=tuple(self._files), symbols=table, stats=stats)


def enumerate_files(root: Path) -> Iterator[str]:
    ""
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
        if path not in seen:  #
            seen.add(path)
            yield path


def _is_binary(raw: bytes) -> bool:
    ""
    return b"\x00" in raw[:_BINARY_SNIFF_BYTES]


def _record_degraded(path: str, degraded: set[str]) -> None:
    ""
    suffix = Path(path).suffix
    degraded.add(suffix if suffix else Path(path).name)


def _compile(term: str, *, regex: bool, ignore_case: bool) -> re.Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(term if regex else re.escape(term), flags)
