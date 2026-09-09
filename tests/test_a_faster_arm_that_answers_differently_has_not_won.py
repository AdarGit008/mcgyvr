"""Speed is only half of a verdict, and this repo has no perplexity harness to
give the other half a false comfort — it has something better.

The arms deliberately run different kernels. Different reduction order gives
different logits, and the 2026-09-01 A/B already shows the symptom: same prompts,
``temperature: 0``, and yet ``otok`` 214 against 221 on the same cell, and
``early_stop`` 3/4 against 2/4. The arms did different amounts of work and
nothing checked whether they did the same *work*.

The instrument exists and is stronger than token identity:
``tools/breadth/measure.py --endpoint ... --protocol openai --tier bench-py``
drives a 257-problem paired corpus through the production gate, and
``tools/bench/null.py`` compares two runs by ``candidate_sha256`` while separating
**sampler drift** (different bytes) from **acceptance drift** (identical bytes
scoring differently). ``STOP_CONDITION_PP = 3.0`` is its adoption bar, and
``tools/bench/reproducibility.json`` carries a measured null: ``flips: 0``,
``bound_pp: 1.47`` over 257 cells.

The catch, and the reason for the second test: that bound's matching rule
requires ``serving_build`` to match, and every arm here is a new build. No
committed bound covers them. Each arm prices its own null first.
"""

from __future__ import annotations

import json

from tests.sweeprows import REPO, evidence_path

CORRECTNESS = evidence_path("correctness.json")
REPRO = REPO / "tools" / "bench" / "reproducibility.json"


def test_the_instrument_and_its_bar_are_in_the_tree() -> None:
    """Green today. The point of this campaign is to *use* what exists rather
    than write a diff harness, so the tests name the tools by path."""
    assert (REPO / "tools" / "breadth" / "measure.py").is_file()
    assert (REPO / "tools" / "bench" / "null.py").is_file()
    declared = json.loads(REPRO.read_text(encoding="utf-8"))
    assert declared["bounds"], "no null bound is declared"
    assert all("serving_build" in b for b in declared["bounds"]), (
        "a bound that does not name its build cannot be matched to a run"
    )


def test_every_arm_named_a_winner_was_scored_through_the_gate() -> None:
    result = json.loads(CORRECTNESS.read_text(encoding="utf-8"))
    scored = {a["arm"] for a in result["arms"]}
    for verdict in result["verdicts"]:
        assert verdict["winner"] in scored, (
            f"{verdict['winner']} is named the winner of {verdict['question']!r} "
            "and was never scored. A faster arm that answers differently has not "
            "won — it has computed something else."
        )


def test_each_arm_priced_its_own_null_before_being_compared() -> None:
    result = json.loads(CORRECTNESS.read_text(encoding="utf-8"))
    for arm in result["arms"]:
        self_null = arm["self_null"]
        assert self_null["serving_build"] == arm["serving_build"], (
            f"{arm['arm']} is judged against a bound measured on "
            f"{self_null['serving_build']!r}. reproducibility.json keys a bound on "
            "serving_build, and every arm here is a new build."
        )
        assert self_null["cells"] == arm["cells"], (
            f"{arm['arm']}: bound measured over {self_null['cells']} cells, run "
            f"over {arm['cells']}. A rate keyed on everything but its own "
            "denominator transfers to subsets it never saw."
        )


def test_drift_from_the_reference_arm_is_inside_the_bound_that_arm_measured() -> None:
    result = json.loads(CORRECTNESS.read_text(encoding="utf-8"))
    reference = [a for a in result["arms"] if a.get("is_reference")]
    assert len(reference) == 1, (
        f"the reference arm is {[a['arm'] for a in reference]}, not exactly one"
    )
    for arm in result["arms"]:
        if arm.get("is_reference"):
            continue
        bound = max(arm["self_null"]["bound_pp"], reference[0]["self_null"]["bound_pp"])
        assert arm["drift_pp"] <= bound, (
            f"{arm['arm']} drifts {arm['drift_pp']}pp from "
            f"{reference[0]['arm']}, outside the {bound}pp the instrument itself "
            "shows. It is not a faster path to the same answer."
        )
        assert arm["acceptance_drift"] == 0, (
            f"{arm['arm']}: identical bytes scored differently, so the gate is "
            "unstable and no conclusion passes through it"
        )
