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

import re
from collections.abc import Sequence
from dataclasses import dataclass

from mcgyvr.capability import CapabilityTable, Model

# HumanEval+ is 164 tasks, so one task is ~0.61 percentage points. 0.03 is
# about five tasks: far enough apart that the ordering is not an artifact of
# the harness, close enough to keep a real gradient on a small card. It is a
# judgment about measurement resolution, not itself a measured value.
#
# **This is a rung-separation floor and nothing else.** It answers "are these
# two models different enough that both are worth carrying in the ladder", per
# rule 3 above. It is not an adoption bar, and it never was: "is this
# improvement worth shipping" is a different question with a different cost
# side, and there is no reason the two numbers should coincide.
#
# #189 borrowed it as the adoption bar for a fine-tune and scored +1.9pp a
# "miss" against it. That reading is withdrawn — #219 showed the instrument
# could not resolve +3pp in the first place, so the comparison decided nothing.
# ADR-0019 replaces the borrowing with a reality floor plus a per-lever rule and
# leaves this constant at its own job. Do not reuse it as an adoption threshold.
MIN_QUALITY_GAIN = 0.03

# Naming tokens for a ladder tier: <locality>_<model>. There is no role
# token: a binding's role is derived from where it sits in the schema, and
# the ladder holds workers only.
LOCAL = "local"
API = "api"

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
    host: str = ""

    def has(self, model_id: str) -> bool:
        return model_id in self.models_present

    @property
    def is_local(self) -> bool:
        """Whether this source runs on the machine doing the proposing.

        An unnamed host means local, which keeps every caller that predates
        multi-host sweeps saying what it always said. It matters because the
        VRAM figure a proposal is handed describes *this* machine's card, and
        so is evidence about local sources and about no others.
        """
        return self.host in ("", "localhost", "127.0.0.1", "::1", "[::1]")


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
    host: str = ""


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


def binding_name(model_id: str, *, locality: str = LOCAL) -> str:
    """Name a ladder tier ``<locality>_<model>``.

    The name is what everything downstream refers to a tier by — risk
    floors, routing policy, telemetry — so it says what the thing IS
    (local or behind an API) rather than where it sits in an ordering. An
    index-based name would silently change meaning when a rung is inserted,
    which for a policy reference is a rename that looks like an edit.

    There is no role token. A binding's role is derived from where it sits
    in the schema: under ``orchestrator`` it is the orchestrator, under
    ``verifier`` it is the verifier, and in the ladder it is a worker. Only
    tiers carry a name, so a role token would be constant across every name
    that exists — it would spend characters saying the one thing already
    known from the name's location.

    The model segment is normalized because a model id is not a safe name:
    ``Qwen/Qwen2.5-Coder-14B-Instruct-AWQ`` carries a path separator and
    ``qwen2.5-coder:7b`` a colon, and both end up as YAML keys a human
    edits. Only the final path segment is kept, lowercased, with anything
    outside ``[a-z0-9.-]`` folded to a dash.
    """
    segment = model_id.rsplit("/", 1)[-1].lower()
    segment = re.sub(r"[^a-z0-9.-]+", "-", segment).strip("-")
    return f"{locality}_{segment}"


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


def _fit_reason(
    model: Model,
    source: AvailableSource,
    vram_gb: float | None,
    headroom_gb: float,
) -> str:
    """Why this model is believed to run where it is being bound.

    Two different grounds, and they are not the same strength of claim. A
    VRAM arithmetic fit is a *prediction* from the table's working figure
    against a card this process can see. A backend reporting the model in its
    own listing is an *observation* that it is loaded there — which is the
    stronger fact, and the only one available for a rig on another machine
    whose card ``nvidia-smi`` here cannot describe (#161).
    """
    if source.has(model.id):
        return (
            f"fit: {source.name} reports holding {model.id}, so the rig is "
            f"provisioned for it — asserted by the machine that will run it, "
            f"not estimated from a card elsewhere"
        )
    if not source.is_local:
        return (
            f"fit: not established on {source.host} — its card is not visible "
            f"from here and it does not report holding {model.id}. The "
            f"table's {model.vram_gb_working:g} GB working figure is what "
            f"this rests on; check it against that machine."
        )
    if vram_gb is None:
        return (
            f"fit: not established — no GPU is visible here to size "
            f"{model.vram_gb_working:g} GB against. Bound on the table's "
            f"figure alone."
        )
    return (
        f"fit: {model.vram_gb_working:g} GB working + {headroom_gb:g} GB "
        f"reserved headroom fits a {vram_gb:g} GB card"
    )


def _placement_reason(
    model: Model,
    source: AvailableSource,
    sources: Sequence[AvailableSource],
) -> str | None:
    """Say when a rung's machine was a coin-toss, and on what.

    With one rig this never fires. With several, more than one can hold the
    same weights, and :func:`_serving_source` takes the first that does —
    first in the order the hosts were named, which is a fact about the
    command line and not about the machines. Silence would let arbitrary read
    as considered.

    The cost of getting it wrong is not hypothetical: measured, one 7B runs
    at 30 tok/s on a 6 GB card and 58 on a 12 GB one, so the same rung is
    twice the wall clock depending on a choice made here by list order. What
    would decide it properly is a throughput figure per (model, host), which
    nothing in this project records yet — #162.
    """
    holders = [s for s in sources if s.has(model.id) and s.host]
    if len(holders) < 2:
        return None
    others = ", ".join(s.host for s in holders if s.host != source.host)
    return (
        f"placement: {source.host} was taken because it is the first host "
        f"named that holds {model.id} — {others} also has it. That is list "
        f"order, not a measurement: the same weights can run at half the "
        f"speed on a smaller card. Reorder the hosts, or pin the source by "
        f"hand, if this is the wrong machine (#162)."
    )


def _reasons(
    model: Model,
    source: AvailableSource,
    vram_gb: float | None,
    headroom_gb: float,
    below: Model | None,
    sources: Sequence[AvailableSource] = (),
) -> tuple[str, ...]:
    quality = model.best_quality or 0.0
    reasons = [
        _fit_reason(model, source, vram_gb, headroom_gb),
        f"quality: HumanEval+ pass@1 {quality:.1%} measured on "
        f"{model.quant or 'the shipped quant'}",
    ]
    placement = _placement_reason(model, source, sources)
    if placement is not None:
        reasons.append(placement)
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


def _candidates(
    table: CapabilityTable,
    vram_gb: float | None,
    sources: Sequence[AvailableSource],
    headroom_gb: float,
) -> tuple[Model, ...]:
    """The models worth considering, admitted on whichever ground applies.

    Two grounds, and which one applies is decided by *where the backend is*
    rather than by which is the stronger evidence:

    * **It fits the card this process can see.** The original rule. It is a
      claim about this machine's GPU, so it governs exactly the backends
      running on this machine.
    * **A backend on another machine reports holding it.** #161's rule. The
      local card is not weaker evidence about a remote rig — it is evidence
      about the wrong machine, and applying it would reject a 7B on a 12 GB
      rig because the laptop asking has no GPU. The rig's own model listing
      is the only fact available, so it is the one used.

    The second ground is deliberately the weaker claim and is labelled as
    such wherever it is reported (:func:`_fit_reason`). A model listing means
    different things to different backends — vLLM lists what it has loaded,
    Ollama lists what has been pulled to disk — so it establishes that the
    rig is *provisioned* for the model, not that the model is resident. That
    is still strictly more than this machine can otherwise know about a card
    it cannot see, and unlike a VRAM estimate it cannot be wrong about which
    machine it describes.

    Only measured models are admitted by the second rule. A backend will
    happily hold something the table has no score for, and binding it would
    put an unmeasured model on the ladder through the back door — which is
    the one thing ``CapabilityTable.fitting`` exists to prevent.
    """
    admitted: dict[str, Model] = {}
    if vram_gb is not None:
        for model in table.fitting(vram_gb, headroom_gb):
            admitted[model.id] = model
    remote = [s for s in sources if not s.is_local]
    for model in table.models:
        if model.id in admitted or not model.is_measured:
            continue
        if any(source.has(model.id) for source in remote):
            admitted[model.id] = model
    return tuple(admitted.values())


def propose(
    table: CapabilityTable,
    *,
    vram_gb: float | None,
    sources: Sequence[AvailableSource] = (),
    headroom_gb: float = DEFAULT_HEADROOM_GB,
    min_quality_gain: float = MIN_QUALITY_GAIN,
) -> Proposal:
    """Propose a local ladder for a card of ``vram_gb`` served by ``sources``.

    ``vram_gb`` is what the *local* card holds, and may be ``None`` — either
    because there is no GPU or because there is one this build cannot see.
    That is no longer the end of the proposal: a source that reports serving
    a measured model supplies the fit evidence the card would have (#161),
    so a laptop with no GPU can still bind the rigs it can reach.

    Never raises. A machine with no GPU, no backend, or nothing that fits
    gets an empty local ladder and notes explaining what is missing — that
    is a coherent API-only install, not a failure.
    """
    rejected: list[Rejection] = []
    notes: list[str] = []

    candidates = _candidates(table, vram_gb, sources, headroom_gb)
    fits = {m.id for m in candidates}
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
        elif vram_gb is None:
            rejected.append(
                Rejection(
                    model.id,
                    "not proposed: no reachable backend reports serving it, and "
                    "there is no GPU here to size its "
                    f"{model.vram_gb_working:g} GB against. Pull it on a rig "
                    "that is being swept and it becomes bindable.",
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
    for model in candidates:
        source = _serving_source(model, sources)
        if source is None:
            rejected.append(Rejection(model.id, _ineligible_reason(model, sources)))
            continue
        eligible.append((model, source))

    if not eligible:
        if not sources:
            notes.append(
                "No local backend is reachable, so the local ladder is empty. "
                "Bind an API source, start a backend and re-run, or name the "
                "rig that serves your models — `mcgyvr init --host <name>`."
            )
        elif vram_gb is None:
            notes.append(
                "No GPU is visible here, and no backend on another machine "
                "reports holding a measured model, so no local rung can be "
                "proposed. This is a supported install: bind an API source, "
                "bind a local model by hand if this machine has a GPU the "
                "build could not see, or name the rig that serves your "
                "models — `mcgyvr init --host <name>`."
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
                name=binding_name(model.id),
                model=model.id,
                source=source.name,
                quality=model.best_quality or 0.0,
                vram_gb=model.vram_gb_working,
                weights_gb=model.weights_gb,
                already_present=source.has(model.id),
                reasons=_reasons(model, source, vram_gb, headroom_gb, below, sources),
                host=source.host,
            )
        )

    to_pull = [r for r in rungs if not r.already_present]
    if to_pull:
        missing = ", ".join(f"{r.model} (~{r.weights_gb:g} GB)" for r in to_pull)
        total = round(sum(r.weights_gb for r in to_pull), 2)
        notes.append(f"Needs pulling before first use: {missing}. Total ~{total:g} GB.")
    spread = _spread_note(rungs)
    if spread is not None:
        notes.append(spread)
    notes.append(_concurrency_note(rungs))
    return Proposal(rungs=tuple(rungs), rejected=tuple(rejected), notes=tuple(notes))


def _spread_note(rungs: Sequence[Rung]) -> str | None:
    """Say so when the proposed ladder crosses machines (#162).

    The gradient rules above order rungs by measured quality, and quality is
    a property of the weights. Throughput is not: the same model measures
    2.4x apart on two different cards, and a 7B that thrives on a 12 GB card
    thrashes on a 6 GB one. So a ladder whose rungs sit on different machines
    can be correctly ordered by quality and still be slower at the bottom
    than at the top — which is the inversion escalation exists to avoid.

    Nothing here reorders it. Ordering across machines is #162's question,
    and this proposal has no throughput figure per (model, host) to answer it
    with. What it can do is refuse to be silent about it.
    """
    hosts = tuple(dict.fromkeys(r.host for r in rungs if r.host))
    if len(hosts) < 2:
        return None
    placed = ", ".join(f"{r.name} on {r.host}" for r in rungs)
    return (
        f"This ladder spans {len(hosts)} machines ({', '.join(hosts)}): "
        f"{placed}. Rungs are ordered by measured quality, which belongs to "
        f"the weights — throughput belongs to the card, and is not in the "
        f"table per host. A cheaper rung on a slower machine can therefore "
        f"cost more wall-clock than the rung above it, which makes escalating "
        f"through it worse than starting higher. Check the order against your "
        f"own machines before trusting it; #162 is where this stops being the "
        f"operator's problem."
    )


def _concurrency_note(rungs: Sequence[Rung]) -> str:
    """What raising ``max_parallel`` does and does not buy (CON-02).

    Stated in the proposal because this is the moment an operator decides what
    the machine is for, and because the failure it warns about is invisible
    afterwards: a single-slot server handed four concurrent requests **serializes
    them rather than refusing them**, so an over-declared capacity looks exactly
    like a source that is merely slow. The config schema already carries CON-01's
    good news — distinct models really do run concurrently on one card — and the
    good news is the half that gets remembered.
    """
    sources = sorted({rung.source for rung in rungs})
    named = ", ".join(sources)
    return (
        f"Concurrency is written twice and only one of them is here. `init` "
        f"writes max_parallel: 1 for {named}, which is always honest; raising it "
        f"only helps if that backend was started with its parallel-slot setting "
        f"enabled. CON-02 measured same-model concurrency at 1.6-3.1x with "
        f"server-side parallelism on, and recorded that a single-slot server "
        f"serializes the requests instead of refusing them — so an over-declared "
        f"capacity is not an error you will see, it is a queue you will not. "
        f"Distinct models are a different question and already answered: CON-01 "
        f"ran three on one card in 23.6 s against ~44 s serial."
    )
