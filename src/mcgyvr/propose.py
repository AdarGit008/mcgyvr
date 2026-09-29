"""Turn what running model servers list into the rungs of a ladder.

Detection says which servers answered and which models each one lists; this
module turns those listings into rungs, one per listed model, and names each
rung. It reads no hardware, no table and no network: everything it needs
arrives as arguments, which is what keeps it testable against machines nobody
here owns.

A ladder is climbed cheapest first, and each rung is meant to do better than
the one below it: a rung that costs more and does no better makes escalation
actively harmful, because it spends the cheaper rung's tokens and its own.
Without a quality figure this module cannot know which of two models does
better, so it judges nothing. The rungs come in the order the models were
found: the machines in the order they were named, then on each machine the
server programs in mcgyvr's fixed probe order, then each server's own listing
order. The user sets the order.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Naming tokens for a ladder unit: <locality>_<model>. There is no role
# token: a binding's role is derived from where it sits in the schema, and
# the ladder holds workers only.
LOCAL = "local"
API = "api"

# CAV-04: a marginal fit degrades rather than failing, which makes it look
# like a working binding. Absolute, not a fraction — see CapabilityTable.
DEFAULT_HEADROOM_GB = 2.0

#: What the proposal says when no model server answered at all.
NO_BACKEND_NOTE = (
    "No local backend is reachable, so the local ladder is empty. "
    "Bind an API source, start a backend and re-run, or name the "
    "rig that serves your models — `mcgyvr init --host <name>`."
)


@dataclass(frozen=True)
class AvailableSource:
    """A model server that answered, and the models it lists, in its order.

    Deliberately a plain input rather than anything imported from detection:
    the proposal is a pure function of the sources, which is what lets it be
    tested against machines nobody here owns.
    """

    name: str
    backend: str
    models_present: tuple[str, ...] = ()
    host: str = ""

    def has(self, model_id: str) -> bool:
        return model_id in self.models_present

    @property
    def is_local(self) -> bool:
        """Whether this source runs on the machine doing the proposing.

        An unnamed host means local.
        """
        return self.host in ("", "localhost", "127.0.0.1", "::1", "[::1]")


@dataclass(frozen=True)
class Rung:
    """One listed model, bound, with why."""

    name: str
    model: str
    source: str
    host: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Rejection:
    """A listing that was not bound, and why not."""

    model: str
    reason: str


@dataclass(frozen=True)
class Proposal:
    rungs: tuple[Rung, ...] = ()
    rejected: tuple[Rejection, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def is_local_empty(self) -> bool:
        """Whether no listed model could be bound. Not an error condition."""
        return not self.rungs

    def why(self, model_id: str) -> str | None:
        """The reason a listing of a model was not bound, if one was not."""
        return next((r.reason for r in self.rejected if r.model == model_id), None)


def binding_name(model_id: str, *, locality: str = LOCAL) -> str:
    """Name a ladder unit ``<locality>_<model>``.

    The name is what everything downstream refers to a unit by — routing
    policy, telemetry — so it says what the thing IS (local or behind an
    API) rather than where it sits in an ordering. An index-based name would
    silently change meaning when a rung is inserted, which for a policy
    reference is a rename that looks like an edit.

    There is no role token. A binding's role is derived from where it sits
    in the schema: under ``orchestrator`` it is the orchestrator, under
    ``verifier`` it is the verifier, and in the ladder it is a worker. Only
    units carry a name, so a role token would be constant across every name
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


def _second_listing(model: str, source: AvailableSource, first: Rung) -> str:
    """Why a listing that mints a name already taken is not bound.

    Both models and both servers are named, because the two listings may be
    one model on two servers or two models whose ids end the same way, and
    the reader cannot tell which from the shared name alone.
    """
    return (
        f"{model} listed by {source.name} is not bound: its unit name "
        f"{first.name} is taken by {first.model} listed by {first.source}, and "
        f"a ladder lists a unit once, so the first listing is bound. To serve "
        f"both, add the other by hand under a name of its own."
    )


def _unwritable(model: str, source: AvailableSource) -> str:
    """Why a listed id that is blank or holds a control character is not bound.

    A blank id names nothing a unit could serve, and the loader refuses a unit
    whose model is empty. An id with a control character, a line break among
    them, may not read back from the file as the same id, so a unit bound to
    it could name another model.
    """
    return (
        f"{source.name} lists the id {model!r}, which is blank or holds a "
        f"control character, so it is not bound."
    )


def propose(*, sources: Sequence[AvailableSource]) -> Proposal:
    """One rung per model a source lists, in the order the sources come.

    Sources are taken in the order given and each source's models in its own
    listing order. A listing that mints a unit name an earlier one took is
    not bound, and neither is an id that is blank or holds a control
    character; the proposal names each.

    Never raises. No source, or sources that list nothing, give an empty
    ladder: a coherent API-only install, not a failure. The note on
    concurrency is about the units bound, so it is given only when one is.
    """
    rungs: list[Rung] = []
    taken: dict[str, Rung] = {}
    rejected: list[Rejection] = []
    notes: list[str] = []
    for source in sources:
        for model in source.models_present:
            if not model.strip() or not model.isprintable():
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
    """What raising a unit's ``width`` does and does not buy (CON-02).

    Stated in the proposal because this is the moment an operator decides what
    the machine is for, and because the failure it warns about is invisible
    afterwards: a single-slot server handed four concurrent requests **serializes
    them rather than refusing them**, so an over-declared capacity looks exactly
    like a source that is merely slow.
    """
    sources = sorted({rung.source for rung in rungs})
    named = ", ".join(sources)
    return (
        f"Concurrency is written twice and only one of them is here. `init` "
        f"writes width: 1 for every unit on {named}, which is always honest; "
        f"raising it only helps if that backend was started with its "
        f"parallel-slot setting enabled. CON-02 records that same-model "
        f"concurrency scales only with server-side parallelism on, and that a "
        f"single-slot server serializes the requests instead of refusing them — "
        f"so an over-declared capacity is not an error you will see, it is a "
        f"queue you will not. Distinct models are a different question: CON-01 "
        f"records them running concurrently on one card."
    )
