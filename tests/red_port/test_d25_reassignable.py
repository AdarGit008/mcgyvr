"""D25 — the failure taxonomy is rich, and it does not say the one thing a driver
has to know: may this work be tried somewhere else?

mcgyvr names failures better than local-ai does. Six
:class:`~mcgyvr.escalate.Outcome` members, four :class:`~mcgyvr.route.Exhaustion`
reasons, three :class:`~mcgyvr.route.Verdict` values, four
:class:`~mcgyvr.runner.StopReason` values and seven ``ReplyError`` codes, each
argued for in the module that owns it. Every one of them answers *what happened*.

None of them answers *what to do next*, and that is a different axis. It is the axis
local-ai found it needed a ``REASSIGNABLE`` set for: a driver reads it and either
ascends to a dearer family or stops. Without it, every caller of
:func:`~mcgyvr.escalate.escalate` has to re-derive the rule from the outcome name,
and the derivations will differ — the queue architecture in §9 makes that concrete,
because a ``main_out_queue`` that pushes work back for another orchestrator to take
is exactly a reassignment, and it cannot be written against a taxonomy that does not
say which failures are eligible.

Three statements:

* **Every terminal outcome answers.** Iterated over the enum rather than over a list
  written here, so a seventh member added later cannot be forgotten — a taxonomy
  with a hole in it is worse than no taxonomy, because the hole is discovered by a
  caller at runtime. The answers are also asserted to *differ across the set*: a
  function that returned ``False`` for everything answers every member and says
  nothing, and it would pass an all-members-covered check.

* **Terminal means terminal, whatever the budget.** The point of the axis is that it
  is not a budget question. A failure outside the reassignable set stays refused
  against a budget of a million, and — the other half, without which this is just
  "the function returns False" — a failure inside the set *is* reassigned against a
  budget that can pay and is *not* reassigned against a budget that cannot. Both
  inputs have to matter or only one of them is real.

* **The three ways a climb can end are three, not one.** ``LADDER_SPENT`` is the
  ladder honestly tried and not up to the work; ``ESCALATION_CEILING`` and
  ``ATTEMPT_CEILING`` are two different numbers the operator set, bounding two
  different things — moves and spend. A caller responds differently to each: raise
  the escalation ceiling, raise the attempt budget, or bind a dearer rung, and only
  one of those three is useful in each case. ``tests/test_escalate.py`` already holds
  that all three are *reachable*; what is unheld is that they are *distinguishable
  in what they tell a caller to do*, which is the thing the reachability of an enum
  member does not give you.

The dotted names are placeholders as everywhere in this package. What must survive a
rename is that the answer exists per outcome, that it carries a reason a human can
read, and that budget and reassignability are two independent inputs to one
decision.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.escalate import Outcome
from tests.red_port.conftest import required

DISPOSITION = "say, for every terminal outcome, whether the work may be reassigned"
DECIDE = "refuse to reassign a terminal failure however much budget is left"

# Large enough that no plausible ceiling declines it, so a refusal can only be
# about the kind of failure and never about the money.
PLENTY = 1_000_000


def _disposition() -> Any:
    return required(
        DISPOSITION,
        lambda: __import__("mcgyvr.escalate", fromlist=["disposition"]).disposition,
    )


def _may_reassign() -> Any:
    return required(
        DECIDE,
        lambda: __import__("mcgyvr.escalate", fromlist=["may_reassign"]).may_reassign,
    )


def test_every_terminal_outcome_says_whether_the_work_may_be_reassigned() -> None:
    """All six, read off the enum, each with a bool and a reason a human can act on.

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


def test_a_terminal_failure_is_never_reassigned_however_much_budget_remains() -> None:
    """Budget and kind are two inputs, and both have to matter.

    Asserted in both directions. Only the first half would pass against a decision
    that always refuses; only the second would pass against one that only ever reads
    the budget, which is the rule this project already has and the reason the axis
    is missing.
    """
    disposition, may_reassign = _disposition(), _may_reassign()

    terminal = [o for o in Outcome if not disposition(o).reassignable]
    movable = [o for o in Outcome if disposition(o).reassignable]
    assert terminal and movable, (
        f"the set is degenerate — terminal={[o.value for o in terminal]}, "
        f"movable={[o.value for o in movable]} — so nothing below distinguishes "
        f"anything"
    )

    for outcome in terminal:
        assert not may_reassign(outcome, budget_remaining=PLENTY), (
            f"{outcome.value!r} is terminal and was reassigned anyway because "
            f"{PLENTY} of budget was left: the work is sent to a dearer family that "
            f"cannot fix it either, and the bill is the only thing that changes"
        )

    for outcome in movable:
        assert may_reassign(outcome, budget_remaining=PLENTY), (
            f"{outcome.value!r} is declared reassignable and was refused with "
            f"{PLENTY} of budget left, so the declaration changes nothing"
        )
        assert not may_reassign(outcome, budget_remaining=0), (
            f"{outcome.value!r} was reassigned with no budget left: reassignable "
            f"says the work *may* move, not that it is free"
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
