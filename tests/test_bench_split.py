"""The bench/reserve split rule is pinned (#225).

The rule's whole value is that it was declared before any generated problem
existed and can never drift afterwards. So the suite pins it three ways: the
salt byte for byte, golden assignments for concrete ids, and the invariants
the campaign leans on (purity of the id → half function, both-halves-only
output). A change to any of these is a re-split of the campaign and must
fail loudly, not slide through.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


split = _by_path("bench_split", REPO / "tools" / "bench" / "split.py")


def test_salt_is_the_declared_rule() -> None:
    """The salt is part of the declared rule; changing it re-splits the campaign."""
    assert split.SALT == "mcgyvr-bench-split-2026-08-10:"


def test_golden_assignments_never_move() -> None:
    """Concrete ids stay where the rule put them on the day it was declared."""
    golden = {
        "b001-ring-buffer": "bench",
        "b002-interval-merge": "bench",
        "b003-lru": "bench",
        "b400-tail": "bench",
    }
    for problem_id, half in golden.items():
        assert split.assignment(problem_id) == half


def test_assignment_is_pure_and_two_valued() -> None:
    """Same id, same answer, and only the two declared halves exist."""
    ids = [f"b{n:03d}-synthetic" for n in range(1, 201)]
    first = [split.assignment(i) for i in ids]
    second = [split.assignment(i) for i in ids]
    assert first == second
    assert set(first) <= {split.BENCH, split.RESERVE}
    # Both halves actually occur over a population the size of a stratum —
    # a rule that sends everything one way is not a split.
    assert split.BENCH in first and split.RESERVE in first


def test_check_mode_flags_a_moved_problem(monkeypatch: object) -> None:
    """--check catches a manifest entry that disagrees with the rule."""
    import io

    right = f"b001-ring-buffer {split.assignment('b001-ring-buffer')}\n"
    wrong_half = (
        split.RESERVE
        if split.assignment("b002-interval-merge") == split.BENCH
        else split.BENCH
    )
    wrong = f"b002-interval-merge {wrong_half}\n"

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "sys.stdin", io.StringIO(right + wrong)
    )
    assert split.main(["--check"]) == 1

    monkeypatch.setattr("sys.stdin", io.StringIO(right))  # type: ignore[attr-defined]
    assert split.main(["--check"]) == 0
