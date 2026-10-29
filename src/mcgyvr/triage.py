"""Ask the jev role which rung a contract's climb starts on.

With `triage: jev` in the config, `escalate` asks this before anything is
spent: one typed `Choice` put to the unit bound to the `jev` role, whose state
is the contract itself and the ladder it may climb, and whose options are
exactly that ladder's rungs. The rung picked is where the climb starts; the
rungs below it are skipped, never spent, and escalation goes on upward from it.

Triage and fan-out compose in that order: triage cuts the ladder to begin on
the rung it picked, and fan-out then reads what is left, so `idle` and `full`
may still start the climb on a free rung above the pick, never below it and
never on a priced api rung.

Triage never fails a contract. With no jev unit bound, with one that cannot be
reached, or with a reply that cannot be read, the answer is a `Triage` that
names no rung and says why, and the climb starts where it would have without
triage. With `triage: none` (unset is `jev` only under `mcgyvr-code` while a
Jev unit is on), nothing is asked and nothing is recorded.

Triage can also be decided ahead of time. `triage_ahead` asks jev about a set
of contracts once, outside any run, and returns one record per contract; a
contract that then states the chosen rung as its `start_rung` starts there on
every later run and jev is not asked again. A stated rung is the one thing here
that is refused rather than fallen back from: a rung the ladder does not list,
or one this contract's climb does not offer, raises `RouteError` before
anything is dispatched, since starting elsewhere would quietly run a different
experiment from the one that was frozen.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any

from mcgyvr import decision
from mcgyvr.route import RouteError, family_of

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap

#: The name the question is asked under, which the prompt shows the model.
QUESTION = "start"

#: The question put to jev. The state above it holds the contract and the
#: ladder, cheapest first, with what this install states about each unit.
INSTRUCTIONS = (
    "The contract is about to be dispatched. The ladder lists the units that "
    "can take it, cheapest first, with what is known about each. Work starts "
    "on the unit you pick and moves to a dearer one only if it fails. What is "
    "the smallest unit that can do this job?"
)


@dataclass(frozen=True)
class Triage:
    """What jev was asked about where a climb starts, and what came of it.

    `rung` is the rung jev picked, and is `None` exactly when its pick did not
    stand; `fallback` then says why, and the climb started where it would have
    without triage. `probabilities` holds every rung's probability and
    `confidence` how decided the answer was, both empty on a fallback. `model`
    is the model the jev role asked, when one was. `source` is `jev` for a
    decision asked for this run and `contract` for a rung the contract stated
    as its `start_rung`, which carries no probabilities because none were read
    here.
    """

    rung: str | None
    probabilities: Mapping[str, float] = field(default_factory=dict)
    confidence: float | None = None
    model: str = ""
    fallback: str = ""
    source: str = "jev"

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def triage_for(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    rungs: Sequence[str],
    *,
    capacity: Capacity | None = None,
) -> Triage | None:
    """Where this contract's climb over `rungs` starts, as a `Triage`, or `None`.

    A contract that states a `start_rung` starts there and nothing is asked;
    one the climb does not offer raises `RouteError` (see `stated`). Otherwise
    `triage: jev` asks jev (see `ask`), and `triage: none` answers `None`.
    """
    if contract.start_rung:
        return stated(config, pool, contract, rungs)
    if config.get("triage", "none") != "jev":
        return None
    return ask(config, pool, contract, rungs, capacity=capacity)


def stated(
    config: Config, pool: SourceMap, contract: Contract, rungs: Sequence[str]
) -> Triage:
    """The record of the rung the contract states as its `start_rung`.

    Raises `RouteError` naming what is wrong when the rung is not one of
    `rungs`: not on the ladder at all, on it but skipped by the pool, or on it
    and below the family this contract's climb starts on.
    """
    rung = contract.start_rung
    if rung in rungs:
        return Triage(rung=rung, source="contract")
    head = f"contract {contract.id!r} states start_rung {rung!r}"
    if config.ladder.get(rung) is None:
        offered = ", ".join(config.ladder.names) or "none"
        raise RouteError(
            f"{head}, which the ladder does not list. Ladder: {offered}. Triage "
            f"it again against this ladder, or remove `start_rung`."
        )
    skipped = next((s for s in pool.skipped if s.name == rung), None)
    if skipped is not None:
        raise RouteError(
            f"{head}, which is on the ladder but not available: {skipped.reason}"
        )
    offered = ", ".join(rungs) or "none"
    raise RouteError(
        f"{head}, which this contract's climb does not offer. It climbs: {offered}."
    )


def ask(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    rungs: Sequence[str],
    *,
    capacity: Capacity | None = None,
) -> Triage:
    """Ask jev which of `rungs` the climb starts on.

    `rungs` is the climb in the order it is taken, cheapest first. They are the
    options, each with its unit's model, family, window and reply room in the
    state where the unit states them. Any failure to ask or to read the answer
    is caught and returned as a fallback naming it, never raised.
    """
    if not rungs:
        return Triage(rung=None, fallback="the climb offers no rung to choose from")
    question = decision.Choice(
        instructions=INSTRUCTIONS,
        options={name: f"{name} ({config.units[name].model})" for name in rungs},
    )
    state = {
        "contract": contract.as_dict(),
        "ladder": [_facts(config, name) for name in rungs],
    }
    try:
        answered = decision.classify_role(
            pool, decision.JEV_ROLE, state, {QUESTION: question}, capacity=capacity
        )
    except Exception as exc:
        return Triage(
            rung=None,
            fallback=(
                f"jev could not be asked or its reply could not be read "
                f"({type(exc).__name__}: {exc}), so the climb starts on its "
                f"first rung"
            ),
        )
    if answered is None:
        return Triage(
            rung=None,
            fallback=(
                "no unit is bound to the jev role, so the climb starts on its "
                "first rung"
            ),
        )
    answer = answered.answers[QUESTION]
    assert isinstance(answer, decision.ChoiceAnswer)  # a Choice is answered so
    return Triage(
        rung=answer.choice,
        probabilities=dict(answer.probabilities),
        confidence=answer.confidence,
        model=pool.role_model(decision.JEV_ROLE) or "",
    )


def triage_ahead(
    config: Config,
    pool: SourceMap,
    contracts: Iterable[Contract],
    *,
    capacity: Capacity | None = None,
) -> dict[str, Triage]:
    """Ask jev about each contract now, once, keyed by contract id.

    Whatever the config's `triage` says, every contract is asked about the
    climb its own ascent offers, as a run would, with any `start_rung` it
    already states left out of what jev reads. Each record names the rung,
    the probabilities and the confidence, or the fallback that stood in; a
    caller stores the rung as the contract's `start_rung` to have every later
    run start there without asking.
    """
    # Imported here: `mcgyvr.escalate` imports this module for the live path.
    from mcgyvr.escalate import ascent

    return {
        each.id: ask(
            config,
            pool,
            replace(each, start_rung=""),
            ascent(config, pool, each, capacity=capacity).rungs,
            capacity=capacity,
        )
        for each in contracts
    }


def _facts(config: Config, name: str) -> dict[str, Any]:
    """What this install states about the unit a rung names, unstated facts left out."""
    unit = config.units[name]
    facts: dict[str, Any] = {
        "unit": name,
        "model": unit.model,
        "family": family_of(config, name).name,
        "window": unit.window,
        "reply_room": unit.output_tokens,
    }
    return {key: value for key, value in facts.items() if value is not None}
