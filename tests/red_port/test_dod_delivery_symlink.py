"""B12 — a symlink on the target path must not redirect a delivery.

``_target`` resolves the target path with ``.resolve()``, which follows symlinks.
A symlink at the target — or at any parent component — therefore silently steers
the write to a different file, and the commit's trailer names a path the commit
does not actually contain. That is worse than a failure: it is a success that is
false.

The statement is that such a target is refused as a hard precondition failure
before anything is written, naming the symlink, because the path the contract
names is not a real file in the tree delivery can commit.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.deliver import DeliveryError
from tests.red_port.conftest import git, required

BEHAVIOR = "refuse a target that is, or crosses, a symlink"


def _deliver() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.deliver", fromlist=["deliver"]).deliver
    )


def test_delivery_refuses_a_symlinked_parent_component(
    repo: Path, contract: Any
) -> None:
    """A symlinked directory on the target path redirects the write; refuse it."""
    head = git(repo, "rev-parse", "HEAD").strip()
    targeted = replace(contract, target="linked/fetch.py")
    (repo / "linked").symlink_to(repo / "src" / "pkg", target_is_directory=True)
    new = "def fetch(url):\n    return url.strip()\n"

    with pytest.raises(DeliveryError, match="symlink"):
        _deliver()(repo=repo, contract=targeted, content=new, base=head)

    assert git(repo, "rev-parse", "HEAD").strip() == head, (
        "a symlinked target was committed"
    )


def test_delivery_refuses_a_symlinked_target_file(repo: Path, contract: Any) -> None:
    """A symlink at the target itself must not be written through."""
    head = git(repo, "rev-parse", "HEAD").strip()
    targeted = replace(contract, target="src/pkg/linked.py")
    (repo / "src" / "pkg" / "linked.py").symlink_to(repo / "src" / "pkg" / "fetch.py")
    new = "def fetch(url):\n    return url.strip()\n"

    with pytest.raises(DeliveryError, match="symlink"):
        _deliver()(repo=repo, contract=targeted, content=new, base=head)

    assert git(repo, "rev-parse", "HEAD").strip() == head, (
        "a symlinked target was committed"
    )
