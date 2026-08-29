"""The two seams between the port's levers and a run that happens.

The 2026-08-29 pressure test's pattern C: *"The port produced levers, not a
driver. The call graph is five disconnected fragments, none rooted anywhere
reachable."* Its suggested order of work ends by naming what closes that — "a
``ToolStep`` executor and a dispatch binding are the two pieces standing between
the port and a working orchestrator" — and this module is those two pieces and
nothing else.

**A ``ToolStep`` executor.** :func:`~mcgyvr.deterministic.tool_steps` plans the
whole command, deliberately: "a planned step names the whole command, because a
step nothing can run is not a floor". It then says, equally deliberately, that
"running the tool is the caller's". Nothing was that caller, so the cheapest
family in the catalog — the one that does four task types for free and in one
attempt — planned steps that no code executed, and every deterministic contract
was paid for by a model or not at all.

**A dispatch binding.** :func:`~mcgyvr.worker.prompt.build_prompt` assembles a
:class:`~mcgyvr.worker.prompt.WorkerPrompt`; :func:`~mcgyvr.runner.dispatch`
takes a :class:`~mcgyvr.runner.Request`. Nothing turned one into the other,
which is why ``contract.limits.max_output_tokens`` was computed at contract load
and applied to nothing, and why ``runner.dispatch`` had no production caller at
all.

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
empty, "the honest answer and the answer a caller can distinguish, which a
guessed command is not". Distinguishing it is this module's half of that
bargain: an executor that read an empty argv as "nothing to do, exit 0" would
report every rename contract complete without touching a file.

**What is deliberately not here.** Where work runs is :mod:`mcgyvr.route` and
:mod:`mcgyvr.escalate`; whether a change is acceptable is :mod:`mcgyvr.gate`;
whether it lands is :mod:`mcgyvr.deliver`; what a retry is told is
:mod:`mcgyvr.attempt`. All four existed and were reachable. What was missing is
the two seams above, and putting policy here would give decisions the port
already settles in one place a second place to be settled differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.escalate import Judgement, RetryNotes, judge, required_policy
from mcgyvr.gate import Gate, GateResult
from mcgyvr.gate.acceptance import DID_NOT_RUN, Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.route import Try, Verdict, family_of
from mcgyvr.runner import Completion, Request, dispatch
from mcgyvr.telemetry import observe
from mcgyvr.worker.prompt import build_prompt
from mcgyvr.worker.reply import ReplyError, parse_reply

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Sequence

    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.escalate import Review
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.pool import SourceMap
    from mcgyvr.sandbox.base import CommandResult, Sandbox
    from mcgyvr.worker.prompt import WorkerPrompt


class DriveError(Exception):
    """A step could not be executed as planned, for a reason in this module."""


class UnrunnableStepError(DriveError):
    """The step names no program, so a subprocess executor cannot run it."""


class PromptTooLargeError(DriveError):
    """The assembled prompt does not fit the ceiling its own contract set."""


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
    sandbox is the boundary that makes the write reversible, and every other
    writer in the project already runs inside one.

    A missing program comes back as :attr:`ToolOutcome.environment_issue`
    rather than as a failure, read from the shell's own exit codes through
    :data:`~mcgyvr.gate.acceptance.DID_NOT_RUN` — the same constant the
    acceptance rung classifies with, so "could not run" cannot come to mean two
    things in one process.

    Raises :class:`UnrunnableStepError` for a step whose ``argv`` is empty.
    """
    if not step.argv:
        raise UnrunnableStepError(
            f"task type {step.tool.task_type!r} is executed in-process by "
            f"mcgyvr's own index, not by a program: its step names no command "
            f"to run. A subprocess executor has nothing to do with it, and "
            f"reporting it complete would report a file changed that nothing "
            f"opened."
        )

    result = sandbox.run(step.argv, timeout=timeout)
    if result.exit_code in DID_NOT_RUN and not result.timed_out:
        program = step.tool.program
        return ToolOutcome(
            step=step,
            environment_issue=(
                f"{program} could not run (exit {result.exit_code}) — the "
                f"deterministic floor for {step.tool.task_type!r} needs it on "
                f"PATH. This is a missing dependency, not a rejected change: "
                f"the work is still doable, on a dearer family."
            ),
        )
    return ToolOutcome(step=step, result=result)


def dispatch_prompt(
    source_map: SourceMap,
    rung: str,
    prompt: WorkerPrompt,
    contract: Contract,
    *,
    capacity: Capacity | None = None,
    response_schema: dict[str, Any] | None = None,
) -> Completion:
    """Send an assembled prompt to a rung, under the contract's own ceilings.

    The binding pattern C names. Both halves of the prompt travel — ``system``
    carries the bundle the target's language earned and dropping it would send a
    worker the instructions for no language at all — and the output cap is the
    contract's, which is the first time ``limits.max_output_tokens`` reaches
    anything: it is validated at contract load, documented as a hard ceiling on
    one execution, and until now was read by nothing.

    ``contract`` is taken whole rather than as a cap, because a binding given
    only a number cannot be the place the fit refusal happens, and the refusal
    is the point: a prompt that does not fit
    :attr:`~mcgyvr.contract.Contract.max_input_tokens` is refused here, with the
    preflight issue ``build_prompt`` already computed, instead of being sent to
    be truncated somewhere that cannot say why.
    """
    if not prompt.fits:
        raise PromptTooLargeError(
            f"contract {contract.id!r}: the assembled prompt does not fit its "
            f"own ceiling and was not sent — {prompt.fit_issue}"
        )
    request = Request(
        prompt=prompt.user,
        system=prompt.system,
        max_output_tokens=contract.limits.max_output_tokens,
        response_schema=response_schema,
    )
    return dispatch(source_map, rung, request, capacity=capacity)


@dataclass(frozen=True)
class Recording:
    """Where attempt records go, and which orchestrator is writing them.

    §9 of the port plan requires that X02 "must not bake in single-orchestrator
    assumptions — no global mutable state, records carry an orchestrator id".
    :func:`~mcgyvr.telemetry.observe` holds up its end: ``orchestrator`` is a
    required parameter and the module keeps no state. What was missing is a
    caller, so the field was carried by nothing and the constraint was satisfied
    only in the sense that it had never been tested.

    The id is a value the caller constructs rather than something this module
    derives from the process. A default — a hostname, a pid, a literal
    ``"mcgyvr"`` — would be exactly the single-orchestrator assumption §9 names:
    two orchestrators sharing a stream would then write rows that agree about who
    produced them, and the field's whole purpose is telling them apart.

    Recording is optional because a run that cannot write its telemetry should
    fail loudly rather than silently — ``observe`` raises on an unwritable sink
    on purpose — and a caller that has not chosen a sink has not chosen to
    accept that failure.
    """

    path: Path
    orchestrator: str

    def __post_init__(self) -> None:
        if not self.orchestrator.strip():
            raise ValueError(
                "an orchestrator id is required to record: a row that cannot "
                "say which orchestrator produced it is the hole the field "
                "exists to close (§9)."
            )

    def attempt_id(self, contract: str, rung: str, attempt: int) -> str:
        """The id one attempt's row is keyed by.

        The orchestrator is part of it, and that is not decoration.
        :func:`~mcgyvr.telemetry.fold` keys attempts by this string and a repeat
        supersedes — "a re-logged attempt id supersedes" — so two orchestrators
        working the same contract on the same rung, which is the exact case §9
        is keeping reachable, would have written one row that erased the other.
        The rest is derived rather than random so a row can be found again from
        a report naming the contract, the rung and the attempt.
        """
        return f"{self.orchestrator}:{contract}:{rung}:{attempt}"


def worker_attempt(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    sandbox: Sandbox,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    verifier: Callable[[], Review] | None = None,
    recording: Recording | None = None,
) -> Callable[[Try], Judgement[str]]:
    """The attempt function :func:`~mcgyvr.escalate.escalate` has always taken.

    Every function it composes was written to be composed — ``escalate``,
    ``climb`` and ``judge`` each say in their own docstring that assembling a
    prompt, dispatching, applying and gating is "the caller's". There was no
    caller. This is it, and it is deliberately the only place in the project
    that knows the order of those five things.

    **One attempt is: prompt, dispatch, parse, apply, gate, judge.** The order
    is not arbitrary at two points. The gate runs before the verifier is named,
    which :func:`~mcgyvr.escalate.judge` enforces structurally and this does not
    get to re-decide. And the sandbox is reset *before* each write rather than
    after each failure, so an attempt that raises cannot leave the next one
    judging a tree it did not produce — a ``finally`` that tidies up is one
    exception away from not having run.

    **The retry note comes from the last judgement on the same rung.**
    :func:`~mcgyvr.route.climb` owns how many attempts a rung gets, and its
    ``Result`` carries a verdict rather than notes, so the note is held here,
    per rung, and handed to ``build_prompt``. ``mcgyvr.attempt.run`` is the
    standalone spelling of the same loop, for a caller that is not climbing;
    running both would be two loops counting one budget.

    **A reply that cannot be read is a failed attempt, not an exception.** The
    parser refuses by name — truncated, no fenced block, a refusal in place of
    a file — and every one of those is something the next attempt could do
    differently, which is the definition of a failure rather than a fault.
    """
    notes: dict[str, RetryNotes] = {}

    def attempt(this: Try) -> Judgement[str]:
        family = family_of(config, this.rung.name)
        prompt = build_prompt(
            contract, adapters=adapters, retry=notes.get(this.rung.name)
        )

        def send() -> Completion:
            return dispatch_prompt(
                pool, this.rung.name, prompt, contract, capacity=this.capacity
            )

        if recording is None:
            completion = send()
        else:
            completion = observe(
                send,
                path=recording.path,
                attempt_id=recording.attempt_id(
                    contract.id, this.rung.name, this.attempt
                ),
                orchestrator=recording.orchestrator,
                rung=this.rung.name,
                model=this.rung.model,
            )
        parsed = parse_reply(
            completion.text,
            output_schema=contract.output_schema,
            stop_reason=completion.stop_reason,
            target=contract.target,
        )
        if isinstance(parsed, ReplyError):
            # No retry note: the note vocabulary is the gate's findings, and
            # nothing was gated. What the next attempt would need to hear is the
            # refusal itself, which `detail` carries to the caller's report.
            return Judgement(
                verdict=Verdict.FAILED,
                policy=required_policy(contract, family),
                detail=f"the reply could not be read: {parsed}",
            )

        gate = gate_in_sandbox(contract, sandbox, parsed.content, adapters=adapters)
        judgement = judge(
            contract, family, gate, value=parsed.content, verifier=verifier
        )
        if judgement.retry is not None:
            notes[this.rung.name] = judgement.retry
        return judgement

    return attempt


def gate_in_sandbox(
    contract: Contract,
    sandbox: Sandbox,
    content: str,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> GateResult:
    """Write ``content`` as the contract's target in ``sandbox`` and gate it.

    Shared by both tiers, which is the point: a change is judged by the same
    rungs whether a program produced it or a model did, and a floor with its own
    weaker gate would make "the deterministic tier is cheap" mean "the
    deterministic tier is unchecked".

    The write is through ``surrogateescape``, as every other writer in the
    project is (:mod:`mcgyvr.lines`): a reply is text that came off a socket and
    may carry bytes no codec round-trips, and a writer that raised on them would
    fail the attempt for the one reason the worker cannot do anything about.

    The acceptance commands are the contract's own, split by
    :attr:`~mcgyvr.contract.Contract.acceptance_commands`, and they run inside
    this sandbox — never on the host. That is the whole reason the gate takes an
    :class:`~mcgyvr.gate.acceptance.Acceptance` bound to a sandbox rather than a
    list of commands.
    """
    sandbox.reset()
    target = sandbox.workspace / contract.target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8", "surrogateescape"))
    return gate_workspace(contract, sandbox, adapters=adapters)


def gate_workspace(
    contract: Contract,
    sandbox: Sandbox,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> GateResult:
    """Judge whatever is in ``sandbox`` right now against ``contract``.

    The half of :func:`gate_in_sandbox` that does not write, because the two
    tiers arrive at a change differently and are judged identically. A model
    hands back content and something has to put it on disk; a program on the
    deterministic floor has already written the tree itself, and a gate that
    insisted on being handed content would have to read the file back out and
    write it again — two more chances for the bytes to stop being the bytes,
    which is the defect class B6 came from.
    """
    acceptance = None
    if contract.acceptance_commands or contract.demonstration_commands:
        acceptance = Acceptance(
            sandbox,
            contract.acceptance_commands,
            demonstrations=contract.demonstration_commands,
        )
    return Gate(adapters).run(
        ChangeSet.detect(sandbox.workspace),
        contract.scope,
        acceptance=acceptance,
    )
