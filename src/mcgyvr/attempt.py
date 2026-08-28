"""Repeated attempts on one rung, each told what the one before it got wrong.

Both ends of this already existed and only the middle was missing.
:class:`~mcgyvr.escalate.RetryNotes` decides what a note may carry and excludes
three things by name; :func:`~mcgyvr.worker.prompt.build_prompt` renders a note
into the user message when it is handed one. What nothing did was take a
rejected attempt, read the note :func:`~mcgyvr.escalate.judge` had already put
on it, and hand that note to the next attempt — so ``build_prompt``'s ``retry``
parameter had no production caller and ``Judgement.retry`` was populated and
read by nobody.

That gap is not cosmetic. Without it a second attempt re-sends the identical
prompt to the identical model at temperature 0.0, which is a second sample of a
deterministic function: spend whose result is known before it is paid for. The
default of one attempt per rung is the only reason it has not cost anything yet.

**The note is not built here.** ``judge`` already produces the right one for
both rejecting paths — ``RetryNotes.of(gate)`` for a gate rejection, and the
reviewer's own words for a refusal, where the gate passed and the refusal is
therefore the whole of what failed. Rebuilding either here would be a second
place for the exclusions to be got wrong, so this module only carries what it
is given.

**A failed attempt with nothing to say ends the loop.** ``reviewer_failed`` is
the case that matters: the verifier broke, the worker did not, and the next
prompt would be byte-identical to the one that just ran. Retrying it spends a
rung's budget to re-run a deterministic function, which is the same waste this
module exists to remove — so an attempt that produces no note is treated as the
end of what this rung can learn.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from mcgyvr.contract import Contract
from mcgyvr.escalate import Judgement, RetryNotes
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.route import Verdict
from mcgyvr.worker.prompt import WorkerPrompt, build_prompt


def run[T](
    contract: Contract,
    work: Callable[[WorkerPrompt], Judgement[T]],
    *,
    attempts: int = 1,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Judgement[T]:
    """Run ``work`` on ``contract`` until it passes or ``attempts`` are spent.

    ``work`` is the caller's, exactly as it is :func:`~mcgyvr.route.climb`'s and
    :func:`~mcgyvr.escalate.escalate`'s. This module decides what an attempt is
    *told*, which is settled before any model is reached; it does not decide how
    one is dispatched.

    The first prompt carries no note. That is asserted negatively as well as
    positively, because a loop that stapled the previous rejection onto every
    prompt would charge the opening attempt of every task for a retry that had
    not happened and may never run.
    """
    if attempts < 1:
        raise ValueError(f"a rung must be allowed at least one attempt, got {attempts}")

    def dispatch(retry: RetryNotes | None) -> Judgement[T]:
        return work(build_prompt(contract, adapters=adapters, retry=retry))

    # The opening attempt is dispatched outside the loop rather than guarded
    # inside it, so that "the first prompt carries no note" is a property of the
    # shape here and not of a flag that some later branch could fail to clear.
    outcome = dispatch(None)
    for _ in range(attempts - 1):
        if outcome.verdict is not Verdict.FAILED or outcome.retry is None:
            return outcome
        outcome = dispatch(outcome.retry)
    return outcome
