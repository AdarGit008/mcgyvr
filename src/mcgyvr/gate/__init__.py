"""The deterministic acceptance gate (E5).

The gate decides whether a worker's change is acceptable, deterministically
and before any model is asked for an opinion. In a keyless install it is the
entire acceptance bar, so it is the component a stranger's first successful
task depends on most.

Every check in the gate reads the same two facts — which files changed, and
which lines the worker added — from a single shared :class:`ChangeSet`, so
the number of subprocesses a gate run spawns is a constant, not a function of
how many files changed. See :mod:`mcgyvr.gate.changeset`.
"""

from __future__ import annotations

from mcgyvr.gate.acceptance import Acceptance, AcceptanceReport
from mcgyvr.gate.adapter import LanguageAdapter, ToolUnavailableError
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.changeset import (
    ChangeSet,
    ChangeSetError,
    FileChange,
)
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.preflight import (
    PreflightIssue,
    check_clean_tree,
    check_prompt_fits,
)
from mcgyvr.gate.runner import Gate, GateResult

__all__ = [
    "Acceptance",
    "AcceptanceReport",
    "ChangeSet",
    "ChangeSetError",
    "FileChange",
    "Finding",
    "Gate",
    "GateResult",
    "LanguageAdapter",
    "PreflightIssue",
    "PythonAdapter",
    "ToolUnavailableError",
    "check_clean_tree",
    "check_prompt_fits",
]
