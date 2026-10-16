"""A ``ToolStep`` executor: run a deterministic step inside a sandbox."""

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
    """What running one deterministic step came to.

    Three states, kept apart for the reason :mod:`mcgyvr.gate.acceptance` keeps
    the same three apart: a program that ran and succeeded, a program that ran
    and failed, and a program that never ran at all. The third is an environment
    fault — ruff is not installed — and is never the change's fault, which is
    the distinction :class:`~mcgyvr.deterministic.Degradation` is built on and
    the reason a missing tool degrades the contract onto a dearer family instead
    of failing it.

    ``result`` is ``None`` only when the program did not run. A caller reading
    ``ok`` alone gets the safe answer in both failing cases; a caller deciding
    *whose* fault it was reads :attr:`environment_issue`.

    The middle state has two halves and :attr:`ok` cannot tell them apart,
    which is what :attr:`performed` is for: a fixer that exits non-zero because
    a diagnostic remains after fixing has carried out a ``lint_fix`` operation,
    and a caller reading ``not ok`` as fatal never reaches the gate that judges
    the result.
    """

    step: ToolStep
    result: CommandResult | None = None
    environment_issue: str = ""

    @property
    def ran(self) -> bool:
        """Whether the program executed at all."""
        return self.result is not None

    @property
    def ok(self) -> bool:
        """Whether the program ran and reported success.

        Note what this does not claim: that the file changed. A formatter given
        an already-formatted file exits 0 having written nothing, which is a
        success — the contract asked for a formatted file and there is one. What
        changed is the change-set's question, and :meth:`ChangeSet.detect
        <mcgyvr.gate.changeset.ChangeSet.detect>` is what answers it.
        """
        return self.result is not None and self.result.ok

    @property
    def performed(self) -> bool:
        """Whether the program ran and did the work its task type describes.

        Wider than :attr:`ok` by exactly one thing: an exit code the invocation
        uses to *report* rather than to *fail*
        (:attr:`~mcgyvr.deterministic.Tool.reporting` says which). For a fixer
        that is 1 — "I applied every autofix I have,
        and here is what I will not fix" — and the catalog puts that residue
        out of the type's scope in as many words, so a caller that stopped
        there stopped on the contract having been satisfied.

        **This is not "non-fatal".** A tool that could not load its config
        exits 2 having applied nothing, and that stays outside the set: there
        is no result for a gate to judge, and a gate reading the same config is
        broken the same way. Nor does it soften a timeout —
        :attr:`~mcgyvr.sandbox.base.CommandResult.ok` excludes one and so does
        this, because a command killed at its ceiling did not finish whatever
        it was part-way through writing.

        A caller with something to say about the residue asks ``performed and
        not ok``. Proceeding is not the same as reporting that nothing
        happened.
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
    """Execute one deterministic step inside ``sandbox``.

    The sandbox is required rather than optional, and the working tree is never
    an argument: a formatter runs with ``--fix`` and writes where it is pointed,
    so an executor that could be handed a repository path could rewrite the
    user's checkout on the strength of a contract's ``target`` field. The
    sandbox is the boundary that makes the write reversible.

    A missing program comes back as :attr:`ToolOutcome.environment_issue`
    rather than as a failure, read from the shell's own exit codes through
    :data:`~mcgyvr.gate.acceptance.DID_NOT_RUN` — the same constant the
    acceptance rung classifies with, so "could not run" cannot come to mean two
    things in one process.

    A step with no ``argv`` is not a step with nothing to do: the floor's one
    in-process operation, ``rename_symbol``, is executed here against the
    sandbox's own tree by :func:`mcgyvr.rename.apply`, because what performs it
    is mcgyvr's index rather than a program on PATH. Its refusals are the
    operation's own — an unstated pair, a symbol the index does not know — and
    they arrive as a failed :class:`ToolOutcome`, never as an environment issue:
    nothing is missing from the machine.

    Raises :class:`UnrunnableStepError` for a step that names neither a command
    nor an in-process executor.
    """
    if not step.argv:
        return _run_in_process(step, sandbox)

    # A formatter is a program like any acceptance command, and one that hangs
    # is held to the same ceiling.
    if timeout is None:
        timeout = _drive.task_ceiling()
    argv = step.argv
    if is_pattern(step.target):
        named = _named_by(step.target, sandbox.workspace)
        if not named:
            from mcgyvr.sandbox.base import CommandResult

            # Exit 2, a usage error: not a code any tool reports as having
            # done its job, so the floor stops here rather than gating a tree
            # nothing touched.
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
    """The files in ``workspace`` that ``pattern`` names, sorted.

    The files the gate would judge — tracked, plus untracked and not ignored,
    the set ``git add -A`` takes — matched by :mod:`mcgyvr.scope`'s glob rules,
    so a pattern names the same files here as it does in ``scope.allow``.
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
    """The floor's in-process executors, keyed by the operation they perform.

    The outcome is shaped as a :class:`~mcgyvr.sandbox.base.CommandResult` with
    a command of ``()`` so that every reader downstream — the journal, the
    escalation ladder, the CLI's own reporting — handles one kind of thing. A
    second outcome shape for the one operation with no program would have every one
    of those readers grow a branch for it.
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
