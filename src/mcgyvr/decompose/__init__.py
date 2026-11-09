"""Decomposition: a prompt turned into contracts by a caller-supplied proposer.

``decompose`` runs the context layer (``mcgyvr.repo``) for a prompt, hands the
evidence to a ``Proposer``, and turns its ``Proposal``s into a
``Decomposition`` of contracts and ``Refusal``s. ``iterate`` re-asks a refused
field and re-emits; ``candidates`` and ``fields`` are the per-field choices a
classifier proposer picks from; ``provides`` reads what a contract says it
creates or changes; ``baseline`` reads the repository's test baseline before any
work is proposed.

Each submodule stays importable directly; this module gathers the public names
of ``decompose`` so a caller can ``from mcgyvr.decompose import decompose``.
"""

from __future__ import annotations

from mcgyvr.decompose.decompose import (
    Decomposition,
    DepRef,
    Evidence,
    Proposal,
    Proposer,
    RecordedProposer,
    Refusal,
    decompose,
)

__all__ = [
    "Decomposition",
    "DepRef",
    "Evidence",
    "Proposal",
    "Proposer",
    "RecordedProposer",
    "Refusal",
    "decompose",
]
