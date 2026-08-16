"""What a null costs, per task, per ``(model, tier)`` cell (#289).

``tools/bench/reproducibility.json``'s ``matching`` prose carried the only
price in circulation: *"a null costs about 40 minutes to re-measure."* One
number, every cell. Measured against r1's four nulls it is **2.5x too high for
the cheapest cell and 18% too low for the dearest** — a 3.0x spread — which is
the same defect as the flat ``1.47pp`` bound it sits beside: a constant applied
to cells it was not measured on.

This states the price as a **rate** instead, so it multiplies rather than
transfers::

    minutes = 2 * n * rate / 60

A rate survives what a total cannot. New problems are being authored, so any
figure computed against today's task count expires with the corpus; seconds per
task does not.

**Two axes, not one.** Generation scales with the model and the gate does not:
on ``bench-py`` the gate is 0.20 s/task at *both* models, identical to two
decimals, which is what a linter blind to the model's output size looks like.
On ``bench-ts`` it is 24-48% of the cell. A card keyed only on ``model`` would
mis-price every ``ts`` cell, and a single pooled average hides the term that
actually separates the arms.

**Every figure here is summed task time** — the per-row ``latency_s`` and
``acceptance_s`` the runner recorded. It excludes harness overhead, model load
and the gap between the two runs of a pair, so it is a **lower bound** on rig
occupancy rather than an estimate of it.

The pairs are not named here. They are read from ``reproducibility.json``'s
declared bounds, so the card prices exactly the runs the bounds were measured
on and a second list cannot drift from the first.

    uv run --no-sync python tools/bench/ratecard.py [--json]

Reads run records and dispatches nothing.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
M = ROOT / "records" / "measurements"
REPRODUCIBILITY = ROOT / "tools" / "bench" / "reproducibility.json"
CARD = ROOT / "tools" / "bench" / "rate-card.json"

# `arm` in results.jsonl is the *draw type*, not the language. The language axis
# is `tier` — the run directory's subdirectory and the field in run.json — which
# is what BOUND_MATCH keys on. Naming it `tier` here rather than `arm` keeps the
# card from adding a fourth sense to a word that already carries three (#289).
DRAW = "greedy"


def _rows(run: str, tier: str) -> list[dict[str, Any]]:
    path = M / run / tier / "results.jsonl"
    with path.open() as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return [r for r in rows if r.get("arm") == DRAW]


def _cell(runs: list[str]) -> dict[str, Any]:
    """Sum one pair. ``runs`` entries are ``"<run-dir>/<tier>"`` as declared."""
    generation = gate = 0.0
    counted = 0
    for entry in runs:
        run, _, tier = entry.partition("/")
        for row in _rows(run, tier):
            generation += row.get("latency_s") or 0.0
            gate += row.get("acceptance_s") or 0.0
            counted += 1
    if not counted:
        raise ValueError(f"no {DRAW} rows under {runs} — the pair cannot be priced")
    return {
        "rows": counted,
        "generation_s": round(generation / counted, 4),
        "gate_s": round(gate / counted, 4),
        "total_s": round((generation + gate) / counted, 4),
    }


def derive() -> list[dict[str, Any]]:
    """One priced cell per declared bound, in the order the bounds are declared.

    Keyed off the bounds rather than a list of run directories: a bound that is
    added, retired or re-measured moves the card with it, and a cell nobody
    declared a bound for is a cell nobody can quote a price for either.
    """
    with REPRODUCIBILITY.open() as fh:
        bounds = json.load(fh)["bounds"]
    card = []
    for bound in bounds:
        cell = _cell(bound["runs"])
        card.append(
            {
                "model": bound["model"],
                "tier": bound["tier"],
                "runs": bound["runs"],
                **cell,
            }
        )
    return card


def minutes(rate_s: float, n: int) -> float:
    """A null is a pair, so the dispatched work is 2n tasks at the cell's rate."""
    return 2 * n * rate_s / 60


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="emit the card as JSON")
    parser.add_argument(
        "--n",
        type=int,
        default=257,
        help="tasks per cell to price the illustrative column at",
    )
    args = parser.parse_args()

    card = derive()
    if args.json:
        print(json.dumps(card, indent=2))
        return 0

    print("Seconds are per task per run. A null is a pair: minutes = 2 * n * rate / 60")
    print("Summed task time — a lower bound on rig occupancy, not an estimate.\n")
    print(
        f"{'model':<20} {'tier':<10} {'rows':>5} {'gen s':>7} {'gate s':>7} "
        f"{'total s':>8} {'min @ n=' + str(args.n):>12}"
    )
    for cell in card:
        print(
            f"{cell['model']:<20} {cell['tier']:<10} {cell['rows']:>5} "
            f"{cell['generation_s']:>7.2f} {cell['gate_s']:>7.2f} "
            f"{cell['total_s']:>8.2f} {minutes(cell['total_s'], args.n):>12.1f}"
        )

    if CARD.exists() and json.loads(CARD.read_text(encoding="utf-8"))["cells"] != card:
        print(
            f"\n{CARD.relative_to(ROOT)} disagrees with this derivation — "
            "the record is stale or the runs moved."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
