"""What a null costs, per task, per ``(model, tier)`` cell (#289).

``tools/bench/reproducibility.json``'s ``matching`` prose priced a null at
*"about 40 minutes to re-measure."* One number, every cell. Compared like with
like — against wall clock at n = 257, which is what that constant was a
statement about — it is **2.0x too high for the cheapest cell and 23% too low
for the dearest**, a 2.66x spread. That is the same defect as the flat
``1.47pp`` bound it sat beside: a constant applied to cells it was not measured
on.

(The first draft of this module compared the constant against *summed task
time* instead — 2.5x, 18%, 3.0x. Those numbers are right for a different
quantity than the one the constant named, and the correction is the module's own
point: state which cost a figure is a figure of.)

ADR-0027's own fan-out arithmetic prices bound combinations at "~40 minutes
each" and is amended rather than left standing, because a figure that stays
quotable somewhere else has not been replaced.

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

**The rates are summed task time** — the per-row ``latency_s`` and
``acceptance_s`` the runner recorded. What they miss is model load and harness
startup, and that term is **additive, not proportional**: differencing the
``invocations[0].started`` stamps of consecutive passes in the two r1 sessions
puts it at **1.64-1.72 minutes per pass, mean 1.67**, flat across a 3x spread
in pass duration (8.1 to 24.4 minutes). So::

    wall_minutes_per_null = 2 * (n * rate / 60 + SETUP_MIN)

An additive term behaves the opposite way to the multiplicative one it is easy
to assume: it is ~20% of the cheapest cell at today's n and ~7% of the dearest,
and it dominates any short pass. Pricing a small sweep off the rate alone
understates it.

Measured on 6 of 8 passes — the last pass of each session has no successor to
difference against. Each gap also contains whatever idle sat between passes, so
1.67 is an **upper** bound on setup; that it holds to +/-0.04 across passes
three times apart in length is the argument that it is setup and not idle.

The pairs are not named here. They are read from ``reproducibility.json``'s
declared bounds, so the card prices exactly the runs the bounds were measured
on and a second list cannot drift from the first.

    uv run --no-sync python tools/bench/ratecard.py [--json]

Reads run records and dispatches nothing.
"""

from __future__ import annotations

import argparse
import datetime
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


def _started(run: str, tier: str) -> datetime.datetime:
    """The pass's start stamp, refused if the pass was not a single dispatch.

    ``_cell`` sums every row in ``results.jsonl``. A resumed pass appends a
    second invocation (``tools/breadth/measure.py``), so its full task time
    would be differenced against a stamp from before the interruption and the
    whole gap would land in ``setup_minutes``. All six differenceable r1 passes
    have exactly one invocation, so this refuses rather than corrects — there is
    no resumed pass here to infer the right behaviour from.
    """
    with (M / run / tier / "run.json").open() as fh:
        invocations = json.load(fh)["invocations"]
    if len(invocations) != 1:
        raise ValueError(
            f"{run}/{tier} has {len(invocations)} invocations. Its task time "
            "covers all of them and its start stamp covers only the first, so "
            "differencing it would charge the interruption to setup. Decide "
            "what a resumed pass's wall clock means before pricing it."
        )
    return datetime.datetime.fromisoformat(invocations[0]["started"])


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
                # The bound's own denominator, carried so the illustrative
                # columns price each cell at the size it was measured over
                # rather than at a constant that outlives the corpus.
                "cells": bound["cells"],
                **cell,
            }
        )
    return card


# Model load plus harness startup, measured per pass rather than assumed as a
# percentage — see the module docstring. Additive, so it dominates a short pass
# and vanishes on a long one; a multiplicative factor would get both wrong.
SETUP_MIN = 1.67


def minutes(rate_s: float, n: int, setup: float = SETUP_MIN) -> float:
    """Wall clock for one null: a pair of passes, each with its own setup.

    Pass ``setup=0`` for summed task time alone — what the rates measure
    directly, and what an occupancy figure must not be confused with.
    """
    return 2 * (n * rate_s / 60 + setup)


def overheads() -> list[dict[str, Any]]:
    """Re-derive the setup term from the invocation stamps, never asserting it.

    A pass's wall clock is bounded above by the gap to the next pass's start in
    the same session, so the last pass of each session yields nothing and is
    omitted rather than estimated.

    **The grouping assumes passes sharing a ``measured`` date were dispatched
    back to back.** That holds for r1 — ``reproducibility.json``'s notes say so
    explicitly — but it is an assumption about how the rig was driven, not a
    fact the records carry. If a second, unrelated pair is ever declared on the
    same calendar day, the gap spanning the two sessions would be read as one
    pass's wall clock. The guard below refuses that rather than reporting an
    inflated setup with a plausible shape.
    """
    with REPRODUCIBILITY.open() as fh:
        bounds = json.load(fh)["bounds"]
    # Group the declared runs into sessions by the pair they belong to, in the
    # order they were dispatched: a session is the run directories sharing a
    # measurement date, and passes were dispatched back to back within it.
    passes: dict[str, list[tuple[str, str]]] = {}
    for bound in bounds:
        for entry in bound["runs"]:
            run, _, tier = entry.partition("/")
            passes.setdefault(bound["measured"], []).append((run, tier))

    out = []
    for session, members in passes.items():
        stamped = sorted(
            ((_started(run, tier), run, tier) for run, tier in set(members)),
            key=lambda row: row[0],
        )
        for index, (start, run, tier) in enumerate(stamped[:-1]):
            gap = (stamped[index + 1][0] - start).total_seconds() / 60
            cell = _cell([f"{run}/{tier}"])
            task_time = cell["rows"] * cell["total_s"] / 60
            if not 0 < gap - task_time < task_time:
                raise ValueError(
                    f"{run}/{tier} in session {session!r}: wall {gap:.1f} min "
                    f"against {task_time:.1f} min of task time gives "
                    f"{gap - task_time:.1f} min of setup. A pass cannot start "
                    "before the one ahead of it finishes, and setup larger than "
                    "the work is a session boundary read as a gap, not a "
                    "measurement. Check that these passes ran back to back."
                )
            out.append(
                {
                    "session": session,
                    "run": run,
                    "tier": tier,
                    "task_minutes": round(task_time, 2),
                    "wall_minutes": round(gap, 2),
                    "setup_minutes": round(gap - task_time, 2),
                }
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="emit the card as JSON")
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help=(
            "tasks per cell to price the illustrative columns at. Defaults to "
            "each bound's own declared `cells` — a hard-coded default would "
            "keep pricing today's corpus after the corpus grew, which is the "
            "thing this card exists not to do"
        ),
    )
    args = parser.parse_args()

    card = derive()
    if args.json:
        print(json.dumps(card, indent=2))
        return 0

    print("Seconds are per task per run. A null is a pair of passes:")
    print(f"  wall minutes = 2 * (n * rate / 60 + {SETUP_MIN})   [setup is additive]\n")
    print(
        f"{'model':<20} {'tier':<10} {'rows':>5} {'gen s':>7} {'gate s':>7} "
        f"{'total s':>8} {'n':>5} {'task':>7} {'wall':>7}"
    )
    for cell in card:
        n = args.n if args.n is not None else cell["cells"]
        print(
            f"{cell['model']:<20} {cell['tier']:<10} {cell['rows']:>5} "
            f"{cell['generation_s']:>7.2f} {cell['gate_s']:>7.2f} "
            f"{cell['total_s']:>8.2f} {n:>5} "
            f"{minutes(cell['total_s'], n, setup=0):>7.1f} "
            f"{minutes(cell['total_s'], n):>7.1f}"
        )

    print("\nsetup, re-derived from consecutive invocation stamps:")
    for row in overheads():
        print(
            f"  {row['run']:<38} {row['tier']:<9} "
            f"task {row['task_minutes']:>6.2f}   wall {row['wall_minutes']:>6.2f}   "
            f"setup {row['setup_minutes']:>5.2f}"
        )

    return 0 if not CARD.exists() else _check_record(card)


def stale(record: dict[str, Any], card: list[dict[str, Any]]) -> list[str]:
    """Every derived value the record commits, checked — not just the cells.

    Checking one of three was its own version of the defect this card corrects:
    ``setup_minutes`` could drift from ``SETUP_MIN`` and ``overheads`` from the
    stamps while the guard reported agreement, leaving the record and the
    formula stating two different constants.
    """
    drifted = []
    if record.get("cells") != card:
        drifted.append("cells")
    if record.get("setup_minutes") != SETUP_MIN:
        drifted.append(
            f"setup_minutes ({record.get('setup_minutes')} vs SETUP_MIN {SETUP_MIN})"
        )
    if record.get("overheads") != overheads():
        drifted.append("overheads")
    return drifted


def _check_record(card: list[dict[str, Any]]) -> int:
    drifted = stale(json.loads(CARD.read_text(encoding="utf-8")), card)
    if drifted:
        print(
            f"\n{CARD.relative_to(ROOT)} disagrees with this derivation on "
            f"{', '.join(drifted)} — the record is stale or the runs moved."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
