"""The rate card, and the property that makes it a rate and not a total (#289).

``reproducibility.json``'s ``matching`` prose priced a null at "about 40
minutes" — one constant for every cell — beside a ``1.47pp`` bound that had the
same shape and the same defect. The card replaces the constant. These tests
hold it to three things:

* it **re-derives** from the runs on disk, so a committed record cannot drift
  from the measurement it claims to be;
* it is keyed on both axes, because the gate does not scale with the model and
  a card keyed on ``model`` alone would mis-price every ``ts`` cell;
* the prose it replaced no longer states a competing constant.

The last one is the one that would rot silently. A record that supersedes a
figure while the figure stays quotable somewhere else has not superseded it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
CARD = REPO / "tools" / "bench" / "rate-card.json"
REPRODUCIBILITY = REPO / "tools" / "bench" / "reproducibility.json"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ratecard() -> Any:
    return _by_path("bench_ratecard_t", REPO / "tools" / "bench" / "ratecard.py")


@pytest.fixture(scope="module")
def card() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(CARD.read_text(encoding="utf-8"))
    return loaded


def test_the_committed_card_re_derives_from_the_runs(
    ratecard: Any, card: dict[str, Any]
) -> None:
    """A stale record is the failure mode; deriving on demand is the fix."""
    assert card["cells"] == ratecard.derive(), (
        "tools/bench/rate-card.json disagrees with tools/bench/ratecard.py's "
        "derivation — re-generate the record or explain which runs moved"
    )


def test_every_declared_bound_is_priced(card: dict[str, Any]) -> None:
    """A cell with a bound and no price is a cell nobody can budget a re-run for."""
    bounds = json.loads(REPRODUCIBILITY.read_text(encoding="utf-8"))["bounds"]
    assert [(b["model"], b["tier"]) for b in bounds] == [
        (c["model"], c["tier"]) for c in card["cells"]
    ]


def test_the_rate_is_the_sum_of_its_two_parts(card: dict[str, Any]) -> None:
    for cell in card["cells"]:
        assert cell["total_s"] == pytest.approx(
            cell["generation_s"] + cell["gate_s"], abs=1e-4
        )


def test_the_formula_recovers_the_pair_totals(
    ratecard: Any, card: dict[str, Any]
) -> None:
    """The r1 pairs at n = 257, task time only, to the tenth of a minute."""
    expected = {
        ("qwen2.5-coder:1.5b", "bench-py"): 16.2,
        ("qwen2.5-coder:1.5b", "bench-ts"): 32.1,
        ("qwen2.5-coder:7b", "bench-py"): 29.5,
        ("qwen2.5-coder:7b", "bench-ts"): 48.7,
    }
    for cell in card["cells"]:
        got = ratecard.minutes(cell["total_s"], 257, setup=0)
        assert got == pytest.approx(expected[(cell["model"], cell["tier"])], abs=0.1)


def test_setup_is_additive_and_re_derives_from_the_invocation_stamps(
    ratecard: Any, card: dict[str, Any]
) -> None:
    """The claim that would silently become a lie if the harness got slower.

    Setup is stated as minutes-per-pass rather than a percentage. That is only
    honest while it does not track pass duration — so this checks the spread
    across passes of very different lengths, not merely the mean.
    """
    rows = ratecard.overheads()
    assert card["overheads"] == rows, "the committed overhead rows are stale"
    assert len(rows) == 6, (
        "6 of 8 passes are differenceable — the last of each session has no "
        "successor. A different count means the sessions or the stamps moved"
    )

    setups = [row["setup_minutes"] for row in rows]
    tasks = [row["task_minutes"] for row in rows]
    # 2.5x, not 3x: the observed ratio is 3.01 and a 3x threshold clears by
    # 0.2%, so any change to the bound set would flip it into a failure that
    # reads like a finding when it is only the threshold.
    ratio = max(tasks) / min(tasks)
    assert ratio > 2.5, (
        f"passes span only {ratio:.2f}x in duration — too narrow for their "
        "flat setup to be evidence that setup is additive rather than a "
        "percentage that happens to look flat"
    )
    assert max(setups) - min(setups) < 0.15, (
        f"setup spread {max(setups) - min(setups):.2f} min across passes "
        f"{ratio:.1f}x apart in length — it is tracking duration, so it is not "
        "additive and rate-card.json's formula is wrong"
    )
    assert pytest.approx(sum(setups) / len(setups), abs=0.05) == ratecard.SETUP_MIN


def test_the_record_cannot_drift_from_the_constant_it_states(
    ratecard: Any, card: dict[str, Any]
) -> None:
    """The guard covers all three derived values, not just the cells.

    Checking one of three was the card's own defect in miniature: bump
    ``SETUP_MIN`` and leave ``rate-card.json``'s ``setup_minutes`` alone, and
    a cells-only guard reports agreement while the record and the formula state
    two different constants.
    """
    assert not ratecard.stale(card, ratecard.derive())

    drifted = dict(card, setup_minutes=card["setup_minutes"] + 0.03)
    assert any(
        "setup_minutes" in item for item in ratecard.stale(drifted, ratecard.derive())
    ), (
        "a setup_minutes that disagrees with SETUP_MIN by less than the mean's "
        "own tolerance passes the guard — exactly the drift the card exists "
        "to make impossible"
    )


def test_the_wall_figure_exceeds_task_time_by_exactly_two_setups(
    ratecard: Any,
) -> None:
    """A null is a pair, and each pass pays setup once — not the pair."""
    task_only = ratecard.minutes(3.44, 257, setup=0)
    wall = ratecard.minutes(3.44, 257)
    assert wall - task_only == pytest.approx(2 * ratecard.SETUP_MIN, abs=1e-6)


def test_the_gate_does_not_scale_with_the_model_and_the_card_can_show_it(
    card: dict[str, Any],
) -> None:
    """The reason the card is keyed on two axes rather than one.

    On ``bench-py`` the gate costs the same at both models — a linter does not
    read the model's output size. Generation does scale. A card keyed on
    ``model`` alone could not represent that, and would carry the ``py`` gate
    cost into every ``ts`` cell.
    """
    by_key = {(c["model"], c["tier"]): c for c in card["cells"]}
    small = by_key[("qwen2.5-coder:1.5b", "bench-py")]
    large = by_key[("qwen2.5-coder:7b", "bench-py")]

    assert small["gate_s"] == pytest.approx(large["gate_s"], abs=0.05), (
        "the py gate moved with the model — the card's two-axis justification "
        "no longer holds and its why_two_axes note needs re-measuring"
    )
    assert large["generation_s"] > 1.5 * small["generation_s"]

    for model in ("qwen2.5-coder:1.5b", "qwen2.5-coder:7b"):
        assert (
            by_key[(model, "bench-ts")]["gate_s"]
            > 5 * by_key[(model, "bench-py")]["gate_s"]
        ), "the ts gate collapsed toward the py gate; the arms no longer differ"


@pytest.fixture(scope="module")
def identity() -> Any:
    return _by_path("bench_identity_rc_t", REPO / "tools" / "bench" / "identity.py")


def test_the_prose_and_the_code_agree_on_what_is_not_yet_enforced(
    identity: Any,
) -> None:
    """The mismatch #289 was asked to close or record. It records it.

    ``reproducibility.json``'s ``matching`` states five fields; ``BOUND_MATCH``
    is four. That is deliberate — ADR-0027 D9 added ``cells`` and #231 owns
    enforcing it — but a deferral written down in only one of the two places a
    reader consults is indistinguishable from an oversight, and satisfiable
    twice. So the code names the pending field, and this test holds the two
    documents to the same list.
    """
    matching = json.loads(REPRODUCIBILITY.read_text(encoding="utf-8"))["matching"]
    for field in identity.BOUND_MATCH_PENDING:
        assert field in matching, (
            f"{field!r} is pending in identity.py but the reproducibility "
            "prose does not mention it"
        )
    assert not set(identity.BOUND_MATCH_PENDING) & set(identity.BOUND_MATCH), (
        "a field cannot be both enforced and pending — if BOUND_MATCH gained "
        "it, drop it from BOUND_MATCH_PENDING in the same change"
    )


def test_the_tier_collision_is_recorded_on_the_side_that_can_carry_it() -> None:
    """Half a cross-reference, and the round pin is why it is only half.

    ``tier`` means a language arm in the bench and a worker rung in the product
    ladder. Both sides should say so. Only the bench side does, because
    ``src/mcgyvr`` is inside ``product.SURFACE`` — so **a docstring in
    ``config.py`` moves ``product_sha256`` and re-baselines the open round**.
    A comment is not worth retiring a round over, and #276's sequencing already
    schedules identity edits to land together before ``r2`` opens.

    The consequence is worth stating plainly, because it is not obvious and it
    accrues: documentation debt inside the product surface cannot be paid off
    except at a round boundary. This test records the half that exists and the
    reason the other half does not, so its absence is a decision rather than an
    omission somebody later mistakes for one.
    """
    bench = (REPO / "tools" / "bench" / "identity.py").read_text(encoding="utf-8")
    assert "LANGUAGE ARM" in bench, (
        "tools/bench/identity.py no longer says which sense of `tier` its "
        "BOUND_MATCH keys on"
    )

    surface = _by_path("bench_product_rc_t", REPO / "tools" / "bench" / "product.py")
    assert "src/mcgyvr" in surface.SURFACE, (
        "src/mcgyvr left the product surface — the ladder-side note this test "
        "documents as deferred is now free to write, so write it and assert it"
    )


def test_the_superseded_constant_is_gone_from_the_prose() -> None:
    """A replaced figure that stays quotable somewhere else was not replaced."""
    matching = json.loads(REPRODUCIBILITY.read_text(encoding="utf-8"))["matching"]
    assert "40 minutes" not in matching, (
        "reproducibility.json still prices a null at a flat 40 minutes. The "
        "rate card measured that constant at 2.0x too high for the cheapest "
        "cell and 23% too low for the dearest — point the prose at the card"
    )
    assert "rate-card.json" in matching, (
        "the prose no longer states the old constant but names no replacement, "
        "so a reader asking what a null costs has nowhere to go"
    )


# The ADR-0027 cross-check that stood here is gone with its subject. It
# asserted that ADR-0027's "~40 minutes each" carried the #289 amendment
# retiring it, so the constant could not stay quotable in the record after
# rate-card.json replaced it. The decision records were archived on
# 2026-08-25 (archive/docs/archive/decisions/) and no longer bind anything, so
# there is nothing left for that check to keep in sync. rate-card.json is
# still checked by the tests above.
