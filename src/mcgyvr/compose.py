""

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

#
# a
#r.
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
    ""

    name: str
    description: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class Recommendation:
    ""

    selected: SetupCandidate
    candidates: tuple[SetupCandidate, ...]
    decision: Decision | None
    priority: str


def endpoint_for_backend(backend: Backend) -> Endpoint:
    ""
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
    ""
    #
    #
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
    ""
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
    ""
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
