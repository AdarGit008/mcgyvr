"""Turn the models each reachable source lists into ladder rungs.

A source reports the model ids it has in `models_present`; every id becomes one
rung whose unit name `binding_name` derives from the id, provided the id is
printable and that name is still free. Ids that cannot be bound are kept as
`Rejection`s with the sentence explaining why, and the same sentences go into
`notes`, which also carry any closing advice. Nothing here dispatches a request
or writes config: a `Proposal` is data for whoever builds the ladder.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# The locality a binding name is prefixed with: `local` for a source on this
# machine, `api` for one reached over the network. `binding_name` defaults to
# `LOCAL` and `propose` never passes another, so every rung it builds is local.
LOCAL = "local"
API = "api"

# Gigabytes kept free on a local card when a model is checked for fit, so the
# footprint is not measured against the whole of the memory.
# ee
# `propose` declares the figure but does not read it: fit is not judged here.
DEFAULT_HEADROOM_GB = 2.0

# What `propose` puts in `notes` when it was handed no sources at all, so an
# empty proposal can say why it is empty and what the caller can do about it.
NO_BACKEND_NOTE = (
    "No local backend is reachable, so the local ladder is empty. "
    "Bind an API source, start a backend and re-run, or name the "
    "rig that serves your models — `mcgyvr setup --host <name>`."
)


@dataclass(frozen=True)
class AvailableSource:
    """A source that can be reached and the model ids it lists.

    `name` is how the config names the source and becomes a rung's `source`;
    `backend` labels the server behind it and is not read here;
    `models_present` holds the ids the source reported, in its own order; and
    `host` is where it is reached. `has` tests membership of that listing, and
    `is_local` decides from `host` alone.
    """

    name: str
    backend: str
    models_present: tuple[str, ...] = ()
    host: str = ""

    def has(self, model_id: str) -> bool:
        return model_id in self.models_present

    @property
    def is_local(self) -> bool:
        """Whether the source sits on this machine.

        True when `host` is empty or one of the loopback names `localhost`,
        `127.0.0.1`, `::1` or `[::1]`; any other host counts as remote.
        """
        return self.host in ("", "localhost", "127.0.0.1", "::1", "[::1]")


@dataclass(frozen=True)
class Rung:
    """One step of the proposed ladder.

    The unit `name` it binds, the `model` id sent to that unit, the `source`
    the id was listed by, the `host` that source is reached at, and the
    `reasons` the rung is on the ladder — `propose` fills that with the
    listing itself.
    """

    name: str
    model: str
    source: str
    host: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Rejection:
    """A model id left out of the ladder, with the sentence saying why.

    `Proposal.why` finds one by model id, and the same sentence is usually in
    the proposal's notes as well.
    """

    model: str
    reason: str


@dataclass(frozen=True)
class Proposal:
    rungs: tuple[Rung, ...] = ()
    rejected: tuple[Rejection, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def is_local_empty(self) -> bool:
        """Whether the proposal holds no rungs at all.

        Read straight from `rungs`, so the `local` in the name is not tested:
        the shared reasons for the emptiness are in `notes`.
        """
        return not self.rungs

    def why(self, model_id: str) -> str | None:
        """The rejection reason recorded for `model_id`.

        `None` when the id was bound or never listed at all.
        """
        return next((r.reason for r in self.rejected if r.model == model_id), None)


def binding_name(model_id: str, *, locality: str = LOCAL) -> str:
    """The unit name a model id binds to under a locality.

    The id's last `/`-separated segment, lowercased, with each run of
    characters outside `[a-z0-9.-]` replaced by one `-` and any `-` at either
    end stripped, then prefixed with the locality: `Qwen/Qwen2.5-7B` yields
    `local_qwen2.5-7b`. Different ids can therefore land on one name, which
    `propose` rejects rather than binding twice.
    """
    segment = model_id.rsplit("/", 1)[-1].lower()
    segment = re.sub(r"[^a-z0-9.-]+", "-", segment).strip("-")
    return f"{locality}_{segment}"


def _second_listing(model: str, source: AvailableSource, first: Rung) -> str:
    """The rejection reason for a model whose binding name is already taken.

    `first` is the rung that holds the name; the sentence names both models and
    says a ladder lists a unit once, so the second model has to be added by
    hand under a name of its own.
    """
    return (
        f"{model} listed by {source.name} is not bound: its unit name "
        f"{first.name} is taken by {first.model} listed by {first.source}, and "
        f"a ladder lists a unit once, so the first listing is bound. To serve "
        f"both, add the other by hand under a name of its own."
    )


def _unwritable(model: str, source: AvailableSource) -> str:
    """The rejection reason for an id that cannot name a unit.

    Covers the three cases `propose` tests: the id is blank, it has space at
    either end, or it holds a character that is not printable.
    """
    return (
        f"{source.name} lists the id {model!r}, which is blank, has space at "
        f"either end or holds a character that is not printable, so it is not "
        f"bound."
    )


def propose(*, sources: Sequence[AvailableSource]) -> Proposal:
    """Bind each listed model to a rung, or reject it with a reason.

    Sources and their models are visited in the order given, and the first
    model to claim a binding name keeps it. An id that is blank, space-padded
    or non-printable is rejected as unwritable, and a later model whose name is
    already taken is rejected as a second listing; both land in `rejected` and
    their sentences in `notes`. Rungs are never dropped, so the result is empty
    only when nothing bound: with sources given it then carries just the
    rejection notes, and with no sources at all it carries `NO_BACKEND_NOTE`.
    A non-empty proposal ends with the note from `_concurrency_note`.
    """
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
    """The closing note of a non-empty proposal.

    It names the distinct sources the rungs come from, sorted, so the reader
    knows which units get `width: 1` written by `init`, and adds that raising
    the figure only helps when the backend was started with its parallel-slot
    setting enabled — an over-declared capacity shows up as a queue, not an
    error.
    """
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
