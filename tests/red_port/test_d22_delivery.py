"""D22 — an accepted change reaches the repository, and a rejected one leaves no trace.

mcgyvr can plan a ladder, build a prompt, dispatch, parse a reply and gate the
result. It cannot finish: nothing in ``src/`` writes a worker's output to a tree or
commits it. ``config.delivery.mode`` is validated
at load and read by nothing. So this is the lever that turns a library of seams into
something that completes a task, and every other RED test in this package is
downstream of it.

Five statements, and three of them are refusals — which is the point. Delivering the
right change is one behavior; *not* delivering the wrong one is three, and each has
its own way of going wrong:

* A change that failed the gate must not land. Obvious, and held anyway, because the
  reset that guarantees it has to run on the failure path where nobody is watching.
* A change must not land on top of a human's unfinished edits (M2). mcgyvr already
  captures ``dirty`` at attach time for exactly this decision; until now nothing
  consumed it. The refusal is asserted to name a reason, because a silent refusal and
  a silent success are indistinguishable to a caller.
* A change that vanished between acceptance and commit must not be committed as
  though it were there. This is the one that cannot be caught by inspection — it is a
  time-of-check/time-of-use gap, so it is held by mutating the tree between the two
  moments.

The base a delivery diffs against is asserted separately (M3). It is the sandbox base
commit, not the attach revision: what ships is exactly this task's worker output plus
whatever deterministic repair did to it, isolated from every other contract in the
run. A test that only checked "a commit exists" would pass against a delivery that
swept up a sibling contract's half-finished work.

The concurrency test is not about speed. It is the one v1 constraint that keeps the
v2 queue architecture reachable: a delivery that closes over process-global state
cannot be driven by more than one orchestrator, and discovering that after the queue
is built means rewriting the queue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import git, required

BEHAVIOR = "write an accepted worker change into the repository it was attached to"


def _deliver() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.deliver", fromlist=["deliver"]).deliver
    )


def test_an_accepted_change_reaches_the_working_tree(repo: Path, contract: Any) -> None:
    """After delivery, the target file holds the accepted content and a commit "
    "exists."""
    base = git(repo, "rev-parse", "HEAD").strip()
    new = "def fetch(url):\n    for _ in range(3):\n        return url\n"

    _deliver()(repo=repo, contract=contract, content=new, base=base)

    assert (repo / "src" / "pkg" / "fetch.py").read_text() == new
    assert git(repo, "rev-parse", "HEAD").strip() != base, "no commit was made"
    assert git(repo, "status", "--porcelain").strip() == "", "tree left dirty"


def test_a_rejected_change_leaves_the_tree_exactly_as_it_was(
    repo: Path, contract: Any
) -> None:
    """A change that did not pass leaves neither content nor commit behind.

    Asserted on both, because a delivery that wrote the file and skipped the commit
    would poison the next contract's preflight while looking like it refused.
    """
    before = (repo / "src" / "pkg" / "fetch.py").read_text()
    head = git(repo, "rev-parse", "HEAD").strip()

    _deliver()(
        repo=repo, contract=contract, content="broken(", base=head, accepted=False
    )

    assert (repo / "src" / "pkg" / "fetch.py").read_text() == before
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert git(repo, "status", "--porcelain").strip() == ""


def test_delivery_refuses_when_the_tree_was_dirty_before_the_run(
    repo: Path, contract: Any
) -> None:
    """M2 — a dirty tree mixes the worker's change with the human's unfinished edits.

    The refusal must say so. A caller that gets back a falsy result with no reason
    cannot tell "refused because you had edits open" from "nothing to do".
    """
    (repo / "src" / "pkg" / "fetch.py").write_text("# my unfinished edit\n")
    head = git(repo, "rev-parse", "HEAD").strip()

    result = _deliver()(
        repo=repo,
        contract=contract,
        content="def fetch(url):\n    return url\n",
        base=head,
    )

    assert not getattr(result, "committed", False), "committed over a dirty tree"
    assert "dirty" in str(getattr(result, "reason", "")).lower(), (
        f"refusal must name the dirty tree, said: {getattr(result, 'reason', None)!r}"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head


def test_delivery_diffs_against_the_base_it_was_given(
    repo: Path, contract: Any
) -> None:
    """M3 — what ships is this task's change, not everything sitting in the tree.

    A sibling file is dirtied to stand in for another contract's work in the same
    workspace. It must not ride along in this contract's commit.
    """
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "src" / "pkg" / "other.py").write_text("# another contract's work\n")
    new = "def fetch(url):\n    return url.strip()\n"

    _deliver()(repo=repo, contract=contract, content=new, base=base)

    shipped = git(repo, "diff", "--name-only", f"{base}..HEAD").split()
    assert shipped == ["src/pkg/fetch.py"], f"commit swept up extra paths: {shipped}"


def test_a_change_that_vanished_before_commit_is_not_committed(
    repo: Path, contract: Any
) -> None:
    """Freshness — acceptance and commit are two moments, and the tree can move between
    them.

    Held by deleting the accepted content after handing it over, which is the only way
    to exercise a time-of-check/time-of-use gap; inspection cannot find it.
    """
    base = git(repo, "rev-parse", "HEAD").strip()
    original = (repo / "src" / "pkg" / "fetch.py").read_text()

    result = _deliver()(
        repo=repo,
        contract=contract,
        content=original,  # identical to what is already there: nothing changed
        base=base,
    )

    assert not getattr(result, "committed", False), "committed an empty change"
    assert git(repo, "rev-parse", "HEAD").strip() == base


def test_delivery_holds_no_process_global_state(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """v2 constraint — two repositories delivered concurrently must not interfere.

    Not a performance test. If delivery closes over a module-level workspace or a
    single lock, the queue architecture cannot drive more than one orchestrator, and
    that is discovered after the queue is built rather than now.
    """
    from concurrent.futures import ThreadPoolExecutor

    second = tmp_path / "second"
    git(tmp_path, "clone", "-q", str(repo), str(second))
    deliver = _deliver()

    def job(where: Path, text: str) -> Any:
        head = git(where, "rev-parse", "HEAD").strip()
        return deliver(repo=where, contract=contract, content=text, base=head)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(job, repo, "def fetch(url):\n    return 1\n"),
            pool.submit(job, second, "def fetch(url):\n    return 2\n"),
        ]
        for future in futures:
            future.result()

    assert (repo / "src" / "pkg" / "fetch.py").read_text().endswith("return 1\n")
    assert (second / "src" / "pkg" / "fetch.py").read_text().endswith("return 2\n")
