"""The deterministic index — the zero-token substrate the cost argument rests on.

Every token the orchestrator spends is justified by *not* having a model read
the whole repository. That only holds if a cheap, model-free pass can shortlist
what matters first. This is that pass: it enumerates the repository's files
(respecting the same ignore rules git does), holds their text for fast search,
and extracts a shallow symbol table — definitions, references, exports, imports —
for the languages the gate already invested grammars in. No model is called
anywhere in this module, by construction: there is nothing here but git, the
standard library, and tree-sitter.

Two guarantees shape the build:

* **It is bounded and reported.** Files past a size cap are skipped rather than
  read, binary files are detected and excluded, and the whole build is timed.
  :class:`BuildStats` carries the numbers so a caller can see what the index
  cost and what it left out — a silent cap would read as "indexed everything".
* **It degrades, never fails, on an unknown language.** A file whose extension
  names no grammar is still enumerated and text-searched; it simply
  contributes no symbols. A repository written entirely in such a language
  yields a text index and an empty symbol table, not an error.

Enumeration goes through ``git ls-files`` because that is where ignore rules
already live: honouring ``.gitignore`` by re-implementing it would be a second,
subtly different matcher, exactly the defect :mod:`mcgyvr.scope` exists to
avoid. The repository is therefore required to be a git checkout — which is what
:func:`mcgyvr.orchestrator.attach` guarantees before an index is ever built.
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

# A file larger than this is skipped, not read. Source files are far smaller;
# a file past a megabyte is a vendored bundle, a data blob or a lockfile, and
# reading it would spend the build's time budget on something no resolver wants
# to point a reader at. The cap is reported, never silent.
DEFAULT_MAX_FILE_BYTES = 1 << 20

# How much of a file to sniff for a NUL byte before deciding it is binary. A
# text file has none; git uses the same "NUL in the first chunk" heuristic.
_BINARY_SNIFF_BYTES = 8192


class IndexBuildError(Exception):
    """The index could not be built (enumeration failed, or the repo is unusable)."""


class SkipReason(StrEnum):
    """Why an enumerated file contributed nothing to the index.

    Every skip is counted and reported on :class:`BuildStats` — a file that was
    listed but not indexed is a hole in the shortlist, and a silent hole reads
    as "there was nothing there".
    """

    LARGE = "large"
    BINARY = "binary"
    GONE = "gone"


@dataclass(frozen=True)
class Match:
    """One text-search hit: a repo-relative path, a 1-based line, and its text."""

    path: str
    line: int
    text: str


@dataclass(frozen=True)
class IndexedFile:
    """A file held in the index: its path, language, and text for search.

    ``lines`` is the decoded content split for line-addressed search. A file
    that was skipped (too large, binary) is not represented here at all — the
    index holds only what it actually indexed.
    """

    path: str
    language: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True)
class FileIndex:
    """One file's whole contribution to the index: its text and its symbols.

    This is the unit the cache (#52) stores and validates, which is what makes
    "a changed file invalidates its own entries and no others" a property of
    the data rather than a rule someone has to remember. ``digest`` identifies
    the exact bytes that produced ``file`` and ``symbols``, so a file that was
    merely touched can be told from one that actually changed.
    """

    file: IndexedFile
    symbols: tuple[Symbol, ...]
    size_bytes: int
    digest: str


@dataclass(frozen=True)
class BuildStats:
    """What the build cost and what it left out — reported, never implied.

    ``languages`` counts indexed files per language name; ``degraded_extensions``
    lists the extensions seen with no grammar, which is the visible face of the
    "text-only fallback" guarantee.
    """

    elapsed_seconds: float
    files_indexed: int
    files_skipped_large: int
    files_skipped_binary: int
    bytes_indexed: int
    symbol_count: int
    languages: Mapping[str, int]
    degraded_extensions: tuple[str, ...]


class SymbolTable:
    """The extracted symbols, bucketed for lookup by name and by kind.

    Built once from a flat symbol list; every query is a dict hit. This is what
    turns "where is ``fetch`` defined" and "who references it" into answers a
    resolver (#48) can rank without reading a file.

    A kind it does not know is held in :meth:`all` and bucketed nowhere: adding
    one is then a question of what it should answer, rather than a silent
    reclassification of it as something else.
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
        """Every place ``name`` is defined, in discovery order."""
        return tuple(self._by_definition.get(name, ()))

    def references(self, name: str) -> tuple[Symbol, ...]:
        """Every place ``name`` is called, in discovery order."""
        return tuple(self._by_reference.get(name, ()))

    def exports(self) -> tuple[Symbol, ...]:
        """Every exported name across the repository, in discovery order."""
        return tuple(self._exports)

    def imports(self, path: str | None = None) -> tuple[Symbol, ...]:
        """Imported names — the whole repository's, or one file's.

        Narrowing by ``path`` is what makes this answer "what does this file
        depend on", which is the question a decomposer asks of a target before
        it names the dependencies a contract carries (ADR-0007).
        """
        if path is None:
            return tuple(self._imports)
        return tuple(symbol for symbol in self._imports if symbol.path == path)


@dataclass(frozen=True)
class Index:
    """A built index of one repository: files, their text, and their symbols.

    Immutable and self-contained — nothing here reaches back to a model or the
    network. Construct with :func:`build_index`.
    """

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
        """Lines across the repository containing ``term``.

        ``term`` is a literal substring by default, or a regular expression when
        ``regex`` is set; ``ignore_case`` folds case either way. ``limit`` caps
        the number of matches returned — a resolver wants a shortlist, not every
        occurrence in a large repository. Results are in file-then-line order.
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
    """Build the index of the git repository at ``root``.

    Enumerates every non-ignored file via git, reads each once (skipping any
    past ``max_file_bytes`` or detected as binary), holds its text for search,
    and extracts its symbols. The build is timed and the numbers are returned on
    :attr:`Index.stats`.

    Every file is read and parsed here, unconditionally. The cached builder in
    :mod:`mcgyvr.orchestrator.cache` reuses this module's per-file primitives to
    skip the work for files that have not changed; both assemble their result
    through :class:`IndexAssembler`, so a cached build and a fresh one cannot
    drift into reporting differently.

    Raises :class:`IndexBuildError` when ``root`` is not a usable git repository —
    the enumerator has no ignore rules to honour without one.
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
    """A short content fingerprint of ``raw``.

    BLAKE2b truncated to 128 bits: not a security boundary, just an identity
    for "these are the same bytes I indexed last time". Truncation keeps the
    cache file small when there is one of these per file.
    """
    return hashlib.blake2b(raw, digest_size=16).hexdigest()


def read_source(
    root: Path, rel: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
) -> bytes | SkipReason:
    """The bytes of ``rel`` under ``root``, or why it will not be indexed.

    Applies the two bounds in one place — the size cap before the read, so an
    oversized file is never pulled into memory, and the binary sniff after —
    so the fresh build and the cached build cannot disagree about what counts
    as indexable. A file git listed but that is gone from disk is a race, not
    an error: it comes back as :attr:`SkipReason.GONE`.
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
    """Index one file's bytes: decode it for search and extract its symbols.

    This is the expensive half of a build — ``ast.parse`` and tree-sitter both
    live behind :func:`~mcgyvr.orchestrator.symbols.extract` — and so it is
    exactly what the cache exists to avoid repeating for an unchanged file.
    """
    language = language_of(rel)
    text = raw.decode("utf-8", "surrogateescape")
    return FileIndex(
        file=IndexedFile(path=rel, language=language, lines=tuple(text.split("\n"))),
        symbols=tuple(extract(rel, raw)),
        size_bytes=len(raw),
        digest=digest_of(raw),
    )


class IndexAssembler:
    """Accumulates per-file results into an :class:`Index`, counting as it goes.

    Both builders assemble through this, so "what the build cost and what it
    left out" is computed once. Timing starts at construction: a cached build
    that reuses everything legitimately reports a near-zero elapsed time, which
    is the number that makes the cache's value visible.
    """

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
        """Fold one indexed file — freshly built or restored from cache — in."""
        if result.file.language is None:
            _record_degraded(result.file.path, self._degraded)
        else:
            self._languages[result.file.language] += 1
        self._files.append(result.file)
        self._symbols.extend(result.symbols)
        self._bytes_indexed += result.size_bytes

    def skipped(self, reason: SkipReason) -> None:
        """Count a file that was enumerated but not indexed."""
        if reason is SkipReason.LARGE:
            self._skipped_large += 1
        elif reason is SkipReason.BINARY:
            self._skipped_binary += 1
        # GONE is a disk race, not a decision the index made; nothing to report.

    def finish(self, root: Path) -> Index:
        """The assembled index, with the stats gathered along the way."""
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
    """Repo-relative paths of every non-ignored file, respecting ignore rules.

    This is never cached. The file list is always re-derived from git, which is
    what makes the cache structurally unable to serve a path that no longer
    exists: a deleted file is absent from this enumeration, so nothing
    downstream ever asks the cache about it (#52).

    ``ls-files --cached --others --exclude-standard`` lists tracked files and
    untracked-but-not-ignored files together, applying ``.gitignore`` and git's
    other exclude sources — the ignore semantics we want, borrowed rather than
    re-implemented. ``-z`` keeps paths verbatim so a name with spaces or
    non-ASCII bytes is never quoted and never silently dropped.
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
        if path not in seen:  # --cached and --others are disjoint, but be safe
            seen.add(path)
            yield path


def _is_binary(raw: bytes) -> bool:
    """Whether ``raw`` looks binary — a NUL byte in the first chunk, as git decides."""
    return b"\x00" in raw[:_BINARY_SNIFF_BYTES]


def _record_degraded(path: str, degraded: set[str]) -> None:
    """Note the extension of an unindexed-language file, for the stats report."""
    suffix = Path(path).suffix
    degraded.add(suffix if suffix else Path(path).name)


def _compile(term: str, *, regex: bool, ignore_case: bool) -> re.Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(term if regex else re.escape(term), flags)
