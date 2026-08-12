"""The responsiveness read's arithmetic and its refusals (#225).

Like the ablation report beside it, a defect here would not crash — it would
publish a number. Three things are worth pinning, and each is checked against a
computation that does not share code with the thing it checks:

* **Fisher's p** decides the pre-registered tranche comparison. It is checked
  against an explicit enumeration of the label assignments, which is the
  permutation argument the hypergeometric formula is a shortcut for.
* **The classification** decides `psi_draw`, and a cell miscounted as pinned is
  a cell silently written off. Checked exhaustively over every verdict pattern.
* **The completeness rule** is what makes "no pass in nine draws" mean anything
  at all. A cell short a draw must be dropped, not scored — otherwise the
  pinned-fail count grows with every draw that failed to dispatch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from itertools import combinations, product
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


resp = _by_path("responsiveness", REPO / "tools" / "bench" / "responsiveness.py")


def _enumerated_fisher(a: int, b: int, c: int, d: int) -> float:
    """The two-sided p by enumerating label assignments, sharing no code.

    Fix the margins. Of ``n`` items, ``a + c`` carry the column-1 label; every
    way of choosing which is equally likely under the null. Counting those
    choices directly gives the null distribution the hypergeometric pmf
    summarises, so agreement is a check on the shortcut rather than on itself.
    """
    n = a + b + c + d
    row1, col1 = a + b, a + c
    rows = [0] * row1 + [1] * (n - row1)
    freq: dict[int, int] = {}
    for pick in combinations(range(n), col1):
        top = sum(1 for i in pick if rows[i] == 0)
        freq[top] = freq.get(top, 0) + 1
    total = sum(freq.values())
    observed = freq[a] / total
    return sum(f / total for x, f in freq.items() if f / total <= observed * (1 + 1e-9))


def test_fisher_matches_an_independent_enumeration() -> None:
    """Every small table, against the permutation count it abbreviates."""
    for a, b, c, d in product(range(5), repeat=4):
        if a + b == 0 or c + d == 0 or a + c == 0 or b + d == 0:
            continue
        got = resp.fisher_two_sided(a, b, c, d)
        assert abs(got - _enumerated_fisher(a, b, c, d)) < 1e-9, (a, b, c, d)


def test_fisher_reproduces_the_published_tea_tasting_value() -> None:
    """Fisher's own 2x2 — the one value of this test anybody can look up."""
    assert abs(resp.fisher_two_sided(3, 1, 1, 3) - 0.4857142857) < 1e-9


def test_fisher_is_one_when_the_table_is_perfectly_balanced() -> None:
    assert resp.fisher_two_sided(10, 10, 10, 10) == 1.0


def test_a_cell_is_pinned_only_when_every_draw_agrees() -> None:
    """Exhaustive over all 2**9 verdict patterns of greedy plus eight draws."""
    for pattern in product([False, True], repeat=9):
        cell = {"greedy": pattern[0], "sampled": list(pattern[1:])}
        got = resp.classify(cell)
        if not any(pattern):
            assert got == "pinned-fail"
        elif all(pattern):
            assert got == "pinned-pass"
        else:
            assert got == "responsive"


def test_one_pass_in_nine_is_responsive_not_pinned() -> None:
    """The whole point of replication: a single reachable draw is a live cell."""
    for i in range(8):
        sampled = [False] * 8
        sampled[i] = True
        assert resp.classify({"greedy": False, "sampled": sampled}) == "responsive"


def test_the_greedy_draw_counts_toward_the_classification() -> None:
    """A cell only greedy-passing is responsive, never pinned-fail."""
    assert resp.classify({"greedy": True, "sampled": [False] * 8}) == "responsive"


def test_wilson_reproduces_the_campaigns_published_interval() -> None:
    """105/270 is the f1 240-sweep figure, published as 33.3-44.8%."""
    lo, hi = resp.wilson(105, 270)
    assert abs(lo - 0.333) < 0.001 and abs(hi - 0.448) < 0.001


def test_tranche_boundaries_land_where_the_ids_were_authored() -> None:
    """b228 opens t4 and every fortieth id opens the next."""
    assert resp.tranche("b228-a") == 4
    assert resp.tranche("b267-a") == 4
    assert resp.tranche("b268-a") == 5
    assert resp.tranche("b388-a") == 8
    assert resp.tranche("b427-a") == 8
    assert resp.tranche("b428-a") == 9
    assert resp.tranche("b466-a") == 9


def _write(run: Path, arm: str, rows: list[dict[str, Any]]) -> None:
    d = run / f"bench-{arm}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _draws(task: str, passes: list[bool], greedy: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"task": task, "arm": "greedy", "draw": 0, "passed": greedy}
    ]
    out += [
        {"task": task, "arm": "sampled", "draw": i, "passed": p}
        for i, p in enumerate(passes)
    ]
    return out


def test_a_cell_short_one_draw_is_dropped_rather_than_scored(tmp_path: Path) -> None:
    """ "No pass in N" has to mean N draws were looked at (#217)."""
    run = tmp_path / "run"
    _write(run, "ts", _draws("b228-a", [False] * 8) + _draws("b230-b", [False] * 7))
    _write(run, "py", [])
    built = resp.cells(run, draws=8)
    assert ("ts", "b228-a") in built
    assert ("ts", "b230-b") not in built


def test_an_errored_draw_does_not_complete_a_cell(tmp_path: Path) -> None:
    """A draw nobody saw is not a draw, so its cell stays incomplete."""
    run = tmp_path / "run"
    rows = _draws("b228-a", [False] * 8)
    rows[4]["dispatch_error"] = "timeout"
    _write(run, "ts", rows)
    _write(run, "py", [])
    assert resp.cells(run, draws=8) == {}


def test_both_arms_are_separate_cells_of_the_same_problem(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write(run, "ts", _draws("b228-a", [True] * 8, greedy=True))
    _write(run, "py", _draws("b228-a", [False] * 8))
    built = resp.cells(run, draws=8)
    assert resp.classify(built[("ts", "b228-a")]) == "pinned-pass"
    assert resp.classify(built[("py", "b228-a")]) == "pinned-fail"


def test_retired_problems_are_dropped_where_the_figure_is_derived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Their rows stay in the record; no derived figure may count them."""
    run = tmp_path / "run"
    _write(run, "ts", _draws("b228-a", [False] * 8) + _draws("b230-b", [False] * 8))
    _write(run, "py", [])
    monkeypatch.setattr(resp, "retired_ids", lambda: frozenset({"b230-b"}))
    built = resp.cells(run, draws=8)
    assert set(built) == {("ts", "b228-a")}
