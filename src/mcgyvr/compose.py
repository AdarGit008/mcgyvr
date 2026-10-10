"""Jev-composed setup recommendation.

``mcgyvr setup`` writes a deterministic ladder: the models a running server
lists, in the order they were found, with hosted ``--api`` units after them.
This module adds the Jev-composed path: the same facts — a measured
:class:`~mcgyvr.detect.Detection`, a :class:`~mcgyvr.propose.Proposal` and the
hosted units asked for — are assembled into a small, deterministic family of
candidate configs, and :func:`~mcgyvr.decision.classify` picks one by a
priority: ``throughput``, ``quality`` or ``cost``.

The one property this module exists to hold: **a model's answer can never
invent a number.** Every candidate is produced by
:func:`mcgyvr.initialize.build` — the same composer init already uses, whose
numbers come from the measured machine and the declared schema — and the model
is asked only to name one candidate. A :class:`~mcgyvr.decision.ChoiceAnswer`
carries a candidate name and probabilities, nothing else, so nothing a model
returns can reach the emitted config except a choice among what was already
assembled.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, classify
from mcgyvr.detect import Backend, Detection
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.propose import Proposal

if TYPE_CHECKING:
    from mcgyvr.initialize import ApiUnit

#: The three candidate compositions differ only in which units the ladder
#: holds — a hosted unit costs money and needs a key, a listed rung is a
#: machine the operator already has — never in a number.
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
    """One candidate config, assembled before any model is consulted."""

    name: str
    description: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class Recommendation:
    """The chosen candidate and the decision that chose it.

    ``decision`` is ``None`` when a single candidate needed no judgment, so no
    model was consulted and no request was made.
    """

    selected: SetupCandidate
    candidates: tuple[SetupCandidate, ...]
    decision: Decision | None
    priority: str


def endpoint_for_backend(backend: Backend) -> Endpoint:
    """The keyless decision endpoint a detected backend provides.

    The same wire path a dispatch uses: a decision asked of a detected backend
    reaches the unit identically to a dispatch to it.
    """
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
    """The candidate configs, assembled deterministically from the same facts
    :func:`mcgyvr.initialize.build` uses.

    Three compositions, each a full loadable config whose numbers are build's
    and whose only difference is which units the ladder holds:

    * ``own`` — the listed rungs only, no hosted unit;
    * ``escalate`` — listed rungs then hosted units (init's default ladder);
    * ``hosted`` — hosted units only.

    A composition whose ladder would be empty is dropped rather than emitted:
    an empty ladder is the one config init refuses to write.

    ``use_case`` and ``deployment`` are passed to every build, so whichever
    candidate is selected states the use case and deployment init was asked
    for, as the deterministic ladder does.
    """
    # Deferred: initialize imports this module, so importing it here keeps the
    # two from forming a cycle at import time.
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
    """The state a decision is asked about: measured facts and the priority.

    Every number here is a measurement the machine made, or absent. The model
    is shown this state and the candidate names; it is never shown a number it
    could copy into a config, because the answer it may return is a name.
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
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
    use_case: str = "coding",
    deployment: str | None = None,
) -> Recommendation:
    """Compose a setup for ``priority`` by ranking the candidate configs.

    ``classify`` is called once, with a single :class:`Choice` whose options
    are the candidate names. The answer names one candidate; the returned
    config is that candidate's, assembled before the model was consulted, so no
    token a model returns can become a number in the config.

    With a single candidate no model is consulted: there is nothing to rank,
    and asking would be spending a request to be told the only option.
    """
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
