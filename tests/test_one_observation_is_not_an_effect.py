"""Nine single observations against a demonstrated 6.2% noise floor.

Every rung in the 2026-09-01 A/B is one batch, once. At n=1 that is one HTTP
request. And the measured spread between nominally identical stock cells — same
rig, same image, same hour — reaches 6.2% at n>=4, because the prompt draw
desyncs whenever the level list differs.

So: five replicates, interleaved rather than blocked (the existing A/B ran all of
one arm and then all of the other, perfectly confounding arm with elapsed time
and card temperature), an A/A null to price the instrument, and a pre-registered
decision rule that refuses to call anything smaller than the noise an effect.

The draws must match position-for-position across arms, and the test asserts that
directly rather than trusting the procedure: two rows are comparable only if
their ``ptok`` and ``otok`` are equal.
"""

from __future__ import annotations

import statistics
from itertools import pairwise

import pytest

from tests.sweeprows import RUN, artifact

BEHAVIOUR = "run tools/runs/srv1-kernel-arms.sh"
ARMS_TSV = RUN / "srv1-lcpp-arms.tsv"
MIN_REPLICATES = 5


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no replicated run")
def test_every_cell_was_measured_at_least_five_times() -> None:
    sweep = artifact(ARMS_TSV, BEHAVIOUR)
    counts: dict[tuple[str, str, int], int] = {}
    for row in sweep.levels():
        assert row.n is not None
        key = (row.fields.get("arm", "?"), row.cell, row.n)
        counts[key] = counts.get(key, 0) + 1
    thin = {k: v for k, v in counts.items() if v < MIN_REPLICATES}
    assert counts and not thin, (
        f"cells measured fewer than {MIN_REPLICATES} times: {sorted(thin)[:5]}"
    )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no replicated run")
def test_the_arms_were_interleaved_rather_than_blocked() -> None:
    """Blocked ordering confounds arm with elapsed time, card temperature and
    page-cache warmth. In the 2026-09-01 A/B the bias happened to run against the
    winning arm, so the number stood — but the design offered no protection and
    for the vLLM pair the sign is unknown."""
    sweep = artifact(ARMS_TSV, BEHAVIOUR)
    order = [r.fields.get("arm", "?") for r in sweep.levels()]
    assert order, "no level rows"
    blocks = 1 + sum(1 for a, b in pairwise(order) if a != b)
    assert blocks >= len(set(order)) * MIN_REPLICATES, (
        f"the arms changed {blocks} times over {len(order)} rows — that is "
        "blocked, not interleaved"
    )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no replicated run")
def test_arms_are_only_compared_where_they_drew_the_same_work() -> None:
    sweep = artifact(ARMS_TSV, BEHAVIOUR)
    draws: dict[tuple[str, int, int], set[tuple[float, float]]] = {}
    for row in sweep.levels():
        if "ptok" not in row.fields:
            continue
        assert row.n is not None
        key = (row.cell, row.n, int(row.fields.get("rep", "0")))
        draws.setdefault(key, set()).add(row.draw())
    mismatched = {k: v for k, v in draws.items() if len(v) > 1}
    assert draws and not mismatched, (
        f"{len(mismatched)} (cell, n, replicate) group(s) drew different work "
        f"across arms: {sorted(mismatched)[:3]}. Equal agg across unequal draws "
        "is coincidence — it happened once already, at 74.2 against 74.4."
    )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no A/A null")
def test_the_instrument_was_priced_before_the_effect_was_claimed() -> None:
    """An A/A null: the same arm against itself, same procedure. Without it there
    is no way to say whether 1.7x, 1.15x or 1.02x is signal."""
    sweep = artifact(RUN / "srv1-aa-null.tsv", "run tools/runs/srv1-aa-null.sh")
    by_cell: dict[tuple[str, int], list[float]] = {}
    for row in sweep.levels():
        assert row.n is not None
        by_cell.setdefault((row.cell, row.n), []).append(row.num("agg"))
    assert by_cell, "the null recorded nothing"
    spreads = [
        (max(v) - min(v)) / statistics.median(v)
        for v in by_cell.values()
        if len(v) >= 2
    ]
    assert spreads, "no cell was measured twice, so no spread was priced"
    declared = sweep.stamp("NULL").get("spread_pct")
    assert declared, (
        "the null run declares no spread_pct — the number it exists to produce"
    )
    assert abs(float(declared) - max(spreads) * 100) <= 0.5, (
        f"the file declares {declared}% and its own rows show {max(spreads) * 100:.1f}%"
    )
