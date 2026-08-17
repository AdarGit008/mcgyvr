"""The arithmetic behind "what does the second language arm buy" (#295).

A defect here would not crash. It would publish a number that decides whether
~280 problems get authored twice or once, which is the most expensive decision
the campaign has left. So each statistic is checked against a computation that
shares no code with it: phi against the 2x2 formula worked by hand, McNemar
against an explicit enumeration of the coin flips it is a shortcut for, and the
concordance against the case it exists to separate — two arms that agree only
by failing together.

The join is checked too. Pairing on task id alone would silently marry a task's
first `ts` draw to whichever `py` draw sorted first, which is not an error a
reader of the output could see.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from math import comb, isclose
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


arms = _by_path("arms", REPO / "tools" / "bench" / "arms.py")


def _pairing(both_pass: int, both_fail: int, py_only: int, ts_only: int) -> Any:
    return arms.Pairing("t", both_pass, both_fail, py_only, ts_only)


def test_phi_matches_the_two_by_two_formula_worked_by_hand() -> None:
    """a=10 b=5 c=5 d=10 gives (100-25)/sqrt(15*15*15*15) = 75/225."""
    assert isclose(_pairing(10, 10, 5, 5).phi, 75 / 225, rel_tol=1e-12)


def test_phi_is_zero_rather_than_one_when_a_margin_is_empty() -> None:
    """Every cell passing on both arms leaves the coefficient undefined.

    Reporting that as perfect correlation is precisely the read this tool
    exists to prevent — it is the shape "the second arm adds nothing" takes
    when in fact there was nothing to disagree about.
    """
    assert _pairing(20, 0, 0, 0).phi == 0.0
    assert _pairing(0, 20, 0, 0).phi == 0.0


def test_mcnemar_matches_an_explicit_enumeration_of_the_flips() -> None:
    """The exact p is a binomial tail; enumerate it rather than trust the call."""
    row = _pairing(0, 0, 9, 1)
    expected = min(1.0, 2 * sum(comb(10, k) for k in range(2)) / 2**10)
    assert isclose(row.mcnemar_p, expected, rel_tol=1e-12)


def test_a_symmetric_disagreement_is_not_an_effect() -> None:
    """Equal splits are what "neither language is harder" looks like."""
    assert _pairing(10, 10, 5, 5).mcnemar_p == 1.0


def test_no_disagreement_at_all_is_p_one_and_not_a_division_by_zero() -> None:
    assert _pairing(7, 3, 0, 0).mcnemar_p == 1.0


def test_concordance_ignores_the_cells_that_failed_on_both_arms() -> None:
    """The number `agreement` hides.

    This table agrees on 95% of cells and 190 of those 200 agreements are
    mutual failure. Of the ten cells anything solved, half were solved twice.
    """
    row = _pairing(both_pass=5, both_fail=190, py_only=5, ts_only=0)
    assert isclose(row.agreement, 195 / 200)
    assert row.solved_anywhere == 10
    assert isclose(row.pass_concordance, 0.5)


def test_concordance_is_zero_rather_than_undefined_when_nothing_passed() -> None:
    assert _pairing(0, 50, 0, 0).pass_concordance == 0.0


def test_the_join_key_holds_the_draw_so_replication_cannot_cross_pair(
    tmp_path: Path,
) -> None:
    """Two draws of one task are two cells, not one."""
    results = tmp_path / "results.jsonl"
    results.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"task": "b001", "arm": "greedy", "draw": 0, "passed": True},
                {"task": "b001", "arm": "greedy", "draw": 1, "passed": False},
            )
        ),
        encoding="utf-8",
    )
    read = arms.verdicts(results)
    assert read == {("b001", "greedy", 0): True, ("b001", "greedy", 1): False}


def test_a_repeated_cell_is_a_refusal_rather_than_a_silent_overwrite(
    tmp_path: Path,
) -> None:
    """Last-write-wins over a duplicated row would change a published rate."""
    results = tmp_path / "results.jsonl"
    results.write_text(
        json.dumps({"task": "b001", "arm": "greedy", "draw": 0, "passed": True})
        + "\n"
        + json.dumps({"task": "b001", "arm": "greedy", "draw": 0, "passed": False}),
        encoding="utf-8",
    )
    with pytest.raises(arms.ArmsError, match="two rows for cell"):
        arms.verdicts(results)


def test_a_single_arm_run_is_skipped_rather_than_read_as_total_agreement(
    tmp_path: Path,
) -> None:
    """A sweep that ran one arm has no pairing in it, and reporting it as
    perfect agreement would put a fabricated row in the table."""
    run = tmp_path / "some-run"
    (run / "bench-py").mkdir(parents=True)
    (run / "bench-py" / "results.jsonl").write_text(
        json.dumps({"task": "b001", "arm": "greedy", "draw": 0, "passed": True}),
        encoding="utf-8",
    )
    assert arms.pair(run) is None
