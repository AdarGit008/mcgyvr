"""X2 — a single-file delivery cannot take a pattern target.

Contract loading already refuses a glob target for a model-run task type, but
that is one seam. A contract assembled in code, or an older record, can still
reach :func:`deliver` with ``src/**/fetch.py`` as its target, and the seam writes
it as a literal filename — creating and committing a literal ``**`` directory
while reporting success.

The statement is that ``deliver`` itself refuses a target carrying glob
metacharacters as a hard precondition failure, before anything is written, with a
message that says why: a single-file delivery has no answer to a pattern.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.deliver import DeliveryError
from tests.red_port.conftest import git, required

BEHAVIOR = "refuse a glob-meta target at the delivery seam"


def _deliver() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.deliver", fromlist=["deliver"]).deliver
    )


def test_a_pattern_target_is_refused_before_it_becomes_a_literal_path(
    repo: Path, contract: Any
) -> None:
    """A target with ``**`` is a pattern, not a file; delivery must not write it."""
    head = git(repo, "rev-parse", "HEAD").strip()
    targeted = replace(contract, target="src/**/fetch.py")
    new = "def fetch(url):\n    return url.strip()\n"

    with pytest.raises(DeliveryError, match="pattern"):
        _deliver()(repo=repo, contract=targeted, content=new, base=head)

    assert not (repo / "src" / "**").exists(), (
        "the pattern target was written as a literal directory"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head, (
        "a pattern target was committed"
    )
