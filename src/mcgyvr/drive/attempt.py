"""How one rung is tried: prompt, draws, gate, review, verdict, journal row.

`worker_attempt` builds the driver the escalation ladder calls once per try of a
rung, answering a `Judgement` for it. An attempt reads the tree the run started
from, assembles the contract's prompt, sends it once per draw the rung is
configured for — greedy for the first, sampled for the rest — parses each reply,
gates every draw that parsed, tidies the winner and puts it through the
reviewer's typed questions, then asks the reviewer for a verdict when the
contract owes one. Every dispatch is one journal row.

What it does not decide is what a failure means for the run: a rung with no free
slot declines, so the climb moves on, and anything else raised leaves as a
`DispatchRaisedError` carrying the rows the attempt wrote and the draw that
raised, for the ladder to weigh.
"""

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
    """What this attempt has written down, for the judgement and the journal.

    `rows` counts the dispatches that were observed into the journal — one row
    each, and none at all when no `Recording` was given, because the counting
    happens on the recording path only. `culprit` is the draw whose dispatch
    raised, remembered by `_settled` so the error that ends the attempt can name
    it.
    """

    rows: int = 0
    culprit: int | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def counted(self) -> None:
        """Count one dispatch that was observed, under the lock threads share."""
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
    reviewers: Reviewers | None = None,
) -> Callable[[Try], Judgement]:
    """Build the driver that tries one rung: `Try` in, `Judgement` out.

    The whole attempt lives in the returned callable, which is why what it needs
    once is bound here: the ladder's config and source map, the contract, the
    sandbox the draws are written into and gated in, the language adapters, the
    journal, the cooldown and the reviewer selector. A driver outlives one
    attempt — the climb calls it again for the same rung — so it also keeps the
    per-rung notes a later attempt is told about.
    """
    notes: dict[str, RetryNotes | None] = {}
    # Each rung's note from its last attempt, handed to `build_prompt` as `retry`
    # so the worker is told what the gate or the reviewer found. The assignment
    # is unconditional, so an attempt that produced no note clears the entry
    # instead of passing a stale one on.
    checked: list[str] = []
    if reviewers is None and reviewer is not None:
        # A bare `ask` seam stands in for the run's reviewer: it becomes one
        # `Reviewer`, carrying the `verifier` role's model or no model at all
        # when the role binds none, and that same reviewer answers for every
        # builder. It is how a caller — a test — hands in a function where the
        # run hands in a configured unit, without a source map able to place the
        # reviewer.
        only = Reviewer(model=pool.role_model(VERIFIER_ROLE) or "", ask=reviewer)
        reviewers = lambda builder: only  # noqa: E731
    # The temperature the draws after the first are sampled at, from
    # `breadth.temperature`: `_temperature_of` keeps draw 0 greedy whatever it
    # says, so a rung that draws once sends a greedy request. A config that does
    # not name the key at all falls back to 0.0 here, which makes every draw
    # greedy.
    temperature = float(config.get("breadth.temperature", 0.0))
    tidying = bool(config.get("cleanup.enabled", True))
    # The run's `max_window_fraction`: the largest share of a rung's window one
    # contract — prompt and declared reply together — may claim, checked before
    # anything is sent. `None` means the run declared no share, which is not the
    # same as 1.0, and `None` is what the preflight is given so only the
    # contract's own `limits.max_window_fraction` then bounds it.
    declared_share = config.get("max_window_fraction")
    window_share = float(declared_share) if declared_share is not None else None
    # The waker this run shares: it wakes a card whose dispatch was refused and
    # is `None` when serving sleep and wake is not configured, in which case
    # every send is simply made.
    waker = _drive.wake_for_config(config)

    def attempt(this: Try) -> Judgement:
        # One try of one rung: a fresh counter for the rows it will write, the
        # number of draws that rung is configured for — `draws:` may override the
        # ladder's `breadth.draws` per unit — and then the attempt itself. A rung
        # with no free slot declines so the climb moves on; anything else raised
        # leaves as a `DispatchRaisedError` carrying the rows already written and
        # the draw that raised.
        made = _Dispatches()
        draws = draws_for(config, this.rung.name)
        try:
            return _attempt(this, made, draws)
        except SlotUnavailableError as busy:
            # The draws found no free slot — every dispatch was refused for
            # capacity, which `_settled` turns into a raise — so nothing was
            # gated and nothing is wrong with the rung: declining is what lets the
            # climb try the next one. The policy is still the one this contract
            # owes in this family, and the counts are what the attempt can
            # honestly report: the draws the rung asked for, and the rows it
            # wrote on the way.
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
        # The reviewer this rung would be judged by, if any: a contract whose
        # kind does not judge a change is never reviewed, and neither is a run
        # with no selector. The selector's answer is kept whole
        # because a `NoReviewer` is a reason to report and not a failure.
        # `_through` routes a reviewer's seams through the waker when its unit is
        # one this run can wake, and `jev_bound` says the typed questions are
        # served by their own bound role, which must not be woken on the
        # reviewer's behalf.
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
            # A source the run holds out is not dispatched to at all: the probe's
            # dead sources and a source whose failure streak armed a cooldown
            # both answer through `unavailable`. Declining keeps the rung in the
            # ladder for a later climb and costs nothing, where a dispatch would
            # spend the attempt on a connection the run already knows will not
            # answer. The check is per source, so every rung on a cooling source
            # goes with it.
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
                    # Nothing was sent, so there is no row to correct: `rows` is
                    # zero while `draws` still says how many this rung would have
                    # asked for had it been dispatched to.
                    draws=draws,
                    rows=0,
                )

        def judge_draw(space: Sandbox) -> GateResult:
            # A code contract is gated over the tree as the reply left it: the
            # project's own checks, the adapters' static ones and the acceptance
            # commands, whose findings are the verdict's. A rejection the
            # deterministic tools can repair is repaired and gated again, unless
            # cleanup is switched off for this run.
            result = _drive.gate_workspace(
                contract, space, adapters=adapters, config=config
            )
            if result.accepted or not tidying:
                return result
            return _repair_and_regate(
                contract, space, result, adapters=adapters, config=config
            )

        # The prompt is assembled from the tree the run started from, not from
        # whatever the previous draw left in the sandbox: `reset` restores it
        # before anything is read, so every attempt of every draw is asked the
        # same question and every reply is gated against the same base.
        sandbox.reset()
        # The target's content in that starting tree: handed to the reviewer as
        # the `original` it compares the change with, and used as the prompt's
        # base when the contract states no target content of its own.
        original = _base_content(sandbox, contract)
        # The contract the prompt and the preflight are built from: the base
        # content stands in for a target the contract did not state, and the
        # `sources` it names are read out of the workspace here — under the rules
        # every read of the tree for a worker follows, so a source that is
        # absolute, escapes the tree, holds a secret, is binary or is too large
        # refuses the attempt before anything is sent. `sized` is what the
        # preflight measures and what every draw is dispatched against.
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
        # The whole climb is preflighted once per driver: a rung further up the
        # ladder that cannot be sent to ends the run before the cheap rungs below
        # it spend anything. Later attempts skip it — the contract and the rungs'
        # windows have not changed since — and rely on the per-rung check below.
        if not checked:
            checked.append(this.rung.name)
            refuse_unsendable_climb(
                config, pool, sized, prompt, window_fraction=window_share
            )
        # This rung is checked on every attempt, because the prompt is not the one
        # the climb check measured: the retry notes grow it. The check refuses an
        # unstated output cap, a prompt that does not fit its own ceiling, a
        # contract whose declared reply is too large for the rung's window and a
        # contract claiming too much of that window — each raised as a
        # `DriveError`, before a token is spent.
        refuse_unsendable(
            this.rung.name,
            pool.bind(this.rung.name),
            prompt,
            sized,
            window_fraction=window_share,
        )
        # Two journal fields, gathered only when the run records: the endpoint the
        # row is stamped with, read from the source map rather than from the
        # completion so a row that never answered still says where it was sent,
        # and the messages exactly as they are about to go on the wire. Neither
        # is used by the dispatch itself.
        served_at = pool.bind(this.rung.name).base_url if recording else None
        messages = _drive._as_sent(prompt) if recording else None

        def fetch(draw: int, capacity: Capacity | None) -> Completion:
            """Send this one draw and answer its completion.

            The temperature is greedy for draw 0 and `breadth.temperature` after
            it. Every step between the prompt and the wire is wrapped around that
            one send: the waker, which wakes a refused card, the cooldown, which
            counts the source's health, and the journal row for this dispatch.
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
                # With a waker, a card that is asleep is woken before the send and
                # a connection it refuses is retried once it is up, which the
                # waker does once per card however many draws are refused while it
                # comes up. With no waker — an install whose units stay resident —
                # the send is simply made.
                if waker is None:
                    return wire()
                return waker.dispatching(this.rung.name, wire, capacity=capacity)

            def once() -> Completion:
                if cooldown is None:
                    return asked()
                served = pool.bind(this.rung.name)
                try:
                    completion = asked()
                except RunnerError:
                    # The send failed at the transport, which is one failed
                    # dispatch against that source: the cooldown counts it, and a
                    # source that keeps failing arms a sentence and is held out.
                    # The error is re-raised unchanged — what a failed draw means
                    # for the attempt is decided by `_settled`, not here.
                    cooldown.record_failure(served.source)
                    raise
                cooldown.record_success(served.source)
                return completion

            if recording is None:
                # No journal means no row to write and nothing to correct later,
                # so the dispatch is just made. `made.counted` below is reached
                # only on the recording path, which is why `rows` stays 0 when a
                # run records nothing.
                return once()
            # A row per dispatch: `attempt_id` suffixes the draw number past draw
            # 0, so each draw of a breadthed rung is a row of its own.
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
                    # The tier a row is filed under is the rung's family, so the
                    # journal reads by what served the work without resolving the
                    # rung back to its unit. `observe` records it beside the
                    # rung, the model and the endpoint.
                    tier=family.name,
                    # The temperature actually sent, so a greedy draw and a
                    # sampled one are told apart in the row without replaying the
                    # draw index.
                    temperature=sampled,
                    mirrors=recording.mirrors,
                    on_copy_error=recording.copy_failed,
                )
            finally:
                # Counted whether the send answered or raised, and only on this
                # path: a row was attempted for this dispatch, so the attempt's
                # count is one higher even when the row that landed says the
                # dispatch failed. Counting before the error leaves means the
                # `DispatchRaisedError` raised above reports the rows that were
                # written rather than the ones that were hoped for.
                made.counted()

        # Every draw is dispatched before any of them is gated: the prompt does
        # not depend on an earlier reply, so the draws can be in flight together
        # and only one reply is ever written into the sandbox at a time. With a
        # capacity in hand the batch runs on its pool, bounded by the slots this
        # try was given; without one the draws are made in order. `_settled` turns
        # the batch back into replies, or raises the failure that ends the
        # attempt.
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
                # A draw that produced nothing stays unusable here: `best_of`
                # records the reason and gates no candidate for it, so one draw
                # that could not be served does not throw away the draws that
                # could.
                return reply
            empty = empty_at_cap(reply)
            if empty is not None:
                # Truncated with nothing visible: the model spent its whole output
                # budget on hidden reasoning. There is no content to gate, so the
                # draw is unusable with that reason rather than being written into
                # the tree as an empty change.
                return Unusable(f"the reply could not be read: {empty}")
            parsed = parse_reply(
                reply.text,
                output_schema=contract.output_schema,
                stop_reason=reply.stop_reason,
                target=contract.target,
            )
            if isinstance(parsed, ReplyError):
                # The reply did not parse as the contract's schema asked — no
                # fenced block, a refusal, a truncated block: `parse_reply`
                # refuses it by name and the draw is unusable, which is honest
                # where a fabricated string would have been gated and ranked.
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
            # Every draw came back unreadable, so there is no winner to judge:
            # nothing was gated and nothing was accepted, and the exception names
            # each draw's refusal. The attempt fails, and the verdict is stamped
            # on draw 0 with the number of draws asked for, because those fields
            # have to describe the dispatches that happened: the journal corrects
            # `range(draws)` rows afterwards, and a judgement describing three
            # dispatches as one leaves the suffixed rows with no outcome at all.
            # Draw 0 is the row a reader reaches first — the unsuffixed one an
            # unconfigured single-draw run already writes — which is why the
            # verdict lands there rather than nowhere.
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
            # The reviewer's typed questions run over the winner here, once, before
            # the verdict: their findings and observations join the gate's, and the
            # change is re-read from the tree so what is bound is what those checks
            # saw. Nothing is asked when the gate rejected the change or when `jev`
            # is `None` — no independent reviewer serving this builder's model.
            gate, bound = _typed_checks(contract, sandbox, gate, bound, jev)
            judgement = _drive.judge(
                contract,
                family,
                gate,
                # The verifier the verdict may rest on, or `None` when no review
                # is owed: none is when the selector answered a `NoReviewer`.
                # `verify` is given the gate the change was accepted by, the
                # change as it will be delivered, the models on both sides, the
                # reviewer's `ask` and `decide` seams and the base content, so it
                # can say what changed. A reviewer that cannot answer leaves the
                # gate's acceptance standing and the verdict `unverified`; it
                # never fails the work.
                verifier=(
                    None
                    if reviewing is None
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
                # Why no review happened, where none did: the selector's own
                # reason when it named one, and the run's default sentence
                # otherwise. `judge` quotes it in the unverified detail.
                absent=(
                    chosen.reason if isinstance(chosen, NoReviewer) else NO_REVIEWER
                ),
                # The reviewer's label for the verdict's detail: the unit or the
                # model that answered, and the stand-in when one was used. Empty
                # when nothing was asked, so the detail names nobody.
                reviewer=reviewing.label if reviewing is not None else "",
            )
            # The verdict is re-stamped with what the attempt actually did.
            # `best_of` indexes its candidates, so `picked.dispatched` is the draw
            # the winning candidate came from — `chosen` would name a different
            # draw whenever an earlier one was unusable. `draws` says how many
            # were asked for and `rows` how many were written, so a reader of the
            # journal can tell one draw from a breadth and see whether every row
            # was accounted for.
            judgement = replace(
                judgement, draw=picked.dispatched, draws=draws, rows=made.rows
            )
            if gate.accepted:
                # The change rides on the judgement only when the gate accepted
                # it, and it is the file as the checks left it — tidied or
                # repaired — not the reply's bytes. `gate.accepted` is the gate's
                # own verdict, and `judge` can still fail the attempt on a
                # reviewer's refusal, so a failed judgement delivers nothing even
                # when it carries a content.
                judgement = replace(judgement, accepted=bound)

        notes[this.rung.name] = judgement.retry
        return judgement

    return attempt


def _temperature_of(draw: int, sampled: float) -> float:
    """The temperature one draw is sent at: draw 0 greedy, the others sampled.

    `sampled` is the run's `breadth.temperature`. Holding draw 0 at zero keeps a
    single-draw rung — and every install that configures no breadth — sending the
    same greedy request, so only the draws whose purpose is to differ are sampled.
    """
    return 0.0 if draw == 0 else sampled


def _in_order[T](
    jobs: Sequence[Callable[[Capacity | None], T]],
    capacity: Capacity | None = None,
) -> tuple[Outcome[T], ...]:
    """Run the draws one at a time, in the order they were asked for.

    The path with no capacity to share: each job is called in turn with the
    `capacity` given, which the attempt leaves as `None`, and its answer or its
    exception is kept as an `Outcome` at that job's index. Nothing is raised here,
    so what a failure means is decided once, in `_settled`.
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
    """Turn a batch of draws into replies, or raise what ends the attempt.

    A failure that is not a full slot is the attempt's failure: the draw that
    raised is remembered on `made` so the error leaving the attempt can name it.
    A batch in which every draw was refused for capacity raises the first of those
    refusals, which declines the rung; any other refusal becomes an `Unusable`
    reply, so a rung that filled one slot short of its draws still offers the
    draws that were served.
    """
    for outcome in outcomes:
        if outcome.error is not None and not isinstance(
            outcome.error, SlotUnavailableError
        ):
            made.culprit = outcome.index
            raise outcome.error
    declined = [o for o in outcomes if o.error is not None]
    if declined and len(declined) == len(outcomes):
        assert declined[0].error is not None  # the refusal this raises carries it
        raise declined[0].error
    replies: list[Completion | Unusable] = []
    for outcome in outcomes:
        if outcome.error is not None:
            replies.append(Unusable(f"no free slot: {outcome.error}"))
        else:
            assert outcome.value is not None  # an outcome with no error has one
            replies.append(outcome.value)
    return replies
