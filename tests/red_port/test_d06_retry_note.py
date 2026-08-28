"""D06 — a second attempt is told what the first one got wrong.

mcgyvr already owns both ends of this. :class:`~mcgyvr.escalate.RetryNotes` decides
what a note may carry and refuses three things by name; ``build_prompt(retry=...)``
renders it into the user message, last, after the output instruction. ``#43``'s own
suite holds both — ``tests/test_escalate.py`` asserts the note's contents and the
rendered prompt, and asserts the exclusions by name.

What does not exist is the middle. Nothing takes a rejected attempt, makes a note
from it, and hands that note to the next attempt. ``build_prompt``'s ``retry``
parameter has no production caller; ``Judgement.retry`` is populated by
:func:`~mcgyvr.escalate.judge` and read by nobody. So every retry mcgyvr could run
today would re-send the identical prompt to the identical model at temperature
0.0 — a second sample of a deterministic function, which is spend with a
known-in-advance result. The default of one attempt per rung is what has been hiding
it.

That is why these tests drive a **loop** rather than a note. Asserting that
``RetryNotes.of`` produces the right note is already done and would be done again
here for nothing; what is unheld is that the note reaches the next prompt. So the
attempt function is the test's, exactly as it is :func:`~mcgyvr.route.climb`'s and
:func:`~mcgyvr.escalate.escalate`'s, and what is asserted is the *prompt the second
call received*.

The first prompt is asserted too, and negatively. A loop that stapled the note onto
every prompt would pass a test that only looked at the second one, and it would
charge the first attempt of every task for a rejection that had not happened yet.

**The exclusions are the substance of the second test.** A note is worth having
because of what it leaves out: the whole gate report is roughly the size of the file
under change, and sending it back re-spends the context window telling a worker what
it already got right. Four exclusions are asserted by name, because each has its own
way of leaking back in:

* the *passing* checks — the temptation is to render the report, and a report has
  rows for what passed;
* the *observations* — findings the gate deliberately did not reject on (the
  semantic rung lives here, and #129 measured its false-positive rate as the reason
  it does), so quoting them asks a worker to change code that was never required to
  change, on the strength of a signal the gate itself declined to act on;
* the *environment issues* — a tool that was not installed, which is not something
  the worker did and not something it can fix, and which reads to a model as an
  instruction to work around a missing linter;
* and, negatively again, the first prompt.

A test that asserted only "the failing check is present" would pass against a note
that dumped all four. That is not a hypothetical failure: dumping the report is the
obvious implementation, and it is the one that makes a retry cost more than the
attempt it follows.

The third test is the verifier's half. When a reviewer refuses with remediation
notes, those notes are the entire content of what failed — the gate passed, so there
is nothing of its to repeat — and they are the most actionable thing any attempt in
this system ever produces. Losing them means the next attempt re-derives, from
nothing, a critique a model has already written down.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.catalog import catalog
from mcgyvr.escalate import Judgement, Review, judge
from mcgyvr.gate import Finding, GateResult
from tests.red_port.conftest import required

BEHAVIOR = "carry a rejected attempt's failing checks into the next attempt's prompt"

LOCAL = catalog().family("local")

# Distinctive strings, so an assertion about what did or did not reach a prompt
# cannot be satisfied by an ordinary English word appearing in the template.
FAILED = "undefined name `backoff_seconds`"
OBSERVED = "call to `frobnicate` resolves against nothing installed"
ENVIRONMENT = "javascript: eslint not installed — lint skipped"
REMEDIATION = "the sleep must be interruptible; wrap it so KeyboardInterrupt lands"

REJECTED = GateResult(
    findings=(
        Finding(
            check="lint",
            path="src/pkg/fetch.py",
            line=2,
            code="F821",
            message=FAILED,
        ),
    ),
    observations=(
        Finding(
            check="semantic",
            path="src/pkg/fetch.py",
            line=3,
            message=OBSERVED,
        ),
    ),
    environment_issues=(ENVIRONMENT,),
)


def _run() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.attempt", fromlist=["run"]).run
    )


class Twice:
    """An attempt function that fails once, then passes, and keeps every prompt.

    The prompts are the whole observation. Nothing here dispatches: what a second
    attempt is *told* is decided before any model is reached, which is what makes
    this assertable without one.
    """

    def __init__(self, contract: Any, first: Judgement[str]) -> None:
        self._contract = contract
        self._first = first
        self.prompts: list[Any] = []

    def __call__(self, prompt: Any) -> Judgement[str]:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return self._first
        return judge(self._contract, LOCAL, GateResult(), value="accepted")

    @property
    def texts(self) -> list[str]:
        return [str(getattr(p, "user", p)) for p in self.prompts]


def _two_attempts(contract: Any, first: Judgement[str]) -> Twice:
    work = Twice(contract, first)
    _run()(contract, work, attempts=2)
    assert len(work.prompts) == 2, (
        f"a rung with two attempts made {len(work.prompts)}: there is no second "
        f"attempt for a note to reach"
    )
    return work


def test_a_second_attempt_on_the_same_rung_is_given_the_failing_checks(
    contract: Any,
) -> None:
    """What failed reaches the retry — and does not reach the attempt before it."""
    work = _two_attempts(contract, judge(contract, LOCAL, REJECTED))
    first, second = work.texts

    assert FAILED in second, (
        f"the second attempt was not told what the first one got wrong, so it is "
        f"the same prompt to the same model at temperature 0.0. It said: {second!r}"
    )
    assert FAILED not in first, (
        "the first attempt was already carrying a rejection that had not happened "
        "yet, which charges every task's opening prompt for a retry it may never run"
    )


def test_the_retry_carries_nothing_but_the_failing_checks(
    contract: Any,
) -> None:
    """Four exclusions, each asserted by name.

    Asserting only that the failure is present would pass against a note that
    returned the entire gate report — which is the obvious implementation, and the
    one that makes a retry prompt cost more than the attempt it follows.
    """
    work = _two_attempts(contract, judge(contract, LOCAL, REJECTED))
    second = work.texts[1]

    assert FAILED in second, f"the failing check itself did not reach it: {second!r}"
    assert OBSERVED not in second and "semantic" not in second, (
        "an observation reached the worker: the gate declined to reject on it, so "
        "quoting it asks for a change that was never required, on a signal the gate "
        "itself does not trust"
    )
    assert ENVIRONMENT not in second and "eslint" not in second, (
        "an environment issue reached the worker: a tool that is not installed is "
        "not something the worker did, and not something it can fix"
    )
    for passed in ("secrets", "syntax", "scope"):
        assert passed not in second, (
            f"the check {passed!r} ran and reported nothing, and the worker was told "
            f"about it anyway — the note is a rendered report, not the failures"
        )


def test_a_reviewers_remediation_notes_reach_the_next_attempt(
    contract: Any,
) -> None:
    """The gate passed, so the reviewer's words are the whole of what failed.

    They are also the most actionable thing this system produces: a critique a model
    has already written. Dropping them makes the next attempt re-derive it from an
    identical prompt.
    """
    refused = judge(
        contract,
        LOCAL,
        GateResult(),
        value="rejected by the reviewer",
        verifier=lambda: Review.refused(REMEDIATION),
    )

    work = _two_attempts(contract, refused)

    assert REMEDIATION in work.texts[1], (
        f"the reviewer's remediation notes did not reach the next attempt, which "
        f"is asked to rediscover them from an unchanged prompt. It said: "
        f"{work.texts[1]!r}"
    )
