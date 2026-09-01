"""B2 — a delivery must not commit onto a detached HEAD or a checkout mid-sequence.

``delivery.mode: none`` runs ``git commit`` onto whatever ``HEAD`` names. When the
operator has checked out a detached commit — or a rebase, merge, cherry-pick or
bisect is partway through — that commit has no branch to hold it, and the work
lands on a SHA nothing names. A delivery that reports ``committed=True`` here has
silently lost the change.

The statement is not "git will refuse". It often will not: a plain ``git commit``
succeeds on a detached HEAD and moves ``HEAD`` to a commit no ref points at. So
delivery has to detect the hazard itself and refuse before it writes anything,
with a reason the operator can act on — check out a branch, or finish the
in-progress operation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import git, required

BEHAVIOR = (
    "refuse to commit when HEAD is detached or a git operation is partway through"
)


def _deliver() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.deliver", fromlist=["deliver"]).deliver
    )


def test_delivery_refuses_onto_a_detached_head(repo: Path, contract: Any) -> None:
    """A commit onto a detached HEAD has no ref; delivery must refuse it."""
    head = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "checkout", "-q", "--detach", head)
    new = "def fetch(url):\n    return url.strip()\n"

    result = _deliver()(repo=repo, contract=contract, content=new, base=head)

    assert not getattr(result, "committed", False), "committed onto a detached HEAD"
    assert "detached" in str(getattr(result, "reason", "")).lower(), (
        f"refusal must name the detached HEAD, said: "
        f"{getattr(result, 'reason', None)!r}"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head, (
        "HEAD moved: the commit was made onto a ref that does not name it"
    )


def test_delivery_refuses_while_a_merge_is_in_progress(
    repo: Path, contract: Any
) -> None:
    """An in-progress merge means HEAD is not a settled checkout; refuse."""
    head = git(repo, "rev-parse", "HEAD").strip()
    git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir").strip())
    (git_dir / "MERGE_HEAD").write_text(head + "\n")
    new = "def fetch(url):\n    return url.strip()\n"

    result = _deliver()(repo=repo, contract=contract, content=new, base=head)

    assert not getattr(result, "committed", False), "committed during a merge"
    assert "merge" in str(getattr(result, "reason", "")).lower(), (
        f"refusal must name the in-progress merge, said: "
        f"{getattr(result, 'reason', None)!r}"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head
