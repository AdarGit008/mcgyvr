"""D25 — every terminal outcome says whether the work may be tried somewhere else.

:class:`~mcgyvr.escalate.Outcome`, :class:`~mcgyvr.route.Exhaustion`,
:class:`~mcgyvr.route.Verdict`, :class:`~mcgyvr.runner.StopReason` and the
``ReplyError`` codes answer *what happened*. *What to do next* is a different axis:
:func:`mcgyvr.escalate.disposition` answers it per outcome, so a caller of
:func:`~mcgyvr.escalate.escalate` does not re-derive the rule from the outcome name.

Two statements:

* **Every terminal outcome answers.** Iterated over the enum rather than over a list
  written here, so a member added later cannot be forgotten — a taxonomy
  with a hole in it is worse than no taxonomy, because the hole is discovered by a
  caller at runtime. The answers are also asserted to *differ across the set*: a
  function that returned ``False`` for everything answers every member and says
  nothing, and it would pass an all-members-covered check.

* **The three ways a climb can end are three, not one.** ``LADDER_SPENT`` is the
  ladder honestly tried and not up to the work; ``ESCALATION_CEILING`` and
  ``ATTEMPT_CEILING`` are two different numbers the operator set, bounding two
  different things — moves and spend. A caller responds differently to each: raise
  the escalation ceiling, raise the attempt budget, or bind a dearer rung, and only
  one of those three is useful in each case. ``tests/test_escalate.py`` holds that
  all three are *reachable*; this holds that they are *distinguishable in what they
  tell a caller to do*.

The answer exists per outcome, and it carries a reason a human can read.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.escalate import Outcome
from tests.red_port.conftest import required

DISPOSITION = "say, for every terminal outcome, whether the work may be reassigned"


def _disposition() -> Any:
    return required(
        DISPOSITION,
        lambda: __import__("mcgyvr.escalate", fromlist=["disposition"]).disposition,
    )


def test_every_terminal_outcome_says_whether_the_work_may_be_reassigned() -> None:
    """All of them, read off the enum, each with a bool and a reason a human can act on.

    The final assertion is what stops this being satisfiable by a constant: an axis
    on which every outcome lands the same way is not an axis, and a driver reading
    it would branch on nothing.
    """
    disposition = _disposition()

    answers = {outcome: disposition(outcome) for outcome in Outcome}

    for outcome, answer in answers.items():
        assert isinstance(getattr(answer, "reassignable", None), bool), (
            f"{outcome.value!r} does not say whether it may be reassigned: a caller "
            f"has to guess from the name, and two callers will guess differently"
        )
        assert str(getattr(answer, "detail", "")).strip(), (
            f"{outcome.value!r} gives a verdict with no reason, so an operator is "
            f"told the work stopped and not what would let it continue"
        )

    decided = {answer.reassignable for answer in answers.values()}
    assert decided == {True, False}, (
        f"every outcome in the taxonomy is reassignable={decided}: a constant is not "
        f"a classification, and nothing downstream can branch on it"
    )


def test_the_two_ceilings_and_a_spent_ladder_are_told_apart() -> None:
    """Three endings, three answers, because the remedy differs for each.

    A ceiling is a number an operator chose and can raise. A spent ladder is a
    statement about what the install can do, and raising a number will not change it.
    Collapsing them tells someone to spend more on a ladder that has already shown
    it cannot do the work.
    """
    disposition = _disposition()
    three = (
        Outcome.ESCALATION_CEILING,
        Outcome.ATTEMPT_CEILING,
        Outcome.LADDER_SPENT,
    )

    answers = [disposition(outcome) for outcome in three]

    distinct = {(a.reassignable, str(a.detail)) for a in answers}
    assert len(distinct) == 3, (
        f"the two ceilings and a genuinely spent ladder give "
        f"{len(distinct)} distinct answers between them, so a caller cannot tell "
        f"'raise a number you set' from 'this install cannot do this work': "
        f"{distinct}"
    )
    for outcome, answer in zip(three, answers, strict=True):
        assert outcome.value in str(answer.detail), (
            f"the answer for {outcome.value!r} does not name it — "
            f"{str(answer.detail)!r} — so three distinct sentences are distinct by "
            f"accident rather than about their own outcome"
        )
