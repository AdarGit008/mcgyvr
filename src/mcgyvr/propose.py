""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#
#
#
LOCAL = "local"
API = "api"

#
#ee
#
DEFAULT_HEADROOM_GB = 2.0

#
NO_BACKEND_NOTE = (
    "No local backend is reachable, so the local ladder is empty. "
    "Bind an API source, start a backend and re-run, or name the "
    "rig that serves your models — `mcgyvr setup --host <name>`."
)


@dataclass(frozen=True)
class AvailableSource:
    ""

    name: str
    backend: str
    models_present: tuple[str, ...] = ()
    host: str = ""

    def has(self, model_id: str) -> bool:
        return model_id in self.models_present

    @property
    def is_local(self) -> bool:
        ""
        return self.host in ("", "localhost", "127.0.0.1", "::1", "[::1]")


@dataclass(frozen=True)
class Rung:
    ""

    name: str
    model: str
    source: str
    host: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Rejection:
    ""

    model: str
    reason: str


@dataclass(frozen=True)
class Proposal:
    rungs: tuple[Rung, ...] = ()
    rejected: tuple[Rejection, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def is_local_empty(self) -> bool:
        ""
        return not self.rungs

    def why(self, model_id: str) -> str | None:
        ""
        return next((r.reason for r in self.rejected if r.model == model_id), None)


def binding_name(model_id: str, *, locality: str = LOCAL) -> str:
    ""
    segment = model_id.rsplit("/", 1)[-1].lower()
    segment = re.sub(r"[^a-z0-9.-]+", "-", segment).strip("-")
    return f"{locality}_{segment}"


def _second_listing(model: str, source: AvailableSource, first: Rung) -> str:
    ""
    return (
        f"{model} listed by {source.name} is not bound: its unit name "
        f"{first.name} is taken by {first.model} listed by {first.source}, and "
        f"a ladder lists a unit once, so the first listing is bound. To serve "
        f"both, add the other by hand under a name of its own."
    )


def _unwritable(model: str, source: AvailableSource) -> str:
    ""
    return (
        f"{source.name} lists the id {model!r}, which is blank, has space at "
        f"either end or holds a character that is not printable, so it is not "
        f"bound."
    )


def propose(*, sources: Sequence[AvailableSource]) -> Proposal:
    ""
    rungs: list[Rung] = []
    taken: dict[str, Rung] = {}
    rejected: list[Rejection] = []
    notes: list[str] = []
    for source in sources:
        for model in source.models_present:
            if not model.strip() or model != model.strip() or not model.isprintable():
                reason = _unwritable(model, source)
                rejected.append(Rejection(model, reason))
                notes.append(reason)
                continue
            name = binding_name(model)
            first = taken.get(name)
            if first is not None:
                reason = _second_listing(model, source, first)
                rejected.append(Rejection(model, reason))
                notes.append(reason)
                continue
            rung = Rung(
                name=name,
                model=model,
                source=source.name,
                host=source.host,
                reasons=(f"{source.name} lists it",),
            )
            taken[name] = rung
            rungs.append(rung)

    if not rungs:
        if not sources:
            notes.append(NO_BACKEND_NOTE)
        return Proposal(rejected=tuple(rejected), notes=tuple(notes))
    notes.append(_concurrency_note(rungs))
    return Proposal(rungs=tuple(rungs), rejected=tuple(rejected), notes=tuple(notes))


def _concurrency_note(rungs: Sequence[Rung]) -> str:
    ""
    sources = sorted({rung.source for rung in rungs})
    named = ", ".join(sources)
    return (
        f"Concurrency is written twice and only one of them is here. `init` "
        f"writes width: 1 for every unit on {named}, which is always honest; "
        f"raising it only helps if that backend was started with its "
        f"parallel-slot setting enabled. Same-model concurrency scales only "
        f"with server-side parallelism on, and a single-slot server serializes "
        f"the requests instead of refusing them — so an over-declared capacity "
        f"is not an error you will see, it is a queue you will not. Distinct "
        f"models are a different question: they can run concurrently on one "
        f"card."
    )
