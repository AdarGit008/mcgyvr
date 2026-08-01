"""Turn detected hardware into a proposed ladder.

The capability table says what models are worth running and what they cost
(``mcgyvr.capability``); detection says what this machine has. This module
is the join: which rungs to bind, in what order, and why each one was
chosen. It reads no hardware and touches no network — everything it needs
arrives as arguments, which is what keeps it testable against machines
nobody here owns.

**The ladder must not invert.** A higher rung has to be measurably better
than the one below, or it is not a rung. This is not a style preference:
escalation spends the cheap rung's tokens *and* the expensive rung's, so a
rung that is bigger but no better makes escalation actively harmful — it
costs strictly more than starting higher would have. The table's
``deepseek-coder-v2:16b`` is the worked example: 9.4 GB for 72.6%, against
``qwen2.5-coder:7b``'s 5.0 GB for 84.1%. Nearly twice the VRAM, meaningfully
worse. A ladder built on size would place it above the 7B and be wrong.

Three stages produce the gradient, and their order matters:

1. **Collapse equal-quality ties.** Two models measuring the same score are
   one rung. The faster one wins, because once both fit the card, latency is
   what the user experiences and footprint only buys concurrency headroom.
   This runs FIRST: doing it after dominance lets a model be eliminated by a
   candidate that is itself dropped a step later, which is how a 12 GB card
   lost its 84.1% middle rung to a model that never made the ladder.
2. **Dominance.** Drop any model another candidate beats on quality while
   fitting in the same VRAM or less. This is what removes the deepseek case.
   It is decided per machine, since eligibility depends on which backends are
   actually reachable.
3. **Measurable separation.** Keep a lower rung only if it is at least
   ``MIN_QUALITY_GAIN`` below the rung above. Rungs closer than that are
   within measurement resolution, so escalating between them buys latency
   variance rather than capability.

The ceiling — the best model that fits — is always kept; lower rungs are
added beneath it. Selecting the other way round would let the ceiling be
dropped for sitting too close to a cheaper rung, which is exactly backwards.

Note that dominance deliberately does *not* rank on speed. deepseek-coder-v2
is the fastest model in the table at 110 tok/s, and treating throughput as a
dimension a model can win on would rescue the one model the gradient rule
exists to exclude. Speed breaks ties between equals; it never buys a rung.

Unmeasured models are never proposed. That is enforced upstream in
``CapabilityTable.fitting``, and the rejection is surfaced here by name so a
user can see that a model they expected was withheld on purpose rather than
overlooked.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mcgyvr.capability import CapabilityTable, Model

# HumanEval+ is 164 tasks, so one task is ~0.61 percentage points. 0.03 is
# about five tasks: far enough apart that the ordering is not an artifact of
# the harness, close enough to keep a real gradient on a small card. It is a
# judgment about measurement resolution, not itself a measured value.
MIN_QUALITY_GAIN = 0.03

# CAV-04: a marginal fit degrades rather than failing, which makes it look
# like a working binding. Absolute, not a fraction — see CapabilityTable.
DEFAULT_HEADROOM_GB = 2.0


@dataclass(frozen=True)
class AvailableSource:
    """A backend that is actually reachable, and what it already holds.

    Deliberately a plain input rather than anything imported from
    detection: the proposal is a pure function of (table, VRAM, sources),
    which is what lets it be tested against a 6 GB card and a 12 GB card on
    a machine that has neither.
    """

    name: str
    backend: str
    models_present: frozenset[str] = frozenset()

    def has(self, model_id: str) -> bool:
        return model_id in self.models_present


@dataclass(frozen=True)
class Rung:
    """One proposed binding, with why it was chosen."""

    name: str
    model: str
    source: str
    quality: float
    vram_gb: float
    weights_gb: float
    already_present: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Rejection:
    """A model that was considered and not proposed, and why not."""

    model: str
    reason: str


@dataclass(frozen=True)
class Proposal:
    rungs: tuple[Rung, ...] = ()
    rejected: tuple[Rejection, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def is_local_empty(self) -> bool:
        """Whether nothing local could be proposed. Not an error condition."""
        return not self.rungs

    @property
    def must_pull(self) -> tuple[Rung, ...]:
        return tuple(r for r in self.rungs if not r.already_present)

    @property
    def download_gb(self) -> float:
        """What accepting this proposal would cost to download, in total."""
        return round(sum(r.weights_gb for r in self.must_pull), 2)

    def why(self, model_id: str) -> str | None:
        """The reason a model was rejected, if it was."""
        return next((r.reason for r in self.rejected if r.model == model_id), None)


def _serving_source(
    model: Model, sources: Sequence[AvailableSource]
) -> AvailableSource | None:
    """The best source for a model: one that already holds it, if any.

    Presence breaks ties; it never overrides the quality gradient. A
    download is a one-time cost, while a weaker rung is a permanent one.
    """
    eligible = [
        s
        for s in sources
        if model.requires_backend is None or s.backend == model.requires_backend
    ]
    if not eligible:
        return None
    return next((s for s in eligible if s.has(model.id)), eligible[0])


def _ineligible_reason(model: Model, sources: Sequence[AvailableSource]) -> str:
    if not sources:
        return "no local backend is reachable, so nothing local can be bound"
    backends = ", ".join(sorted({s.backend for s in sources})) or "none"
    return (
        f"needs the {model.requires_backend} backend; reachable here: "
        f"{backends}. Binding it elsewhere is not a downgrade but a wrong "
        f"answer — the measured score belongs to this backend and this quant."
    )


def _slower(candidate: Model, reference: Model) -> bool:
    """Whether ``candidate`` has a measured throughput below ``reference``.

    Unmeasured throughput is not treated as slow — an absent number is not
    evidence. Note that the two figures may come from different rigs, since
    a model is measured where it runs; the table's own guidance is to read
    throughput as ratios rather than absolutes. It is used here only to
    break a tie between two models of identical measured quality, where the
    alternative is picking on footprint alone.
    """
    theirs = candidate.best_throughput
    ours = reference.best_throughput
    return theirs is not None and ours is not None and theirs < ours


def _tie_reason(loser: Model, winner: Model) -> str:
    """Why one of two models with identical measured quality was not bound."""
    if _slower(loser, winner):
        return (
            f"same measured quality as {winner.id} but slower here "
            f"({loser.best_throughput:g} against {winner.best_throughput:g} "
            f"tok/s), and both fit this card. Equal quality is not a second "
            f"rung."
        )
    return (
        f"same measured quality as {winner.id} with no speed advantage, in "
        f"{loser.vram_gb_working:g} GB against {winner.vram_gb_working:g} GB. "
        f"Equal quality is not a second rung."
    )


def _best_of_equal_quality(group: list[Model]) -> list[Model]:
    """Order models of identical measured quality, best first.

    Faster wins: once both fit the card, latency is the difference the user
    experiences, and footprint only buys concurrency headroom. Size then id
    break the remaining ties so the result never depends on table order.
    """
    return sorted(
        group,
        key=lambda m: (-(m.best_throughput or 0.0), m.vram_gb_working, m.id),
    )


def _dominated_by(model: Model, others: Sequence[Model]) -> Model | None:
    """The strongest candidate that is strictly better and no larger.

    Runs only after equal-quality ties are collapsed, so "at least as good"
    reduces to "better". Several models may dominate one; the message names
    the best of them, because "you could have this instead" is more use than
    "something beat it".
    """
    quality = model.best_quality or 0.0
    dominators = [
        other
        for other in others
        if (other.best_quality or 0.0) > quality
        and other.vram_gb_working <= model.vram_gb_working
    ]
    if not dominators:
        return None
    dominators.sort(key=lambda m: (-(m.best_quality or 0.0), m.vram_gb_working, m.id))
    return dominators[0]


def _reasons(
    model: Model,
    source: AvailableSource,
    vram_gb: float,
    headroom_gb: float,
    below: Model | None,
) -> tuple[str, ...]:
    quality = model.best_quality or 0.0
    reasons = [
        f"fit: {model.vram_gb_working:g} GB working + {headroom_gb:g} GB "
        f"reserved headroom fits a {vram_gb:g} GB card",
        f"quality: HumanEval+ pass@1 {quality:.1%} measured on "
        f"{model.quant or 'the shipped quant'}",
    ]
    if below is not None:
        gap = quality - (below.best_quality or 0.0)
        reasons.append(
            f"gradient: {gap:.1%} above the rung below ({below.id}), which is "
            f"past the {MIN_QUALITY_GAIN:.1%} floor for a rung to be worth "
            f"escalating to"
        )
    else:
        reasons.append("gradient: the cheapest rung — nothing sits below it")
    if source.has(model.id):
        reasons.append(f"already pulled on {source.name}")
    else:
        reasons.append(f"needs pulling on {source.name} (~{model.weights_gb:g} GB)")
    return tuple(reasons)


def propose(
    table: CapabilityTable,
    *,
    vram_gb: float | None,
    sources: Sequence[AvailableSource] = (),
    headroom_gb: float = DEFAULT_HEADROOM_GB,
    min_quality_gain: float = MIN_QUALITY_GAIN,
) -> Proposal:
    """Propose a local ladder for a card of ``vram_gb`` served by ``sources``.

    Never raises. A machine with no GPU, no backend, or nothing that fits
    gets an empty local ladder and notes explaining what is missing — that
    is a coherent API-only install, not a failure.
    """
    rejected: list[Rejection] = []
    notes: list[str] = []

    if vram_gb is None:
        notes.append(
            "No GPU was detected, so no local rung can be proposed. This is a "
            "supported install: bind an API source, or bind a local model by "
            "hand if the machine has a GPU this build could not see."
        )
        return Proposal(notes=tuple(notes))

    fitting = table.fitting(vram_gb, headroom_gb)
    fits = {m.id for m in fitting}
    for model in table.models:
        if model.id in fits:
            continue
        if not model.is_measured:
            rejected.append(
                Rejection(
                    model.id,
                    "never proposed: no valid quality measurement survives the "
                    "table's harness caveats, and an unmeasured model must not "
                    "be bound on the assumption that it is fine",
                )
            )
        else:
            rejected.append(
                Rejection(
                    model.id,
                    f"does not fit: {model.vram_gb_working:g} GB working + "
                    f"{headroom_gb:g} GB reserved headroom exceeds "
                    f"{vram_gb:g} GB",
                )
            )

    # Eligibility is per machine: a model whose backend is not here cannot be
    # bound, and must not be allowed to dominate one that can.
    eligible: list[tuple[Model, AvailableSource]] = []
    for model in fitting:
        source = _serving_source(model, sources)
        if source is None:
            rejected.append(Rejection(model.id, _ineligible_reason(model, sources)))
            continue
        eligible.append((model, source))

    if not eligible:
        if not sources:
            notes.append(
                "No local backend is reachable, so the local ladder is empty. "
                "Bind an API source, or start a backend and re-run."
            )
        else:
            notes.append(
                "Every model that fits this card needs a backend that is not "
                "reachable here. The local ladder is empty rather than wrong."
            )
        return Proposal(rejected=tuple(rejected), notes=tuple(notes))

    # Collapse equal-quality ties FIRST. Doing it after dominance would let a
    # model be eliminated by a candidate that is itself dropped a step later,
    # which is how a 12 GB card lost its 84.1% middle rung to a model that
    # never made the ladder.
    groups: dict[float, list[Model]] = {}
    for model, _ in eligible:
        groups.setdefault(model.best_quality or 0.0, []).append(model)

    survivors: list[Model] = []
    for group in groups.values():
        ranked = _best_of_equal_quality(group)
        survivors.append(ranked[0])
        for loser in ranked[1:]:
            rejected.append(Rejection(loser.id, _tie_reason(loser, ranked[0])))

    kept: list[Model] = []
    for model in survivors:
        dominant = _dominated_by(model, survivors)
        if dominant is None:
            kept.append(model)
            continue
        rejected.append(
            Rejection(
                model.id,
                f"dominated by {dominant.id}: same or better measured quality "
                f"in {dominant.vram_gb_working:g} GB against "
                f"{model.vram_gb_working:g} GB. A bigger model that is not "
                f"better is not a higher rung.",
            )
        )

    # Build downward from the ceiling: the best model that fits is always
    # bound, and a cheaper rung joins it only if it is measurably below.
    # Quality first; at equal quality the faster model is the better rung,
    # because once both fit, latency is the difference the user experiences.
    kept.sort(
        key=lambda m: (m.best_quality or 0.0, m.best_throughput or 0.0), reverse=True
    )
    ladder: list[Model] = []
    for model in kept:
        if not ladder:
            ladder.append(model)
            continue
        above = ladder[-1]
        gap = (above.best_quality or 0.0) - (model.best_quality or 0.0)
        if gap >= min_quality_gain:
            ladder.append(model)
        else:
            rejected.append(
                Rejection(
                    model.id,
                    f"within {gap:.1%} of {above.id}, under the "
                    f"{min_quality_gain:.1%} floor — two rungs that close are "
                    f"one rung, and escalating between them buys latency "
                    f"rather than capability",
                )
            )
    ladder.reverse()  # cheapest first

    # Keyed by id: Model holds lists of measurements, so it is not hashable.
    by_id = {m.id: s for m, s in eligible}
    rungs: list[Rung] = []
    for index, model in enumerate(ladder):
        source = by_id[model.id]
        below = ladder[index - 1] if index else None
        rungs.append(
            Rung(
                name=f"local-{index + 1}",
                model=model.id,
                source=source.name,
                quality=model.best_quality or 0.0,
                vram_gb=model.vram_gb_working,
                weights_gb=model.weights_gb,
                already_present=source.has(model.id),
                reasons=_reasons(model, source, vram_gb, headroom_gb, below),
            )
        )

    to_pull = [r for r in rungs if not r.already_present]
    if to_pull:
        missing = ", ".join(f"{r.model} (~{r.weights_gb:g} GB)" for r in to_pull)
        total = round(sum(r.weights_gb for r in to_pull), 2)
        notes.append(f"Needs pulling before first use: {missing}. Total ~{total:g} GB.")
    return Proposal(rungs=tuple(rungs), rejected=tuple(rejected), notes=tuple(notes))
