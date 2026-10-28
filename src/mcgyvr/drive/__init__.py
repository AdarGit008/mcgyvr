"""The driver: one attempt at one contract, from prompt to recorded judgement.

``mcgyvr.drive`` sits between a parsed contract and the rungs that serve it.
Its submodules assemble the worker prompt and refuse a contract the bound
endpoint cannot be sent, dispatch the draws, gate what came back in a
sandbox, judge the gate's result, and turn one :class:`~mcgyvr.route.Try`
into a :class:`~mcgyvr.escalate.Judgement` — recording the attempt when a
:class:`Recording` is handed in. ``run_tool_step`` covers the deterministic
floor, for a contract a program answers instead of a model.

This module holds no logic of its own: it re-exports the driver's surface,
and the services that surface composes, so the CLI and the tests import one
name.
"""

from __future__ import annotations

# isort: off
# The services the driver composes, re-exported so a caller needs one
# import: jobs run in parallel under a capacity, the tidy-up of a rejected
# change, best-of-n consensus over draws, the escalation judge, the model
# runner, the sleep/wake waker and the worker prompt builder.
from mcgyvr.capacity import run_batch
from mcgyvr.repair import tidy
from mcgyvr.consensus import best_of
from mcgyvr.escalate import judge
from mcgyvr.runner import dispatch
from mcgyvr.wake import for_config as wake_for_config
from mcgyvr.worker.prompt import build_prompt

# The driver's own layers: the refusal errors that stop a contract before a
# prompt is sent or a step is run, the identity of a recorded attempt, the
# deterministic floor's tool steps, the pre-dispatch checks and prompt
# rendering, the sandbox gate that judges a reply, and the attempt loop that
# turns one `Try` into a `Judgement`.
from mcgyvr.drive.errors import (
    ContractTooLargeForRungError,
    DriveError,
    PromptTooLargeError,
    UnitCeilingUnknownError,
    UnrunnableStepError,
)
from mcgyvr.drive.record import Recording
from mcgyvr.drive.exec import ToolOutcome, run_tool_step
from mcgyvr.drive.prompt import (
    _as_sent,
    _base_content,
    dispatch_prompt,
    refuse_unsendable,
    refuse_unsendable_climb,
)
from mcgyvr.drive.gate import (
    acceptance_for,
    gate_adapters,
    ungated_notes,
    gate_in_sandbox,
    gate_workspace,
    task_ceiling,
)
from mcgyvr.drive.attempt import _in_order, worker_attempt
# isort: on
# The exported surface, underscored helpers included: the tests reach them here.

__all__ = [
    "ContractTooLargeForRungError",
    "DriveError",
    "PromptTooLargeError",
    "Recording",
    "ToolOutcome",
    "UnitCeilingUnknownError",
    "UnrunnableStepError",
    "_as_sent",
    "_base_content",
    "_in_order",
    "acceptance_for",
    "best_of",
    "build_prompt",
    "dispatch",
    "dispatch_prompt",
    "gate_adapters",
    "gate_in_sandbox",
    "gate_workspace",
    "judge",
    "refuse_unsendable",
    "refuse_unsendable_climb",
    "run_batch",
    "run_tool_step",
    "task_ceiling",
    "tidy",
    "ungated_notes",
    "wake_for_config",
    "worker_attempt",
]
