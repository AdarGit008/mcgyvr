"""Bounded targeted reads — the one place in exploration where tokens are spent.

Attach (#46) and index (#47) cost nothing; resolve (#48) costs nothing. Here is
where the orchestrator finally reads source, and so here is where the north star
is won or lost: read only what the shortlist justifies, only the regions that
matter, and never one token past the budget without saying so.

Three commitments, straight from #49's acceptance:

* **The spend is bounded and recorded.** A budget, in estimated tokens, caps the
  exploration; every region read carries its own estimated cost and the total is
  reported on the plan. The estimate is a plain, deterministic function of the
  text — there is no model here to ask — and it is injectable, so a caller that
  owns a real tokenizer can account exactly.
* **Every read is attributed.** A :class:`TargetedRead` names the candidate rank
  that motivated it and the reason the region mattered — a definition, a text
  match, or a filename-only fallback to the file head. The spend is auditable
  against the shortlist, not a black box.
* **Exhaustion forces a decision, never silent continuation.** When the budget
  cannot cover the next region, that region is *deferred*, recorded on the plan
  with what it would have cost, and :attr:`Exploration.exhausted` is set. The
  plan always states plainly what it covered and what it left; a caller that
  overruns gets an explicit partial plan, never a quietly truncated one.

The regions themselves come from the index: a candidate's query-relevant symbol
definitions and text hits become line anchors, each widened to a bounded window
and merged with its neighbours so an overlap is read once. A candidate that
matched only on its filename has no line anchor, so its window is the file head —
the imports and top-level shape that stand in for "what is this file".

**Who the budget is for.** :func:`explore` takes the budget as a number, which
leaves every caller to invent one; :func:`explore_for` takes the *model* and sizes
it. The two are not interchangeable questions. A 1.5B whose useful window collapses
long before its declared one and a 14B that could have read four times as much
cannot both be served by one constant, and which of them is being served wrong
changes with the rung — so a ladder that escalates to a larger model and hands it
the same context has escalated the model and not the question.

What does *not* change with the budget is which regions exist. Planning belongs to
the index and the shortlist, so a smaller budget reads less of the same plan and
never a different plan, and the regions it could not reach are deferred with their
cost. That is the property to hold on to while porting a budget in: the cheap way
to make context smaller is to cut the text, and every such implementation would
still look like it was following the model while quietly handing a worker half a
function.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from mcgyvr.capability import shipped_table
from mcgyvr.orchestrator.context import VerifiedContext
from mcgyvr.orchestrator.index import Index, IndexedFile
from mcgyvr.orchestrator.resolve import (
    Candidate,
    Resolution,
    _content_tokens,
    _tokenize,
)
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind

# A default exploration budget, in estimated tokens — a few windows' worth, on
# the assumption that a resolved shortlist needs sampling, not wholesale reading.
# The caller sets it; this is only the floor of "enough to look".
_DEFAULT_BUDGET = 2000

# Model size in billions of parameters → exploration budget in estimated tokens,
# smallest rung first. Ported verbatim from local-ai's `context_prune.py:18-29`,
# and the numbers are inherited rather than measured: they come from the
# lost-in-the-middle result that a small model's *usable* window is a fraction of
# its declared one, not from a run on this rate card. What is measured here is only
# the ordering — the rate card's own `params_b`, which is why the size comes from
# the capability table rather than from a caller's guess.
#
# Two rungs is the shape local-ai shipped and it is kept, because a third would be
# a number nobody has taken. #117 measures the estimator these are denominated in;
# a bench arm varying only this is what would earn a finer table.
_SIZE_BUDGETS: tuple[tuple[float, int], ...] = ((3.0, 4096), (float("inf"), 8192))

# A region's shape: how many lines it spans, and how many of those sit *above*
# the anchor so the line that matched has context leading into it.
_DEFAULT_CONTEXT = 25
_LEAD = 3

# How many text-match anchors to take per candidate before merging. Symbol
# anchors are unbounded (a file has few definitions); raw text hits can be many,
# and past a handful they stop adding regions the windows don't already cover.
_MAX_TEXT_ANCHORS = 5

# Which symbol kinds may anchor a window. A definition or an export is a place
# worth reading; a reference and an import are mentions of something declared
# elsewhere, and anchoring on an import line would spend the budget on a file's
# header instead of on its substance.
_ANCHOR_KINDS = frozenset({SymbolKind.DEFINITION, SymbolKind.EXPORT})


class ExplorationError(Exception):
    """Exploration was asked for the impossible — a non-positive budget."""


@dataclass(frozen=True)
class TargetedRead:
    """One region actually read, with its cost and what motivated it.

    ``start`` and ``end`` are 1-based inclusive line numbers; ``text`` is exactly
    those lines. ``candidate_rank`` is the 1-based shortlist position that pulled
    this region in, and ``reason`` says why the region mattered.

    ``estimated_tokens`` is always the region's real estimated cost, whether or
    not the budget paid it. ``supplied`` marks a region the caller already holds
    (#51): its content was verified equal to the repository's, so it was charged
    nothing. The two fields together are the audit trail for what a hint saved.
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
    """A region the budget could not afford — recorded, so exhaustion is visible.

    Carries what the read *would* have cost, so a caller can see how far over the
    budget the full exploration would have run and decide what to do about it.
    """

    path: str
    start: int
    end: int
    reason: str
    candidate_rank: int
    estimated_tokens: int


@dataclass(frozen=True)
class Exploration:
    """The plan a bounded exploration produces: what was read, and what was left.

    Always returned, complete or not. ``reads`` are attributed and in the order
    they were taken; ``deferred`` are the regions the budget could not reach;
    ``exhausted`` is true exactly when something was deferred. The plan is the
    forced decision surface — a caller reads ``exhausted`` and acts, rather than
    receiving a silently shortened result.

    ``saved`` is the estimated cost of the regions the caller already held, which
    the budget therefore did not pay — the measurable value of supplied context
    (#51), and zero when none was given.
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
        """Whether every region the shortlist justified was read within budget."""
        return not self.exhausted


@dataclass(frozen=True)
class _Region:
    """A candidate line-window before it is read: where, why, and from which rank."""

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
    """Read the regions the shortlist justifies, best-first, within ``budget``.

    Walks ``resolution``'s candidates in rank order, turns each into bounded line
    windows over the regions that matched, and reads them until the next region
    would exceed ``budget`` — deferring the rest. Returns a plan recording the
    reads (each attributed and costed), the deferrals, and whether the budget was
    exhausted. ``estimate`` counts a region's tokens; the default is a
    deterministic character-based approximation.

    ``supplied`` is verified caller context (#51). A region in a file whose text
    the caller already holds — and which :func:`~mcgyvr.orchestrator.context.verify`
    confirmed matches the repository — is charged nothing, because the caller is
    not being asked to read anything it does not already have. Region planning is
    unaffected: which regions exist is still decided entirely by the index and the
    shortlist, so supplied context can make exploration cheaper but never
    different. Unverified or contradicted context never reaches here.

    Raises :class:`ExplorationError` when ``budget`` is not positive — there is
    no bounded exploration to perform.
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
        # A region the caller already holds is free, so it is always taken — even
        # after the budget has run out. Taking it cannot displace anything, since
        # it charges nothing and the prefix below is defined over *charged*
        # regions only; refusing it would discard a saving for no gain.
        held = region.path in free
        # Read a strict best-first prefix: the first region that does not fit ends
        # the exploration, and it and everything after it are deferred. A cheaper
        # region further down is *not* pulled ahead of a costlier higher-priority
        # one — the deferral list stays a faithful account of where budget ran out.
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


def budget_for_model(model: str) -> int:
    """The exploration budget, in estimated tokens, for the model being dispatched to.

    ``model`` is an id from the capability table — the rate card is where a model's
    size is already recorded and measured, so nothing here asks a caller to declare
    it and nothing contacts a backend to find out.

    A model the table does not hold gets the *smallest* budget, which is the
    conservative answer rather than the timid one. An unmeasured model is not
    evidence for a large window, and the two ways of being wrong are not
    symmetrical: under-reading for a large model costs a deferral the plan states
    plainly, while over-filling a small one degrades the answer with nothing
    anywhere saying so. That asymmetry is the whole reason this lever exists.
    """
    entry = shipped_table().get(model)
    if entry is None:
        return _SIZE_BUDGETS[0][1]
    return next(
        budget for ceiling, budget in _SIZE_BUDGETS if entry.params_b <= ceiling
    )


def explore_for(
    index: Index,
    resolution: Resolution,
    *,
    model: str,
    context: int = _DEFAULT_CONTEXT,
    estimate: Callable[[str], int] | None = None,
    supplied: VerifiedContext | None = None,
) -> Exploration:
    """:func:`explore`, with the budget sized for the model that will read it.

    The same exploration in every other respect, and deliberately so: this adds a
    budget and nothing else. Region planning, the best-first prefix, the deferral
    of what does not fit and the audit trail on the returned
    :class:`Exploration` are all unchanged, because the model the context is *for*
    is not an input to which regions matter — that is the index's and the
    shortlist's answer, and a budget reaching into it would be a budget deciding
    what is relevant.

    Everything else is passed through rather than fixed here, so that sizing the
    budget by model and supplying already-held context (#51) are choices a caller
    makes independently instead of a menu of two.
    """
    return explore(
        index,
        resolution,
        budget=budget_for_model(model),
        context=context,
        estimate=estimate,
        supplied=supplied,
    )


# --- region planning: candidates become bounded windows --------------------


def _plan_regions(
    candidates: tuple[Candidate, ...],
    index: Index,
    files: dict[str, IndexedFile],
    query_tokens: frozenset[str],
    context: int,
) -> list[_Region]:
    """Every candidate's merged windows, flattened best-first for the budget.

    Regions are emitted in candidate-rank order, and within a candidate in line
    order, so spending is depth-first down the ranked shortlist: the best
    candidate is read before the next is begun. What the budget cannot reach is
    deferred in exactly this order, which is what makes the deferral list a
    faithful account of "where the money ran out".
    """
    symbols_by_path: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in index.symbols.all():
        if symbol.kind in _ANCHOR_KINDS:
            symbols_by_path[symbol.path].append(symbol)

    regions: list[_Region] = []
    for rank, candidate in enumerate(candidates, start=1):
        file = files.get(candidate.path)
        if file is None:  # a candidate always indexes, but stay defensive
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
    """Line anchors for a candidate: its matched definitions, then text hits.

    A definition or export whose name carries a query token is the strongest
    anchor. Text hits for those tokens catch matches that are not symbols — a
    mention in a comment or string. When neither fires (a filename-only match),
    the file head stands in, so the candidate is never read as nothing.
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
    """Bounded, non-overlapping (start, end, reason) windows around anchors.

    Each anchor becomes a window of ``context`` lines with a short lead above it,
    clamped to the file. Overlapping or adjacent windows are merged so a region
    is read once; a merged window keeps the reasons of every anchor it absorbed,
    since all of them motivated it.
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


# --- small deterministic helpers -------------------------------------------


def _slice(file: IndexedFile, start: int, end: int) -> str:
    """The 1-based inclusive line range ``[start, end]`` of a file, as text."""
    return "\n".join(file.lines[start - 1 : end])


def _unique(items: list[str]) -> list[str]:
    """The items with duplicates dropped, first occurrence order preserved."""
    return list(dict.fromkeys(items))


def estimate_tokens(text: str) -> int:
    """A deterministic, model-free token estimate — roughly four characters each.

    Not a tokenizer: a stable proxy so the budget is enforced the same way every
    run. A caller with a real tokenizer passes its own ``estimate`` to account
    exactly; this only has to be monotonic in the text it is given.

    Public so that anything else sizing a budget in tokens — the decomposer
    sizing ``context.max_input_tokens`` (#50) — measures with the same proxy the
    read plan spends against, rather than growing a second one that could drift
    from it. What the proxy's error actually is remains #117's to measure.
    """
    return max(1, (len(text) + 3) // 4)


def _name_tokens(name: str) -> list[str]:
    """The lowercased, plural-folded sub-tokens of a name — the resolver's own."""
    return _tokenize(name)


def _first_token_in(line: str, query_tokens: frozenset[str]) -> str | None:
    """The first query token appearing as a sub-token of ``line``, or ``None``."""
    line_tokens = set(_name_tokens(line))
    for token in sorted(query_tokens):
        if token in line_tokens:
            return token
    return None
