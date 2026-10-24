"""Public surface of the gate subpackage.

Re-exports the gate's building blocks so callers can import them from
``mcgyvr.gate`` instead of the individual modules:

- acceptance: :class:`Acceptance` and :class:`AcceptanceReport`.
- adapter: :class:`LanguageAdapter` plus the environment, tool-failure, and
  tool-unavailable errors.
- adapters: the :class:`JavaScriptAdapter` and :class:`PythonAdapter`
  implementations of :class:`LanguageAdapter`.
- changeset: :class:`ChangeSet`, :class:`FileChange`, and
  :class:`ChangeSetError`.
- findings: :class:`Finding`.
- jev: :class:`JevCheck` and :class:`JevReport`.
- preflight: the prompt/reply budget helpers (``unit_max``, ``unit_ceiling``,
  ``ESTIMATE_RESERVE``, ``LEAST_ROOM``, and their types), plus the ``check_*``
  preflight validators.
- runner: :class:`Gate`, :class:`GateResult`, and :class:`InconclusiveRung`.
- semantic: :class:`SemanticCheck` and :class:`SemanticReport`.

``__all__`` lists exactly the names re-exported here.
"""

from __future__ import annotations

from mcgyvr.gate.acceptance import Acceptance, AcceptanceReport
from mcgyvr.gate.adapter import (
    EnvironmentFaultError,
    LanguageAdapter,
    ToolFailedError,
    ToolUnavailableError,
)
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import (
    ChangeSet,
    ChangeSetError,
    FileChange,
)
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.jev import JevCheck, JevReport
from mcgyvr.gate.preflight import (
    ESTIMATE_RESERVE,
    LEAST_ROOM,
    PreflightIssue,
    ReplyCap,
    ServingWindow,
    TokenCount,
    UnitCeiling,
    check_clean_tree,
    check_contract_against_rung,
    check_contract_fits,
    check_prompt_fits,
    check_unit_ceiling_stated,
    check_window_fraction,
    unit_ceiling,
    unit_max,
)
from mcgyvr.gate.runner import Gate, GateResult, InconclusiveRung
from mcgyvr.gate.semantic import SemanticCheck, SemanticReport

__all__ = [
    "ESTIMATE_RESERVE",
    "LEAST_ROOM",
    "Acceptance",
    "AcceptanceReport",
    "ChangeSet",
    "ChangeSetError",
    "EnvironmentFaultError",
    "FileChange",
    "Finding",
    "Gate",
    "GateResult",
    "InconclusiveRung",
    "JavaScriptAdapter",
    "JevCheck",
    "JevReport",
    "LanguageAdapter",
    "PreflightIssue",
    "PythonAdapter",
    "ReplyCap",
    "SemanticCheck",
    "SemanticReport",
    "ServingWindow",
    "TokenCount",
    "ToolFailedError",
    "ToolUnavailableError",
    "UnitCeiling",
    "check_clean_tree",
    "check_contract_against_rung",
    "check_contract_fits",
    "check_prompt_fits",
    "check_unit_ceiling_stated",
    "check_window_fraction",
    "unit_ceiling",
    "unit_max",
]
