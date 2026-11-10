"""The re-ask: a refused field is asked again, once.

When a proposal is refused on a field the classifier decides, ``reask`` records
the refusal's ``what_to_change`` as that field's constraint, drops the rejected
candidate value, carries the already-decided upstream fields forward, and asks
the classifier again. ``reproposals`` takes it once per refused proposal a
decomposition hands back to the classifier (F16, ``Evidence.refused``), so
there is one re-ask and one retry policy: the decomposition's
``max_reproposals``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr.decompose.decompose import Proposal, Refusal
from mcgyvr.decompose.fields import FIELD_ORDER

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.decompose.decompose import Evidence


class Classifier(Protocol):
    """The classifier seam `reask` asks: one proposal per call, or a refusal."""

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
