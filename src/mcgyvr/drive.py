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

import threading
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.capacity import Outcome, SlotUnavailableError, run_batch
from mcgyvr.cleanup import tidy
from mcgyvr.consensus import NoUsableDrawError, Unusable, best_of
from mcgyvr.deliver import Accepted
from mcgyvr.escalate import (
    DispatchRaisedError,
    Judgement,
    RetryNotes,
    judge,
    required_policy,
)
from mcgyvr.gate import Finding, Gate, GateResult
from mcgyvr.gate.acceptance import DID_NOT_RUN, Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.preflight import reply_cap
from mcgyvr.gate.semantic import SemanticCheck
from mcgyvr.gate.typecheck import TypeCheck
from mcgyvr.route import Try, Verdict, draws_for, family_of
from mcgyvr.runner import Completion, Request, RunnerError, dispatch
from mcgyvr.sandbox.base import nested_git
from mcgyvr.scope import inside
from mcgyvr.telemetry import observe
from mcgyvr.verify import VERIFIER_ROLE, verify
from mcgyvr.wake import for_config as wake_for_config
from mcgyvr.worker.prompt import build_prompt
from mcgyvr.worker.reply import ReplyError, parse_reply

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Sequence

    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.cooldown import Cooldown
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.pool import SourceMap
    from mcgyvr.sandbox.base import CommandResult, Sandbox
    from mcgyvr.verify import Ask
    from mcgyvr.worker.prompt import WorkerPrompt


class DriveError(Exception):
    """A step could not be executed as planned, for a reason in this module."""


class UnrunnableStepError(DriveError):
    """The step names no program, so a subprocess executor cannot run it."""


class PromptTooLargeError(DriveError):
    """The assembled prompt does not fit the ceiling its own contract set."""


class OutputCapTooLargeError(DriveError):
    """The reply cap for this rung does not fit the window that rung serves.

    Distinct from :class:`PromptTooLargeError` because the repair is: one is a
    contract to re-decompose, the other is a number on the ladder to re-declare.
    A rung asking for more reply room than its machine serves would be
    truncated at a boundary nobody chose — the failure a per-rung cap exists to
    end — so it is refused at the seam that would have sent it.
    """


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
    a diagnostic remains after fixing has carried out a ``lint_fix`` contract,
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
    in-process type, ``rename_symbol``, is executed here against the sandbox's
    own tree by :func:`mcgyvr.rename.apply`, because what performs it is
    mcgyvr's index rather than a program on PATH. Its refusals are the type's
    own — an unstated pair, a symbol the index does not know — and they arrive
    as a failed :class:`ToolOutcome`, never as an environment issue: nothing is
    missing from the machine.

    Raises :class:`UnrunnableStepError` for a step that names neither a command
    nor an in-process executor.
    """
    if not step.argv:
        return _run_in_process(step, sandbox)

    # A formatter is a program like any acceptance command, and one that hangs
    # is held to the same ceiling.
    if timeout is None:
        timeout = task_ceiling()
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


def _run_in_process(step: ToolStep, sandbox: Sandbox) -> ToolOutcome:
    """The floor's in-process executors, keyed by the type they perform.

    The outcome is shaped as a :class:`~mcgyvr.sandbox.base.CommandResult` with
    a command of ``()`` so that every reader downstream — the journal, the
    escalation ladder, the CLI's own reporting — handles one kind of thing. A
    second outcome shape for the one type with no program would have every one
    of those readers grow a branch for it.
    """
    from mcgyvr.deterministic import IN_PROCESS
    from mcgyvr.rename import RenameError
    from mcgyvr.rename import apply as rename_apply
    from mcgyvr.sandbox.base import CommandResult

    if step.tool.task_type not in IN_PROCESS:
        raise UnrunnableStepError(
            f"task type {step.tool.task_type!r} names no command to run and "
            f"mcgyvr has no in-process executor for it. Reporting it complete "
            f"would report a file changed that nothing opened."
        )
    try:
        report = rename_apply(Path(sandbox.workspace), step.rename.old, step.rename.new)
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


def dispatch_prompt(
    source_map: SourceMap,
    rung: str,
    prompt: WorkerPrompt,
    contract: Contract,
    *,
    capacity: Capacity | None = None,
    response_schema: dict[str, Any] | None = None,
    timeout_s: float | None = None,
    temperature: float | None = None,
) -> Completion:
    """Send an assembled prompt to a rung, under the contract's own ceilings.

    Both halves of the prompt travel — ``system`` carries the bundle the
    target's language earned and dropping it would send a worker the
    instructions for no language at all — and the output cap is
    :func:`~mcgyvr.gate.preflight.reply_cap`'s: the rung's own
    ``units.*.output_tokens`` where it declared one, and the contract's
    ``limits.max_output_tokens`` where it did not. The argument for which of
    the two wins is written where the choice is made, in ``reply_cap``.

    ``contract`` is taken whole rather than as a cap, because a binding given
    only a number cannot be the place the fit refusal happens, and the refusal
    is the point: a prompt that does not fit
    :attr:`~mcgyvr.contract.Contract.max_input_tokens` is refused here, with the
    preflight issue ``build_prompt`` already computed, instead of being sent to
    be truncated somewhere that cannot say why. A per-rung cap adds a second
    refusal of the same kind and for the same reason — a cap the rung's own
    window cannot hold — and it is checked here rather than trusted to the
    ladder's author, because this is the last place that holds both numbers
    before they reach a socket. ``build_prompt`` cannot ask it: a prompt is
    assembled once and may be offered to several rungs, and which window it
    faces is only known here.

    ``temperature`` is the draw's, threaded from ``breadth.temperature`` by the
    caller that knows which draw this is: draw 0 of an attempt is greedy and
    the draws after it sample. ``None`` keeps :class:`~mcgyvr.runner.Request`'s
    own default of ``0.0``.
    """
    if not prompt.fits:
        raise PromptTooLargeError(
            f"contract {contract.id!r}: the assembled prompt does not fit its "
            f"own ceiling and was not sent — {prompt.fit_issue}"
        )
    endpoint = source_map.bind(rung)
    cap = reply_cap(contract, endpoint)
    window = endpoint.context_window
    if window is not None and cap >= window:
        raise OutputCapTooLargeError(
            f"rung {rung!r}: a reply cap of {cap} tokens does not fit the "
            f"{window}-token window {endpoint.source!r} serves, leaving nothing "
            f"for the prompt. Lower `units.{rung}.output_tokens`, or "
            f"point the rung at a machine that serves more"
        )
    # ``timeout_s`` is the unit's ``request_timeout_s``, passed by the caller
    # that holds the config. ``None`` keeps ``Request``'s own default.
    fields: dict[str, Any] = {
        "prompt": prompt.user,
        "system": prompt.system,
        "max_output_tokens": cap,
        "response_schema": response_schema,
    }
    if timeout_s is not None:
        fields["timeout_s"] = timeout_s
    if temperature is not None:
        fields["temperature"] = temperature
    request = Request(**fields)
    return dispatch(source_map, rung, request, capacity=capacity)


@dataclass(frozen=True)
class Recording:
    """Where attempt records go, and which orchestrator is writing them.

    Records carry an orchestrator id and nothing here keeps global mutable
    state, so two orchestrators can share a stream.
    :func:`~mcgyvr.telemetry.observe` takes ``orchestrator`` as a required
    parameter.

    The id is a value the caller constructs rather than something this module
    derives from the process. A default — a hostname, a pid, a literal
    ``"mcgyvr"`` — would be a single-orchestrator assumption: two orchestrators
    sharing a stream would then write rows that agree about who produced them,
    and the field's whole purpose is telling them apart.

    Recording is optional at this seam because a run that cannot write its
    telemetry should fail loudly rather than silently — ``observe`` raises on
    an unwritable sink on purpose — and a caller that has not chosen a sink
    has not chosen to accept that failure. ``mcgyvr run`` always chooses one
    for a dispatching contract: the config's ``journal.dir``, or ``--record``.

    ``path`` is the line sink. The prompts and replies the run dispatches land
    beside it, content-addressed under ``path.parent / "blobs"``, so two
    orchestrators recording into one directory share one blob store and own
    one file each — the layout ``<journal dir>/<orchestrator>.jsonl`` relies
    on.

    ``run`` tells one run of a contract from the next. The orchestrator is
    a whole session, and a session re-runs a contract exactly when the last
    run failed, so without it two runs would key their rows identically and
    :func:`~mcgyvr.telemetry.fold` would bind every correction to the latest
    row — erasing the failure from the folded view. It is the stamp the run's
    result file carries, so a row and its result name the same run.
    """

    path: Path
    orchestrator: str
    run: str = ""
    #: The transcript of the session that typed the command, when the
    #: orchestrator is one (:mod:`mcgyvr.session`). Written on every row so an
    #: attempt can be followed back to the conversation that produced it.
    session_file: Path | None = None
    #: Directories the caller asked for a copy of this journal in (``--record``).
    #: Every line and every blob goes to each of them as well as to
    #: :attr:`path`, which is mcgyvr's own and is the one that cannot move: the
    #: journal is a corpus to be compounded, and a run recorded only in a
    #: directory somebody chose for that run is a run no later question reaches.
    #: A copy lives in a repository as often as not, and repositories are
    #: cloned, go stale and are thrown away.
    mirrors: tuple[Path, ...] = ()
    #: The first failure seen per copy, kept rather than raised. Mutable inside
    #: a frozen record on purpose: the failures are learned while the run is
    #: happening and are reported once when it ends, and the alternative — a
    #: line per row — is thousands of lines about one full disk.
    #:
    #: Out of ``__eq__`` and ``__hash__`` (``compare=False``), which a frozen
    #: dataclass generates from its fields: two recordings pointed at the same
    #: sink are the same recording whatever has since gone wrong with somebody's
    #: copy, and a dict field left in would make this class unhashable the day
    #: anything put one in a set.
    copy_errors: dict[Path, str] = field(default_factory=dict, compare=False)

    def copy_failed(self, mirror: Path, exc: BaseException) -> None:
        """Keep the first thing that went wrong with one copy, and carry on.

        Handed to :mod:`mcgyvr.telemetry` as its ``on_copy_error``. First and
        not last, because the first is the one that says what happened: a
        directory that is a file fails identically on every row after the
        first, and the last failure of a thousand identical ones is no more
        informative than the first and arrives with the wrong timestamp.
        """
        self.copy_errors.setdefault(mirror, f"{type(exc).__name__}: {exc}")

    def __post_init__(self) -> None:
        if not self.orchestrator.strip():
            raise ValueError(
                "an orchestrator id is required to record: a row that cannot "
                "say which orchestrator produced it is the hole the field "
                "exists to close."
            )

    def attempt_id(self, contract: str, rung: str, attempt: int, draw: int = 0) -> str:
        """The id one dispatch's row is keyed by.

        The orchestrator is part of it, and that is not decoration.
        :func:`~mcgyvr.telemetry.fold` binds a correction to the latest row
        carrying this string, so two orchestrators working the same contract on
        the same rung would otherwise share an id, and a correction meant for
        one row would land on the other. The rest is derived rather than random
        so a row can be found again from a report naming the contract, the rung
        and the attempt.

        ``draw`` is here for the same reason the orchestrator is. An attempt
        that asks its rung for several candidates makes one dispatch per draw,
        and a key that named only the attempt would give every draw's row one
        id, so a correction could reach only the last. The first draw is left
        unsuffixed: rows a journal already holds carry keys with no draw, and a
        correction finds its row by that key.
        """
        who = f"{self.orchestrator}:{self.run}" if self.run else self.orchestrator
        row = f"{who}:{contract}:{rung}:{attempt}"
        return row if draw == 0 else f"{row}#{draw}"


@dataclass
class _Dispatches:
    """What one attempt has sent so far, kept so a raise can say it.

    Mutable and deliberately so: it is written by the dispatches that are
    happening and read by the ``except`` that ends the attempt, which is the
    one moment the two facts still exist together. Everything below has thrown
    them away — an exception carries no draw — and everything above can only
    infer them, which is what :class:`~mcgyvr.escalate.DispatchRaisedError` exists
    to stop.

    ``rows`` is how many draws left a journal row. It is counted around
    :func:`~mcgyvr.telemetry.observe`, which writes exactly one record per
    call — the answering row or the failing one — and never where a dispatch
    was merely intended: ``pool.bind`` and the prompt are read once, before
    any draw goes out, so a raise there is a raise before the first dispatch
    and leaves no row. A driver built without a ``recording`` reaches
    ``observe`` never and counts nothing, which is the same rule and not an
    exception to it: this is rows written, not draws taken. The single case
    the count cannot see is the journal file itself being unwritable, which
    loses every row of the run and not one of them.

    The draws of one attempt are dispatched together, so the count is taken
    under ``lock``: two draws finishing at once must not lose a row between
    them, because the caller corrects ``range(rows)`` of them and a row
    uncounted is a row never corrected.

    ``culprit`` is the draw the attempt died in, or ``None`` where no
    dispatch is the culprit. It is settled *after* the draws have all come
    back, not while they are in flight — with several in flight there is no
    single "draw happening right now" — and when more than one raised it is
    the **lowest** that raised: the row a reader reaches first, and the answer
    that does not depend on which thread finished first. ``None`` is everything else
    — the gate that judges a draw, the cleanup, the verifier all run after the
    dispatches and none of them is a dispatch's fault — and ``rows`` says
    where: ``0`` is before the first dispatch, and anything more is past draw
    ``rows - 1``, a reading that belongs to a run with a journal, since a run
    without one has no rows to count and says ``0`` for every moment.
    """

    rows: int = 0
    culprit: int | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def counted(self) -> None:
        """One more row is on disk."""
        with self.lock:
            self.rows += 1


def worker_attempt(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    sandbox: Sandbox,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    reviewer: Ask | None = None,
    recording: Recording | None = None,
    cooldown: Cooldown | None = None,
) -> Callable[[Try], Judgement]:
    """The attempt function :func:`~mcgyvr.escalate.escalate` takes.

    ``escalate``, ``climb`` and ``judge`` leave assembling a prompt,
    dispatching, applying and gating to their caller. This is that caller, and
    it is deliberately the only place in the project that knows the order of
    those things.

    **One attempt is: prompt, dispatch, parse, apply, gate, judge.** The order
    is not arbitrary at two points. The gate runs before the verifier is named,
    which :func:`~mcgyvr.escalate.judge` enforces structurally and this does not
    get to re-decide. And the sandbox is reset *before* each write rather than
    after each failure, so an attempt that raises cannot leave the next one
    judging a tree it did not produce — a ``finally`` that tidies up is one
    exception away from not having run.

    **Everything it raises comes out as
    :class:`~mcgyvr.escalate.DispatchRaisedError`,** carrying the cause and two
    facts nothing above can recover: how many of this attempt's draws left a
    journal row, and which one it was in when it died — or that it died where
    no dispatch was, before the first draw or after the last. Only the function
    making the dispatches holds either. :func:`~mcgyvr.escalate.escalate`
    unwraps the envelope, so the operator is still told what died and not what
    carried the news.

    **The retry note comes from the last judgement on the same rung — the last
    one, not the last one that had something to say.**
    :func:`~mcgyvr.route.climb` owns how many attempts a rung gets, and its
    ``Result`` carries a verdict rather than notes, so the note is held here,
    per rung, and handed to ``build_prompt``. A standalone spelling of the same
    loop for a caller that is not climbing would be two loops counting one
    budget.

    The write is unconditional and the map holds ``RetryNotes | None``. A
    guarded write — ``if judgement.retry is not None`` — could store a note and
    never clear one, and two kinds of attempt produce none: one where no draw
    was usable, and a ``reviewer_failed`` judgement, which carries
    ``retry=None`` because the gate passed and a verifier that produced no
    verdict left nothing to quote. The attempt after either of those would be
    prompted with the note from the attempt before. So a note is *this*
    attempt's account of *this* attempt: an attempt with nothing to say says
    nothing.

    **A reply that cannot be read is a failed attempt, not an exception.** The
    parser refuses by name — truncated, no fenced block, a refusal in place of
    a file — and every one of those is something the next attempt could do
    differently, which is the definition of a failure rather than a fault. It
    reaches :func:`~mcgyvr.consensus.best_of` as an
    :class:`~mcgyvr.consensus.Unusable` draw, so at ``n > 1`` one unreadable
    reply costs its own draw and not the verdicts of the draws beside it; the
    attempt fails only when :class:`~mcgyvr.consensus.NoUsableDrawError` says every
    draw refused, which for the default single draw is the same thing.

    **How many answers the attempt asks for is the rung's breadth
    (:func:`~mcgyvr.route.draws_for`).** Every attempt goes through
    :func:`~mcgyvr.consensus.best_of`, including a single-draw one, rather
    than through a single-dispatch branch beside it: one draw, one
    verdict, and the draw is the answer. What it costs is that the workspace is
    reset after the last draw as it is after every other one, so the attempt
    ends with the sandbox holding the base — which is why the accepted bytes
    leave here as the binding ``best_of`` minted in the tree its gate read,
    rather than being re-read off a workspace that no longer holds them.

    **The draws go out together, and draw 0 is greedy.** They are dispatched
    as one :func:`~mcgyvr.capacity.run_batch` under the attempt's capacity,
    so a unit declared able to serve several requests serves the draws at
    once and a width-1 unit's slot serializes them without a second limiter;
    ``best_of`` is then handed a ``sample`` that returns the reply already in
    hand, and gates the draws one at a time in the one sandbox, which is
    inherent. Draw 0 goes out at temperature ``0.0`` and draws 1..n-1 at
    ``breadth.temperature``, because a second candidate that is the first one
    again buys a gate run and nothing else. Each row of the journal says which
    draw it was and at what temperature.

    **A style-only rejection is cleaned before it is judged, when
    ``cleanup.enabled`` says so.** The ordering is the whole of it: the cleanup
    goes between the gate and :func:`~mcgyvr.escalate.judge`, so what is judged
    is the file that came *out* of it. Running it afterwards would mean deciding
    whether to escalate on a verdict about bytes nobody was still holding, and
    running it before the gate would mean tidying a change nothing had yet found
    a problem with. On by default; ``cleanup.enabled: false`` leaves the gate's
    rejection standing.

    **``reviewer`` is the verifier seam, not a finished verdict function.** It
    is an :data:`~mcgyvr.verify.Ask` — one prompt in, one reply out — and the
    :class:`~mcgyvr.escalate.Review` :func:`~mcgyvr.escalate.judge` wants is
    assembled per attempt from it, because :func:`~mcgyvr.verify.verify` needs
    the gate that has just run, the bytes it read and the name of the model
    that wrote them, and a caller standing outside the attempt has none of
    those three things.
    :func:`~mcgyvr.verify.reviewer_for` is where an install's ``verifier`` role
    becomes one of these, and ``None`` is an ordinary answer — an install with
    no verifier accepts on the gate and ``judge`` labels it ``UNVERIFIED``.

    The pre-change file goes with it, read off the workspace in the moment
    between the reset and the first draw. A reviewer shown only the new content
    of an edited file is being asked to judge a change it cannot see, and the
    contract's own ``target_content`` — what ``build_prompt`` falls back to — is
    the orchestrator's copy from when the contract was written and is empty on a
    hand-authored one.
    """
    notes: dict[str, RetryNotes | None] = {}
    # Asked once, and only when there is a reviewer to name: `role_model`
    # raises for a role declared but unusable, and an install that is not
    # verifying has not asked that question. An empty name is left to `verify`,
    # which refuses it — a review is worth the distance between two names, and
    # an unnamed reviewer establishes no distance.
    reviewer_model = pool.role_model(VERIFIER_ROLE) if reviewer is not None else None
    # What the draws after the first sample at. Draw 0 never reads it: it is
    # greedy whatever this says, and the loader has refused `0.0` wherever any
    # unit draws more than once. The breadth itself is read per attempt, below,
    # because it is the rung's — `draws_for` — and not the driver's.
    temperature = float(config.get("breadth.temperature", 0.0))
    tidying = bool(config.get("cleanup.enabled", True))
    # `None` for a config that did not ask for sleep and wake. Built here rather than
    # threaded through `dispatch` as a parameter because this is the layer that
    # holds the config, and a card is derived from a config: `runner.dispatch`
    # takes a source map and a rung and deliberately knows about no machine.
    waker = wake_for_config(config)

    def attempt(this: Try) -> Judgement:
        # The whole of this function's failure path, in one place. Everything
        # `_attempt` can raise is turned into the one sentence only a driver
        # can say — what breadth it was asked for, how many of its dispatches
        # left a journal row, and which one it was in — because the caller that
        # corrects those rows has no other way to learn it. `escalate` unwraps
        # this into `_AttemptError`, so nothing downstream sees the envelope.
        made = _Dispatches()
        draws = draws_for(config, this.rung.name)
        try:
            return _attempt(this, made, draws)
        except SlotUnavailableError as busy:
            # Every slot of this rung was taken for as long as the task was
            # willing to wait. Nothing was asked and nothing answered, so this
            # is the cooldown's verdict and not a failure: `escalate` walks
            # past a declined rung without spending an attempt or funding an
            # escalation, which sends the work to a rung that has room instead
            # of holding a command open on one that does not.
            return Judgement(
                verdict=Verdict.DECLINED,
                policy=required_policy(contract, family_of(config, this.rung.name)),
                detail=f"rung {this.rung.name!r} has no free slot: {busy}",
                draws=draws,
                rows=made.rows,
            )
        except Exception as exc:
            raise DispatchRaisedError(
                exc, draws=draws, rows=made.rows, draw=made.culprit
            ) from exc

    def _attempt(this: Try, made: _Dispatches, draws: int) -> Judgement:
        family = family_of(config, this.rung.name)
        if cooldown is not None:
            # Ask before a prompt is built or a sandbox is opened: a rung on a
            # source that has just failed several dispatches in a row is
            # declined rather than tried, and the decline costs nothing because
            # `escalate` walks past a declined rung without spending an attempt.
            # The liveness half is a stub here (the caller supplies one), so the
            # only reasons that reach this are the failures the dispatches have
            # already paid for.
            endpoint = pool.bind(this.rung.name)
            cooling = cooldown.unavailable([endpoint])
            if endpoint.source in cooling:
                return Judgement(
                    verdict=Verdict.DECLINED,
                    policy=required_policy(contract, family),
                    detail=(
                        f"rung {this.rung.name!r} is on source {endpoint.source!r}, "
                        f"which is cooling down: {cooling[endpoint.source]}"
                    ),
                    # The breadth this rung would have spent, and the nothing
                    # it did spend: a decline costs no dispatch, so it wrote no
                    # row.
                    draws=draws,
                    rows=0,
                )

        def judge_draw(space: Sandbox) -> GateResult:
            # The gate is handed the sandbox, not a bare path, because a
            # contract's acceptance commands are arbitrary shell and run inside
            # a sandbox and nowhere else. `gate_workspace` takes the
            # sandbox and judges whatever is in it right now, so the draw
            # `best_of` just wrote is what the verdict is about.
            result = gate_workspace(contract, space, adapters=adapters, config=config)
            if result.accepted or not tidying:
                return result
            return _repair_and_regate(
                contract, space, result, adapters=adapters, config=config
            )

        # Before the writes rather than after the last one, which is the same
        # bargain `gate_in_sandbox` makes and for the same reason: `best_of`
        # tidies up in a `finally`, and a `finally` is one exception away from
        # not having run. An attempt that inherited the previous one's tree
        # would judge a change it did not produce.
        sandbox.reset()
        # Read here, in the one moment the base is on disk: the workspace has
        # just been reset and no draw has been written over it yet.
        original = _base_content(sandbox, contract)
        # The worker prompt needs the file it is changing. A decomposed
        # contract carries it as `target_content`; a hand-authored one does
        # not, so fall back to the workspace's own copy.
        prompt = build_prompt(
            replace(contract, target_content=contract.target_content or original),
            adapters=adapters,
            retry=notes.get(this.rung.name),
        )
        # Read once, before any draw goes out, because they are the attempt's
        # and not a draw's: the endpoint that will serve every draw and the
        # prompt exactly as the runner sends it. Both can raise, and a raise
        # here is a raise before the first dispatch — no row, `rows == 0`: the
        # draws leave together, so there is no "between two draws" for it to
        # land in.
        served_at = pool.bind(this.rung.name).base_url if recording else None
        messages = _as_sent(prompt) if recording else None

        def fetch(draw: int, capacity: Capacity | None) -> Completion:
            """One draw's reply off the wire, under the capacity it was handed.

            ``capacity`` is a parameter rather than a closure over
            ``this.capacity`` because :func:`~mcgyvr.capacity.run_batch` hands
            every job the capacity it must dispatch under, and the signature is
            the one place that puts the thing a job needs into its hand. It is
            the same object; what the shape buys is that a draw dispatching
            without a slot cannot be written by accident.
            """
            sampled = _temperature_of(draw, temperature)

            def wire() -> Completion:
                return dispatch_prompt(
                    pool,
                    this.rung.name,
                    prompt,
                    contract,
                    capacity=capacity,
                    timeout_s=(
                        config.units[this.rung.name].request_timeout_s
                        if this.rung.name in config.units
                        else None
                    ),
                    temperature=sampled,
                )

            def asked() -> Completion:
                # The wake sits *inside* the cooldown's view and outside the
                # transport, and the order is the whole of what it buys. A
                # refused port on a card mcgyvr holds a launch spec for is not
                # a fault of the rung — nothing was asked and nothing answered
                # — so the cooldown must not learn from it and the attempt must
                # not be charged for it. `waker` is None for a config that did
                # not ask for the feature.
                if waker is None:
                    return wire()
                return waker.dispatching(this.rung.name, wire)

            def once() -> Completion:
                if cooldown is None:
                    return asked()
                served = pool.bind(this.rung.name)
                try:
                    completion = asked()
                except RunnerError:
                    # The dispatch is what the cooldown learns from: a source
                    # that answered and failed the generation is the fault this
                    # lever exists for. A prompt that did not fit is a contract
                    # fault and raises `DriveError`, which must not count against
                    # the source.
                    cooldown.record_failure(served.source)
                    raise
                cooldown.record_success(served.source)
                return completion

            if recording is None:
                # No journal, so no rows to count and none to correct. The
                # dispatch still happened, and a raise out of it is still
                # settled onto this draw by `_settled`.
                return once()
            # The row's id is derived, not read, so it cannot raise; what
            # could — the endpoint and the prompt — was read once above.
            attempt_id = recording.attempt_id(
                contract.id, this.rung.name, this.attempt, draw
            )
            try:
                return observe(
                    once,
                    path=recording.path,
                    attempt_id=attempt_id,
                    orchestrator=recording.orchestrator,
                    rung=this.rung.name,
                    model=this.rung.model,
                    messages=messages,
                    endpoint=served_at,
                    task_type=contract.task_type,
                    session_file=recording.session_file,
                    # The tier this rung belongs to, so one query can count a
                    # ladder dispatch against a floor run: the floor's rows
                    # carry a program's name in `rung` and `deterministic`
                    # here, and without the second field the two vocabularies
                    # share a column and nothing tells them apart.
                    tier=family.name,
                    # What this draw sampled at, on its own row, so the
                    # journal can say which draw a passing candidate was and
                    # at what temperature.
                    temperature=sampled,
                    mirrors=recording.mirrors,
                    on_copy_error=recording.copy_failed,
                )
            finally:
                # In `finally`, because the row is written on both of
                # `observe`'s paths: it promises exactly one record per call,
                # the answering row or the failing one, and a dispatch that
                # left none is one no caller can tell from a dispatch nobody
                # made. So the count is of rows on disk and not of intentions
                # — which is what it has to be, or the correction for the last
                # one names a row nobody wrote. Counted under the lock: the
                # draws finish in whatever order the unit answers.
                made.counted()

        # The draws go out together, bounded by the unit's width and nothing
        # else. Each `run_batch` job dispatches under the capacity it is
        # handed, so on a width-1 unit the slot serializes the draws and no
        # second limiter is needed. The outcomes come back in draw order
        # whatever order the unit answered in, and `_settled` turns them into
        # the replies `best_of` ranks — or into the one raise the attempt
        # dies of, charged to the lowest draw that raised. With no capacity
        # there is no width to dispatch within, and the draws go out one after
        # another in this thread.
        jobs = [partial(fetch, draw) for draw in range(draws)]
        outcomes = (
            run_batch(jobs, this.capacity)
            if this.capacity is not None
            else _in_order(jobs)
        )
        fetched = _settled(outcomes, made)

        def sample(index: int) -> str | Unusable:
            reply = fetched[index]
            if isinstance(reply, Unusable):
                # A draw that found no free slot for as long as the task would
                # wait: nothing was asked and nothing answered, so it is not a
                # candidate and not a failure. The draws that did answer keep
                # their verdicts.
                return reply
            parsed = parse_reply(
                reply.text,
                output_schema=contract.output_schema,
                stop_reason=reply.stop_reason,
                target=contract.target,
            )
            if isinstance(parsed, ReplyError):
                # A refusal, not a raise: at `n > 1` the draws already gated
                # keep their verdicts, and a reply that could not be read is
                # the ordinary failure this rung is being measured on rather
                # than something that ends the attempt from underneath it.
                return Unusable(f"the reply could not be read: {parsed}")
            return parsed.content

        try:
            picked = best_of(
                contract=contract,
                sample=sample,
                gate=judge_draw,
                n=draws,
                sandbox=sandbox,
            )
        except NoUsableDrawError as exc:
            # No retry note: the note vocabulary is the gate's findings, and
            # nothing was gated. What the next attempt would need to hear is the
            # refusal itself, which `detail` carries to the caller's report.
            #
            # `rows` is stated here for the same reason it is stated on the
            # branch below: `fetch` wrote one journal row per dispatch, and the
            # caller corrects `range(rows)` of them. It is read off
            # `made`, which counted the rows that went down, rather than off
            # the breadth, which is what was asked for: with no `recording`
            # there is no journal and the honest count is none. The verdict is
            # carried on draw 0 because no draw earned it: nothing was gated,
            # the refusal names every draw, and 0 is both the row a reader
            # reaches first and the only draw an unconfigured install has.
            judgement = Judgement(
                verdict=Verdict.FAILED,
                policy=required_policy(contract, family),
                detail=str(exc),
                draw=0,
                draws=draws,
                rows=made.rows,
            )
        else:
            gate, bound = picked.gate, picked.winner
            if tidying:
                gate, bound = _cleaned(
                    contract, sandbox, gate, bound, adapters=adapters, config=config
                )
            judgement = judge(
                contract,
                family,
                gate,
                # Built here rather than handed in, because `verify` needs
                # three things only this moment holds: the gate that has just
                # run, the bytes it read, and which model wrote them. What
                # crosses the seam is the reviewer itself, and `judge` decides
                # whether to ask it: `partial` binds arguments and dispatches
                # nothing, so a rejected gate costs no verifier spend.
                verifier=(
                    None
                    if reviewer is None
                    else partial(
                        verify,
                        contract,
                        family=family,
                        gate=gate,
                        change=bound.content,
                        builder=this.rung.model,
                        reviewer=reviewer_model or "",
                        ask=reviewer,
                        original=original,
                    )
                ),
            )
            # Which draw the verdict is about, how many were asked for, and how
            # many left a row: one journal row per draw was written above,
            # keyed by the *dispatch* index `fetch` was called with.
            # `picked.chosen` counts candidates and skips the draws that
            # produced none, so under an unreadable first reply it names the
            # wrong row; `dispatched` is the index the row was keyed by. An
            # attempt that reached a verdict finished its draws, so with a
            # journal `made.rows == len(picked) == draws` here — the numbers
            # are stated separately anyway, because what makes them equal is
            # this branch and not the fields. `made.rows` is the one of the
            # three that stays true without a journal: a driver built with no
            # `recording` wrote nothing, and `rows` is what was written.
            judgement = replace(
                judgement, draw=picked.dispatched, draws=draws, rows=made.rows
            )
            if gate.accepted:
                # The winner's own binding, minted by `best_of` one line after
                # its gate and one line before its reset — in the tree the
                # verdict was reached in, which is the only moment it exists.
                # Reading the workspace here instead would answer for whatever
                # the last draw left behind, and after the reset for the base
                # itself. A binding minted from a string the caller happens to
                # be holding would be true by construction and would check
                # nothing. Where a cleanup rewrote the file, `_cleaned` has
                # replaced both halves together.
                judgement = replace(judgement, accepted=bound)

        notes[this.rung.name] = judgement.retry
        return judgement

    return attempt


def _temperature_of(draw: int, sampled: float) -> float:
    """What one draw samples at: greedy for draw 0, ``sampled`` for the rest.

    Draw 0 is the anchor: what a single-draw install sends, at the
    :class:`~mcgyvr.runner.Request` default of ``0.0``. The draws after it
    exist to be *different* candidates, and a greedy second draw is the first
    draw again: N dispatches, N identical replies, N gate runs, and nothing the
    first did not already say. The loader refuses ``breadth.temperature: 0.0``
    wherever a unit draws more than once for exactly that reason, so
    ``sampled`` is never zero here when it is read.
    """
    return 0.0 if draw == 0 else sampled


def _in_order[T](
    jobs: Sequence[Callable[[Capacity | None], T]],
    capacity: Capacity | None = None,
) -> tuple[Outcome[T], ...]:
    """The draws one after another in this thread, for an attempt with no capacity.

    :func:`~mcgyvr.capacity.run_batch` bounds a batch by a capacity, and a
    :class:`~mcgyvr.route.Try` handed none has no width to dispatch within — a
    single task running alone, which :func:`~mcgyvr.runner.dispatch` sends
    unbounded. Dispatching N draws at once with no bound would be the batch
    ``dispatch`` says it is wrong for, so they go out in order, here. The
    outcomes are shaped as ``run_batch``'s so the caller settles both paths the
    same way, and ``capacity`` is handed to each job as ``run_batch`` hands it,
    so a caller standing in for the batch still puts the capacity it was given
    into every draw's hand.
    """
    outcomes: list[Outcome[T]] = []
    for index, job in enumerate(jobs):
        try:
            outcomes.append(Outcome(index=index, value=job(capacity)))
        except Exception as exc:
            outcomes.append(Outcome(index=index, error=exc))
    return tuple(outcomes)


def _settled(
    outcomes: Sequence[Outcome[Completion]], made: _Dispatches
) -> list[Completion | Unusable]:
    """What each draw came back with, or the one raise the attempt dies of.

    Three kinds of outcome, settled in this order:

    * **A raise.** The lowest draw that raised is the culprit — recorded on
      ``made`` for the envelope the attempt is wrapped in — and its exception
      is re-raised as the attempt's. Every draw ran to completion first, so
      the rows are all down and ``made.rows`` says how many; the draws that
      answered are not judged, because an attempt that died reached no
      verdict and writing one on some of its draws would report a judgement
      that never happened.
    * **Every draw declined.** No slot freed for any of them for as long as
      the task would wait: nothing was asked and nothing answered, so the
      first decline is raised for the wrapper to turn into the rung stepping
      aside.
    * **Some draws declined.** The ones that answered were paid for and are
      judged; a declined draw is :class:`~mcgyvr.consensus.Unusable`, which
      is what it is — no candidate, no verdict — and is recorded in the
      consensus in its own words rather than counted as a failure of the
      unit. A decline is never a raise: :class:`SlotUnavailableError` is the
      one :class:`~mcgyvr.capacity.CapacityError` a caller may route around.
    """
    for outcome in outcomes:
        if outcome.error is not None and not isinstance(
            outcome.error, SlotUnavailableError
        ):
            made.culprit = outcome.index
            raise outcome.error
    declined = [o for o in outcomes if o.error is not None]
    if declined and len(declined) == len(outcomes):
        assert declined[0].error is not None  # the filter above
        raise declined[0].error
    replies: list[Completion | Unusable] = []
    for outcome in outcomes:
        if outcome.error is not None:
            replies.append(Unusable(f"no free slot: {outcome.error}"))
        else:
            assert outcome.value is not None  # `ok` outcomes carry a completion
            replies.append(outcome.value)
    return replies


def _base_content(sandbox: Sandbox, contract: Contract) -> str:
    """The target as it stands before this attempt writes anything.

    What a reviewer needs to judge an *edit*: without it
    :func:`~mcgyvr.verify.build_prompt` says the original was not supplied and
    asks the model to judge the change on its own, which for a change to an
    existing file is most of the question missing. ``""`` is the other real
    answer and the block below renders it as one — the target is not there, so
    the change creates it.

    Taken from the workspace rather than from ``contract.target_content``,
    which is what ``build_prompt`` falls back to. That field is the
    orchestrator's copy of the file as it stood when the contract was written,
    and a hand-authored contract does not carry it at all; this is the tree the
    gate diffed against a moment ago, in this attempt, which is the only
    original the verdict is actually about.

    Decoded with ``surrogateescape``, so a file holding a byte no decoder can read
    still reaches the reviewer as the rest of its content rather than raising
    out of an attempt that has not failed.
    """
    target = inside(sandbox.workspace, contract.target)
    if not target.is_file():
        return ""
    return target.read_bytes().decode("utf-8", "surrogateescape")


def _as_sent(prompt: WorkerPrompt) -> list[dict[str, str]]:
    """The messages exactly as :func:`dispatch_prompt` has the runner send them.

    Built here rather than inside :func:`~mcgyvr.telemetry.observe` because the
    journal records what was *sent* and only this module knows that: the runner
    adds a system message only when ``Request.system`` is non-empty, so an
    empty bundle is no message at all — not a message with nothing in it, whose
    digest would put a ``bundle_sha256`` on the row for a system prompt nobody
    received.
    """
    messages: list[dict[str, str]] = []
    if prompt.system:
        messages.append({"role": "system", "content": prompt.system})
    messages.append({"role": "user", "content": prompt.user})
    return messages


def _cleaned(
    contract: Contract,
    sandbox: Sandbox,
    result: GateResult,
    bound: Accepted,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> tuple[GateResult, Accepted]:
    """Tidy the winning draw, and re-judge it when the tidy-up changed it.

    The verdict and the binding move together or not at all, which is the whole
    reason this is one function rather than two lines at the call site. A
    :class:`~mcgyvr.cleanup.Cleanup` reports :attr:`~mcgyvr.cleanup.Cleanup.regate`
    when the bytes it hands back were rewritten, and its own
    :attr:`~mcgyvr.cleanup.Cleanup.accepted` is the verdict about the bytes that
    went *in* — deliberately, because behind a format rejection the gate stopped
    before its typecheck, semantic and acceptance rungs and this module has no
    idea what they would have said. Carrying that verdict forward beside the new
    file would be a verdict about bytes that are not the file's.

    So the answer to ``regate`` is a gate run, not a re-read. ``gate_in_sandbox``
    writes the cleaned bytes into the workspace and judges what is now there,
    and the binding is minted from that same tree — so the pair that leaves here
    is a verdict and the file it was computed over, as the pair that arrived was.

    ``tidy`` is handed :attr:`~mcgyvr.deliver.Accepted.content` rather than a
    string carried from the reply, and ``repo`` is the sandbox workspace rather
    than the user's checkout: the tree whose formatter configuration decides what
    clean means has to be the tree the gate checked, or the cleanup tidies a file
    into a shape the gate then complains about.

    One pass, not a loop. ``ruff format`` is a fixed point, so a second cleanup
    over the first one's output would rewrite nothing; a loop would be a retry
    budget nobody declared, inside an attempt that already has one.
    """
    cleanup = tidy(
        content=bound.content,
        result=result,
        target=contract.target,
        repo=sandbox.workspace,
    )
    if not cleanup.regate:
        return result, bound
    regated = gate_in_sandbox(
        contract, sandbox, cleanup.content, adapters=adapters, config=config
    )
    return regated, Accepted.read(
        repo=sandbox.workspace, contract=contract, result=regated
    )


def _repair_and_regate(
    contract: Contract,
    sandbox: Sandbox,
    rejected: GateResult,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> GateResult:
    """Repair and re-gate, on the same rung and with no model retry.

    The gate judges and never writes; :func:`mcgyvr.repair.repair` writes and
    never judges — the declared imports, the linter's own autofixes and the
    formatter, over the contract's scope and nothing else. A rejected draw is
    repaired in place and judged again before the ladder spends anything,
    under ``cleanup.enabled``, which is on unless an install says otherwise.

    The tree is what is delivered. ``best_of`` mints the winner's binding off
    this sandbox one line after this returns, so an accepted verdict here is
    a verdict about the repaired bytes and the file that leaves is the file
    that was judged; the reply the model sent is in the journal. When the
    tools changed nothing the first verdict stands unrepeated — a second
    gate over identical bytes is a subprocess for an answer already in hand.
    A repair that ran is said out loud as an observation, so a reader of the
    row knows the delivered file is not the reply verbatim; what the repair
    could not run rides along as an environment issue.
    """
    from mcgyvr.gate.findings import Finding
    from mcgyvr.gate.typecheck import STYLE
    from mcgyvr.repair import repair

    outcome = repair(sandbox=sandbox, contract=contract)
    if not outcome.changed:
        if outcome.environment_issues:
            return replace(
                rejected,
                environment_issues=(
                    *rejected.environment_issues,
                    *outcome.environment_issues,
                ),
            )
        return rejected
    regated = gate_workspace(contract, sandbox, adapters=adapters, config=config)
    noted = tuple(
        Finding(
            check=STYLE,
            path=path,
            message="repair: the deterministic tools rewrote this file before "
            "the verdict; what is delivered is the repaired tree, not the reply",
        )
        for path in outcome.repaired
    )
    return replace(
        regated,
        observations=(*regated.observations, *noted),
        environment_issues=(*regated.environment_issues, *outcome.environment_issues),
    )


def gate_in_sandbox(
    contract: Contract,
    sandbox: Sandbox,
    content: str,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> GateResult:
    """Write ``content`` as the contract's target in ``sandbox`` and gate it.

    Shared by both tiers, which is the point: a change is judged by the same
    rungs whether a program produced it or a model did, and a floor with its own
    weaker gate would make "the deterministic tier is cheap" mean "the
    deterministic tier is unchecked".

    The write is through ``surrogateescape``: a reply is text that came off a
    socket and may carry bytes no codec round-trips, and a writer that raised
    on them would fail the attempt for the one reason the worker cannot do
    anything about.

    The acceptance commands are the contract's own, split by
    :attr:`~mcgyvr.contract.Contract.acceptance_commands`, and they run inside
    this sandbox — never on the host. That is the whole reason the gate takes an
    :class:`~mcgyvr.gate.acceptance.Acceptance` bound to a sandbox rather than a
    list of commands.
    """
    sandbox.reset()
    target = inside(sandbox.workspace, contract.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8", "surrogateescape"))
    return gate_workspace(contract, sandbox, adapters=adapters, config=config)


def task_ceiling(config: Config | None = None) -> float | None:
    """The policy's ``task_timeout_s``, or ``None`` where no config settles it.

    A contract's acceptance command is arbitrary shell, and this is the ceiling
    one that hangs is held to.

    ``config`` is the run's own — the one ``--config`` named — and when a caller
    holds one it is the only answer: a run judged under another setup's ceiling
    is judged under a budget nobody gave it. A caller holding none gets the
    config at the default location.

    A *missing* default config is not an error here: refusing a gate because
    there is no config would make the ceiling a requirement rather than a
    bound, and a bare install is supported. No config means no declared
    ceiling, which is what `None` says. A config that is *there* and does not
    load is the other situation and raises (owner ruling): it is a ceiling the
    operator wrote, and reading it as "no ceiling" hands a contract's arbitrary
    shell no wall clock at all — silently, on the one surface a user is asked
    to edit.
    """
    if config is None:
        from mcgyvr.config import ConfigMissingError, load

        try:
            config = load()
        except ConfigMissingError:
            return None
    declared = config.get("task_timeout_s")
    return float(declared) if declared is not None else None


def acceptance_for(
    contract: Contract, sandbox: Sandbox, *, config: Config | None = None
) -> Acceptance | None:
    """The contract's acceptance rung, bound to ``sandbox`` and to the ceiling.

    ``None`` when the contract declares neither list — there is nothing to run
    and nothing to time. Built here rather than inside `Gate` because only this
    layer holds the open sandbox, and read by both the preflight in
    `cli._climb` and by :func:`gate_workspace`, so the commands a run is judged
    on are the commands its baseline was taken with.
    """
    if not (contract.acceptance_commands or contract.demonstration_commands):
        return None
    return Acceptance(
        sandbox,
        contract.acceptance_commands,
        timeout=task_ceiling(config),
        demonstrations=contract.demonstration_commands,
    )


def gate_workspace(
    contract: Contract,
    sandbox: Sandbox,
    *,
    adapters: Sequence[LanguageAdapter] | None = None,
    config: Config | None = None,
) -> GateResult:
    """Judge whatever is in ``sandbox`` right now against ``contract``.

    The half of :func:`gate_in_sandbox` that does not write, because the two
    tiers arrive at a change differently and are judged identically. A model
    hands back content and something has to put it on disk; a program on the
    deterministic floor has already written the tree itself, and a gate that
    insisted on being handed content would have to read the file back out and
    write it again — two more chances for the bytes to stop being the bytes.

    "Against ``contract``" includes the contract's own words
    (``contract_text``). Two rungs can only be as right as what the contract
    asked for — the acceptance commands, and ``param-mutation``, which rejects
    a function for mutating its caller's object and has to stand down where the
    contract *ordered* that.
    """
    nested = nested_git(sandbox.workspace)
    if nested is not None:
        # Before any host git reads the tree (owner ruling): a nested
        # repository's config is run by the child git host git starts in it.
        return GateResult(
            findings=(
                Finding(
                    check="workspace",
                    path=nested,
                    names_a_file=False,
                    code="nested-git",
                    message=(
                        f"the workspace holds the git entry {nested}; host git "
                        f"would run that repository's config, so the tree is "
                        f"not read and the change is not accepted"
                    ),
                ),
            )
        )
    acceptance = acceptance_for(contract, sandbox, config=config)
    return Gate(adapters).run(
        ChangeSet.detect(sandbox.workspace),
        contract.scope,
        acceptance=acceptance,
        # The other two rungs `Gate.run` accepts. They are built here and not
        # inside `Gate` because both need what only this layer holds: the open
        # sandbox, and the workspace the declaration lives in. A repository
        # that declares no checker still gets `None` from
        # `TypeCheck.declared_command`, so the absence is not a rejection.
        typecheck=TypeCheck(repo=sandbox.workspace),
        semantic=SemanticCheck(sandbox=sandbox),
        contract_text=contract.prose,
    )
