"""The self-contained retry loop (W6): re-ask a refused field, then re-emit.

`iterate` drives one classifier proposal through the same `emit_one` seam
`decompose` uses. When the proposal is refused on a field the classifier can
re-ask, the loop records the refusal's ``what_to_change`` as a constraint,
drops the rejected candidate value, carries the already-decided upstream fields
forward, and asks again — each retry gated by an injected ``approve`` callable.
The loop is inert unless an approver is wired in: ``approve`` has no default.

The re-ask itself is ``reask``, one step: the loop takes it once per retry,
and ``reproposals`` takes it once per refused proposal a decomposition hands
back to the classifier (F16, ``Evidence.refused``), so there is one re-ask,
not two.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.orchestrator.decompose import (
    _DEFAULT_MAX_INPUT_TOKENS,
    Decomposition,
    Proposal,
    Refusal,
    _default_adapters,
    _evidence,
    emit_one,
)
from mcgyvr.orchestrator.fields import FIELD_ORDER

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.orchestrator.decompose import Evidence
    from mcgyvr.orchestrator.index import Index

#: The gate each retry must clear: given the refusal and the attempt index,
#: return True to re-ask (so an always-False approver leaves the loop inert).
Approver = Callable[[Refusal, int], bool]

#: Total attempts the loop makes before giving up (so 3 == 2 retries).
MAX_REFUSAL_RETRIES = 3


class Classifier(Protocol):
    """The classifier seam `iterate` drives: one proposal per call, or a refusal."""

    def propose(
        self,
        evidence: Evidence,
        *,
        decided: Mapping[str, Any] | None = None,
        constraints: Mapping[str, str] | None = None,
        rejected: Mapping[str, Collection[Any]] | None = None,
    ) -> Proposal | Refusal: ...


def _plan_value(proposal: Proposal, field: str) -> Any:
    """The plan-representation value `proposal` chose for `field`.

    `deps` candidates are a single `DepRef` or `()` while `Proposal.deps` is a
    tuple, so the chosen value is the tuple's single element (or `()` when the
    proposal carries no dependency). Every other field matches its plan value
    directly. (`symbol` has no `Proposal` slot and is never looked up here; it
    is an intermediate decision, not a re-askable value.)
    """
    value = getattr(proposal, field)
    if field == "deps":
        return value[0] if value else ()
    return value


def reaskable(refusal: Refusal) -> bool:
    """Whether the classifier decides `refusal.field`, so it can be asked again."""
    return refusal.field in FIELD_ORDER


def reask(
    classify: Classifier,
    evidence: Evidence,
    refused: Proposal | Refusal,
    refusal: Refusal,
    *,
    decided: dict[str, Any],
    constraints: dict[str, str],
    rejected: dict[str, frozenset[Any]],
) -> Proposal | Refusal:
    """Ask the classifier again for the field `refusal` names, once.

    The refusal's ``what_to_change`` becomes that field's constraint. When
    `refused` is the proposal that was refused, its value for the field is
    dropped from the next question and the fields upstream of it are carried
    as decided; a refusal from the classifier itself keeps what was decided.
    `decided`, `constraints` and `rejected` are updated in place, so a caller
    that re-asks again carries them on.
    """
    constraints[refusal.field] = refusal.what_to_change
    if isinstance(refused, Proposal):
        rejected[refusal.field] = rejected.get(refusal.field, frozenset()) | {
            _plan_value(refused, refusal.field)
        }
        # `symbol` is an intermediate decision with no `Proposal` slot, so
        # upstream fields are only those the proposal records, carried in
        # plan representation (a single `DepRef`, not the proposal's tuple).
        upstream = FIELD_ORDER[: FIELD_ORDER.index(refusal.field)]
        decided.clear()
        decided.update(
            {
                field: _plan_value(refused, field)
                for field in upstream
                if hasattr(refused, field)
            }
        )
    return classify.propose(
        evidence, decided=decided, constraints=constraints, rejected=rejected
    )


def reproposals(classify: Classifier, evidence: Evidence) -> tuple[Proposal, ...]:
    """What the classifier proposes in place of each of `evidence.refused`.

    Each refused proposal whose refusal names a field the classifier decides is
    re-asked once (`reask`), against the same evidence with that proposal's own
    task as the request and nothing marked refused; one the classifier refuses
    again, or whose field it does not decide, has no replacement here.
    """
    replacements: list[Proposal] = []
    for item in evidence.refused:
        if not reaskable(item.refusal):
            continue
        asked = reask(
            classify,
            replace(evidence, prompt=item.proposal.task, refused=()),
            item.proposal,
            item.refusal,
            decided={},
            constraints={},
            rejected={},
        )
        if isinstance(asked, Proposal):
            replacements.append(asked)
    return tuple(replacements)


def iterate(
    index: Index,
    prompt: str,
    *,
    classify: Classifier,
    approve: Approver,
    config: Config | None = None,
    budget: int | None = None,
    adapters: Sequence[LanguageAdapter] | None = None,
    located: Mapping[str, Sequence[str]] | None = None,
    max_attempts: int = MAX_REFUSAL_RETRIES,
    max_input_tokens: int = _DEFAULT_MAX_INPUT_TOKENS,
) -> Decomposition:
    """Turn one prompt into one contract through a classifier, retrying refusals.

    The classifier emits a single proposal (`N=1`). On a refusal that names a
    re-askable field, the loop re-asks only that field — carrying the upstream
    fields already decided and the rejected candidate out of the next question,
    with the refusal's ``what_to_change`` rendered as a constraint — until the
    emission succeeds, the attempt budget runs out, an approver declines, or
    the refusal names a field that cannot be re-asked (terminal).

    `max_attempts` counts *total* attempts, so ``max_attempts=1`` means no
    retry. `approve` is required: no default, so nothing retries unless a real
    approver is wired in.
    """
    ceiling = max_input_tokens
    evidence = _evidence(
        index,
        prompt,
        config=config,
        budget=budget,
        adapters=adapters,
        ceiling=ceiling,
    )
    owners = tuple(adapters) if adapters is not None else _default_adapters()
    seen: dict[str, str] = {}
    refusals: list[Refusal] = []
    decided: dict[str, Any] = {}
    constraints: dict[str, str] = {}
    rejected: dict[str, frozenset[Any]] = {}

    proposal = classify.propose(evidence)
    attempt = 1
    while True:
        if isinstance(proposal, Refusal):
            refusal = proposal
        else:
            emitted = emit_one(
                evidence,
                proposal,
                seen=seen,
                adapters=owners,
                ceiling=ceiling,
                located=located,
            )
            if not isinstance(emitted, Refusal):
                built, document = emitted
                return Decomposition(
                    contracts=(built,),
                    documents=(document,),
                    refusals=tuple(refusals),
                    resolution=evidence.resolution,
                    exploration=evidence.exploration,
                )
            refusal = emitted

        # A field the classifier never decides (type_check, request, a
        # catch-all, ...) cannot be re-asked: this is terminal.
        if not reaskable(refusal):
            refusals.append(refusal)
            return Decomposition(
                contracts=(),
                documents=(),
                refusals=tuple(refusals),
                resolution=evidence.resolution,
                exploration=evidence.exploration,
            )

        if attempt >= max_attempts or not approve(refusal, attempt):
            refusals.append(refusal)
            return Decomposition(
                contracts=(),
                documents=(),
                refusals=tuple(refusals),
                resolution=evidence.resolution,
                exploration=evidence.exploration,
            )

        proposal = reask(
            classify,
            evidence,
            proposal,
            refusal,
            decided=decided,
            constraints=constraints,
            rejected=rejected,
        )
        attempt += 1
