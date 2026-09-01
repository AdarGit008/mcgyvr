"""X05 — style is cleaned for free, correctness is rejected, and a failed cleanup costs
nothing.

mcgyvr already makes the distinction this lever needs. :class:`~mcgyvr.gate.GateResult`
splits what a rung saw into ``findings`` (which reject), ``observations`` (real,
line-attributed, and deliberately outside the verdict) and ``environment_issues``
(a check that could not run). What it never does is *act* on the split: ``ruff format``
is run with ``--diff`` and ``ruff check`` without ``--fix``, so a change whose only
problem is a blank line in the wrong place is reported and then handed to a model to
fix — a dispatch, a full context, an attempt off the ceiling, to insert a space.

Where the split does not fall where its name suggests, the values below follow the
gate rather than the name. The format rung emits ``check="format"``, and
``Gate.run`` files it in ``findings``: a change whose only problem is its formatting
is a *rejected* change, and a style-only verdict built as an observation is a value
no gate run returns. That is what these constants were, and the version of this file
that held them was green over a state the system cannot produce.

Three statements, and the two after the first are what stop this from being a footgun.

*A style-only violation is cleaned deterministically, at no model cost* is the lever.
It is asserted four ways, because "cleaned" has three cheap wrong answers. The content
must actually change, or nothing was cleaned. The change must be *stable* — the same
input cleaned twice gives the same bytes — because a rewriter that is not deterministic
puts a coin flip inside the acceptance path, and D26 is on the KEEP list. Cleaning
already-clean content must be a fixed point, or the cleanup cannot be run twice, which
it will be the moment it sits in a retry loop. And the program must survive: a
"cleanup" that deleted the body would satisfy every other assertion here, so the
function's actual behaviour is asserted to still be in the file. The spend is asserted
to be zero because that is the entire economic argument for this lever — a cleanup that
dispatches is just a cheaper-sounding retry.

*A correctness violation is never cleaned* is the refusal, and it is the one that makes
the lever safe. The input is the same messy content, so the only difference between this
test and the first is which rung rejected it. The change must be rejected and the
content must come back untouched — both, because a cleanup that tidied the bytes and
then rejected would hand the next attempt a file it never wrote, and the worker's diff
would stop matching what the worker produced.

*A cleanup that itself fails does not turn a passing gate into a failing one* is the
best-effort statement. It is held with a deliberate contradiction: a gate result that
accepted, over content that no formatter can parse. That combination cannot arise from
a healthy gate, and that is the point — this is the hostile case, standing in for a
crashed formatter, a missing tool, an unsupported syntax version. The verdict was
already reached by the gate; a tidy-up that runs afterwards has no standing to overturn
it, and a rewriter that reports its own failure as a finding would fail changes that
passed everything mcgyvr actually checks. Note it is *not* asserted that cleanup
silently claims success: the outcome must not say it cleaned anything it did not.

Nothing here runs the gate. The gate results are constructed, which is what makes the
style/correctness split assertable independently of which rung produced it — and it is
also how this file was once green over an impossible value, so the correspondence
between these constants and what ``Gate.run`` returns is pinned by a real run in
``tests/test_fix_b4_b9_text_handling.py`` rather than assumed here.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.gate import Finding, GateResult
from tests.red_port.conftest import required

BEHAVIOR = (
    "rewrite a style-only violation out of a change deterministically and at zero "
    "model spend, while a correctness violation still rejects"
)

TARGET = "src/pkg/fetch.py"

# Valid Python, wrong shape: ruff's formatter has an opinion about every line of it.
MESSY = "def fetch( url ):\n    return  url\n"

# Not valid Python at all — the stand-in for a cleanup that cannot run.
UNPARSEABLE = "def fetch(url:\n    return url\n"

# What the gate returns for a change whose only problem is its formatting: the format
# rung's own finding, in `findings`, rejecting. `observations` carries only what the
# gate classes as STYLE, and the format rung does not emit that.
STYLE_ONLY = GateResult(
    findings=(
        Finding(
            check="format",
            path=TARGET,
            message="formatter would reflow a worker-added line",
            line=1,
        ),
    )
)

# A correctness rejection, and nothing beside it: the acceptance rung runs only while
# nothing cheaper has rejected, so a verdict carrying one of its findings never carries
# a format finding too.
CORRECTNESS = GateResult(
    findings=(
        Finding(
            check="acceptance",
            path=TARGET,
            message="the declared demonstration did not pass",
        ),
    )
)


def _tidy() -> Any:
    """Deterministic cleanup of an accepted change.

    Placeholder path. The contract is the outcome: what comes back, whether it is still
    accepted, and that no model was involved in getting there.
    """
    return required(
        BEHAVIOR,
        lambda: __import__("mcgyvr.cleanup", fromlist=["tidy"]).tidy,
    )


def test_a_style_only_violation_is_cleaned_before_the_change_is_reviewed() -> None:
    """Everything the change was rejected on, the formatter itself raised.

    Nobody is asked to fix it, and nothing here claims it now passes: the cleanup
    removes the reason for the rejection and the caller re-runs the gate, because the
    rungs behind a rejection never ran.

    Stability and idempotence are asserted alongside the rewrite because a
    non-deterministic rewriter puts a coin flip inside acceptance — and D26, no RNG in
    the decision path, is on the list of things this port must not regress. The
    surviving behaviour is asserted because a cleanup that emptied the file would pass
    every other check in this test.
    """
    tidy = _tidy()

    first = tidy(content=MESSY, result=STYLE_ONLY, target=TARGET)

    assert first.cleaned, (
        "a change whose only problem was its formatting was handed back untouched, so "
        "a model is about to be paid to insert a space"
    )
    assert not first.accepted, (
        "the cleanup reported an acceptance the gate never gave: the gate stops before "
        "its acceptance rung the moment anything rejects"
    )
    assert first.content != MESSY, "nothing was cleaned"
    assert "return url" in first.content, "the cleanup changed what the code does"
    assert first.tokens_spent == 0, (
        f"the cleanup spent {first.tokens_spent} tokens; a cleanup that dispatches is "
        f"a retry wearing a cheaper name"
    )

    again = tidy(content=MESSY, result=STYLE_ONLY, target=TARGET)
    assert again.content == first.content, (
        "the same input cleaned to two different files"
    )

    settled = tidy(content=first.content, result=STYLE_ONLY, target=TARGET)
    assert settled.content == first.content, (
        "cleaning already-clean content changed it again, so the cleanup cannot be run "
        "twice"
    )


def test_a_correctness_violation_is_rejected_and_never_tidied_away() -> None:
    """Same bytes, same style noise — and a finding instead of an observation.

    Both halves are asserted. A cleanup that rewrote the content and *then* rejected
    would hand the next attempt a file the worker never produced, and every retry note
    about "your change" would be about somebody else's.
    """
    outcome = _tidy()(content=MESSY, result=CORRECTNESS, target=TARGET)

    assert not outcome.accepted, "a real finding was cleaned away into an acceptance"
    assert outcome.content == MESSY, (
        "a rejected change was rewritten; what the next attempt is shown must be what "
        "the worker wrote"
    )


def test_a_cleanup_that_cannot_run_does_not_reject_the_change() -> None:
    """Best-effort: the gate reached the verdict, and a tidy-up does not overturn it.

    The input is a deliberate contradiction — an accepting gate result over content no
    formatter can parse — because that is the only way to exercise the failure without
    prescribing how the cleanup is built. A crashed formatter, an absent tool and a
    syntax the parser does not know all arrive here.
    """
    outcome = _tidy()(content=UNPARSEABLE, result=GateResult(), target=TARGET)

    assert outcome.accepted, (
        "a cleanup that could not run turned a passing gate into a failing one"
    )
    assert outcome.content == UNPARSEABLE, (
        "content was mangled by a cleanup that failed"
    )
    assert outcome.tokens_spent == 0
    assert not getattr(outcome, "cleaned", False), (
        "the outcome reports a cleanup that did not happen"
    )
