"""The setup composed from measured facts, with the choice of one left to a model.

A candidate is a whole setup both config files can be rendered from: the data
`initialize.build` writes from a `Detection`, a `Proposal` and the declared
`ApiUnit`s. `candidate_setups` assembles every candidate the facts allow, and
`recommend` asks one typed `Choice` question naming them, so what the model
picks is which setup is written — never a number inside one, since each
candidate is built by code from the measured machine and the declared schema
before the question is asked.

The endpoint the question is sent to is a backend the sweep already reached,
via `endpoint_for_backend`, or one the caller names. With only one candidate
assembled there is nothing to choose and no model is consulted at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.decision import Choice, ChoiceAnswer, Decision, classify
from mcgyvr.detect import Backend, Detection
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.propose import Proposal

if TYPE_CHECKING:
    from mcgyvr.initialize import ApiUnit

# What each candidate is offered as in the `Choice` the model answers: one
# description per candidate name, saying where the work runs and what it costs,
# read against the priority and the measured machine that make up the state.
OWN_DESCRIPTION = (
    "run only on the machine(s) already listed, with no hosted unit: no API "
    "spend and no key to export"
)
ESCALATE_DESCRIPTION = (
    "start on the machine(s) already listed and climb to the hosted unit when "
    "they are not enough"
)
HOSTED_DESCRIPTION = (
    "run everything on the hosted unit(s): simplest, and every dispatch spends "
    "API money"
)


@dataclass(frozen=True)
class SetupCandidate:
    """One setup the composition may select: the `name` it is offered under, the
    `description` the model reads beside that name, and the `data` both files are
    rendered from, as `initialize.build` wrote it."""

    name: str
    description: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class Recommendation:
    """The composition this module settled on: the `selected` candidate, every
    `candidates` entry it was chosen from, the `decision` read from the endpoint
    (None when there was a single candidate and nothing was asked), and the
    `priority` the selection was made for."""

    selected: SetupCandidate
    candidates: tuple[SetupCandidate, ...]
    decision: Decision | None
    priority: str


def endpoint_for_backend(backend: Backend) -> Endpoint:
    """The decision endpoint a detected backend answers on: the backend's own name
    and base URL, the OpenAI-compatible protocol, one request at a time, and no
    credential, since a backend the sweep reached is asked without a key."""
    return Endpoint(
        source=backend.name,
        base_url=backend.base_url,
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def candidate_setups(
    detection: Detection,
    proposal: Proposal,
    *,
    api_units: Sequence[ApiUnit] = (),
    use_case: str = "coding",
    deployment: str | None = None,
) -> tuple[SetupCandidate, ...]:
    """Every setup these facts allow, in a fixed order.

    `own` comes first, and only when the proposal listed a rung. When hosted
    units were named, `escalate` follows — it needs a listed rung to start on, so
    it is offered only beside `own` — and `hosted` last, which binds the hosted
    units alone. A machine with neither a listed rung nor a hosted unit yields no
    candidate at all, which the caller sees as an empty tuple.

    Each candidate's data is what `build` writes from the same detection,
    proposal and hosted units, plus the `use_case` and `deployment` passed
    through unchanged, so two calls on the same facts give the same setups.
    """
    # Imported here rather than at module level: `initialize` imports `recommend`
    # and `Recommendation` from this module, so building the import at call time
    # is what keeps the two modules from importing each other on load.
    from mcgyvr.initialize import build

    asked: dict[str, Any] = {"use_case": use_case, "deployment": deployment}
    candidates: list[SetupCandidate] = []
    if proposal.rungs:
        candidates.append(
            SetupCandidate(
                name="own",
                description=OWN_DESCRIPTION,
                data=build(detection, proposal, api_units=(), **asked),
            )
        )
    if api_units:
        if proposal.rungs:
            candidates.append(
                SetupCandidate(
                    name="escalate",
                    description=ESCALATE_DESCRIPTION,
                    data=build(detection, proposal, api_units=api_units, **asked),
                )
            )
        candidates.append(
            SetupCandidate(
                name="hosted",
                description=HOSTED_DESCRIPTION,
                data=build(detection, Proposal(), api_units=api_units, **asked),
            )
        )
    return tuple(candidates)


def decision_state(
    detection: Detection,
    proposal: Proposal,
    priority: str,
    *,
    api_units: Sequence[ApiUnit] = (),
) -> dict[str, Any]:
    """The state the choice is made on, as plain JSON-ready values: the priority
    asked for, the machine as measured (each card's name and VRAM, the CPU count,
    RAM and whether a Docker daemon answered), the listed ladder as name, model
    and host, and the hosted units as name and model.

    Every entry is a value detection, the proposal or the hosted spec already
    established, so the model reads the facts of this machine rather than numbers
    it could state itself.
    """
    return {
        "priority": priority,
        "measured": {
            "gpus": [
                {"name": gpu.name, "vram_gb": gpu.vram_gb} for gpu in detection.gpus
            ],
            "cpu_count": detection.cpu_count,
            "ram_gb": detection.ram_gb,
            "docker": detection.docker,
        },
        "ladder": [
            {"name": rung.name, "model": rung.model, "host": rung.host}
            for rung in proposal.rungs
        ],
        "hosted": [{"name": unit.name, "model": unit.model} for unit in api_units],
    }


def recommend(
    endpoint: Endpoint,
    model: str,
    detection: Detection,
    proposal: Proposal,
    priority: str,
    *,
    api_units: Sequence[ApiUnit] = (),
    timeout_s: float | None = None,
    use_case: str = "coding",
    deployment: str | None = None,
) -> Recommendation:
    """Compose the setup for one priority: assemble the candidates, then ask
    `endpoint`, serving `model`, which of them fits.

    The question is a single `Choice` whose options are the candidate names and
    their descriptions, asked against `decision_state`, and the reply's chosen
    name selects the candidate returned. One candidate is returned without any
    request — there is nothing to choose and `decision` is then None — while no
    candidate at all raises a ValueError, since nothing can be composed from a
    machine with no listed rung and no hosted unit. `timeout_s` bounds the request
    and the other keyword arguments reach `build` through `candidate_setups`; a
    reply no label can be read from raises `DecisionError` out of `classify`."""
    candidates = candidate_setups(
        detection,
        proposal,
        api_units=api_units,
        use_case=use_case,
        deployment=deployment,
    )
    if not candidates:
        raise ValueError(
            "nothing to compose: no listed rung and no hosted unit, so there "
            "is no candidate setup to select from"
        )
    if len(candidates) <= 1:
        return Recommendation(
            selected=candidates[0],
            candidates=candidates,
            decision=None,
            priority=priority,
        )
    state = decision_state(detection, proposal, priority, api_units=api_units)
    question = Choice(
        instructions=(
            "Given this priority and the measured machine, pick the setup "
            "that best fits."
        ),
        options={candidate.name: candidate.description for candidate in candidates},
    )
    decision = classify(
        endpoint, model, state, {"setup": question}, timeout_s=timeout_s
    )
    answer = decision.answers["setup"]
    assert isinstance(answer, ChoiceAnswer)
    by_name = {candidate.name: candidate for candidate in candidates}
    return Recommendation(
        selected=by_name[answer.choice],
        candidates=candidates,
        decision=decision,
        priority=priority,
    )
