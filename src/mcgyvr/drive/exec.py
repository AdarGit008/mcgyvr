"""Running one deterministic tool step, and the outcome it reports.

``run_tool_step`` is the floor's executor: handed a :class:`ToolStep` and a
``Sandbox``, it runs the step's command in the sandbox — or, for a step naming
an operation mcgyvr performs itself, applies it in process — and returns a
:class:`ToolOutcome` saying what happened. A step whose program is not on the
sandbox's PATH comes back with ``environment_issue`` set and no result, so the
caller can report a missing dependency rather than a rejected change.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import mcgyvr.drive as _drive
from mcgyvr.contract import is_pattern
from mcgyvr.drive.errors import UnrunnableStepError
from mcgyvr.gate.acceptance import DID_NOT_RUN
from mcgyvr.scope import Scope

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.sandbox.base import CommandResult, Sandbox


@dataclass(frozen=True)
class ToolOutcome:
    """What one tool step did: the step, the result it produced if it ran, and
    the environment issue that stopped it if it never did. A step either has a
    result or an issue, never both.
    """

    step: ToolStep
    result: CommandResult | None = None
    environment_issue: str = ""

    @property
    def ran(self) -> bool:
        """True when the step reached a command and produced a result; a step
        stopped by a missing program has none.
        """
        return self.result is not None

    @property
    def ok(self) -> bool:
        """True when the step ran and its command exited zero without timing
        out.
        """
        return self.result is not None and self.result.ok

    @property
    def performed(self) -> bool:
        """True when the step ran, did not time out, and exited with a code its
        tool reports as having done the work: 0, or 1 for operations whose
        point is to leave residue behind. A timeout performs nothing.
        """
        if self.result is None or self.result.timed_out:
            return False
        return self.result.exit_code in self.step.tool.reporting


def run_tool_step(
    step: ToolStep,
    sandbox: Sandbox,
    *,
    timeout: float | None = None,
) -> ToolOutcome:
    """Run one step in the sandbox and report what it did.

    A step with no command is run in process. A step whose target is a glob is
    expanded to the workspace files the pattern names, and fails as a step with
    no work to do when it names none. A step whose program cannot be executed
    comes back with `environment_issue` set instead of a result, so a missing
    dependency is not read as a rejected change.
    """
    if not step.argv:
        return _run_in_process(step, sandbox)

    # The step's command runs inside the sandbox, held to the run's task
    # ceiling unless the caller passed its own timeout.
    if timeout is None:
        timeout = _drive.task_ceiling()
    argv = step.argv
    if is_pattern(step.target):
        named = _named_by(step.target, sandbox.workspace)
        if not named:
            from mcgyvr.sandbox.base import CommandResult

            # Nothing in the workspace matches the pattern, so no program is
            # started: the step reports a synthetic failing result carrying the
            # reason, and the caller stops on it like any other failure.
            return ToolOutcome(
                step=step,
                result=CommandResult(
                    command=argv,
                    exit_code=2,
                    stdout="",
                    stderr=(
                        f"{step.target!r} names no file in the workspace, so "
                        f"there is nothing for {step.tool.program} to run on."
                    ),
                ),
            )
        argv = step.argv_over(named)
    result = sandbox.run(argv, timeout=timeout)
    if result.exit_code in DID_NOT_RUN and not result.timed_out:
        program = step.tool.program
        return ToolOutcome(
            step=step,
            environment_issue=(
                f"{program} could not run (exit {result.exit_code}) — the "
                f"deterministic floor for {step.tool.operation!r} needs it on "
                f"PATH. This is a missing dependency, not a rejected change: "
                f"the work is still doable, on a dearer family."
            ),
        )
    return ToolOutcome(step=step, result=result)


def _named_by(pattern: str, workspace: Path) -> tuple[str, ...]:
    """The workspace files the pattern names, sorted: every tracked file plus
    every untracked file git does not ignore, kept only where the pattern's
    scope permits the path.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=workspace,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", "surrogateescape")
    names = Scope.of([pattern])
    return tuple(sorted({p for p in listed.split("\0") if p and names.permits(p)}))


def _run_in_process(step: ToolStep, sandbox: Sandbox) -> ToolOutcome:
    """Run a step whose tool names no command through mcgyvr's own executor for
    its operation, reporting the executor's summary as the result's stdout. A
    refused rename comes back as a failing result carrying the refusal, and an
    operation with no in-process executor is refused as unrunnable rather than
    reported done.
    """
    from mcgyvr.deterministic import IN_PROCESS
    from mcgyvr.rename import RenameError
    from mcgyvr.rename import apply as rename_apply
    from mcgyvr.sandbox.base import CommandResult

    if step.tool.operation not in IN_PROCESS:
        raise UnrunnableStepError(
            f"operation {step.tool.operation!r} names no command to run and "
            f"mcgyvr has no in-process executor for it. Reporting it complete "
            f"would report a file changed that nothing opened."
        )
    try:
        report = rename_apply(
            Path(sandbox.workspace),
            step.rename.old,
            step.rename.new,
            target=step.target,
        )
    except RenameError as refusal:
        return ToolOutcome(
            step=step,
            result=CommandResult(
                command=(), exit_code=1, stdout="", stderr=str(refusal)
            ),
        )
    return ToolOutcome(
        step=step,
        result=CommandResult(
            command=(), exit_code=0, stdout=report.summary(), stderr=""
        ),
    )
