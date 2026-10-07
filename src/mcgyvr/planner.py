"""The planner behind ``mcgyvr recommend``: units per rig, sized by the serving sizer.

Owner, Round 2 (2026-10-07): "Plan shape: a FULL LADDER PER RIG. Each unit has
rig, card(s), model, quant, context, slots, and role (always-on /
sleeps-until-needed / Jev). Sized with the product's existing serving sizer
(serving.fit, sharding.py, vramfit: several models per card, multi-card split,
MoE experts in RAM), not recommend's own _fits."

So nothing here prices a card. A model is one GGUF file with its header row
(:mod:`mcgyvr.knowledge.geometry`, or the header read on the rig for a file
already there), and a unit is what :func:`mcgyvr.serving.unit_for` builds for
it on the measured card, or :func:`mcgyvr.serving.split_unit` across the rig's
cards: the same law, the same argv, the same refusals ``mcgyvr emit`` gives.
What this module decides is only what the sizer is asked:

* **the shape the use case allows** (plan section 3). ``chat`` and ``agent``
  get one strong unit per rig, one slot per user, at the most context per
  slot that fits, capped at the model's own context, and never below
  :data:`STRONG_MIN_CTX`. ``coding`` gets a ladder; its top rung is sized at
  :data:`TOP_RUNG_CTX` per slot and its spare card memory becomes slots (the
  sizer's own width rule: as wide as fits without moving one more expert
  block off the card). ``media-gen`` is not planned here yet.
* **the levers** (section 5). The KV cache is f16, and q8_0 only when f16
  misses the context the use case needs; the plan says so. The model's MTP
  head is run as its draft only when its header carries one and it fits. An
  MoE's experts go to RAM at the lowest offload the card admits, which is the
  sizer's own floor. A model no card holds is split across the rig's cards.
* **the order the candidates are offered in**: the use case's boards
  (:func:`mcgyvr.knowledge.boards.boards_for`), then the larger file. The
  first :data:`SHORTLIST` are what a Jev unit may name; with no Jev the first
  is the pick. Nothing a model answers becomes a number.

The plan document is version 2 (plan section 7); :func:`document` writes it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
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

#: The use cases planned as one strong unit per rig, and as a ladder.
STRONG_USE_CASES = ("chat", "agent")
LADDER_USE_CASES = ("coding",)
PLANNED_USE_CASES = (*STRONG_USE_CASES, *LADDER_USE_CASES)

#: What a unit is to its fleet (plan section 7).
ROLE_ALWAYS_ON = "always-on"
ROLE_SLEEPER = "sleeps-until-needed"
ROLE_JEV = "jev"

#: The coding top rung's context per slot, owner Round 4 ("top/strong rung
#: 32k"): the ceiling decompose may raise a contract's prompt to
#: (``orchestrator/decompose.py``), so it serves anything decompose emits.
TOP_RUNG_CTX = 32768
#: The least context per slot a chat or agent strong unit is planned at, when
#: the model's own context allows it: the coding fast rungs' window (owner
#: Round 4, "fast rungs 8k"), so no strong unit holds less than a fast rung.
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

#: The KV cache types: f16, and q8_0 only when f16 misses the context needed.
KV_F16 = "f16"
KV_Q8 = "q8_0"
KV_TYPES = (KV_F16, KV_Q8)

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
    ``context``, ``geometry``); ``scores`` are its board scores.
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


@dataclass(frozen=True)
class Sized:
    """One model sized as one unit on one rig, by the serving sizer."""

    rig: str
    model: Model
    unit: serving.Unit
    ctx_per_slot: int
    kv: str
    speculative: str
    role: str
    #: What the plan says beside the unit: why its cache is not f16.
    notes: tuple[str, ...] = ()

    @property
    def option(self) -> str:
        """The name a question offers it under: the rig and the model."""
        return f"{self.rig}: {self.model.label}"

    @property
    def description(self) -> str:
        unit = self.unit
        cards = ", ".join(str(card) for card in unit.cards)
        spill = f", {unit.fit.ram_gb:.1f} GB in RAM" if unit.fit.ram_gb else ""
        return (
            f"{self.model.label} on {self.rig} card(s) {cards}: "
            f"{unit.width.value} slot(s) of {self.ctx_per_slot} context, "
            f"{unit.fit.vram_gb:.1f} GB on the card{spill}"
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


def _on_one_card(
    scan: Scan, spec: serving.ModelSpec, *, width: int | None, ctx: int
) -> serving.Unit:
    return serving.unit_for(
        scan, spec, engine=ENGINE, width=width, port=FIRST_PORT, ctx_per_slot=ctx
    )


def _split(
    scan: Scan, spec: serving.ModelSpec, *, width: int | None, ctx: int
) -> serving.Unit:
    return serving.split_unit(
        scan,
        spec,
        cards=tuple(gpu.index for gpu in scan.gpus),
        width=width or 1,
        port=FIRST_PORT,
        ctx_per_slot=ctx,
        engine=ENGINE,
    )


def _placed(
    scan: Scan, spec: serving.ModelSpec, *, width: int | None, ctx: int
) -> tuple[serving.Unit, Any] | str:
    """The unit on the roomiest card, else split across the rig's cards, with
    the placer that held; or why neither does."""
    try:
        return _on_one_card(scan, spec, width=width, ctx=ctx), _on_one_card
    except serving.UnitError as exc:
        why = str(exc)
    if len(scan.gpus) >= 2 and spec.speculative == serving.SPECULATIVE_NONE:
        try:
            return _split(scan, spec, width=width, ctx=ctx), _split
        except serving.UnitError as exc:
            why = f"{why}; split across its {len(scan.gpus)} cards: {exc}"
    return why


def _most_context(
    scan: Scan,
    spec: serving.ModelSpec,
    placer: Any,
    *,
    width: int,
    least: int,
    cap: int,
) -> tuple[int, serving.Unit]:
    """The most context per slot ``placer`` admits between ``least`` (which
    it admits) and ``cap``, in :data:`CONTEXT_STEP` steps, and its unit."""
    steps = [least]
    steps += [n for n in range(CONTEXT_STEP, cap, CONTEXT_STEP) if n > least]
    if cap > least:
        steps.append(cap)
    best = placer(scan, spec, width=width, ctx=least)
    low, high = 0, len(steps) - 1
    found = 0
    while low < high:
        middle = (low + high + 1) // 2
        try:
            unit = placer(scan, spec, width=width, ctx=steps[middle])
        except serving.UnitError:
            high = middle - 1
            continue
        best, found, low = unit, middle, middle
    return steps[found], best


def _kv_note(kv: str, ctx: int) -> tuple[str, ...]:
    if kv == KV_F16:
        return ()
    return (
        f"KV cache {kv}: an f16 cache does not fit {ctx} context per slot here, "
        f"and a {kv} cache does",
    )


def size_strong(
    rig: str, scan: Scan, model: Model, *, users: int, ctx: int | None = None
) -> Sized | str:
    """A chat or agent strong unit: one slot per user, at the most context per
    slot that fits (capped at the model's own), or at ``ctx`` when one is
    asked. Or why it does not fit."""
    cap = model.context_length
    least = ctx if ctx is not None else min(STRONG_MIN_CTX, cap)
    if least > cap:
        return f"{model.label}: its own context is {cap}, below the {least} asked"
    why = ""
    for kv, head in _variants(model):
        spec = spec_of(model, kv=kv, speculative=head)
        placed = _placed(scan, spec, width=users, ctx=least)
        if isinstance(placed, str):
            why = why or placed
            continue
        unit, placer = placed
        chosen = least
        if ctx is None:
            chosen, unit = _most_context(
                scan, spec, placer, width=users, least=least, cap=cap
            )
        return Sized(
            rig=rig,
            model=model,
            unit=unit,
            ctx_per_slot=chosen,
            kv=kv,
            speculative=head,
            role=ROLE_ALWAYS_ON,
            notes=_kv_note(kv, least),
        )
    return why


def size_top(
    rig: str, scan: Scan, model: Model, *, ctx: int | None = None
) -> Sized | str:
    """A coding top rung at :data:`TOP_RUNG_CTX` per slot (or ``ctx``, or the
    model's own context when shorter), with its spare card memory as slots.
    Or why it does not fit."""
    cap = model.context_length
    want = ctx if ctx is not None else min(TOP_RUNG_CTX, cap)
    if want > cap:
        return f"{model.label}: its own context is {cap}, below the {want} asked"
    why = ""
    for kv, head in _variants(model):
        spec = spec_of(model, kv=kv, speculative=head)
        placed = _placed(scan, spec, width=None, ctx=want)
        if isinstance(placed, str):
            why = why or placed
            continue
        unit, _placer = placed
        return Sized(
            rig=rig,
            model=model,
            unit=unit,
            ctx_per_slot=want,
            kv=kv,
            speculative=head,
            role=ROLE_ALWAYS_ON,
            notes=_kv_note(kv, want),
        )
    return why


def _rank_key(use_case: str, sized: Sized) -> tuple[int, float, int, str]:
    """Smaller is better: the use case's first board that scores the model,
    then its figure, then the larger file, then the name."""
    order = boards.boards_for(use_case)
    model = sized.model
    for tier, board in enumerate(order):
        score = next((s for s in model.scores if s.board == board.id), None)
        if score is not None:
            sign = -1.0 if board.better == "higher" else 1.0
            return (
                tier,
                sign * float(score.value.value),
                -model.size_bytes,
                sized.option,
            )
    return (len(order), 0.0, -model.size_bytes, sized.option)


def rule(use_case: str) -> str:
    """The deterministic order, in words."""
    named = ", ".join(board.id for board in boards.boards_for(use_case)) or "none"
    return f"ranked by the {use_case} boards ({named}), then the larger file"


@dataclass(frozen=True)
class Choices:
    """What one rig can hold: the fitting candidates, best first, and the
    models that do not fit there, each with the sizer's reason."""

    rig: str
    ranked: tuple[Sized, ...]
    dropped: tuple[tuple[str, str], ...]

    @property
    def shortlist(self) -> tuple[Sized, ...]:
        return self.ranked[:SHORTLIST]


def assemble(
    use_case: str,
    users: int,
    scans: Mapping[str, Scan],
    models: Mapping[str, Sequence[Model]],
    *,
    ctx_per_slot: int | None = None,
) -> dict[str, Choices]:
    """Every model sized on every rig for ``use_case``, ranked."""
    if use_case not in PLANNED_USE_CASES:
        raise PlanError(f"{use_case!r} is not a use case this planner places")
    out: dict[str, Choices] = {}
    for rig, scan in scans.items():
        fitting: list[Sized] = []
        dropped: list[tuple[str, str]] = []
        if not scan.gpus:
            for model in models.get(rig, ()):
                dropped.append((model.label, f"{rig}: the scan read no card"))
            out[rig] = Choices(rig=rig, ranked=(), dropped=tuple(dropped))
            continue
        for model in models.get(rig, ()):
            if use_case in STRONG_USE_CASES:
                sized = size_strong(rig, scan, model, users=users, ctx=ctx_per_slot)
            else:
                sized = size_top(rig, scan, model, ctx=ctx_per_slot)
            if isinstance(sized, str):
                dropped.append((model.label, sized))
            else:
                fitting.append(sized)
        ranked = tuple(sorted(fitting, key=lambda one: _rank_key(use_case, one)))
        out[rig] = Choices(rig=rig, ranked=ranked, dropped=tuple(dropped))
    return out


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-") or "model"


def unit_name(rig: str, model: Model, port: int) -> str:
    """``<rig>-<model>-<port>``: unique in a plan, since a port is one process."""
    return f"{rig}-{_slug(model.stem)}-{port}"


def lay_out(
    picks: Mapping[str, Sequence[Sized]], *, first_port: int = FIRST_PORT
) -> dict[str, tuple[Sized, ...]]:
    """Each rig's picked units, given ports from ``first_port`` up."""
    laid: dict[str, tuple[Sized, ...]] = {}
    for rig, chosen in picks.items():
        placed: list[Sized] = []
        for offset, one in enumerate(chosen):
            port = first_port + offset
            unit = one.unit
            unit = replace(unit, port=port, key=replace(unit.key, port=port))
            if one.model.present is not None:
                path = Path(one.model.present)
                unit = replace(
                    unit, weights=path, args={**unit.args, "--model": str(path)}
                )
            placed.append(replace(one, unit=unit))
        laid[rig] = tuple(placed)
    return laid


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


def unit_document(one: Sized) -> dict[str, Any]:
    """One planned unit, as the plan states it: every number the sizer's."""
    unit = one.unit
    model = one.model
    present = model.present is not None
    sources = dict(model.sources)
    return {
        "name": unit_name(one.rig, model, unit.port),
        "role": one.role,
        "cards": list(unit.cards),
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
        "port": unit.port,
        "ctx_per_slot": one.ctx_per_slot,
        "slots": unit.width.value,
        "kv_cache": {"k": one.kv, "v": one.kv},
        "n_cpu_moe": int(unit.args.get("--n-cpu-moe", "0")),
        "speculative": one.speculative,
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
        "sources": sources,
        "notes": list(one.notes),
    }


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
    laid: Mapping[str, Sequence[Sized]],
    decision: Mapping[str, str],
    knowledge: Mapping[str, Any] | None,
    models_from: str | None,
    dropped: Sequence[Mapping[str, str]],
    unreachable: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """The plan, version 2 (plan section 7)."""
    rigs: dict[str, Any] = {}
    ladder: list[str] = []
    by_rig: dict[str, int] = {}
    slots = 0
    for rig, scan in scans.items():
        units = [unit_document(one) for one in laid.get(rig, ())]
        rigs[rig] = {"measured": measured(scan, read_at), "units": units}
        ladder.extend(unit["name"] for unit in units)
        by_rig[rig] = sum(unit["download"]["bytes"] for unit in units)
        slots += sum(unit["slots"] for unit in units if unit["role"] != ROLE_JEV)
    fanout = "idle" if use_case in LADDER_USE_CASES and slots > users else "none"
    sleeper = any(
        unit["role"] == ROLE_SLEEPER for rig in rigs.values() for unit in rig["units"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "use_case": use_case,
        "priority": priority,
        "users": users,
        "fleet": fleet_name(use_case or "none", [str(h) for h in hosts]),
        "models_from": models_from,
        "knowledge": None if knowledge is None else dict(knowledge),
        "decision": dict(decision),
        "ladder": ladder,
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
    """The units a printed plan names, sized again from what it states.

    Each unit is asked of the serving sizer again at the plan's own card(s),
    slots, context, KV cache and head, against the full measured card: what
    ``mcgyvr emit`` would build from it. A unit the sizer refuses now, or a
    model the knowledge no longer holds, is refused by name.
    """
    known = {
        (model.repo, model.revision, model.file): model
        for model in (models if models is not None else library().models)
    }
    built: list[serving.Unit] = []
    for rig, laid in plan.get("rigs", {}).items():
        scan = scans.get(rig)
        if scan is None:
            raise PlanError(f"{rig}: not scanned, so its units cannot be sized again")
        for unit in laid.get("units", ()):
            stated = unit["model"]
            model = known.get((stated["repo"], stated["revision"], stated["file"]))
            if model is None:
                raise PlanError(f"{unit['name']}: its model is not in the knowledge")
            spec = spec_of(
                model, kv=unit["kv_cache"]["k"], speculative=unit["speculative"]
            )
            cards = tuple(int(card) for card in unit["cards"])
            try:
                if len(cards) > 1:
                    sized = serving.split_unit(
                        scan,
                        spec,
                        cards=cards,
                        width=int(unit["slots"]),
                        port=int(unit["port"]),
                        ctx_per_slot=int(unit["ctx_per_slot"]),
                        engine=ENGINE,
                    )
                else:
                    (gpu,) = [g for g in scan.gpus if g.index == cards[0]]
                    sized = serving.unit_for(
                        replace(scan, gpus=(gpu,)),
                        spec,
                        engine=ENGINE,
                        width=int(unit["slots"]),
                        port=int(unit["port"]),
                        ctx_per_slot=int(unit["ctx_per_slot"]),
                    )
            except (serving.UnitError, ValueError) as exc:
                raise PlanError(f"{unit['name']}: {exc}") from exc
            built.append(sized)
    return tuple(built)
