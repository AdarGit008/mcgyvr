"""D12 — a smaller budget reads less of the same plan, and says what it left.

D12 was originally two statements. The first — *the context budget is sized from
the model the context is being assembled for* — is withdrawn. It was ported into
``mcgyvr.orchestrator.read`` as a second entry point taking a model id, it never
acquired a caller under ``src/``, and action 18 deleted it: a lever nothing pulls
is not a behavior mcgyvr has, it is a function its own tests exercise. Whatever a
budget is eventually derived from, it is derived where a rung is chosen, and the
assertion moves there with it.

The second statement is the one that survives, and it was always the important
one here: *what does not fit is deferred, not truncated*. That is a property
mcgyvr already has and the one a budget change of any kind is most likely to
destroy. A smaller budget invites a cheaper implementation — cut the text, drop
the tail, keep the first N tokens — and every such implementation still looks
like it is spending less. So it is held three ways, against two explicit budgets
over one index and one resolution.

The set of regions the exploration *knows about* — read plus deferred — must be
identical under both budgets, because which regions exist is decided by the index
and the shortlist and has nothing to do with how much budget there is; a budget
that changed the region set is a budget that reached into planning. The regions
actually read must be a subset under the smaller budget, which is what "a strict
best-first prefix" means and what makes the deferral list a faithful account of
where the budget ran out rather than a bag of leftovers. And every read must
still carry exactly the lines it claims to span, which is the assertion that
catches a region trimmed to fit and reported as though it were whole — the one
failure mode that leaves no trace anywhere else.

Every deferral is asserted to carry a non-zero cost, because a deferral that
cannot say what it would have cost gives a caller nothing to decide with, and
deciding is the entire reason
:attr:`~mcgyvr.orchestrator.read.Exploration.exhausted` exists.

Nothing here dispatches. No backend is contacted and no token is bought.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import Exploration, explore
from mcgyvr.orchestrator.resolve import Resolution, resolve
from tests.red_port.conftest import git

QUERY = "fetch retry backoff"

# Two budgets over the same corpus, far enough apart that the smaller one cannot
# reach regions the larger one pays for. Numbers, not model ids: the budget is
# the caller's to state.
SMALL_BUDGET = 4096
LARGE_BUDGET = 8192


def _regions(plan: Exploration) -> set[tuple[str, int, int]]:
    """Every region the plan knows about, read or deferred — the planning outcome."""
    return {(r.path, r.start, r.end) for r in plan.reads} | {
        (d.path, d.start, d.end) for d in plan.deferred
    }


def _read_regions(plan: Exploration) -> set[tuple[str, int, int]]:
    return {(r.path, r.start, r.end) for r in plan.reads}


@pytest.fixture
def corpus(repo: Path) -> tuple[Index, Resolution]:
    """A repository with more relevant source than either of these budgets can hold.

    Deliberately oversized: if the corpus fit inside the smaller budget, both
    explorations would read all of it and the assertions would pass against a
    constant. Ten files, each with several matching definitions, so the shortlist
    plans ten regions and the budget decides how many of them are paid for.
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


def test_what_does_not_fit_is_deferred_and_never_silently_cut(
    corpus: tuple[Index, Resolution],
) -> None:
    """Held against the cheapest way to break it.

    A budget that shrank by truncating text would still spend less and would
    silently hand a worker half a function. So: the planned region set must not
    move with the budget, the read set must be a prefix of the larger one, and
    every read must still span exactly the lines it says it spans.
    """
    index, resolution = corpus

    small = explore(index, resolution, budget=SMALL_BUDGET)
    large = explore(index, resolution, budget=LARGE_BUDGET)

    assert small.spent < large.spent, (
        f"the same contract cost {small.spent} under a budget of {SMALL_BUDGET} "
        f"and {large.spent} under {LARGE_BUDGET}; the corpus cannot say whether "
        f"the overflow is deferred or cut"
    )
    assert len(small.reads) < len(large.reads), (
        "the smaller budget was charged less but covered the same regions"
    )
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
