"""The null read's one load-bearing distinction (#231 check 1).

The headline ``d`` — verdicts that differ between two identical greedy runs —
cannot tell two very different instruments apart, and the whole reason
``tools/bench/null.py`` exists is to split them:

* **Sampler drift** — the backend returned different text and some of it landed
  on the other side of the acceptance boundary. A property of the serving
  stack, which is why ADR-0024 pins the build.
* **Acceptance drift** — the *same bytes* scored differently. That is the
  harness being nondeterministic, it puts a floor under every contrast the
  bench will ever run, and no number of extra problems lowers it.

The 2026-08-12 run reported zero of the second kind. A defect that silently
folded them together would publish that same zero whether or not it was true,
so the classification is pinned here against rows built to contain one of each.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _row(task: str, passed: bool, sha: str) -> dict[str, object]:
    return {
        "task": task,
        "arm": "greedy",
        "draw": 0,
        "passed": passed,
        "candidate_sha256": sha,
        "stop_reason": "complete",
        "parse_error": None,
    }


@pytest.fixture
def null(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """The module, pointed at a synthetic pair of runs.

    Four cells, one of each kind the read must distinguish:

    ``concordant``   same bytes, same verdict — carries nothing.
    ``sampler``      different bytes, verdict flips — the expected mechanism.
    ``wobble``       different bytes, verdict holds — drift that never lands.
    ``acceptance``   *same* bytes, verdict flips — the defect that matters.
    """
    module = _by_path("bench_null", REPO / "tools" / "bench" / "null.py")
    monkeypatch.setattr(module, "M", tmp_path)
    monkeypatch.setattr(module, "ARMS", ("bench-py",))
    a = [
        _row("concordant", True, "aa"),
        _row("sampler", True, "bb"),
        _row("wobble", False, "cc"),
        _row("acceptance", True, "dd"),
    ]
    b = [
        _row("concordant", True, "aa"),
        _row("sampler", False, "b2"),
        _row("wobble", False, "c2"),
        _row("acceptance", False, "dd"),
    ]
    _write(tmp_path / module.RUN_A / "bench-py" / "results.jsonl", a)
    _write(tmp_path / module.RUN_B / "bench-py" / "results.jsonl", b)
    return module


def test_flips_count_both_mechanisms(null: types.ModuleType) -> None:
    """``d`` is every verdict that differs, whatever produced it."""
    r = null.compare("bench-py")
    assert sorted(r["flips"]) == ["acceptance", "sampler"]
    assert len(r["shared"]) == 4


def test_acceptance_drift_is_only_the_identical_bytes(
    null: types.ModuleType,
) -> None:
    """The split is the point: one of the two flips is the harness, not the model."""
    r = null.compare("bench-py")
    assert r["acceptance_flips"] == ["acceptance"]
    assert "sampler" not in r["acceptance_flips"]


def test_text_drift_that_never_reaches_the_verdict_is_not_a_flip(
    null: types.ModuleType,
) -> None:
    """90% byte-identity with d = 1 is the real run; the other 49 must not count."""
    r = null.compare("bench-py")
    assert "wobble" in r["diff_bytes"]
    assert "wobble" not in r["flips"]
    assert sorted(r["same_bytes"]) == ["acceptance", "concordant"]


def test_gains_and_losses_are_directional(null: types.ModuleType) -> None:
    """A null with all flips one way is still a null, but the direction is recorded."""
    r = null.compare("bench-py")
    assert r["gains"] == []
    assert sorted(r["losses"]) == ["acceptance", "sampler"]


def test_the_declared_bound_is_re_derivable_from_the_runs_it_names() -> None:
    """#231 check 4: the declaration is a measurement, or it is an assertion.

    ``reproducibility.json`` carries a bound per (model, tier, bar, build) and
    names the two run directories it came from. This walks back from the
    declaration to those directories and recomputes the number. Until ``null.py``
    printed the per-arm interval, the two entries on disk were computed by hand
    off-screen and nothing tied them to the rows.
    """
    real = _by_path("bench_null_real", REPO / "tools" / "bench" / "null.py")
    declared = json.loads(
        (REPO / "tools" / "bench" / "reproducibility.json").read_text(encoding="utf-8")
    )["bounds"]
    measurements = REPO / "records" / "measurements"
    for entry in declared:
        run_a, run_b = (Path(r) for r in entry["runs"])
        assert run_a.name == run_b.name, "a bound's two runs must be the same arm"
        if not (measurements / run_a / "results.jsonl").is_file():
            continue
        compared = real.compare(run_a.name, run_a.parent.name, run_b.parent.name)
        n = len(compared["shared"])
        assert n == entry["cells"], (
            f"{entry['tier']}: {n} cells, {entry['cells']} declared"
        )
        assert len(compared["flips"]) == entry["flips"]
        _, high = real.wilson(len(compared["flips"]), n)
        assert round(high * 100, 2) == entry["bound_pp"]
