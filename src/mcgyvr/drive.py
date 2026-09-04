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

from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.cleanup import tidy
from mcgyvr.consensus import NoUsableDrawError, Unusable, best_of
from mcgyvr.deliver import Accepted
from mcgyvr.escalate import Judgement, RetryNotes, judge, required_policy
from mcgyvr.gate import Gate, GateResult
from mcgyvr.gate.acceptance import DID_NOT_RUN, Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.route import Try, Verdict, family_of
from mcgyvr.runner import Completion, Request, RunnerError, dispatch
from mcgyvr.telemetry import observe
from mcgyvr.verify import VERIFIER_ROLE, verify
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
    which is what :attr:`performed` is for. ``ruff check --fix`` exits **1**
    whenever a diagnostic remains after fixing — the ordinary outcome of a
    ``lint_fix`` contract, and the exact shape that type's guarantee describes.
    A caller reading ``not ok`` as fatal reported a contract carried out to the
    letter as an error and never reached the gate that was supposed to judge
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
        (:attr:`~mcgyvr.deterministic.Tool.reporting`, whose measured table
        says which). For a fixer that is 1 — "I applied every autofix I have,
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

    ``run`` tells one run of a contract from the next. The orchestrator is now
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

    def __post_init__(self) -> None:
        if not self.orchestrator.strip():
            raise ValueError(
                "an orchestrator id is required to record: a row that cannot "
                "say which orchestrator produced it is the hole the field "
                "exists to close (§9)."
            )

    def attempt_id(self, contract: str, rung: str, attempt: int, draw: int = 0) -> str:
        """The id one dispatch's row is keyed by.

        The orchestrator is part of it, and that is not decoration.
        :func:`~mcgyvr.telemetry.fold` keys attempts by this string and a repeat
        supersedes — "a re-logged attempt id supersedes" — so two orchestrators
        working the same contract on the same rung, which is the exact case §9
        is keeping reachable, would have written one row that erased the other.
        The rest is derived rather than random so a row can be found again from
        a report naming the contract, the rung and the attempt.

        ``draw`` is here for the same reason the orchestrator is. An attempt
        that asks its rung for several candidates (``breadth.draws``) makes one
        dispatch per draw, and a key that named only the attempt would have let
        each row supersede the last: n dispatches paid for, one recorded, and
        the telemetry saying breadth costs what a single draw costs. The first
        draw is left unsuffixed so that every row an unconfigured install writes
        is byte-identical to the ones written before breadth existed — a
        superseding key must not change meaning under a stream that already
        holds rows.
        """
        who = f"{self.orchestrator}:{self.run}" if self.run else self.orchestrator
        row = f"{who}:{contract}:{rung}:{attempt}"
        return row if draw == 0 else f"{row}#{draw}"


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

    **The retry note comes from the last judgement on the same rung — the last
    one, not the last one that had something to say.**
    :func:`~mcgyvr.route.climb` owns how many attempts a rung gets, and its
    ``Result`` carries a verdict rather than notes, so the note is held here,
    per rung, and handed to ``build_prompt``. ``mcgyvr.attempt.run`` is the
    standalone spelling of the same loop, for a caller that is not climbing;
    running both would be two loops counting one budget.

    The write is unconditional and the map holds ``RetryNotes | None``, which
    is ``tools/missions/attempt.py``'s spelling and is the right one. The guard
    it replaces — ``if judgement.retry is not None`` — could store a note and
    never clear one, and two attempts produce none: the ``ReplyError`` branch
    below returns before the assignment is reached, and a ``reviewer_failed``
    judgement reaches it carrying ``retry=None`` because the gate passed and a
    verifier that produced no verdict left nothing to quote. Under the guard,
    the attempt after either of those was prompted with the note from the
    attempt before, which the worker has already been asked to fix once.

    That is worse than sending nothing rather than merely stale, because of
    what the prompt does with it: ``render_user_message`` renders a note under
    "YOUR PREVIOUS ATTEMPT WAS REJECTED. Fix exactly these and change nothing
    else — every other check passed". Against an attempt that was never gated,
    all three claims are false, and the last of them is a claim about a gate
    run that did not happen. So the rule is that a note is *this* attempt's
    account of *this* attempt: an attempt with nothing to say says nothing, and
    the next one starts from the evidence rather than from a memory of it.

    The alternative was to keep the guard and give the parse failure a note of
    its own — which the sibling does, in its ``_unparsed``. It is rejected here
    on two counts: it fixes one of the two producers of ``retry=None`` and
    leaves ``reviewer_failed`` waved through the same guard, and the note it
    would invent is not the gate's finding a note is supposed to be. The guard
    was the defect, not the branch that stepped over it.

    **A reply that cannot be read is a failed attempt, not an exception.** The
    parser refuses by name — truncated, no fenced block, a refusal in place of
    a file — and every one of those is something the next attempt could do
    differently, which is the definition of a failure rather than a fault. It
    reaches :func:`~mcgyvr.consensus.best_of` as an
    :class:`~mcgyvr.consensus.Unusable` draw, so at ``n > 1`` one unreadable
    reply costs its own draw and not the verdicts of the draws beside it; the
    attempt fails only when :class:`~mcgyvr.consensus.NoUsableDrawError` says every
    draw refused, which for the default single draw is the same thing.

    **How many answers the attempt asks for is ``breadth.draws``'s, and the
    default asks once.** Every attempt goes through
    :func:`~mcgyvr.consensus.best_of`, including the unconfigured one, rather
    than through a single-dispatch branch beside it. A lever the ordinary
    install skips is a lever the ordinary install never proves, and ``n = 1``
    through ``best_of`` is the same behaviour by construction: one draw, one
    verdict, and the draw is the answer. What it costs is that the workspace is
    reset after the last draw as it is after every other one, so the attempt
    ends with the sandbox holding the base — which is why the accepted bytes
    leave here as the binding ``best_of`` minted in the tree its gate read,
    rather than being re-read off a workspace that no longer holds them.

    **A style-only rejection is cleaned before it is judged, when
    ``cleanup.enabled`` says so.** The ordering is the whole of it: the cleanup
    goes between the gate and :func:`~mcgyvr.escalate.judge`, so what is judged
    is the file that came *out* of it. Running it afterwards would mean deciding
    whether to escalate on a verdict about bytes nobody was still holding, and
    running it before the gate would mean tidying a change nothing had yet found
    a problem with. Off by default, and the default is the behaviour that
    existed: the gate's rejection stands, the note goes to the next attempt, and
    a model is asked about the whitespace.

    **``reviewer`` is the verifier seam, not a finished verdict function.** It
    is an :data:`~mcgyvr.verify.Ask` — one prompt in, one reply out — and the
    :class:`~mcgyvr.escalate.Review` :func:`~mcgyvr.escalate.judge` wants is
    assembled per attempt from it, because :func:`~mcgyvr.verify.verify` needs
    the gate that has just run, the bytes it read and the name of the model
    that wrote them. The parameter this replaces asked the caller for a
    ``Callable[[], Review]``, and that is why nothing in production ever passed
    one: a caller standing outside the attempt has none of those three things.
    :func:`~mcgyvr.verify.reviewer_for` is where an install's ``verifier`` role
    becomes one of these, and ``None`` stays the ordinary answer — a keyless
    install accepts on the gate and ``judge`` labels it ``UNVERIFIED``.

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
    draws = int(config.get("breadth.draws", 1))
    tidying = bool(config.get("cleanup.enabled", False))

    def attempt(this: Try) -> Judgement:
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
                )

        def send(draw: int) -> Completion:
            def once() -> Completion:
                if cooldown is None:
                    return dispatch_prompt(
                        pool,
                        this.rung.name,
                        prompt,
                        contract,
                        capacity=this.capacity,
                    )
                endpoint = pool.bind(this.rung.name)
                try:
                    completion = dispatch_prompt(
                        pool,
                        this.rung.name,
                        prompt,
                        contract,
                        capacity=this.capacity,
                    )
                except RunnerError:
                    # The dispatch is what the cooldown learns from: a source
                    # that answered and failed the generation is the fault this
                    # lever exists for. A prompt that did not fit is a contract
                    # fault and raises `DriveError`, which must not count against
                    # the source.
                    cooldown.record_failure(endpoint.source)
                    raise
                cooldown.record_success(endpoint.source)
                return completion

            if recording is None:
                return once()
            return observe(
                once,
                path=recording.path,
                attempt_id=recording.attempt_id(
                    contract.id, this.rung.name, this.attempt, draw
                ),
                orchestrator=recording.orchestrator,
                rung=this.rung.name,
                model=this.rung.model,
                # The journal exists to be reviewed, and a review needs the
                # prompt as the runner sent it and the endpoint that served
                # it. Bound here, before the attempt, so the row of an attempt
                # that raised still says what it asked and where.
                messages=_as_sent(prompt),
                endpoint=pool.bind(this.rung.name).base_url,
                task_type=contract.task_type,
                session_file=recording.session_file,
            )

        def sample(draw: int) -> str | Unusable:
            completion = send(draw)
            parsed = parse_reply(
                completion.text,
                output_schema=contract.output_schema,
                stop_reason=completion.stop_reason,
                target=contract.target,
            )
            if isinstance(parsed, ReplyError):
                # A refusal, not a raise: at `n > 1` the draws already gated
                # keep their verdicts, and a reply that could not be read is
                # the ordinary failure this rung is being measured on rather
                # than something that ends the attempt from underneath it.
                return Unusable(f"the reply could not be read: {parsed}")
            return parsed.content

        def judge_draw(space: Sandbox) -> GateResult:
            # The gate is handed the sandbox, not a bare path, because a
            # contract's acceptance commands are arbitrary shell and run inside
            # a sandbox and nowhere else (ADR-0005). `gate_workspace` takes the
            # sandbox and judges whatever is in it right now, so the draw
            # `best_of` just wrote is what the verdict is about.
            return gate_workspace(contract, space, adapters=adapters)

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
        # not, so fall back to the workspace's own copy (K6).
        prompt = build_prompt(
            replace(contract, target_content=contract.target_content or original),
            adapters=adapters,
            retry=notes.get(this.rung.name),
        )
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
            judgement = Judgement(
                verdict=Verdict.FAILED,
                policy=required_policy(contract, family),
                detail=str(exc),
            )
        else:
            gate, bound = picked.gate, picked.winner
            if tidying:
                gate, bound = _cleaned(
                    contract, sandbox, gate, bound, adapters=adapters
                )
            judgement = judge(
                contract,
                family,
                gate,
                # Built here rather than handed in, because `verify` needs
                # three things only this moment holds: the gate that has just
                # run, the bytes it read, and which model wrote them. The
                # parameter this replaces was a `Callable[[], Review]`
                # assembled before the attempt, which is why it never had a
                # production caller — there was nothing a caller could build it
                # out of. What crosses the seam is the reviewer itself, and
                # `judge` still decides whether to ask it: `partial` binds
                # arguments and dispatches nothing, so a rejected gate costs no
                # verifier spend, exactly as before.
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
            # Which draw the verdict is about, and how many were paid for: one
            # journal row per draw was written above, keyed by the *dispatch*
            # index `send` was called with. `picked.chosen` counts candidates
            # and skips the draws that produced none, so under an unreadable
            # first reply it named the wrong row; `dispatched` is the index
            # the row was keyed by.
            judgement = replace(judgement, draw=picked.dispatched, draws=len(picked))
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

    Decoded the way every other reader in the project decodes worker-adjacent
    bytes: ``surrogateescape``, so a file holding a byte no decoder can read
    still reaches the reviewer as the rest of its content rather than raising
    out of an attempt that has not failed.
    """
    target = sandbox.workspace / contract.target
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
    file is exactly the substitution the whole port was audited for.

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
    regated = gate_in_sandbox(contract, sandbox, cleanup.content, adapters=adapters)
    return regated, Accepted.read(
        repo=sandbox.workspace, contract=contract, result=regated
    )


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

    "Against ``contract``" now includes the contract's own words. Two rungs
    could only ever be as right as what the contract asked for — the acceptance
    commands, and ``param-mutation``, which rejects a function for mutating its
    caller's object and has to stand down where the contract *ordered* that.
    Only the first was wired; the second's stand-down existed with no parameter
    anywhere between here and it, so a contract saying "sort the rows in place"
    was unsatisfiable by any change a worker could write.
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
        contract_text=contract.prose,
    )
