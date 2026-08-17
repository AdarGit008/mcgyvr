"""The acceptance ceiling's evidence, and the two ways it could be read wrong.

`tools/bench/ceiling.py` produces every figure ADR-0035 rests on. Two of its
steps are the kind that pass silently when they are wrong:

* **which rows are timeouts.** Two scorers wrote the corpus and they phrase it
  differently — the acceptance-only path says "timed out after 30.0s", `Gate.run`
  says the acceptance command "exceeded the task's time limit". Matching one
  phrasing puts 3 timeout rows into the *passing-candidate* population, and the
  slowest of them is the number the whole decision turns on.
* **which rows could have observed the disputed band.** A run measured at a 30 s
  ceiling cannot produce a row above it, so counting the [30, 120) band over the
  whole corpus reads 31,062 censored rows as evidence of emptiness. The
  uncensored subset has to be identified, and no manifest recorded a ceiling
  before #262, so it is identified from the rows themselves.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def ceiling() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "bench_ceiling_t", REPO / "tools" / "bench" / "ceiling.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(**overrides: Any) -> dict[str, Any]:
    row = {
        "population": "candidate",
        "run": "run-a",
        "file": "run-a/results.jsonl",
        "id": "b001",
        "seconds": 0.1,
        "passed": True,
        "timed_out": False,
    }
    return row | overrides


def test_a_timeout_is_never_counted_as_a_slow_pass(ceiling: types.ModuleType) -> None:
    """The population a ceiling is chosen against is the rows that PASSED.

    A timeout that leaked into it would put a censored value — the ceiling
    itself — into a band that is supposed to say how close a real pass got to
    one. The whole argument would then be circular.
    """
    summary = ceiling.summarise(
        [
            _candidate(seconds=2.5),
            _candidate(seconds=28.718, id="p242"),
            _candidate(seconds=30.0, passed=False, timed_out=True),
            _candidate(seconds=121.4, passed=False, timed_out=True, run="run-b"),
        ]
    )
    assert summary["candidates"]["passing"]["max"] == 28.718
    assert summary["candidates"]["slowest_pass"]["id"] == "p242"
    assert summary["candidates"]["second_slowest_pass"] == 2.5
    assert summary["candidates"]["timeouts"] == 2
    assert summary["candidates"]["timeouts_that_passed"] == 0


def test_both_scorers_phrasings_are_recognised_as_timeouts(
    ceiling: types.ModuleType,
) -> None:
    """One marker would misclassify the three rows measured at the wide ceiling.

    Asserted against the constant rather than against a hand-written pair, so a
    third scorer arriving with a third phrasing fails here rather than quietly
    reclassifying its timeouts as very slow passes.
    """
    assert "timed out" in ceiling.TIMEOUT_MARKERS
    assert "exceeded the task's time limit" in ceiling.TIMEOUT_MARKERS


def test_the_censored_rows_are_excluded_from_the_band_count(
    ceiling: types.ModuleType,
) -> None:
    """A 30 s run cannot answer a question about [30, 120). It must not be asked.

    `run-narrow` tops out at 30 s, so its rows are censored and carry no
    information about the band; `run-wide` produced a row above it, so its rows
    could have landed there. Counting the band over both would report the same
    zero while resting on 3x the rows, which is the overstatement this splits.
    """
    rows = [
        _candidate(run="run-narrow", seconds=30.0, passed=False, timed_out=True),
        _candidate(run="run-narrow", seconds=0.2),
        _candidate(run="run-wide", seconds=121.4, passed=False, timed_out=True),
        _candidate(run="run-wide", seconds=45.0),
    ]
    band = ceiling.summarise(rows)["band_30_to_120"]
    assert band["runs_that_could_observe_it"] == ["run-wide"]
    assert band["rows_that_could_observe_it"] == 2
    assert band["rows_censored_at_30"] == 2
    # The one row genuinely in the band, from the one run that could show it.
    assert band["rows_in_the_band"] == 1


def test_the_recorded_measurement_still_says_what_the_decision_cites(
    ceiling: types.ModuleType,
) -> None:
    """ADR-0035's four numbers, held to the record they were read off.

    Not recomputed from the corpus here — that is a 30 s read of 32,601 rows and
    belongs in the tool, not the suite. What this catches is the record and the
    decision drifting apart, which is the failure `test_estimate_reserve_is_derived`
    exists for one lens over: a shipped number citing evidence nobody re-checks.
    """
    record = (
        REPO
        / "records"
        / "measurements"
        / "acceptance-ceiling-2026-08-17"
        / "summary.json"
    )
    summary = json.loads(record.read_text(encoding="utf-8"))
    assert summary["candidates"]["slowest_pass"]["seconds"] == 28.718
    assert summary["candidates"]["second_slowest_pass"] == 2.5
    assert summary["band_30_to_120"]["rows_in_the_band"] == 0
    assert summary["references"]["all"]["n"] == 514
    assert summary["references"]["failed"] == [], (
        "every admitted reference must pass its own checker — a corpus that "
        "fails its own bar makes every duration here a timing of something else"
    )

    score = REPO / "tools" / "bench" / "score.py"
    ceiling_s = summary["candidates"]["slowest_pass"]["seconds"]
    assert f"{ceiling_s}" in score.read_text(encoding="utf-8"), (
        "the scorer's ceiling cites this measurement; if the record moves and "
        "the derivation does not, the number stops being derived"
    )
