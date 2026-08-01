"""The deterministic index — the zero-token substrate the cost argument rests on.

Every token the orchestrator spends is justified by *not* having a model read
the whole repository. That only holds if a cheap, model-free pass can shortlist
what matters first. This is that pass: it enumerates the repository's files
(respecting the same ignore rules git does), holds their text for fast search,
and extracts a shallow symbol table — definitions, references, exports — for
the languages the gate already invested grammars in. No model is called
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

import re
import subprocess
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.orchestrator.symbols import Symbol, SymbolKind, extract, language_of

# A file larger than this is skipped, not read. Source files are far smaller;
# a file past a megabyte is a vendored bundle, a data blob or a lockfile, and
# reading it would spend the build's time budget on something no resolver wants
# to point a reader at. The cap is reported, never silent.
_MAX_FILE_BYTES = 1 << 20

# How much of a file to sniff for a NUL byte before deciding it is binary. A
# text file has none; git uses the same "NUL in the first chunk" heuristic.
_BINARY_SNIFF_BYTES = 8192


class IndexBuildError(Exception):
    """The index could not be built (enumeration failed, or the repo is unusable)."""


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
    """

    def __init__(self, symbols: tuple[Symbol, ...]) -> None:
        self._all = symbols
        self._by_definition: dict[str, list[Symbol]] = defaultdict(list)
        self._by_reference: dict[str, list[Symbol]] = defaultdict(list)
        self._exports: list[Symbol] = []
        for symbol in symbols:
            if symbol.kind is SymbolKind.DEFINITION:
                self._by_definition[symbol.name].append(symbol)
            elif symbol.kind is SymbolKind.REFERENCE:
                self._by_reference[symbol.name].append(symbol)
            elif symbol.kind is SymbolKind.EXPORT:
                self._exports.append(symbol)

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


def build_index(root: Path, *, max_file_bytes: int = _MAX_FILE_BYTES) -> Index:
    """Build the index of the git repository at ``root``.

    Enumerates every non-ignored file via git, reads each once (skipping any
    past ``max_file_bytes`` or detected as binary), holds its text for search,
    and extracts its symbols. The build is timed and the numbers are returned on
    :attr:`Index.stats`.

    Raises :class:`IndexBuildError` when ``root`` is not a usable git repository —
    the enumerator has no ignore rules to honour without one.
    """
    started = time.perf_counter()
    files: list[IndexedFile] = []
    symbols: list[Symbol] = []
    skipped_large = 0
    skipped_binary = 0
    bytes_indexed = 0
    languages: dict[str, int] = defaultdict(int)
    degraded: set[str] = set()

    for rel in _enumerate(root):
        absolute = root / rel
        try:
            size = absolute.stat().st_size
        except OSError:
            continue  # listed by git but gone from disk (a race); skip quietly
        if size > max_file_bytes:
            skipped_large += 1
            continue
        try:
            raw = absolute.read_bytes()
        except OSError:
            continue
        if _is_binary(raw):
            skipped_binary += 1
            continue

        language = language_of(rel)
        if language is None:
            _record_degraded(rel, degraded)
        else:
            languages[language] += 1
        text = raw.decode("utf-8", "surrogateescape")
        files.append(
            IndexedFile(path=rel, language=language, lines=tuple(text.split("\n")))
        )
        bytes_indexed += size
        symbols.extend(extract(rel, raw))

    table = SymbolTable(tuple(symbols))
    stats = BuildStats(
        elapsed_seconds=time.perf_counter() - started,
        files_indexed=len(files),
        files_skipped_large=skipped_large,
        files_skipped_binary=skipped_binary,
        bytes_indexed=bytes_indexed,
        symbol_count=len(table),
        languages=dict(languages),
        degraded_extensions=tuple(sorted(degraded)),
    )
    return Index(root=root, files=tuple(files), symbols=table, stats=stats)


def _enumerate(root: Path) -> Iterator[str]:
    """Repo-relative paths of every non-ignored file, respecting ignore rules.

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
