"""A5 — an orphan correction must still say who wrote it.

:func:`mcgyvr.telemetry.correct` took ``orchestrator`` as optional, on the
reasoning that a matched correction is keyed by an attempt that already names
its own writer. The reasoning fails for an orphan: a correction naming no
attempt has no attempt row to borrow an author from, and a fold that surfaces it
surfaces an anonymous record.

The fix makes the author required — the same way :func:`observe` already
requires it — so every correction carries ``applied_by``, matched or orphan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required

CORRECT = (
    "append how the work finally landed without rewriting the attempt's own record"
)
FOLD = "read attempt records back with their corrections folded in, latest wins"


def _correct() -> Any:
    return required(
        CORRECT, lambda: __import__("mcgyvr.telemetry", fromlist=["correct"]).correct
    )


def _fold() -> Any:
    return required(
        FOLD, lambda: __import__("mcgyvr.telemetry", fromlist=["fold"]).fold
    )


def test_a_correction_cannot_be_written_without_naming_its_author(
    tmp_path: Path,
) -> None:
    """The defect is the optional parameter; the fix refuses the omission."""
    sink = tmp_path / "attempts.jsonl"
    with pytest.raises(TypeError, match="orchestrator"):
        _correct()(path=sink, attempt_id="ghost-1", outcome="merged")


def test_an_orphan_correction_carries_the_author_it_named(tmp_path: Path) -> None:
    """A correction naming no attempt still says who wrote it, on its own row."""
    sink = tmp_path / "attempts.jsonl"
    _correct()(
        path=sink,
        attempt_id="ghost-1",
        outcome="merged",
        orchestrator="orch-b",
    )

    orphan = [r for r in _fold()(path=sink) if r.get("attempt_id") == "ghost-1"]
    assert len(orphan) == 1
    assert orphan[0].get("applied_by") == "orch-b", (
        f"an orphan correction carries no author: {orphan}"
    )
