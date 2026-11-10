"""A proposer for tests: it answers fixed proposals and keeps the evidence shown."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mcgyvr.decompose.decompose import Evidence, Proposal


@dataclass(frozen=True)
class RecordedProposer:
    """A proposer that answers the same proposals and keeps the evidence it was shown.

    For callers that already know what to propose: `seen` receives each
    `Evidence` in the order the calls arrived.
    """

    proposals: tuple[Proposal, ...] = ()
    seen: list[Evidence] = field(default_factory=list)

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        self.seen.append(evidence)
        return self.proposals
