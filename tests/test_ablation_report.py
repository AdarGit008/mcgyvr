"""The ablation report's statistics (#225), held against first principles.

A defect in these two functions would not crash anything — it would publish a
p-value. This project has already spent a lane correcting a claim whose
arithmetic nobody re-derived, so both tests are checked against independent
computation rather than against a remembered formula.

The anchor worth naming: six problems that all moved the same way give
p = 0.0312 under both tests, and that is the best a six-pair comparison can
do. It is where ADR-0019's `m >= 6` wall comes from, and the report prints
`m` for every contrast so a result below it is visibly undecidable rather
than quietly weak.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
import types
from itertools import product
from math import comb
from pathlib import Path

from mcgyvr.contract import Contract, loads

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


report = _by_path("ablation_report", REPO / "tools" / "bench" / "ablation_report.py")


def test_the_sign_test_matches_the_closed_form_exhaustively() -> None:
    """Every (m, positives) up to m = 12, against the binomial tail directly."""
    for m in range(1, 13):
        for up in range(m + 1):
            diffs = [1] * up + [-1] * (m - up)
            got_m, got_up, p = report.sign_test(diffs)
            tail = sum(comb(m, k) for k in range(min(up, m - up) + 1))
            assert (got_m, got_up) == (m, up)
            assert abs(p - min(1.0, 2 * tail / 2**m)) < 1e-12


def _independent_wilcoxon(diffs: list[int]) -> float:
    """The permutation p-value, computed without touching the module's code."""
    moved = [d for d in diffs if d != 0]
    m = len(moved)
    if m == 0:
        return 1.0
    absv = sorted(abs(d) for d in moved)
    rank: dict[int, float] = {}
    i = 0
    while i < m:
        j = i
        while j + 1 < m and absv[j + 1] == absv[i]:
            j += 1
        rank.setdefault(absv[i], (i + j) / 2 + 1)
        i = j + 1
    ranks = [rank[abs(d)] for d in moved]
    total = sum(ranks)
    plus = sum(r for r, d in zip(ranks, moved, strict=True) if d > 0)
    observed = min(plus, total - plus)
    hits = 0
    for signs in product((0, 1), repeat=m):
        p = sum(r for r, s in zip(ranks, signs, strict=True) if s)
        if min(p, total - p) <= observed + 1e-9:
            hits += 1
    exact: float = min(1.0, hits / 2**m)
    return exact


def test_wilcoxon_matches_an_independent_enumeration() -> None:
    """Random vectors, ties and zeros included, against a separate derivation."""
    random.seed(7)
    for _ in range(200):
        m = random.randint(1, 9)
        diffs = [random.choice([-3, -2, -1, 1, 2, 3]) for _ in range(m)]
        diffs += [0] * random.randint(0, 4)
        _, p = report.wilcoxon(diffs)
        assert p is not None
        assert abs(p - _independent_wilcoxon(diffs)) < 1e-9


def test_six_pairs_all_one_way_is_the_wall() -> None:
    """ADR-0019's `m >= 6`, in the number it actually denotes."""
    _, p_wilcoxon = report.wilcoxon([1, 2, 3, 4, 5, 6])
    _, _, p_sign = report.sign_test([1, 2, 3, 4, 5, 6])
    assert abs(p_sign - 2 / 64) < 1e-12
    assert p_wilcoxon is not None and abs(p_wilcoxon - 2 / 64) < 1e-12

    # Five pairs, perfect and one-directional, cannot reach 0.05 — which is
    # the whole content of the wall.
    _, _, p_five = report.sign_test([1, 2, 3, 4, 5])
    assert p_five > 0.05


def test_no_movement_is_reported_as_no_information() -> None:
    """Concordant pairs must not be mistaken for evidence of no effect."""
    m, up, p = report.sign_test([0, 0, 0, 0])
    assert (m, up, p) == (0, 0, 1.0)


def test_a_dispatch_error_row_is_not_counted_as_a_draw(tmp_path: Path) -> None:
    """#217: a cell nobody observed must not shrink or pad a denominator."""
    cell = tmp_path / "stock" / "bench-ts"
    cell.mkdir(parents=True)
    rows = [
        {"task": "b001-x", "passed": True},
        {"task": "b001-x", "passed": False},
        {"task": "b001-x", "dispatch_error": "TimeoutError: gone"},
    ]
    cell.joinpath("results.jsonl").write_text(
        "\n".join(__import__("json").dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    assert report.counts(tmp_path, "stock", "bench-ts") == {"b001-x": (1, 2)}


def test_the_two_row_sources_are_read_apart(tmp_path: Path) -> None:
    """A re-score is a different judge on the same output, not a correction.

    `results.jsonl` is what the sweep recorded on the day, under the checker of
    the day; `regrade.jsonl` is `tools/bench/regrade.py`'s verdict under the
    checkers as they stand now. They must never be silently merged or silently
    preferred — ADR-0023's `ValueError` fix moved 40 py cells, and a reader that
    chose a file on its own would make it impossible to tell which number a
    table was quoting.
    """
    cell = tmp_path / "stock" / "bench-py"
    cell.mkdir(parents=True)
    cell.joinpath("results.jsonl").write_text(
        json.dumps({"task": "b001-x", "passed": False}) + "\n", encoding="utf-8"
    )
    cell.joinpath("regrade.jsonl").write_text(
        json.dumps({"task": "b001-x", "passed": True, "regraded": True}) + "\n",
        encoding="utf-8",
    )
    assert report.counts(tmp_path, "stock", "bench-py") == {"b001-x": (0, 1)}
    assert report.counts(tmp_path, "stock", "bench-py", "as-measured") == {
        "b001-x": (0, 1)
    }
    assert report.counts(tmp_path, "stock", "bench-py", "regraded") == {
        "b001-x": (1, 1)
    }


def test_asking_for_a_regrade_that_was_never_run_reads_as_an_absent_cell(
    tmp_path: Path,
) -> None:
    """Absent is absent: a missing re-score must not fall back to the old rows.

    Falling back would report as-measured numbers under a `regraded` heading,
    which is precisely the confusion the two files exist to prevent.
    """
    cell = tmp_path / "stock" / "bench-py"
    cell.mkdir(parents=True)
    cell.joinpath("results.jsonl").write_text(
        json.dumps({"task": "b001-x", "passed": True}) + "\n", encoding="utf-8"
    )
    assert report.counts(tmp_path, "stock", "bench-py", "regraded") == {}


# --- the analysis set: declared apart from the numbers, and re-derived here ---


def _contract(arm: str, task_id: str) -> Contract:
    path = REPO / "tools" / "bench" / "tasks" / arm / task_id / "contract.yaml"
    return loads(path.read_text(encoding="utf-8"))


def test_the_dispatched_set_is_every_scaffolded_function_problem() -> None:
    """The eligibility rule, re-derived from the contracts rather than trusted.

    A hand-kept list of ids is a claim about the bench that stops being true
    the moment the bench changes. The rule is: a scaffold to remove, and a
    function to implement. The 19 scaffolded `bug_fix` problems are outside it
    because their scaffold *is* the problem — removing a buggy program deletes
    the task instead of enlarging it, which is a different experiment wearing
    this one's name.
    """
    declared = set(report.declared_sets()["dispatched"])
    for arm in ("ts", "py"):
        derived = {
            task.name
            for task in sorted((REPO / "tools" / "bench" / "tasks" / arm).iterdir())
            if _contract(arm, task.name).task_type == "function_implementation"
            and (_contract(arm, task.name).target_content or "").strip()
        }
        assert derived == declared, f"{arm}: the declaration and the bench disagree"


def test_the_excluded_problems_are_the_ones_whose_prompt_contradicts_itself() -> None:
    """Seven exclusions, and the reason is checkable in the material.

    Ablating a scaffold the prose calls "already written" dispatches a prompt
    that contradicts itself, and what it measures is a model's response to an
    impossible instruction. The list is committed for readability; this test is
    what makes it a rule, in both arms — a phrase present in one language's
    prose and not the other's would silently make the two arms different
    experiments.
    """
    doc = json.loads((REPO / "tools" / "bench" / "ablation-sets.json").read_text())
    phrase = doc["excluded"]["phrase"]
    declared = {entry["id"] for entry in doc["excluded"]["ids"]}
    for arm in ("ts", "py"):
        derived = {
            task_id
            for task_id in report.declared_sets()["dispatched"]
            if phrase in _contract(arm, task_id).task
        }
        assert derived == declared, f"{arm}: the exclusion rule moved"

    for entry in doc["excluded"]["ids"]:
        assert entry["prose"] in " ".join(_contract("ts", entry["id"]).task.split())


def test_the_sets_nest_and_the_derived_ones_are_never_listed() -> None:
    """`analysis` and `strict` are subtractions, so they cannot drift.

    Three committed lists would be three things to keep in agreement, and the
    one that goes stale is the one nobody reads. Only `dispatched` is listed.
    """
    sets = report.declared_sets()
    assert set(sets["strict"]) < set(sets["analysis"]) < set(sets["dispatched"])
    assert (len(sets["dispatched"]), len(sets["analysis"]), len(sets["strict"])) == (
        34,
        27,
        23,
    )
    doc = json.loads((REPO / "tools" / "bench" / "ablation-sets.json").read_text())
    assert set(doc) == {
        "record",
        "issue",
        "why",
        "dispatched",
        "excluded",
        "borderline",
        "audit",
    }, "a set stored rather than derived is a set that can disagree"


def test_a_set_file_survives_being_newline_terminated(tmp_path: Path) -> None:
    """The silent failure: `split(",")` keeps the newline on the last id.

    An id that matches nothing is dropped without a word, so the report would
    print n = 26 where 27 was meant and nothing would look wrong. Every editor
    writes that trailing byte.
    """
    ids = report.declared_sets()["analysis"]
    path = tmp_path / "set.txt"
    path.write_text(",".join(ids) + "\n", encoding="utf-8")
    run = REPO / "records" / "measurements" / "bench-scaffold-ablation-3b-2026-08-11"
    assert report.main(["--run", str(run), "--set", str(path)]) == 0


def test_a_retired_problems_rows_reach_no_figure(tmp_path: Path) -> None:
    """A problem withdrawn from the bench must not survive in a derived rate.

    Its rows stay in the run record — `results.jsonl` states what was
    dispatched on the day, and `regrade.py`'s docstring is explicit that a
    record which changes with the tooling is not a record. Removal happens
    here, where a figure is computed, which is the same reasoning as #230's
    instrument pin stamping rather than excluding.
    """
    retired = sorted(report.retired_ids())
    assert retired, "the declaration is the mechanism; an empty one is a no-op"
    victim = retired[0]

    cell = tmp_path / "stock" / "bench-ts"
    cell.mkdir(parents=True)
    rows = [
        {"task": "b001-x", "passed": True},
        {"task": victim, "passed": True},
        {"task": victim, "passed": False},
    ]
    cell.joinpath("results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    assert report.counts(tmp_path, "stock", "bench-ts") == {"b001-x": (1, 1)}, (
        "a retired problem contributes neither a pass nor a draw"
    )


def test_a_retired_problem_leaves_every_declared_set() -> None:
    """Including `dispatched`, which would otherwise hold a permanently empty cell."""
    withdrawn = report.retired_ids()
    for name, ids in report.declared_sets().items():
        assert not (set(ids) & withdrawn), name
