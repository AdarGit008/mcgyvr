"""A commit lands on the branch it was sent to, and nowhere else.

:func:`mcgyvr.deliver.deliver` takes ``branch``. Empty — the default — commits
onto the branch the operator has checked out. A name commits onto that branch
instead, and leaves the checkout, the index and the working tree exactly as it
found them:

* **absent** — the branch is created from the checked-out commit;
* **present** — the commit goes on its tip, when the target there is still the
  copy the change was judged against; a branch whose copy moved is refused,
  because committing over it would revert work nobody judged;
* **the branch in hand** — the same as naming none;
* **checked out in another worktree** — refused: moving it would change the
  files under somebody else's checkout.

Whether to commit at all is not delivery's question. ``delivery.commit``,
``--commit`` and ``--no-commit`` answer it before delivery is called
(``tests/test_run_commits_only_when_asked_and_where_asked.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import Delivery, DeliveryError, deliver
from tests._helpers import git

CONTRACT = """
id: fetch-retry
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

BEFORE = "def fetch(url):\n    return url\n"
AFTER = 'def fetch(url):\n    """Retry."""\n    return url\n'


def heads(repo: Path) -> set[str]:
    """Every local branch, by short name."""
    listed = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return set(listed.split())


def rev(repo: Path, name: str) -> str:
    return git(repo, "rev-parse", name).strip()


def shown(repo: Path, ref: str, path: str = "src/pkg/fetch.py") -> str:
    return git(repo, "show", f"{ref}:{path}")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    where = tmp_path / "repo"
    (where / "src/pkg").mkdir(parents=True)
    (where / "src/pkg/fetch.py").write_text(BEFORE, encoding="utf-8")
    (where / "src/pkg/other.py").write_text("X = 0\n", encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "work", str(where))
    git(where, "config", "user.email", "test@example.invalid")
    git(where, "config", "user.name", "test")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


@pytest.fixture
def contract() -> Contract:
    return loads(CONTRACT)


def delivered(repo: Path, contract: Contract, branch: str = "") -> Delivery:
    return deliver(
        repo=repo,
        contract=contract,
        content=AFTER,
        base=rev(repo, "HEAD"),
        branch=branch,
    )


def untouched(repo: Path, head: str) -> None:
    """The checkout is where it was: same branch, same commit, clean tree."""
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "work", (
        "delivery switched the branch the operator has checked out"
    )
    assert rev(repo, "HEAD") == head, "delivery moved the checked-out branch"
    assert (repo / "src/pkg/fetch.py").read_text(encoding="utf-8") == BEFORE, (
        "delivery left its change in the working tree as well as on the branch"
    )
    assert not git(repo, "status", "--porcelain").strip(), (
        f"delivery left the tree dirty:\n{git(repo, 'status', '--porcelain')}"
    )


# --- no branch named: the branch in hand --------------------------------------


def test_no_branch_named_commits_onto_the_checked_out_branch(
    repo: Path, contract: Contract
) -> None:
    head = rev(repo, "HEAD")

    result = delivered(repo, contract)

    assert result.committed, f"nothing was delivered: {result}"
    assert rev(repo, "HEAD") == result.commit, "the commit is not on `work`"
    assert rev(repo, "HEAD~1") == head
    assert heads(repo) == {"work"}, f"a branch was created: {sorted(heads(repo))}"
    assert not result.branch and not result.handoff, result
    assert (repo / "src/pkg/fetch.py").read_text(encoding="utf-8") == AFTER


def test_naming_the_checked_out_branch_is_the_same_as_naming_none(
    repo: Path, contract: Contract
) -> None:
    """Moving the checked-out ref behind the tree's back would leave the tree
    reading as a revert of the commit just made; it is committed in place."""
    head = rev(repo, "HEAD")

    result = delivered(repo, contract, branch="work")

    assert result.committed, f"nothing was delivered: {result}"
    assert rev(repo, "HEAD") == result.commit
    assert rev(repo, "HEAD~1") == head
    assert not git(repo, "status", "--porcelain").strip()
    assert (repo / "src/pkg/fetch.py").read_text(encoding="utf-8") == AFTER


# --- a branch that does not exist: created from the checked-out commit --------


def test_an_absent_branch_is_created_from_head_and_takes_the_commit(
    repo: Path, contract: Contract
) -> None:
    head = rev(repo, "HEAD")

    result = delivered(repo, contract, branch="mcgyvr-work")

    assert result.committed, f"nothing was delivered: {result}"
    assert heads(repo) == {"work", "mcgyvr-work"}, sorted(heads(repo))
    assert rev(repo, "mcgyvr-work") == result.commit
    assert rev(repo, "mcgyvr-work~1") == head, "the branch did not start at HEAD"
    assert shown(repo, "mcgyvr-work") == AFTER
    assert result.branch == "mcgyvr-work"
    untouched(repo, head)


def test_the_handoff_is_the_push_of_the_named_branch(
    repo: Path, contract: Contract
) -> None:
    git(repo, "remote", "add", "upstream", "https://example.invalid/x.git")

    result = delivered(repo, contract, branch="mcgyvr-work")

    assert result.handoff == "git push -u upstream mcgyvr-work", result.handoff
    assert "mcgyvr-work" in str(result), (
        f"the one line a caller prints does not say where the work went: {result}"
    )


# --- a branch that exists: the commit goes on its tip -------------------------


def test_an_existing_branch_takes_the_commit_on_its_tip(
    repo: Path, contract: Contract
) -> None:
    """Work accumulates on a named branch run after run; the branch's other
    changes are kept, because the commit is its tip plus this one path."""
    git(repo, "checkout", "-q", "-b", "mcgyvr-work")
    (repo / "src/pkg/other.py").write_text("X = 1\n", encoding="utf-8")
    git(repo, "commit", "-qam", "earlier work on the branch")
    tip = rev(repo, "HEAD")
    git(repo, "checkout", "-q", "work")
    head = rev(repo, "HEAD")

    result = delivered(repo, contract, branch="mcgyvr-work")

    assert result.committed, f"nothing was delivered: {result}"
    assert rev(repo, "mcgyvr-work") == result.commit
    assert rev(repo, "mcgyvr-work~1") == tip, "the branch's own history was lost"
    assert shown(repo, "mcgyvr-work") == AFTER
    assert shown(repo, "mcgyvr-work", "src/pkg/other.py") == "X = 1\n", (
        "committing onto the branch reverted what was already on it"
    )
    untouched(repo, head)


def test_an_existing_branch_whose_target_moved_is_refused(
    repo: Path, contract: Contract
) -> None:
    """The change was judged against the target at the base. The branch holds a
    different copy, and committing over it would revert that copy unjudged."""
    git(repo, "checkout", "-q", "-b", "mcgyvr-work")
    (repo / "src/pkg/fetch.py").write_text("def fetch(u):\n    return u\n")
    git(repo, "commit", "-qam", "someone else's fetch")
    tip = rev(repo, "HEAD")
    git(repo, "checkout", "-q", "work")
    head = rev(repo, "HEAD")

    result = delivered(repo, contract, branch="mcgyvr-work")

    assert not result.committed, f"committed over the branch's copy: {result}"
    assert "mcgyvr-work" in result.reason and "src/pkg/fetch.py" in result.reason, (
        result.reason
    )
    assert rev(repo, "mcgyvr-work") == tip, "the refused branch moved anyway"
    untouched(repo, head)


def test_a_branch_checked_out_in_another_worktree_is_refused(
    repo: Path, contract: Contract, tmp_path: Path
) -> None:
    git(repo, "branch", "mcgyvr-work")
    git(repo, "worktree", "add", "-q", str(tmp_path / "elsewhere"), "mcgyvr-work")
    tip = rev(repo, "mcgyvr-work")
    head = rev(repo, "HEAD")

    result = delivered(repo, contract, branch="mcgyvr-work")

    assert not result.committed, f"moved a branch checked out elsewhere: {result}"
    assert "worktree" in result.reason, result.reason
    assert rev(repo, "mcgyvr-work") == tip
    untouched(repo, head)


def test_a_name_git_will_not_take_is_refused_before_anything_is_written(
    repo: Path, contract: Contract
) -> None:
    head = rev(repo, "HEAD")

    with pytest.raises(DeliveryError) as raised:
        delivered(repo, contract, branch="two..dots")

    assert "two..dots" in str(raised.value), raised.value
    assert heads(repo) == {"work"}
    untouched(repo, head)
