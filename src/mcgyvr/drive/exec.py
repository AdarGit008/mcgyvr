""

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

if TYPE_CHECKING:  #
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.sandbox.base import CommandResult, Sandbox


@dataclass(frozen=True)
class ToolOutcome:
    ""

    step: ToolStep
    result: CommandResult | None = None
    environment_issue: str = ""

    @property
    def ran(self) -> bool:
        ""
        return self.result is not None

    @property
    def ok(self) -> bool:
        ""
        return self.result is not None and self.result.ok

    @property
    def performed(self) -> bool:
        ""
        if self.result is None or self.result.timed_out:
            return False
        return self.result.exit_code in self.step.tool.reporting


def run_tool_step(
    step: ToolStep,
    sandbox: Sandbox,
    *,
    timeout: float | None = None,
) -> ToolOutcome:
    ""
    if not step.argv:
        return _run_in_process(step, sandbox)

    #
    #
    if timeout is None:
        timeout = _drive.task_ceiling()
    argv = step.argv
    if is_pattern(step.target):
        named = _named_by(step.target, sandbox.workspace)
        if not named:
            from mcgyvr.sandbox.base import CommandResult

            #
            #
            #
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
    ""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=workspace,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", "surrogateescape")
    names = Scope.of([pattern])
    return tuple(sorted({p for p in listed.split("\0") if p and names.permits(p)}))


def _run_in_process(step: ToolStep, sandbox: Sandbox) -> ToolOutcome:
    ""
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
