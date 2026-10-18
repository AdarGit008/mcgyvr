"""Turn a resolution into a bounded set of excerpts worth reading.

`explore` walks the resolution's candidates in rank order, turns each one into
line windows around its anchors (see `_plan_regions`), and charges every
window's estimated token cost to a budget. Windows that fit become
`TargetedRead`s. The first window that would overrun the budget stops the plan:
it and every later charged region are recorded as `Deferral`s, so
`Exploration.exhausted` announces a partial plan instead of hiding one. Regions
whose text the caller already supplied verbatim (`VerifiedContext.fresh`) are
planned and reported like any other, but they cost nothing — their estimated
cost is summed into `Exploration.saved` instead of `Exploration.spent`, which is
what lets the same budget reach further.

Nothing here re-ranks: supplied context changes what a plan costs, never which
candidates or line regions it covers.
"""

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

# Default ceiling on an exploration's estimated token spend. It only bounds a plan
# when the caller states nothing better; a caller that knows its real context
# window passes `budget` explicitly, and no region is read once it would overrun.
_DEFAULT_BUDGET = 2000

# Window sizing: a region spans `context` lines, starting `_LEAD` lines above its
# anchor, so a definition keeps the few lines that precede it.
_DEFAULT_CONTEXT = 25
_LEAD = 3

# Cap on query-word text anchors per file, so one long file whose lines happen to
# repeat the query cannot fill the plan on its own. Symbol anchors are not capped:
# a matched definition is already a bounded, meaningful site.
_MAX_TEXT_ANCHORS = 5

# Symbol kinds worth reading at their site. A definition or an export is code the
# caller can act on, so it anchors a region; imports and references only point
# elsewhere and are left out of anchoring, which is why a file without either
# falls back to query-word lines or to its head.
_ANCHOR_KINDS = frozenset({SymbolKind.DEFINITION, SymbolKind.EXPORT})


class ExplorationError(Exception):
    """Raised when a request cannot be honoured at all, such as a budget that is
    not positive."""


@dataclass(frozen=True)
class TargetedRead:
    """One planned excerpt: the inclusive 1-based line range `start`-`end` of
    `path`, the text of those lines, and why they were chosen.

    `reason` describes the anchors that justified the window, `candidate_rank` is
    the 1-based position of `path` in the resolution that motivated the read, so
    every read stays attributable to a candidate, and `estimated_tokens` is what
    the region would cost — always recorded, even when `supplied` is true and
    nothing was charged for it.
    """

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
    """A region the budget could not cover, carrying the same range, reason,
    candidate rank and estimated cost the read would have had, so the overrun is
    named and costed rather than dropped."""

    path: str
    start: int
    end: int
    reason: str
    candidate_rank: int
    estimated_tokens: int


@dataclass(frozen=True)
class Exploration:
    """The whole plan for one query: what was read, what was deferred, and what it
    cost.

    `spent` is the estimated tokens charged for reads the caller did not already
    hold, `budget` the ceiling it was held to, `saved` the estimated tokens of
    reads that were free because the caller supplied them, and `exhausted` is true
    exactly when at least one region had to be deferred.
    """

    query: str
    budget: int
    spent: int
    reads: tuple[TargetedRead, ...]
    deferred: tuple[Deferral, ...]
    exhausted: bool
    saved: int = 0

    @property
    def complete(self) -> bool:
        """True when every planned region was read, so a plan with deferrals is
        partial."""
        return not self.exhausted


@dataclass(frozen=True)
class _Region:
    """A window the plan intends to read, before budgeting: its range, the anchor
    description that justified it, and the rank of the candidate it came from."""

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
    """Plan and serve the excerpts `resolution` justifies, within `budget` tokens.

    Candidates are taken in rank order and each is turned into merged line windows
    around its anchors (see `_plan_regions`). Regions are then charged in that
    order, in the unit `estimate` reports or `estimate_tokens` when no estimator
    is supplied. A region whose path is in `supplied.fresh` costs nothing: the
    caller already holds that text, so its cost is added to `saved` rather than
    `spent`. The first charged region that would overrun the budget stops the
    spending; it and every later charged region become deferrals, which is what
    makes `exhausted` true and `complete` false.

    `context` sets the window length. `supplied` is optional: without it every
    region is charged. Raises `ExplorationError` when `budget` is not positive.
    """
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
        # A region the caller already holds verbatim is still planned and
        # reported, so coverage does not depend on the hints; it is simply not
        # charged, and its cost is counted as saved instead.
        held = region.path in free
        # Charging happens in rank order, and once a region the caller does not
        # hold would overrun the budget, no later charged region is read at all:
        # the plan stops spending and records them as deferred. Regions the caller
        # already holds are unaffected by that stop — they stay free, are still
        # read, and keep adding to `saved`.
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


# Turning the ranked candidates into the line regions worth reading.


def _plan_regions(
    candidates: tuple[Candidate, ...],
    index: Index,
    files: dict[str, IndexedFile],
    query_tokens: frozenset[str],
    context: int,
) -> list[_Region]:
    """Turn each candidate, in rank order, into the line regions worth reading.

    Definitions and exports are collected per path up front; each candidate's
    anchors are drawn from them by `_anchors`, widened and merged by `_windows`,
    and every resulting window is tagged with the candidate's 1-based rank. A
    candidate path the index does not hold contributes nothing.
    """
    symbols_by_path: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in index.symbols.all():
        if symbol.kind in _ANCHOR_KINDS:
            symbols_by_path[symbol.path].append(symbol)

    regions: list[_Region] = []
    for rank, candidate in enumerate(candidates, start=1):
        file = files.get(candidate.path)
        if file is None:  # a path with no indexed lines has nothing to read
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
    """The `(line, reason)` pairs in `file` that justify reading it.

    A definition or export anchors its line when its name shares a token with the
    query, reported as "defines ...". Then, up to `_MAX_TEXT_ANCHORS` of them,
    lines whose text carries a query token anchor themselves as "match ...",
    which covers hits that are not symbols. A line anchors once, symbol anchors
    are collected first, and a file with no anchor at all is read from its head so
    a filename-only match still yields a region.
    """
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
    """Widen every anchor into a `context`-line window and merge what overlaps.

    Each anchor yields the span that starts `_LEAD` lines above it, never before
    line 1, and is clamped to `total_lines`. Spans that touch or overlap — the
    next one starts at most one line after the previous end — become a single
    span whose end is the furthest end and whose reasons are joined with "; " in
    first-seen order, so neighbouring anchors are read once instead of twice.
    """
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


# Reading indexed lines back out, and the token sizing and lookup they need.


def _slice(file: IndexedFile, start: int, end: int) -> str:
    """The text of lines `start`-`end` inclusive, 1-based, joined as the index
    split them."""
    return "\n".join(file.lines[start - 1 : end])


def _unique(items: list[str]) -> list[str]:
    """`items` deduplicated, keeping first-seen order."""
    return list(dict.fromkeys(items))


def estimate_tokens(text: str) -> int:
    """Rough token cost of `text`: one token per four characters, never zero.

    This is the default `explore` charges against its budget when the caller
    supplies no estimator of its own, so plans stay comparable across runs
    without a model tokenizer.
    """
    return max(1, (len(text) + 3) // 4)


def _name_tokens(name: str) -> list[str]:
    """The word tokens of `name`, folded exactly as the resolver folds query
    words, so anchors and queries are compared on equal terms."""
    return _tokenize(name)


def _first_token_in(line: str, query_tokens: frozenset[str]) -> str | None:
    """The alphabetically first query token contained in `line`, or `None`.

    Both sides are tokenized the same way, and sorting makes the choice of which
    token to report deterministic when a line carries several of them.
    """
    line_tokens = set(_name_tokens(line))
    for token in sorted(query_tokens):
        if token in line_tokens:
            return token
    return None
