""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from mcgyvr.orchestrator.context import VerifiedContext
from mcgyvr.orchestrator.index import Index, IndexedFile
from mcgyvr.orchestrator.resolve import (
    Candidate,
    Resolution,
    _content_tokens,
    _tokenize,
)
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind

#on
#
#
_DEFAULT_BUDGET = 2000

#
#
_DEFAULT_CONTEXT = 25
_LEAD = 3

#
#
#
_MAX_TEXT_ANCHORS = 5

#
#
#
#
_ANCHOR_KINDS = frozenset({SymbolKind.DEFINITION, SymbolKind.EXPORT})


class ExplorationError(Exception):
    ""


@dataclass(frozen=True)
class TargetedRead:
    ""

    path: str
    start: int
    end: int
    text: str
    reason: str
    candidate_rank: int
    estimated_tokens: int
    supplied: bool = False


@dataclass(frozen=True)
class Deferral:
    ""

    path: str
    start: int
    end: int
    reason: str
    candidate_rank: int
    estimated_tokens: int


@dataclass(frozen=True)
class Exploration:
    ""

    query: str
    budget: int
    spent: int
    reads: tuple[TargetedRead, ...]
    deferred: tuple[Deferral, ...]
    exhausted: bool
    saved: int = 0

    @property
    def complete(self) -> bool:
        ""
        return not self.exhausted


@dataclass(frozen=True)
class _Region:
    ""

    path: str
    start: int
    end: int
    reason: str
    candidate_rank: int


def explore(
    index: Index,
    resolution: Resolution,
    *,
    budget: int = _DEFAULT_BUDGET,
    context: int = _DEFAULT_CONTEXT,
    estimate: Callable[[str], int] | None = None,
    supplied: VerifiedContext | None = None,
) -> Exploration:
    ""
    if budget <= 0:
        raise ExplorationError(f"exploration budget must be positive, got {budget}")
    tokens = estimate if estimate is not None else estimate_tokens
    free = supplied.fresh if supplied is not None else frozenset()

    files = {file.path: file for file in index.files}
    query_tokens = frozenset(_content_tokens(resolution.query))
    regions = _plan_regions(resolution.candidates, index, files, query_tokens, context)

    reads: list[TargetedRead] = []
    deferred: list[Deferral] = []
    spent = 0
    saved = 0
    stopped = False
    for region in regions:
        text = _slice(files[region.path], region.start, region.end)
        cost = tokens(text)
        #en
        #
        #
        #
        held = region.path in free
        #
        #
        #
        #t.
        if held or (not stopped and spent + cost <= budget):
            if held:
                saved += cost
            else:
                spent += cost
            reads.append(
                TargetedRead(
                    path=region.path,
                    start=region.start,
                    end=region.end,
                    text=text,
                    reason=region.reason,
                    candidate_rank=region.candidate_rank,
                    estimated_tokens=cost,
                    supplied=held,
                )
            )
        else:
            stopped = True
            deferred.append(
                Deferral(
                    path=region.path,
                    start=region.start,
                    end=region.end,
                    reason=region.reason,
                    candidate_rank=region.candidate_rank,
                    estimated_tokens=cost,
                )
            )

    return Exploration(
        query=resolution.query,
        budget=budget,
        spent=spent,
        reads=tuple(reads),
        deferred=tuple(deferred),
        exhausted=bool(deferred),
        saved=saved,
    )


#


def _plan_regions(
    candidates: tuple[Candidate, ...],
    index: Index,
    files: dict[str, IndexedFile],
    query_tokens: frozenset[str],
    context: int,
) -> list[_Region]:
    ""
    symbols_by_path: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in index.symbols.all():
        if symbol.kind in _ANCHOR_KINDS:
            symbols_by_path[symbol.path].append(symbol)

    regions: list[_Region] = []
    for rank, candidate in enumerate(candidates, start=1):
        file = files.get(candidate.path)
        if file is None:  #
            continue
        anchors = _anchors(symbols_by_path[candidate.path], file, query_tokens)
        for start, end, reason in _windows(anchors, len(file.lines), context):
            regions.append(_Region(candidate.path, start, end, reason, rank))
    return regions


def _anchors(
    symbols: list[Symbol],
    file: IndexedFile,
    query_tokens: frozenset[str],
) -> list[tuple[int, str]]:
    ""
    anchors: list[tuple[int, str]] = []
    seen_lines: set[int] = set()

    for symbol in symbols:
        if (
            query_tokens & set(_name_tokens(symbol.name))
            and symbol.line not in seen_lines
        ):
            detail = f" ({symbol.detail})" if symbol.detail else ""
            anchors.append((symbol.line, f"defines {symbol.name}{detail}"))
            seen_lines.add(symbol.line)

    text_hits = 0
    for number, line in enumerate(file.lines, start=1):
        if text_hits >= _MAX_TEXT_ANCHORS:
            break
        if number in seen_lines:
            continue
        hit = _first_token_in(line, query_tokens)
        if hit is not None:
            anchors.append((number, f"match {hit!r}"))
            seen_lines.add(number)
            text_hits += 1

    if not anchors:
        anchors.append((1, "file head"))
    return anchors


def _windows(
    anchors: list[tuple[int, str]],
    total_lines: int,
    context: int,
) -> list[tuple[int, int, str]]:
    ""
    spans = sorted(
        (
            max(1, line - _LEAD),
            min(total_lines, max(1, line - _LEAD) + context - 1),
            reason,
        )
        for line, reason in anchors
    )
    merged: list[tuple[int, int, list[str]]] = []
    for start, end, reason in spans:
        if merged and start <= merged[-1][1] + 1:
            prev_start, prev_end, reasons = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end), [*reasons, reason])
        else:
            merged.append((start, end, [reason]))
    return [(start, end, "; ".join(_unique(reasons))) for start, end, reasons in merged]


#


def _slice(file: IndexedFile, start: int, end: int) -> str:
    ""
    return "\n".join(file.lines[start - 1 : end])


def _unique(items: list[str]) -> list[str]:
    ""
    return list(dict.fromkeys(items))


def estimate_tokens(text: str) -> int:
    ""
    return max(1, (len(text) + 3) // 4)


def _name_tokens(name: str) -> list[str]:
    ""
    return _tokenize(name)


def _first_token_in(line: str, query_tokens: frozenset[str]) -> str | None:
    ""
    line_tokens = set(_name_tokens(line))
    for token in sorted(query_tokens):
        if token in line_tokens:
            return token
    return None
