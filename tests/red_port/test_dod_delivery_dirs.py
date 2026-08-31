"""B7/X8 — a refused delivery must not leave behind the directories it created.

``_write`` creates the target's parent directories as a side effect, then writes
the bytes. When the delivery does not commit, the undo unlinks the file it wrote
— but the parent directories it made are left standing. A refusal is supposed to
put the tree back byte-for-byte as it was found, and an empty ``src/newdir/`` is
a change too: it is exactly the kind of residue that poisons the next contract's
preflight.

The statement is about the *tree*, not the file. A delivery that removes the
written file but leaves the directories it created still fails.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from tests.red_port.conftest import git, required

BEHAVIOR = "leave no created directories behind when a delivery is refused"


def _deliver() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.deliver", fromlist=["deliver"]).deliver
    )


def _directories(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_dir() and not path.is_relative_to(root / ".git")
    }


def test_a_refused_delivery_removes_the_directories_it_created(
    repo: Path, contract: Any
) -> None:
    """Writing a new file into a new directory and then refusing leaves neither.

    The target is ignored so the refusal is reached after the write but before
    any commit: the change is invisible to the change set, which is the seam
    that exercises the undo path without depending on gate internals.
    """
    head = git(repo, "rev-parse", "HEAD").strip()
    targeted = replace(contract, target="src/newdir/newfile.py")
    (repo / ".gitignore").write_text("src/newdir/\n")
    before = _directories(repo)

    result = _deliver()(
        repo=repo,
        contract=targeted,
        content="def fetch(url):\n    return url\n",
        base=head,
    )

    assert not getattr(result, "committed", False), "committed an ignored target"
    assert not (repo / "src" / "newdir").exists(), (
        "the refusal left the created directory behind"
    )
    assert not (repo / "src" / "newdir" / "newfile.py").exists(), (
        "the refusal left the written file behind"
    )
    assert _directories(repo) == before, (
        "the refusal changed the set of directories in the tree"
    )
