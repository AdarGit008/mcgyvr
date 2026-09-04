"""The raised history entry says what the raise site told it, and nothing else.

Which dispatch of an attempt was in flight when it raised is knowable in
exactly one place: the attempt function that was making it. Everywhere below
that it is gone — an exception carries no draw — and everywhere above it can
only be inferred, which is what the first repair of finding 7 did and what
made it wrong.

:class:`~mcgyvr.escalate.DispatchRaisedError` is the sentence the raise site gets to
say: *this many draws left a row, and this one is the row I died in* (or
``None``, for a raise before the first dispatch or after the last). ``escalate``
copies it onto the history entry and invents nothing; a bare exception, from a
driver that says nothing, is a raise that dispatched nothing.

This is pinned here rather than only through ``mcgyvr run`` because the entry
is ``escalate``'s alone: the caller that corrects the journal reads these two
fields and no longer has anything else to read them from.
"""

from __future__ import annotations

from collections.abc import Callable

from mcgyvr.escalate import DispatchRaisedError, Judgement, Outcome, escalate
from mcgyvr.route import Try, Verdict
from mcgyvr.runner import RunnerError
from tests.test_escalate import KEYLESS, contract, halted, mapped


def _raising(error: BaseException) -> Callable[[Try], Judgement]:
    """An attempt function that does the one thing this file is about."""

    def attempt(this: Try) -> Judgement:
        raise error

    return attempt


def test_the_entry_names_the_draw_the_raise_site_named() -> None:
    """Two draws written, the second one in flight: the entry says exactly that."""
    config, pool = mapped(KEYLESS)
    cause = RunnerError("connection refused")

    result = halted(
        escalate(
            config,
            pool,
            contract(),
            _raising(DispatchRaisedError(cause, dispatched=2, draw=1)),
        )
    )

    assert result.outcome is Outcome.ERROR
    (entry,) = result.history
    assert entry.raised is True
    assert entry.verdict is Verdict.FAILED
    assert (entry.draw, entry.draws) == (1, 2)
    assert (
        "RunnerError" in entry.detail and "DispatchRaisedError" not in entry.detail
    ), "the operator is told what died, not the envelope that carried the news"


def test_a_raise_after_the_draws_names_no_draw() -> None:
    """The rows are the attempt's; none of them is the one that raised."""
    config, pool = mapped(KEYLESS)

    result = halted(
        escalate(
            config,
            pool,
            contract(),
            _raising(DispatchRaisedError(RuntimeError("the judge died"), dispatched=2)),
        )
    )

    (entry,) = result.history
    assert (entry.draw, entry.draws) == (None, 2)


def test_a_driver_that_says_nothing_dispatched_nothing() -> None:
    """No claim from the raise site is no dispatch, not draw 0 of 1."""
    config, pool = mapped(KEYLESS)

    result = halted(
        escalate(config, pool, contract(), _raising(RuntimeError("nothing was built")))
    )

    (entry,) = result.history
    assert entry.raised is True
    assert (entry.draw, entry.draws) == (None, 0), (
        "the dataclass defaults claim draw 0 of 1, which is a dispatch nobody made"
    )
