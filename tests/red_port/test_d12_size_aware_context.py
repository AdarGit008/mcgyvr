"""D12 — the context budget is sized for the model, and what does not fit is still
deferred.

:func:`mcgyvr.orchestrator.read.explore` takes a budget in estimated tokens and
defaults it to a flat 2000 for every caller. That number is the same for a 1.5B model
whose useful window collapses long before its declared one and for a 14B that could
have read four times as much — so one of the two is always being served wrong, and
which one changes with the rung. A ladder that escalates to a larger model and hands
it the same 2000 tokens has escalated the model and not the question.

Three statements. The second is a regression guard and is the most important one here.

*The context assembled for the same contract is smaller for a small model* is the
lever, and it is asserted on the same index and the same resolution, so the only input
that differs between the two calls is the model. Asserting a particular number for a
particular model would freeze a table the port should be free to measure; the ordering
across three real entries of ``data/capability-table.json`` is the requirement.

*What does not fit is deferred, not truncated* is the property mcgyvr already has and
the one a "budget" port is most likely to destroy. A smaller budget invites a cheaper
implementation — cut the text, drop the tail, keep the first N tokens — and every such
implementation still satisfies "smaller for a small model". So it is held three ways.
The set of regions the exploration *knows about* — read plus deferred — must be
identical for both models, because which regions exist is decided by the index and the
shortlist and has nothing to do with how much budget there is; a budget that changed
the region set is a budget that reached into planning. The regions actually read must
be a subset for the smaller model, which is what "a strict best-first prefix" means and
what makes the deferral list a faithful account of where the budget ran out rather than
a bag of leftovers. And every read must still carry exactly the lines it claims to
span, which is the assertion that catches a region trimmed to fit and reported as
though it were whole — the one failure mode that leaves no trace anywhere else.

Every deferral is asserted to carry a non-zero cost, because a deferral that cannot say
what it would have cost gives a caller nothing to decide with, and deciding is the
entire reason :attr:`~mcgyvr.orchestrator.read.Exploration.exhausted` exists.

*The budget derives from the model being dispatched to* is asserted over three sizes
rather than two. Two points cannot tell a size-aware budget from a coin flip that
happened to land in the right order; three that do not decrease, with at least two
distinct values, says the budget is a function of the input. It is also asserted that
the exploration reports the budget it actually enforced — ``spent <= budget`` — because
a plan whose stated budget is not the one it spent against is unauditable, and auditing
the spend is what this module is for.

Nothing here dispatches. A model is a string identifier out of the shipped capability
table; no backend is contacted and no token is bought.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import Exploration
from mcgyvr.orchestrator.resolve import Resolution, resolve
from tests.red_port.conftest import git, required

BEHAVIOR = (
    "size the exploration budget from the model the context is being assembled for, "
    "while still reporting what did not fit as deferred rather than truncating it"
)

# Three real ids from data/capability-table.json, one family, three sizes. Real
# because a budget keyed on a model that does not exist proves nothing about a
# budget keyed on a model.
SMALL = "qwen2.5-coder:1.5b"
MIDDLE = "qwen2.5-coder:7b"
LARGE = "qwen2.5-coder:14b"

QUERY = "fetch retry backoff"


def _explore_for() -> Any:
    """Exploration that knows which model it is assembling for.

    Placeholder name. What must survive the port is everything asserted about the
    :class:`~mcgyvr.orchestrator.read.Exploration` it returns, not where it lives.
    """
    return required(
        BEHAVIOR,
        lambda: (
            __import__("mcgyvr.orchestrator.read", fromlist=["explore_for"]).explore_for
        ),
    )


def _regions(plan: Exploration) -> set[tuple[str, int, int]]:
    """Every region the plan knows about, read or deferred — the planning outcome."""
    return {(r.path, r.start, r.end) for r in plan.reads} | {
        (d.path, d.start, d.end) for d in plan.deferred
    }


def _read_regions(plan: Exploration) -> set[tuple[str, int, int]]:
    return {(r.path, r.start, r.end) for r in plan.reads}


@pytest.fixture
def corpus(repo: Path) -> tuple[Index, Resolution]:
    """A repository with more relevant source than any of these budgets can hold.

    Deliberately oversized: if the corpus fit inside the smallest budget, every model
    would read all of it and the ordering assertions would pass against a constant.
    Ten files, each with several matching definitions, so the shortlist plans ten
    regions and the budget decides how many of them are paid for.
    """
    pkg = repo / "src" / "pkg"
    for file_no in range(10):
        body = "\n".join(
            f"def fetch_{file_no}_{fn}(url):\n"
            f'    """Fetch with retry and backoff."""\n'
            + "\n".join(
                f"    step_{line} = url + {line}  # retry backoff fetch"
                for line in range(12)
            )
            + "\n    return url\n"
            for fn in range(6)
        )
        (pkg / f"fetch_{file_no}.py").write_text(body)
    git(repo, "add", "-A")

    index = build_index(repo)
    return index, resolve(index, QUERY)


def test_a_small_model_is_given_less_context_than_a_large_one(
    corpus: tuple[Index, Resolution],
) -> None:
    """Same index, same shortlist, same query — only the model differs.

    Asserted on both the spend and the number of regions read, because a budget that
    changed the spend without changing what was covered would have bought nothing.
    """
    index, resolution = corpus
    explore_for = _explore_for()

    small = explore_for(index, resolution, model=SMALL)
    large = explore_for(index, resolution, model=LARGE)

    assert small.spent < large.spent, (
        f"the same contract cost {small.spent} for {SMALL} and {large.spent} for "
        f"{LARGE}; the budget did not follow the model"
    )
    assert len(small.reads) < len(large.reads), (
        "the smaller model was charged less but covered the same regions"
    )


def test_what_does_not_fit_is_deferred_and_never_silently_cut(
    corpus: tuple[Index, Resolution],
) -> None:
    """The property mcgyvr already has, held against the cheapest way to break it.

    A budget that shrank by truncating text would satisfy the ordering test above and
    silently hand a worker half a function. So: the planned region set must not move
    with the budget, the read set must be a prefix of the larger one, and every read
    must still span exactly the lines it says it spans.
    """
    index, resolution = corpus
    explore_for = _explore_for()

    small = explore_for(index, resolution, model=SMALL)
    large = explore_for(index, resolution, model=LARGE)

    assert small.deferred, (
        "nothing was deferred under the smaller budget, so this corpus cannot say "
        "whether the overflow is deferred or cut"
    )
    assert small.exhausted, "regions were left unread without the plan saying so"

    assert _regions(small) == _regions(large), (
        "the budget changed which regions exist; region planning belongs to the index "
        "and the shortlist, so a smaller budget may read less and never plan "
        "differently"
    )
    assert _read_regions(small) <= _read_regions(large), (
        "the smaller budget read a region the larger one did not — the reads are no "
        "longer a best-first prefix, so the deferral list no longer says where the "
        "budget ran out"
    )
    for deferral in small.deferred:
        assert deferral.estimated_tokens > 0, (
            f"deferred {deferral.path}:{deferral.start}-{deferral.end} with no cost; a "
            f"caller cannot decide how far over budget it is running"
        )
    for read in small.reads:
        assert len(read.text.split("\n")) == read.end - read.start + 1, (
            f"{read.path}:{read.start}-{read.end} was trimmed to fit and reported as "
            f"though it were the whole region"
        )


def test_the_budget_follows_the_model_and_not_a_constant(
    corpus: tuple[Index, Resolution],
) -> None:
    """Three sizes, not two: two points cannot distinguish a function from a guess.

    The budget is asserted non-decreasing with model size and not all one value, and
    each plan is asserted to have spent within the budget it reports — a plan whose
    stated budget is not the one it enforced cannot be audited, which is the whole
    point of stating it.
    """
    index, resolution = corpus
    explore_for = _explore_for()

    plans = [
        explore_for(index, resolution, model=name) for name in (SMALL, MIDDLE, LARGE)
    ]
    budgets = [plan.budget for plan in plans]

    assert budgets == sorted(budgets), (
        f"budgets {budgets} for {[SMALL, MIDDLE, LARGE]} do not follow model size"
    )
    assert len(set(budgets)) > 1, (
        f"every model was given the same budget ({budgets[0]}), which is the flat "
        f"constant this lever exists to replace"
    )
    for plan in plans:
        assert plan.spent <= plan.budget, (
            f"spent {plan.spent} against a stated budget of {plan.budget}"
        )
