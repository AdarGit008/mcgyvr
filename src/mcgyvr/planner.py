"""The planner behind ``mcgyvr recommend``: units per rig, sized by the serving sizer.

Owner, Round 2 (2026-10-07): "Plan shape: a FULL LADDER PER RIG. Each unit has
rig, card(s), model, quant, context, slots, and role (always-on /
sleeps-until-needed / Jev). Sized with the product's existing serving sizer
(serving.fit, sharding.py, vramfit: several models per card, multi-card split,
MoE experts in RAM), not recommend's own _fits."

So nothing here prices a card. A model is one GGUF file with its header row
(:mod:`mcgyvr.knowledge.geometry`, or the header read on the rig for a file
already there), and a unit is what :func:`mcgyvr.serving.unit_for` builds for
it on a measured card, or :func:`mcgyvr.serving.split_units` across cards and
machines: the same law, the same argv, the same refusals ``mcgyvr emit``
gives. What this module decides is only what the sizer is asked:

* **the Jev unit**, opt-in (owner, Round 3): resident, sized first on the card
  with the most room, at :data:`JEV_CTX` per slot and a slot per user, the
  default model :data:`JEV_DEFAULT`. Every other unit is sized around it.
* **chat and agent** (owner, Round 7): ONE unit spanning every card of every
  machine, split by layer (the pipeline split; across machines over RPC), the
  biggest model that fits there, a slot per user, at the most context per
  slot that fits, never below :data:`STRONG_MIN_CTX`. Where the machines
  cannot be spanned (the product binds an RPC worker only to an address it
  was given, never to a name it would have to resolve), the unit spans one
  machine's cards, else takes the roomiest card, and says why.
* **coding** (owner, Round 7): a ladder per rig. It starts with the fastest
  model that serves coding, filled with slots; a bigger rung is added only
  when it is a clear step up (:data:`CLEAR_STEP`) and only while a task that
  climbs every rung finishes within :data:`CLIMB_BUDGET` times the top rung's
  own time; the top rung is always-on when it fits beside the rest, else it
  sleeps until needed and swaps with the rungs on its card (``--priority
  throughput`` plans no sleeper). Fast rungs get :data:`FAST_RUNG_CTX` per
  slot, the top rung :data:`TOP_RUNG_CTX`.
* **the levers** (plan section 5). The KV cache is f16, and q8_0 only when f16
  misses the context the unit needs; the unit says so. A model's MTP head is
  its draft only when its header carries one and it fits. A unit that is not
  asleep holds its model wholly on its card(s): experts in RAM are for the
  sleeper.
* **the order candidates are offered in**: for a strong unit, a model wholly
  on the card(s) first, then the use case's boards
  (:func:`mcgyvr.knowledge.boards.boards_for`), then the larger file; for a
  coding top rung, the boards, then the larger file. The first
  :data:`SHORTLIST` are what a Jev unit may name; with no Jev the first is
  the pick. Nothing a model answers becomes a number.

The plan document is version 2 (plan section 7); :func:`document` writes it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from mcgyvr import serving
from mcgyvr.knowledge import boards
from mcgyvr.knowledge import geometry as kg
from mcgyvr.knowledge import store as ks
from mcgyvr.knowledge.record import ModelRecord, Score
from mcgyvr.scan import Scan

#: The version of the plan document. Version 1 was one placement and no host.
SCHEMA_VERSION = 2
#: The engine every planned text unit is served by: a model is a GGUF file.
#: vLLM loads a repository's safetensors, whose header is not read yet.
ENGINE = serving.DEFAULT_ENGINE

#: The use cases planned as one strong unit, and as a ladder.
STRONG_USE_CASES = ("chat", "agent")
LADDER_USE_CASES = ("coding",)
PLANNED_USE_CASES = (*STRONG_USE_CASES, *LADDER_USE_CASES)

#: What a unit is to its fleet: the two values ``units.<unit>.role`` takes.
#: The Jev unit is resident, so always-on, and is marked ``jev`` beside it.
ROLE_ALWAYS_ON = "always-on"
ROLE_SLEEPER = "sleeps-until-needed"

#: The Jev unit's default model (owner, Round 3) and its context per slot
#: (owner, Round 4; ``--jev-ctx`` says another).
JEV_DEFAULT = "Qwen/Qwen3.5-4B"
JEV_CTX = 4096

#: The coding top rung's context per slot, owner Round 4 ("top/strong rung
#: 32k"): the ceiling decompose may raise a contract's prompt to
#: (``orchestrator/decompose.py``), so it serves anything decompose emits.
TOP_RUNG_CTX = 32768
#: The coding fast rungs' context per slot, owner Round 4 ("fast rungs 8k"):
#: a contract's default prompt ceiling with its preflight reserve and a reply
#: budget fits it (plan section 3.1).
FAST_RUNG_CTX = 8192
#: The least context per slot a chat or agent strong unit is planned at, when
#: the model's own context allows it, owner Round 7 ("least context 8k per
#: user, more whenever it fits").
STRONG_MIN_CTX = 8192
#: The step the most context that fits is searched in, in tokens.
CONTEXT_STEP = 1024
#: The port the first unit of a rig answers on, the next unit one above it:
#: one above llama.cpp's own default (:data:`mcgyvr.serving.DEFAULT_PORT`),
#: which a server the user already runs often holds. ``--first-port`` says
#: another.
FIRST_PORT = serving.DEFAULT_PORT + 1
#: The most options one question to a Jev unit holds (plan section 4.5): a
#: choice of more than its server's ``top_logprobs`` cannot see every label.
SHORTLIST = 8
#: How much longer than the top rung alone a task that climbs every rung may
#: take, owner Round 7 ("within ~2x the time the top rung alone would take").
#: A rung's time is estimated from the bytes it reads per token
#: (:func:`token_bytes`); the sample run checks real timings.
CLIMB_BUDGET = 2.0
#: How much larger a rung's file must be than the rung below it to be a clear
#: step up and not a near-copy (owner, Round 7: "add a bigger rung only when it
#: is a CLEAR quality step up"); where a board of the use case scores both,
#: the larger must also score better.
CLEAR_STEP = 1.5

#: The KV cache types: f16, and q8_0 only when f16 misses the context needed.
KV_F16 = "f16"
KV_Q8 = "q8_0"
KV_TYPES = (KV_F16, KV_Q8)

#: A card: the machine, and the card's index there.
Card = tuple[str, int]

_SLUG = re.compile(r"[^a-z0-9._-]+")


class PlanError(Exception):
    """A plan cannot be made or read back, and the message says why."""


@dataclass(frozen=True)
class Model:
    """A model a plan may place: one GGUF file and its header row.

    ``geometry`` is the file's ``ggufscan`` row, the one thing the serving
    sizer reads. A file to download names its ``repo``, ``revision`` and
    ``sha256``; a file already on the rig names its ``present`` path there.
    ``sources`` says where its numbers came from, by what they are (``size``,
    ``context``, ``geometry``); ``scores`` are its board scores; ``serves``
    what it is catalogued for (:func:`serves`).
    """

    model_id: str
    quant: str
    file: str
    size_bytes: int
    context_length: int
    geometry: Mapping[str, Any]
    repo: str | None = None
    revision: str | None = None
    sha256: str | None = None
    present: str | None = None
    sources: Mapping[str, str] = field(default_factory=dict)
    scores: tuple[Score, ...] = ()
    #: What the model is catalogued as serving; empty: any text use case.
    serves: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """What the model is called in a question and a refusal."""
        return self.present or f"{self.model_id} {self.quant}"

    @property
    def stem(self) -> str:
        """The file's name without ``.gguf``: the name the sizer serves it under."""
        name = Path(self.file).name
        return name[: -len(".gguf")] if name.lower().endswith(".gguf") else name

    @property
    def has_mtp_head(self) -> bool:
        return bool(self.geometry.get("nextn_blocks"))


@dataclass(frozen=True)
class Library:
    """The models a plan may place from the model knowledge.

    ``unsized`` names each known model that cannot be sized, with why;
    ``skipped`` each knowledge cache file that was not read, with why.
    """

    models: tuple[Model, ...] = ()
    unsized: tuple[tuple[str, str], ...] = ()
    skipped: tuple[tuple[Path, str], ...] = ()
    oldest_read_at: date | None = None


def _scores_source(scores: Sequence[Score]) -> str | None:
    if not scores:
        return None
    return "; ".join(score.value.source for score in scores)


def model_from_record(record: ModelRecord, row: kg.Geometry) -> Model:
    """A knowledge record and the header row of its file, as a model to place."""
    assert record.weights is not None
    weights = record.weights
    sources = {
        "size": record.size_bytes.source,
        "context": record.context_length.source,
        "geometry": row.source,
    }
    scored = _scores_source(record.scores)
    if scored is not None:
        sources["score"] = scored
    return Model(
        model_id=record.model_id,
        quant=record.quant,
        file=weights.file,
        size_bytes=int(record.size_bytes.value),
        context_length=int(record.context_length.value),
        geometry=row.row,
        repo=weights.repo,
        revision=weights.revision,
        sha256=weights.sha256,
        sources=sources,
        scores=record.scores,
        serves=record.serves,
    )


def model_from_header(host: str, path: str, header: Mapping[str, Any]) -> Model:
    """A file already on ``host`` at ``path``, from the header read there."""
    file = Path(path).name
    where = f"gguf-header-on-rig:{host}:{path}"
    size = header.get("size_bytes")
    context = header.get("n_ctx_train")
    if not isinstance(size, int) or not isinstance(context, int) or context <= 0:
        raise PlanError(f"{host}:{path}: its header states no size or no context")
    stem = Path(file).stem
    return Model(
        model_id=stem,
        quant=str(header.get("quant") or "") or "as-built",
        file=file,
        size_bytes=size,
        context_length=context,
        geometry=dict(header, file=file),
        present=path,
        sources={"size": where, "context": where, "geometry": where},
    )


def library() -> Library:
    """The model knowledge read offline (the cache, then the shipped catalog),
    each model with its file's header row. A model with no row, or one no
    llama.cpp can serve, is named in :attr:`Library.unsized` with why."""
    known = ks.offline()
    rows = kg.load()
    models: list[Model] = []
    unsized: list[tuple[str, str]] = []
    days = [day for day in (known.oldest_read_at,) if day is not None]
    for record in known.records:
        label = f"{record.model_id} {record.quant}"
        if ENGINE not in record.engines or record.weights is None:
            unsized.append((label, f"no {ENGINE} file is known for it"))
            continue
        row = rows.of(record.weights)
        if row is None:
            unsized.append(
                (
                    label,
                    f"the header of {record.weights.file} has not been read, so "
                    f"it cannot be sized; an online run reads it",
                )
            )
            continue
        days.append(row.read_at)
        models.append(model_from_record(record, row))
    return Library(
        models=tuple(models),
        unsized=tuple(unsized),
        skipped=(*known.skipped, *rows.skipped),
        oldest_read_at=min(days) if days else None,
    )


def spec_of(
    model: Model, *, kv: str = KV_F16, speculative: str = serving.SPECULATIVE_NONE
) -> serving.ModelSpec:
    """The serving sizer's spec of ``model``: its header row, and the KV cache
    types and speculative head the unit is launched with."""
    return serving.ModelSpec(
        name=model.stem,
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=dict(model.geometry, file=Path(model.file).name),
        kv_cache_dtype_k=kv,
        kv_cache_dtype_v=kv,
        speculative=speculative,
    )


def serves(model: Model, use_case: str) -> bool:
    """Whether ``model`` may be planned for ``use_case`` (or ``jev``): what
    its record says it serves, or any text use case when it says nothing."""
    if not model.serves:
        return use_case in PLANNED_USE_CASES
    return use_case in model.serves


def token_bytes(model: Model) -> float:
    """The bytes one generated token reads: the whole file of a dense model;
    an MoE's non-expert weights and the share of its experts it routes to.

    The estimate a rung's time is compared by (:data:`CLIMB_BUDGET`): decode
    is bound by the bytes it reads, so two rungs on one machine take time
    roughly as these two figures do.
    """
    row = model.geometry
    experts = int(row.get("bytes_experts") or 0)
    n_expert = int(row.get("n_expert") or 0)
    used = int(row.get("n_expert_used") or 0)
    if experts <= 0 or n_expert <= 0:
        return float(model.size_bytes)
    nonexpert = int(row.get("bytes_nonexpert") or model.size_bytes - experts)
    return nonexpert + experts * min(used, n_expert) / n_expert


@dataclass(frozen=True)
class Sized:
    """One model sized as one unit, by the serving sizer.

    ``unit`` is the serving process, on ``rig``; ``workers`` the processes on
    other machines that lend it their cards. ``role`` is
    :data:`ROLE_ALWAYS_ON` or :data:`ROLE_SLEEPER`; ``jev`` marks the Jev
    unit. ``notes`` is what the plan says beside the unit.
    """

    rig: str
    model: Model
    unit: serving.Unit
    ctx_per_slot: int
    kv: str
    speculative: str
    role: str = ROLE_ALWAYS_ON
    jev: bool = False
    workers: tuple[serving.Unit, ...] = ()
    notes: tuple[str, ...] = ()
    #: The cards of the always-on units this sleeper sleeps when it wakes.
    swaps_with: tuple[str, ...] = ()

    @property
    def units(self) -> tuple[serving.Unit, ...]:
        return (self.unit, *self.workers)

    @property
    def cards(self) -> tuple[Card, ...]:
        return tuple((unit.host, card) for unit in self.units for card in unit.cards)

    @property
    def wholly_on_cards(self) -> bool:
        """No expert of it in host memory."""
        return all(
            unit.fit.ram_gb == 0 and "--n-cpu-moe" not in unit.args
            for unit in self.units
        )

    @property
    def option(self) -> str:
        """The name a question offers it under: where it is, and the model."""
        return f"{self.rig}: {self.model.label}"

    @property
    def description(self) -> str:
        unit = self.unit
        cards = ", ".join(f"{host} card {card}" for host, card in self.cards)
        spill = f", {unit.fit.ram_gb:.1f} GB in RAM" if unit.fit.ram_gb else ""
        return (
            f"{self.model.label} on {cards}: {unit.width.value} slot(s) of "
            f"{self.ctx_per_slot} context, {unit.fit.vram_gb:.1f} GB on the "
            f"card{spill}"
        )


def least_ctx(use_case: str, model: Model) -> int:
    """The least context per slot ``use_case`` plans ``model`` at."""
    wanted = TOP_RUNG_CTX if use_case in LADDER_USE_CASES else STRONG_MIN_CTX
    return min(wanted, model.context_length)


def least_width(use_case: str, users: int) -> int:
    """The fewest slots ``use_case`` plans a unit with: one per user for a
    strong unit, one for a rung (its spare memory becomes slots)."""
    return users if use_case in STRONG_USE_CASES else 1


def _variants(model: Model) -> tuple[tuple[str, str], ...]:
    """The (KV type, speculative head) pairs to try, in the order preferred."""
    heads = (
        (serving.SPECULATIVE_MTP, serving.SPECULATIVE_NONE)
        if model.has_mtp_head
        else (serving.SPECULATIVE_NONE,)
    )
    return tuple((kv, head) for kv in KV_TYPES for head in heads)


#: A placer: a spec, a width (None: as wide as the card allows) and a context
#: per slot in, the processes that serve it out, or :class:`UnitError`.
Placer = Callable[[serving.ModelSpec, int | None, int], tuple[serving.Unit, ...]]


def _gpu(scans: Mapping[str, Scan], card: Card) -> Any:
    rig, index = card
    return next(gpu for gpu in scans[rig].gpus if gpu.index == index)


def free_mib(
    scans: Mapping[str, Scan], card: Card, claims: Mapping[Card, float]
) -> int:
    """What ``card`` has free once ``claims`` (GiB) are taken from it."""
    free: int = _gpu(scans, card).vram.free_mib
    return max(0, free - int(claims.get(card, 0.0) * 1024 + 0.999))


def _card_scan(
    scans: Mapping[str, Scan], card: Card, claims: Mapping[Card, float]
) -> Scan:
    """The rig's scan as one card with what ``claims`` leave of it free."""
    rig, _index = card
    gpu = _gpu(scans, card)
    left = free_mib(scans, card, claims)
    taken = gpu.vram.free_mib - left
    reduced = replace(
        gpu,
        vram=replace(gpu.vram, used_mib=gpu.vram.used_mib + taken, free_mib=left),
    )
    return replace(scans[rig], gpus=(reduced,))


def _on_card(
    scans: Mapping[str, Scan], card: Card, claims: Mapping[Card, float]
) -> Placer:
    """A placer onto one card, with what ``claims`` leave of it.

    The fit is recorded against the card's whole free memory, so units
    planned onto one card are summed against the card and not cut into
    alternatives (:func:`mcgyvr.serving.alternate`): the claims were taken
    into account when each was sized.
    """
    whole = _gpu(scans, card).vram.free_mib / 1024

    def place(
        spec: serving.ModelSpec, width: int | None, ctx: int
    ) -> tuple[serving.Unit, ...]:
        unit = serving.unit_for(
            _card_scan(scans, card, claims),
            spec,
            engine=ENGINE,
            width=width,
            port=FIRST_PORT,
            ctx_per_slot=ctx,
        )
        return (replace(unit, fit=replace(unit.fit, card_free_gb=whole)),)

    return place


def _across(scans: Mapping[str, Scan], shards: Sequence[Card]) -> Placer:
    """A placer split by layer across ``shards``, the first on the head machine."""

    def place(
        spec: serving.ModelSpec, width: int | None, ctx: int
    ) -> tuple[serving.Unit, ...]:
        return serving.split_units(
            scans,
            spec,
            shards=list(shards),
            width=width or 1,
            port=FIRST_PORT,
            ctx_per_slot=ctx,
            engine=ENGINE,
        )

    return place


@dataclass(frozen=True)
class _Fit:
    units: tuple[serving.Unit, ...]
    ctx: int
    kv: str
    head: str
    notes: tuple[str, ...]


def _kv_note(kv: str, ctx: int) -> tuple[str, ...]:
    if kv == KV_F16:
        return ()
    return (
        f"KV cache {kv}: an f16 cache does not fit {ctx} context per slot here, "
        f"and a {kv} cache does",
    )


def _most(
    placer: Placer,
    spec: serving.ModelSpec,
    *,
    width: int | None,
    least: int,
    cap: int,
) -> tuple[int, tuple[serving.Unit, ...]]:
    """The most context per slot ``placer`` admits between ``least`` (which it
    admits) and ``cap``, in :data:`CONTEXT_STEP` steps, and its processes."""
    steps = [least]
    steps += [n for n in range(CONTEXT_STEP, cap, CONTEXT_STEP) if n > least]
    if cap > least:
        steps.append(cap)
    best = placer(spec, width, least)
    low, high, found = 0, len(steps) - 1, 0
    while low < high:
        middle = (low + high + 1) // 2
        try:
            units = placer(spec, width, steps[middle])
        except serving.UnitError:
            high = middle - 1
            continue
        best, found, low = units, middle, middle
    return steps[found], best


def _size(
    placer: Placer,
    model: Model,
    *,
    width: int | None,
    ctx: int,
    cap: int | None = None,
    wholly: bool = False,
) -> _Fit | str:
    """``model`` through ``placer`` at ``ctx`` per slot (the most up to
    ``cap`` that fits, when one is given), trying each KV type and head in
    the order preferred; or why none fits. ``wholly`` refuses a placement
    that puts experts in host memory."""
    why = ""
    for kv, head in _variants(model):
        spec = spec_of(model, kv=kv, speculative=head)
        try:
            units = placer(spec, width, ctx)
        except serving.UnitError as exc:
            why = why or str(exc)
            continue
        if wholly and any(u.fit.ram_gb or "--n-cpu-moe" in u.args for u in units):
            why = why or (
                f"{model.label}: fits only with experts in RAM, and a unit that "
                f"is not asleep holds its model wholly on its card(s)"
            )
            continue
        chosen = ctx
        if cap is not None and cap > ctx:
            chosen, units = _most(placer, spec, width=width, least=ctx, cap=cap)
        return _Fit(units=units, ctx=chosen, kv=kv, head=head, notes=_kv_note(kv, ctx))
    return why or f"{model.label}: does not fit"


def _sized(
    model: Model,
    fit: _Fit,
    *,
    role: str = ROLE_ALWAYS_ON,
    jev: bool = False,
    notes: tuple[str, ...] = (),
) -> Sized:
    head, *workers = fit.units
    return Sized(
        rig=head.host,
        model=model,
        unit=head,
        ctx_per_slot=fit.ctx,
        kv=fit.kv,
        speculative=fit.head,
        role=role,
        jev=jev,
        workers=tuple(workers),
        notes=(*notes, *fit.notes),
    )


def all_cards(scans: Mapping[str, Scan]) -> tuple[Card, ...]:
    return tuple((rig, gpu.index) for rig, scan in scans.items() for gpu in scan.gpus)


def _roomiest(
    scans: Mapping[str, Scan],
    claims: Mapping[Card, float],
    cards: Sequence[Card] | None = None,
) -> Card | None:
    """The card with the most free memory left, the first one on a tie."""
    among = list(cards) if cards is not None else list(all_cards(scans))
    if not among:
        return None
    return max(
        among, key=lambda card: (free_mib(scans, card, claims), -among.index(card))
    )


def size_jev(
    scans: Mapping[str, Scan], model: Model, *, users: int, ctx: int = JEV_CTX
) -> Sized | str:
    """The Jev unit: resident, on the card with the most room, at
    ``ctx`` (:data:`JEV_CTX`) per slot, or the model's own context when
    shorter, and a
    slot per user. Or why it does not fit."""
    card = _roomiest(scans, {})
    if card is None:
        return "no card was read to hold the Jev unit"
    fit = _size(
        _on_card(scans, card, {}),
        model,
        width=users,
        ctx=min(ctx, model.context_length),
        wholly=True,
    )
    if isinstance(fit, str):
        return f"the Jev unit does not fit: {fit}"
    return _sized(model, fit, jev=True)


def _claim(claims: dict[Card, float], one: Sized) -> None:
    for unit in one.units:
        for card in unit.cards:
            claims[(unit.host, card)] = (
                claims.get((unit.host, card), 0.0) + unit.fit.vram_gb
            )


def size_strong(
    scans: Mapping[str, Scan],
    model: Model,
    *,
    users: int,
    ctx: int | None = None,
    claims: Mapping[Card, float] | None = None,
) -> Sized | str:
    """A chat or agent strong unit: one slot per user, at the most context per
    slot that fits (capped at the model's own, never below
    :data:`STRONG_MIN_CTX`), or at ``ctx`` when one is asked.

    It spans every card of every machine not claimed (owner, Round 7), split
    by layer, the serving process on the machine the model is on (else the
    first). Where that does not fit, or the machines cannot be spanned, it
    spans the head machine's cards, else takes the roomiest card left; the
    unit says why it spans less. Or why it does not fit at all.
    """
    taken = dict(claims or {})
    cap = model.context_length
    least = ctx if ctx is not None else min(STRONG_MIN_CTX, cap)
    if least > cap:
        return f"{model.label}: its own context is {cap}, below the {least} asked"
    rigs = [rig for rig, scan in scans.items() if scan.gpus]
    if not rigs:
        return "no card was read"
    present = _present_rig(model)
    if model.present is not None and present not in rigs:
        return f"{model.label}: its machine was not read"
    head = present if present in rigs else rigs[0]
    order = [head, *(rig for rig in rigs if rig != head)]
    free = [
        card
        for rig in order
        for card in all_cards({rig: scans[rig]})
        if card not in taken
    ]
    tries: list[tuple[str, Placer]] = []
    if len(free) >= 2:
        machines = len({rig for rig, _ in free})
        tries.append(
            (f"across {len(free)} cards of {machines} machine(s)", _across(scans, free))
        )
    head_free = [card for card in free if card[0] == head]
    if len(head_free) >= 2 and len(head_free) < len(free):
        tries.append(
            (f"across the {len(head_free)} cards of {head}", _across(scans, head_free))
        )
    single = _roomiest(
        scans, taken, [c for c in all_cards(scans) if c[0] == head or not model.present]
    )
    if single is not None:
        tries.append(
            (f"on {single[0]} card {single[1]}", _on_card(scans, single, taken))
        )
    notes: list[str] = []
    whys: list[str] = []
    for where, placer in tries:
        fit = _size(placer, model, width=users, ctx=least, cap=None if ctx else cap)
        if isinstance(fit, str):
            notes.append(f"not {where}: {fit}")
            whys.append(fit)
            continue
        return _sized(model, fit, notes=tuple(notes))
    return "; ".join(dict.fromkeys(whys))


def _present_rig(model: Model) -> str | None:
    where = model.sources.get("geometry", "")
    prefix = "gguf-header-on-rig:"
    if not where.startswith(prefix):
        return None
    rig, _, _path = where[len(prefix) :].partition(":")
    return rig


def _strength(use_case: str, model: Model) -> tuple[int, float, int]:
    """Smaller is stronger: the use case's first board that scores the model,
    then its figure, then the larger file."""
    order = boards.boards_for(use_case)
    for tier, board in enumerate(order):
        score = next((s for s in model.scores if s.board == board.id), None)
        if score is not None:
            sign = -1.0 if board.better == "higher" else 1.0
            return (tier, sign * float(score.value.value), -model.size_bytes)
    return (len(order), 0.0, -model.size_bytes)


def _rank_key(use_case: str, sized: Sized) -> tuple[Any, ...]:
    """Smaller is better. A strong unit wholly on its cards before one with
    experts in RAM (RAM and CPU units are for sleepers), then strength."""
    wholly = 0 if sized.wholly_on_cards or use_case in LADDER_USE_CASES else 1
    return (wholly, *_strength(use_case, sized.model), sized.option)


def rule(use_case: str) -> str:
    """The deterministic order, in words."""
    named = ", ".join(board.id for board in boards.boards_for(use_case)) or "none"
    if use_case in LADDER_USE_CASES:
        return (
            f"the top rung ranked by the {use_case} boards ({named}), then the "
            f"larger file"
        )
    return (
        f"a model wholly on the card(s) first, then the {use_case} boards "
        f"({named}), then the larger file"
    )


def clear_step(use_case: str, lower: Model, upper: Model, *, step: float) -> bool:
    """Whether ``upper`` is a clear quality step above ``lower`` and not a
    near-copy: a file at least ``step`` times as large, and, where a board of
    the use case scores both, a better score there."""
    if upper.size_bytes < step * lower.size_bytes:
        return False
    for board in boards.boards_for(use_case):
        low = next((s for s in lower.scores if s.board == board.id), None)
        high = next((s for s in upper.scores if s.board == board.id), None)
        if low is None or high is None:
            continue
        if board.better == "higher":
            return float(high.value.value) > float(low.value.value)
        return float(high.value.value) < float(low.value.value)
    return True


@dataclass(frozen=True)
class Choices:
    """What can be planned for one question: the candidates, best first, and
    the models that do not fit, each with the sizer's reason.

    ``key`` is the rig a coding ladder is for, or ``fleet`` for the one chat
    or agent unit. ``fast`` is a coding rig's fast rung, placed before the top
    rung is chosen; ``claims`` what the Jev unit and it hold of each card.
    """

    key: str
    ranked: tuple[Sized, ...]
    dropped: tuple[tuple[str, str], ...]
    fast: Sized | None = None
    claims: Mapping[Card, float] = field(default_factory=dict)

    @property
    def shortlist(self) -> tuple[Sized, ...]:
        return self.ranked[:SHORTLIST]


FLEET = "fleet"


def _fast_rung(
    scans: Mapping[str, Scan],
    rig: str,
    models: Sequence[Model],
    claims: Mapping[Card, float],
    ctx: int | None,
) -> tuple[Sized | None, list[tuple[str, str]]]:
    """The fastest model serving coding that fits wholly on a card of ``rig``
    at the fast rungs' context and one slot. The catalog says which models
    serve coding: that is what "good enough to be useful" is read from.

    When none fits wholly, the fastest that fits with experts in RAM is the
    one rung there is, and it says so: a ladder of one slow rung is a plan,
    nothing is not.
    """
    cards = [card for card in all_cards(scans) if card[0] == rig]
    dropped: list[tuple[str, str]] = []
    order = sorted(models, key=lambda m: (token_bytes(m), m.label))
    for wholly in (True, False):
        for model in order:
            want = ctx if ctx is not None else min(FAST_RUNG_CTX, model.context_length)
            card = _roomiest(scans, claims, cards)
            if card is None:
                return None, dropped
            fit = _size(
                _on_card(scans, card, claims), model, width=1, ctx=want, wholly=wholly
            )
            if isinstance(fit, str):
                if wholly:
                    dropped.append((model.label, f"not a fast rung on {rig}: {fit}"))
                continue
            note = (
                ()
                if wholly
                else (
                    "no model serving coding fits wholly on a card here, so this "
                    "rung holds experts in RAM",
                )
            )
            return _sized(model, fit, notes=note), dropped
    return None, dropped


def _top_option(
    scans: Mapping[str, Scan],
    rig: str,
    model: Model,
    fast: Sized,
    claims: Mapping[Card, float],
    jev_claims: Mapping[Card, float],
    *,
    ctx: int | None,
    sleeper: bool,
    step: float,
) -> Sized | str:
    """``model`` as the top rung of ``rig``'s ladder over ``fast``: always-on
    beside the others when it fits there wholly, else (unless ``sleeper`` is
    off) asleep until needed, sized alone against its card less the Jev
    unit, swapping with the always-on rungs on that card."""
    if model.label == fast.model.label:
        return fast
    if not clear_step("coding", fast.model, model, step=step):
        return (
            f"{model.label}: not a clear step up from the fast rung {fast.model.label}"
        )
    want = ctx if ctx is not None else min(TOP_RUNG_CTX, model.context_length)
    cards = [card for card in all_cards(scans) if card[0] == rig]
    card = _roomiest(scans, claims, cards)
    assert card is not None
    awake = _size(_on_card(scans, card, claims), model, width=1, ctx=want, wholly=True)
    if not isinstance(awake, str):
        return _sized(model, awake)
    if not sleeper:
        return f"{awake}; --priority throughput plans no rung that sleeps"
    alone = _roomiest(scans, jev_claims, cards)
    assert alone is not None
    asleep = _size(_on_card(scans, alone, jev_claims), model, width=1, ctx=want)
    if isinstance(asleep, str):
        return asleep
    partners = tuple(f"{c[0]}:{c[1]}" for c in fast.cards if c == alone)
    return replace(_sized(model, asleep, role=ROLE_SLEEPER), swaps_with=partners)


def assemble(
    use_case: str,
    users: int,
    scans: Mapping[str, Scan],
    models: Mapping[str, Sequence[Model]],
    *,
    ctx_per_slot: int | None = None,
    jev: Sized | None = None,
    priority: str | None = None,
    clear: float = CLEAR_STEP,
) -> dict[str, Choices]:
    """Every model sized for ``use_case``, ranked: one :class:`Choices` for
    the fleet's strong unit (chat, agent), or one per rig for its ladder's top
    rung (coding), around the Jev unit when one is planned."""
    if use_case not in PLANNED_USE_CASES:
        raise PlanError(f"{use_case!r} is not a use case this planner places")
    jev_claims: dict[Card, float] = {}
    if jev is not None:
        _claim(jev_claims, jev)
    if use_case in STRONG_USE_CASES:
        seen: dict[str, Model] = {}
        for rig in scans:
            for model in models.get(rig, ()):
                if serves(model, use_case):
                    seen.setdefault(model.label, model)
        fitting: list[Sized] = []
        dropped: list[tuple[str, str]] = []
        for model in seen.values():
            sized = size_strong(
                scans, model, users=users, ctx=ctx_per_slot, claims=jev_claims
            )
            if isinstance(sized, str):
                dropped.append((model.label, sized))
            else:
                fitting.append(sized)
        ranked = tuple(sorted(fitting, key=lambda one: _rank_key(use_case, one)))
        return {
            FLEET: Choices(
                key=FLEET, ranked=ranked, dropped=tuple(dropped), claims=jev_claims
            )
        }
    out: dict[str, Choices] = {}
    for rig, scan in scans.items():
        coders = [m for m in models.get(rig, ()) if serves(m, use_case)]
        if not scan.gpus:
            out[rig] = Choices(
                key=rig,
                ranked=(),
                dropped=tuple(
                    (m.label, f"{rig}: the scan read no card") for m in coders
                ),
            )
            continue
        fast, dropped = _fast_rung(scans, rig, coders, jev_claims, ctx_per_slot)
        if fast is None:
            out[rig] = Choices(key=rig, ranked=(), dropped=tuple(dropped))
            continue
        claims = dict(jev_claims)
        _claim(claims, fast)
        options: list[Sized] = []
        for model in coders:
            top = _top_option(
                scans,
                rig,
                model,
                fast,
                claims,
                jev_claims,
                ctx=ctx_per_slot,
                sleeper=priority != "throughput",
                step=clear,
            )
            if isinstance(top, str):
                dropped.append((model.label, top))
            else:
                options.append(top)
        ranked = tuple(
            sorted(
                options, key=lambda one: (*_strength(use_case, one.model), one.option)
            )
        )
        out[rig] = Choices(
            key=rig, ranked=ranked, dropped=tuple(dropped), fast=fast, claims=claims
        )
    return out


def _fill(
    scans: Mapping[str, Scan], fast: Sized, others: Sequence[Sized], jev: Sized | None
) -> Sized:
    """``fast`` as wide as its card allows beside the other awake units on it,
    with no expert moved off the card: spare memory becomes slots on the
    cheapest rung (plan section 6.1)."""
    claims: dict[Card, float] = {}
    for one in (*others, *((jev,) if jev else ())):
        if one.role == ROLE_ALWAYS_ON:
            _claim(claims, one)
    (card,) = fast.cards
    placer = _on_card(scans, card, claims)
    spec = spec_of(fast.model, kv=fast.kv, speculative=fast.speculative)
    low, high = 1, serving.MAX_WIDTH
    best = fast.unit
    while low < high:
        middle = (low + high + 1) // 2
        try:
            (unit,) = placer(spec, middle, fast.ctx_per_slot)
        except serving.UnitError:
            high = middle - 1
            continue
        if unit.fit.ram_gb or "--n-cpu-moe" in unit.args:
            high = middle - 1
            continue
        best, low = unit, middle
    return replace(fast, unit=best)


def ladder(
    choices: Choices,
    top: Sized,
    scans: Mapping[str, Scan],
    models: Sequence[Model],
    *,
    jev: Sized | None,
    ctx_per_slot: int | None = None,
    budget: float = CLIMB_BUDGET,
    clear: float = CLEAR_STEP,
) -> tuple[Sized, ...]:
    """``choices``'s rig's ladder with ``top`` as its top rung (owner, Round 7).

    The fast rung, then each bigger model that is a clear step above the rung
    below it and below the top, cheapest first, while it fits awake and
    wholly on a card beside the others and a task that climbs every rung
    still finishes within ``budget`` times the top rung's own time; then the
    top; then the fast rung's spare card memory becomes slots.
    """
    fast = choices.fast
    assert fast is not None
    if top is fast or top.model.label == fast.model.label:
        # One rung is its own top rung: it serves anything decompose emits.
        want = (
            ctx_per_slot
            if ctx_per_slot is not None
            else min(TOP_RUNG_CTX, fast.model.context_length)
        )
        jev_claims: dict[Card, float] = {}
        if jev is not None:
            _claim(jev_claims, jev)
        (card,) = fast.cards
        fit = _size(
            _on_card(scans, card, jev_claims),
            fast.model,
            width=1,
            ctx=want,
            wholly=fast.wholly_on_cards,
        )
        if isinstance(fit, str):
            fast = replace(
                fast,
                notes=(
                    *fast.notes,
                    f"the only rung, at {fast.ctx_per_slot} per slot: a contract "
                    f"larger than that has no rung to go to ({fit})",
                ),
            )
        else:
            fast = _sized(fast.model, fit, notes=fast.notes)
        return (_fill(scans, fast, (), jev),)
    rungs = [fast]
    claims = dict(choices.claims)
    if top.role == ROLE_ALWAYS_ON:
        _claim(claims, top)
    top_time = token_bytes(top.model)
    middle = sorted(
        (
            m
            for m in models
            if serves(m, "coding")
            and m.label not in (fast.model.label, top.model.label)
            and token_bytes(m) < top_time
        ),
        key=lambda m: (token_bytes(m), m.label),
    )
    cards = [card for card in all_cards(scans) if card[0] == choices.key]
    for model in middle:
        below = rungs[-1].model
        if not clear_step("coding", below, model, step=clear):
            continue
        if not clear_step("coding", model, top.model, step=clear):
            continue
        climb = sum(token_bytes(r.model) for r in rungs) + token_bytes(model) + top_time
        if climb > budget * top_time:
            continue
        want = (
            ctx_per_slot
            if ctx_per_slot is not None
            else min(FAST_RUNG_CTX, model.context_length)
        )
        roomiest = _roomiest(scans, claims, cards)
        if roomiest is None:
            break
        card = roomiest
        fit = _size(
            _on_card(scans, card, claims), model, width=1, ctx=want, wholly=True
        )
        if isinstance(fit, str):
            continue
        rung = _sized(model, fit)
        _claim(claims, rung)
        rungs.append(rung)
    filled = _fill(scans, fast, [*rungs[1:], top], jev)
    rungs[0] = filled
    if top.role == ROLE_SLEEPER:
        partners = tuple(
            f"{host}:{card}"
            for rung in rungs
            for host, card in rung.cards
            if (host, card) in top.cards
        )
        top = replace(top, swaps_with=partners)
    return (*rungs, top)


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-") or "model"


def unit_name(rig: str, model: Model, port: int, *, worker: bool = False) -> str:
    """``<rig>-<model>-<port>``: unique in a plan, since a port is one process."""
    return f"{rig}-{_slug(model.stem)}-{'rpc-' if worker else ''}{port}"


def lay_out(
    picks: Sequence[Sized], *, first_port: int = FIRST_PORT
) -> tuple[Sized, ...]:
    """The planned units, each serving process given a port from
    ``first_port`` up on its machine, in the order given."""
    ports: dict[str, int] = {}
    placed: list[Sized] = []
    for one in picks:
        port = ports.get(one.rig, first_port)
        ports[one.rig] = port + 1
        unit = one.unit
        unit = replace(unit, port=port, key=replace(unit.key, port=port))
        if one.model.present is not None:
            path = Path(one.model.present)
            unit = replace(unit, weights=path, args={**unit.args, "--model": str(path)})
        placed.append(replace(one, unit=unit))
    return tuple(placed)


def measured(scan: Scan, read_at: str) -> dict[str, Any]:
    """What a rig measured, as the plan states it."""
    return {
        "read_at": read_at,
        "cards": [
            {
                "index": gpu.index,
                "name": gpu.name,
                "free_mib": gpu.vram.free_mib,
                "total_mib": gpu.vram.total_mib,
            }
            for gpu in scan.gpus
        ],
        "ram_available_gb": None if scan.memory is None else scan.memory.available_gb,
        "ram_total_gb": None if scan.memory is None else scan.memory.total_gb,
        "disk_free_gb": None if scan.disk is None else scan.disk.free_gb,
        "disk_path": None if scan.disk is None else str(scan.disk.path),
    }


def _name(one: Sized) -> str:
    return unit_name(one.rig, one.model, one.unit.port)


def unit_documents(
    one: Sized, by_card: Mapping[str, Sequence[str]]
) -> list[tuple[str, dict[str, Any]]]:
    """One planned unit as the plan states it, every number the sizer's: the
    serving process, then each worker under its own machine. ``by_card``
    names the always-on units on each ``rig:card``, for a sleeper's swaps."""
    unit = one.unit
    model = one.model
    present = model.present is not None
    name = _name(one)
    common = {
        "role": one.role,
        "jev": one.jev,
        "engine": unit.engine,
        "model": {
            "id": model.model_id,
            "quant": model.quant,
            "repo": model.repo,
            "revision": model.revision,
            "file": model.file,
            "size_bytes": model.size_bytes,
            "context_length": model.context_length,
        },
        "ctx_per_slot": one.ctx_per_slot,
        "slots": unit.width.value,
        "kv_cache": {"k": one.kv, "v": one.kv},
        "speculative": one.speculative,
        "sources": dict(model.sources),
    }
    head: dict[str, Any] = {
        "name": name,
        **common,
        "process": unit.role,
        "cards": list(unit.cards),
        "port": unit.port,
        "n_cpu_moe": int(unit.args.get("--n-cpu-moe", "0")),
        "load_mode": unit.fit.load_mode,
        "args": dict(unit.args),
        "fit": {
            "vram_gib": unit.fit.vram_gb,
            "ram_gib": unit.fit.ram_gb,
            "why": unit.fit.why,
        },
        "download": {
            "bytes": 0 if present else model.size_bytes,
            "sha256": model.sha256,
            "present": present,
            "to": str(
                Path(model.present).parent
                if model.present is not None
                else unit.weights.parent
            ),
        },
        "notes": list(one.notes),
    }
    if len(one.cards) > 1:
        head["shards"] = [{"rig": rig, "card": card} for rig, card in one.cards]
    if one.role == ROLE_SLEEPER:
        head["swaps_with"] = sorted(
            {name for card in one.swaps_with for name in by_card.get(card, ())}
        )
    out = [(one.rig, head)]
    for worker in one.workers:
        out.append(
            (
                worker.host,
                {
                    "name": unit_name(worker.host, model, worker.port, worker=True),
                    **common,
                    "process": worker.role,
                    "head": name,
                    "cards": list(worker.cards),
                    "port": worker.port,
                    "n_cpu_moe": 0,
                    "load_mode": None,
                    "args": dict(worker.args),
                    "fit": {
                        "vram_gib": worker.fit.vram_gb,
                        "ram_gib": worker.fit.ram_gb,
                        "why": worker.fit.why,
                    },
                    "download": {
                        "bytes": 0,
                        "sha256": None,
                        "present": False,
                        "to": None,
                    },
                    "notes": [],
                },
            )
        )
    return out


def fleet_name(use_case: str, rigs: Sequence[str]) -> str:
    """The name the fleet's stamp will carry: the use case and its rigs."""
    return "-".join((use_case, *(_slug(rig) for rig in rigs)))


def document(
    *,
    use_case: str | None,
    users: int,
    priority: str | None,
    hosts: Sequence[str],
    scans: Mapping[str, Scan],
    read_at: str,
    laid: Sequence[Sized],
    decision: Mapping[str, str],
    knowledge: Mapping[str, Any] | None,
    models_from: str | None,
    dropped: Sequence[Mapping[str, str]],
    unreachable: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """The plan, version 2 (plan section 7)."""
    rigs: dict[str, Any] = {
        rig: {"measured": measured(scan, read_at), "units": []}
        for rig, scan in scans.items()
    }
    by_card: dict[str, list[str]] = {}
    for one in laid:
        if one.role == ROLE_ALWAYS_ON and not one.jev:
            for host, card in one.cards:
                by_card.setdefault(f"{host}:{card}", []).append(_name(one))
    rungs = sorted(
        (one for one in laid if not one.jev),
        key=lambda one: (one.role == ROLE_SLEEPER, token_bytes(one.model)),
    )
    for one in laid:
        for rig, doc in unit_documents(one, by_card):
            rigs[rig]["units"].append(doc)
    by_rig = {
        rig: sum(u["download"]["bytes"] for u in laid_rig["units"])
        for rig, laid_rig in rigs.items()
    }
    slots = sum(one.unit.width.value for one in rungs if one.role == ROLE_ALWAYS_ON)
    fanout = "idle" if use_case in LADDER_USE_CASES and slots > users else "none"
    sleeper = any(one.role == ROLE_SLEEPER for one in laid)
    return {
        "schema_version": SCHEMA_VERSION,
        "use_case": use_case,
        "priority": priority,
        "users": users,
        "fleet": fleet_name(use_case or "none", [str(h) for h in hosts]),
        "models_from": models_from,
        "knowledge": None if knowledge is None else dict(knowledge),
        "decision": dict(decision),
        "ladder": [_name(one) for one in rungs],
        "fanout": fanout,
        "manager": {
            "enable": sleeper,
            "fanouts": ["none", "idle"] if fanout == "idle" else [],
            "leads": [],
        },
        "rigs": rigs,
        "sample": {
            "use_case": use_case,
            "probes": ["warm_decode", "prefill"],
            "swap_round_trip": sleeper,
        },
        "downloads": {"total_bytes": sum(by_rig.values()), "by_rig": by_rig},
        "dropped": [dict(one) for one in dropped],
        "unreachable": [dict(one) for one in unreachable],
    }


def units_of(
    plan: Mapping[str, Any],
    scans: Mapping[str, Scan],
    models: Sequence[Model] | None = None,
) -> tuple[serving.Unit, ...]:
    """The processes a printed plan names, sized again from what it states.

    Each serving process is asked of the serving sizer again at the plan's
    own card(s), slots, context, KV cache and head: an awake unit against what
    the awake units before it on its card leave, a sleeper against its card
    less the Jev unit, a split across the cards it names. What ``mcgyvr
    emit`` would build from the plan. A unit the sizer refuses now, or a
    model the knowledge no longer holds, is refused by name.
    """
    known = {
        (model.repo, model.revision, model.file): model
        for model in (models if models is not None else library().models)
    }
    docs = [
        unit
        for laid in plan.get("rigs", {}).values()
        for unit in laid.get("units", ())
        if unit.get("process", serving.ROLE_SERVE) == serving.ROLE_SERVE
    ]
    docs.sort(key=lambda u: (not u.get("jev"), u["role"] == ROLE_SLEEPER))
    claims: dict[Card, float] = {}
    jev_claims: dict[Card, float] = {}
    built: list[serving.Unit] = []
    for doc in docs:
        stated = doc["model"]
        model = known.get((stated["repo"], stated["revision"], stated["file"]))
        if model is None:
            raise PlanError(f"{doc['name']}: its model is not in the knowledge")
        spec = spec_of(model, kv=doc["kv_cache"]["k"], speculative=doc["speculative"])
        width, port, ctx = int(doc["slots"]), int(doc["port"]), int(doc["ctx_per_slot"])
        try:
            if "shards" in doc:
                shards = [(s["rig"], int(s["card"])) for s in doc["shards"]]
                units = serving.split_units(
                    scans,
                    spec,
                    shards=shards,
                    width=width,
                    port=port,
                    ctx_per_slot=ctx,
                    engine=ENGINE,
                )
            else:
                rig = next(
                    r for r, laid in plan["rigs"].items() if doc in laid["units"]
                )
                card = (rig, int(doc["cards"][0]))
                taken = jev_claims if doc["role"] == ROLE_SLEEPER else claims
                (unit,) = _on_card(scans, card, taken)(spec, width, ctx)
                units = (replace(unit, port=port, key=replace(unit.key, port=port)),)
        except (serving.UnitError, StopIteration, ValueError) as exc:
            raise PlanError(f"{doc['name']}: {exc}") from exc
        if doc["role"] == ROLE_ALWAYS_ON:
            for unit in units:
                for card_index in unit.cards:
                    key = (unit.host, card_index)
                    claims[key] = claims.get(key, 0.0) + unit.fit.vram_gb
                    if doc.get("jev"):
                        jev_claims[key] = jev_claims.get(key, 0.0) + unit.fit.vram_gb
        built.extend(units)
    return tuple(built)
