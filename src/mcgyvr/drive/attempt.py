"""The one attempt: prompt, dispatch, parse, apply, gate, judge."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from functools import partial
from typing import TYPE_CHECKING

import mcgyvr.drive as _drive
from mcgyvr.capacity import Outcome, SlotUnavailableError
from mcgyvr.consensus import NoUsableDrawError, Unusable
from mcgyvr.decision import jev_bound
from mcgyvr.drive.gate import (
    _cleaned,
    _jev_for,
    _repair_and_regate,
    _through,
    _typed_checks,
)
from mcgyvr.drive.prompt import (
    _base_content,
    dispatch_prompt,
    refuse_unsendable,
    refuse_unsendable_climb,
)
from mcgyvr.drive.record import Recording
from mcgyvr.escalate import (
    NO_REVIEWER,
    DispatchRaisedError,
    Judgement,
    RetryNotes,
    required_policy,
)
from mcgyvr.route import Try, Verdict, draws_for, family_of
from mcgyvr.runner import Completion, RunnerError
from mcgyvr.telemetry import observe
from mcgyvr.verify import VERIFIER_ROLE, NoReviewer, Reviewer, verify
from mcgyvr.worker.reply import (
    MEDIA_ARTIFACT,
    PROSE,
    ReplyError,
    empty_at_cap,
    parse_reply,
)
from mcgyvr.worker.sources import read_sources

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Sequence

    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.cooldown import Cooldown
    from mcgyvr.gate import GateResult
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.verify import Ask, Reviewers


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


#: Where a session's reply is staged inside the sandbox workspace, and only
#: there: the workspace is thrown away and a session delivers nothing.
SESSION_REPLY = ".mcgyvr-session-reply.txt"


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
    reviewers: Reviewers | None = None,
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

    **``reviewers`` is the same seam, chosen per builder, and it is what
    ``mcgyvr run`` hands in.** :func:`~mcgyvr.verify.reviewers_for` names the
    reviewer of each rung's work — the bound ``verifier`` role (or a fallback
    standing in for it where its model wrote the work), or the next dearer
    local rung with another model — or says why there is none, and that
    sentence reaches the judgement. Each reviewer is asked for a typed verdict
    first and in prose where it serves no probabilities, and the same typed
    seam is the gate's Jev rung (:class:`~mcgyvr.gate.jev.JevCheck`): its
    questions are asked of the reviewer over the added lines of the change
    the gate accepted — once, never of a draw the gate rejected or of one that
    lost — and its answers arrive as observations, which reject nothing. A
    reviewer's dispatches go through the same waker as the builder's, so a
    reviewer on a sleeping card is woken rather than counted unusable.
    ``reviewer`` is the older, prose-only spelling and is used only when
    ``reviewers`` is not given.

    The pre-change file goes with it, read off the workspace in the moment
    between the reset and the first draw. A reviewer shown only the new content
    of an edited file is being asked to judge a change it cannot see, and the
    contract's own ``target_content`` — what ``build_prompt`` falls back to — is
    the orchestrator's copy from when the contract was written and is empty on a
    hand-authored one.

    **A cap one rung of the climb cannot hold ends the run before its first
    attempt.** :func:`refuse_unsendable_climb` asks every rung, with the first
    prompt, before anything is dispatched; each attempt then asks its own rung
    again, because a retry's prompt is longer.

    **A session's reply is staged at :data:`SESSION_REPLY`, never at its
    target.** A ``chat`` or ``agent`` contract names no target — its reply is
    the answer, returned in the result file and kept in the session log — but
    the draws are still written into the throwaway workspace so the output
    checks and the binding read them as they read a file. One fixed name for
    every session, so a target given anyway is not used here either.
    """
    if contract.is_session:
        contract = replace(contract, target=SESSION_REPLY)
    notes: dict[str, RetryNotes | None] = {}
    # The rung the climb was checked from, once: empty until the first attempt
    # has built its prompt (`refuse_unsendable_climb`).
    checked: list[str] = []
    if reviewers is None and reviewer is not None:
        # The prose-only seam, as one reviewer for every builder. Its model is
        # asked once, and only because there is a reviewer to name:
        # `role_model` raises for a role declared but unusable. An empty name
        # is left to `verify`, which refuses it — a review is worth the
        # distance between two names, and an unnamed reviewer establishes no
        # distance.
        only = Reviewer(model=pool.role_model(VERIFIER_ROLE) or "", ask=reviewer)
        reviewers = lambda builder: only  # noqa: E731
    # What the draws after the first sample at. Draw 0 never reads it: it is
    # greedy whatever this says, and the loader has refused `0.0` wherever any
    # unit draws more than once. The breadth itself is read per attempt, below,
    # because it is the rung's — `draws_for` — and not the driver's.
    temperature = float(config.get("breadth.temperature", 0.0))
    tidying = bool(config.get("cleanup.enabled", True))
    # The run's share of a rung's window, a ceiling over every contract's own.
    # Read once, here, because this is the layer holding the config, and
    # handed to both refusals below — before the draws and at the binding — so
    # the two cannot disagree on what the run allows.
    declared_share = config.get("max_window_fraction")
    window_share = float(declared_share) if declared_share is not None else None
    # `None` for a config that did not ask for sleep and wake. Built here rather than
    # threaded through `dispatch` as a parameter because this is the layer that
    # holds the config, and a card is derived from a config: `runner.dispatch`
    # takes a source map and a rung and deliberately knows about no machine.
    waker = _drive.wake_for_config(config)

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
        prose = contract.output_schema in (PROSE, MEDIA_ARTIFACT)
        # Who reviews this rung's work, read before anything is dispatched.
        # Its dispatches go through the waker, as the builder's do below: a
        # reviewer on a card that is asleep refuses the connection, and
        # without the wake every review on such an install is unusable. A
        # reply (`chat`, `agent`, `media`) has no reviewer at all — not the
        # prose verifier and not the gate's typed Jev questions either: there
        # is no change to review (owner, e2e run 2 R11: "agent and chat have
        # no gates").
        chosen: Reviewer | NoReviewer | None = (
            reviewers(this.rung.name)
            if reviewers is not None and contract.kind.judges_a_change
            else None
        )
        reviewing = (
            _through(waker, chosen, jev_resident=jev_bound(pool))
            if isinstance(chosen, Reviewer)
            else None
        )
        jev = _jev_for(this.rung.model, reviewing)
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
            if prose:
                # A raw-text reply is the answer, not a file to tidy or repair.
                # The only bar it must clear is the output evidence its
                # contract declares; chat declares none and accepts on the spot.
                return _drive.gate_prose_workspace(contract, space)
            # The gate is handed the sandbox, not a bare path, because a
            # contract's acceptance commands run any program they name, inside
            # a sandbox and nowhere else. `gate_workspace` takes the
            # sandbox and judges whatever is in it right now, so the draw
            # `best_of` just wrote is what the verdict is about.
            result = _drive.gate_workspace(
                contract, space, adapters=adapters, config=config
            )
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
        # not, so fall back to the workspace's own copy. Its `sources` are read
        # off the same tree, in the same moment (`mcgyvr.worker.sources`): a
        # source that cannot be given raises here, before the first dispatch.
        # The same contract is what is checked and dispatched below, so the
        # prompt measured against a unit's ceiling is the prompt that is sent.
        sized = replace(
            contract,
            target_content=contract.target_content or original,
            source_content=read_sources(sandbox.workspace, contract.sources),
        )
        prompt = _drive.build_prompt(
            sized,
            adapters=adapters,
            retry=notes.get(this.rung.name),
        )
        # Before the first attempt, every rung of the climb: a cap one of them
        # cannot hold would otherwise be found only on the escalation to it,
        # after the cheaper rungs had spent their attempts (owner, 2026-10-14).
        # The first prompt is the one measured; each attempt still checks its
        # own, below, because a retry's notes make it longer.
        if not checked:
            checked.append(this.rung.name)
            refuse_unsendable_climb(
                config, pool, sized, prompt, window_fraction=window_share
            )
        # A prompt that cannot go to this rung is refused here, before the
        # draws, and not only inside `dispatch_prompt`: there it would be
        # inside the journal's `observe` (a row for a request never sent) and
        # behind the waker (a sleeping card woken to be refused). Raised before
        # the first dispatch, it is `rows == 0`, and `escalate` ends the run as
        # an error on this rung without trying a bigger one (owner ruling).
        refuse_unsendable(
            this.rung.name,
            pool.bind(this.rung.name),
            prompt,
            sized,
            window_fraction=window_share,
        )
        # Read once, before any draw goes out, because they are the attempt's
        # and not a draw's: the endpoint that will serve every draw and the
        # prompt exactly as the runner sends it. Both can raise, and a raise
        # here is a raise before the first dispatch — no row, `rows == 0`: the
        # draws leave together, so there is no "between two draws" for it to
        # land in.
        served_at = pool.bind(this.rung.name).base_url if recording else None
        messages = _drive._as_sent(prompt) if recording else None

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
                    sized,
                    capacity=capacity,
                    timeout_s=(
                        config.units[this.rung.name].request_timeout_s
                        if this.rung.name in config.units
                        else None
                    ),
                    temperature=sampled,
                    window_fraction=window_share,
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
            _drive.run_batch(jobs, this.capacity)
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
            empty = empty_at_cap(reply)
            if empty is not None:
                # Before the parser, which would call this a truncated file:
                # nothing visible came back to be truncated (the e2e run of
                # 2026-10-13), and the repair is a larger cap, not a smaller
                # task.
                return Unusable(f"the reply could not be read: {empty}")
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
            picked = _drive.best_of(
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
            if tidying and not prose:
                gate, bound = _cleaned(
                    contract, sandbox, gate, bound, adapters=adapters, config=config
                )
            # The reviewer's typed checks, asked once, of the change that is
            # delivered, and only once the gate has accepted it: each is a
            # request to the reviewer, so neither a draw the gate rejected nor
            # a draw that lost to another is worth one.
            gate, bound = _typed_checks(contract, sandbox, gate, bound, jev)
            judgement = _drive.judge(
                contract,
                family,
                gate,
                # Built here rather than handed in, because `verify` needs
                # three things only this moment holds: the gate that has just
                # run, the bytes it read, and which model wrote them. What
                # crosses the seam is the reviewer itself, and `judge` decides
                # whether to ask it: `partial` binds arguments and dispatches
                # nothing, so a rejected gate costs no verifier spend. A
                # raw-text reply is never verifier-reviewed — there is no file
                # change to review — so prose answers are judged with no
                # verifier whatever an install configured.
                verifier=(
                    None
                    if prose or reviewing is None
                    else partial(
                        verify,
                        contract,
                        family=family,
                        gate=gate,
                        change=bound.content,
                        builder=this.rung.model,
                        reviewer=reviewing.model,
                        ask=reviewing.ask,
                        original=original,
                        decide=reviewing.decide,
                    )
                ),
                # Why no reviewer was asked, for a change that wanted one: the
                # configured reviewer's own reason it cannot be used, or none
                # configured at all. A reply never reads this — `judge` says
                # how it was judged without a reviewer in the sentence.
                absent=(
                    chosen.reason if isinstance(chosen, NoReviewer) else NO_REVIEWER
                ),
                # Who signs a `verified`: the reviewing unit, and — for one
                # standing in for a `verifier.unit` that wrote the change —
                # that it is a fallback and why (`Reviewer.label`).
                reviewer=reviewing.label if reviewing is not None else "",
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
