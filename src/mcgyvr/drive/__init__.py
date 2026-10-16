"""The two seams between the levers and a run that happens.

**A ``ToolStep`` executor.** :func:`~mcgyvr.deterministic.tool_steps` plans the
whole command and leaves running it to the caller. :func:`run_tool_step` is
that caller.

**A dispatch binding.** :func:`~mcgyvr.worker.prompt.build_prompt` assembles a
:class:`~mcgyvr.worker.prompt.WorkerPrompt`; :func:`~mcgyvr.runner.dispatch`
takes a :class:`~mcgyvr.runner.Request`. :func:`dispatch_prompt` turns one into
the other, and :func:`worker_attempt` is the attempt built on it.

**Two things this module refuses rather than papers over.**

*An over-budget prompt is not sent.* ``build_prompt`` already measures the
assembled prompt against the contract's ceiling and records a
:class:`~mcgyvr.gate.preflight.PreflightIssue` when it does not fit. A binding
that dispatched anyway would make that measurement decorative — the cost of the
check paid, the answer discarded — and would send a request whose reply is
truncated at a boundary nobody chose. Refusing costs nothing at the one moment
it is still free.

*An in-process step is not run as a program.* ``rename_symbol`` is executed by
mcgyvr's own index and its :attr:`~mcgyvr.deterministic.ToolStep.argv` is
empty. Distinguishing it is this module's half of that bargain: an executor
that read an empty argv as "nothing to do, exit 0" would report every rename
contract complete without touching a file.

**What is deliberately not here.** Where work runs is :mod:`mcgyvr.route` and
:mod:`mcgyvr.escalate`; whether a change is acceptable is :mod:`mcgyvr.gate`;
whether it lands is :mod:`mcgyvr.deliver`; what a retry is told is held here,
per rung. Putting policy here would give decisions already settled in one
place a second place to be settled differently.
"""

from __future__ import annotations

# The seam below is monkeypatched at package level by the tests
# (`monkeypatch.setattr(mcgyvr.drive, "<name>", ...)`). The drive submodules
# resolve these names through this package at call time (`_drive.<name>`), so
# one patch reaches every caller exactly as it did when this was one module.
from mcgyvr.capacity import run_batch
from mcgyvr.cleanup import tidy
from mcgyvr.consensus import best_of
from mcgyvr.drive.attempt import SESSION_REPLY, _in_order, worker_attempt
from mcgyvr.drive.errors import (
    ContractTooLargeForRungError,
    DriveError,
    OutputCapTooLargeError,
    OutputCapUnstatedError,
    PromptTooLargeError,
    UnitCeilingUnknownError,
    UnrunnableStepError,
)
from mcgyvr.drive.exec import ToolOutcome, run_tool_step
from mcgyvr.drive.gate import (
    _through,
    acceptance_for,
    gate_adapters,
    gate_in_sandbox,
    gate_prose_workspace,
    gate_workspace,
    output_checks_for,
    task_ceiling,
)
from mcgyvr.drive.prompt import (
    _as_sent,
    _base_content,
    dispatch_prompt,
    refuse_unsendable,
    refuse_unsendable_climb,
)
from mcgyvr.drive.record import Recording
from mcgyvr.escalate import judge
from mcgyvr.runner import dispatch
from mcgyvr.wake import for_config as wake_for_config
from mcgyvr.worker.prompt import build_prompt

__all__ = [
    "SESSION_REPLY",
    "ContractTooLargeForRungError",
    "DriveError",
    "OutputCapTooLargeError",
    "OutputCapUnstatedError",
    "PromptTooLargeError",
    "Recording",
    "ToolOutcome",
    "UnitCeilingUnknownError",
    "UnrunnableStepError",
    "_as_sent",
    "_base_content",
    "_in_order",
    "_through",
    "acceptance_for",
    "best_of",
    "build_prompt",
    "dispatch",
    "dispatch_prompt",
    "gate_adapters",
    "gate_in_sandbox",
    "gate_prose_workspace",
    "gate_workspace",
    "judge",
    "output_checks_for",
    "refuse_unsendable",
    "refuse_unsendable_climb",
    "run_batch",
    "run_tool_step",
    "task_ceiling",
    "tidy",
    "wake_for_config",
    "worker_attempt",
]
