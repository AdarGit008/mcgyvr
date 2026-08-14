"""The bench's null drift, and the mechanism underneath it (#231 check 1).

``tools/power/report.py --section null`` prints the number ADR-0019's D2 asks
for: ``d``, the count of verdicts that differ between two identical greedy runs.
This script asks *why* it is what it is, because a null of the same size can
come from two very different instruments:

**Sampler drift.** The backend returns different text for the same prompt at
temperature 0 — batching, kv-cache reuse and floating-point non-associativity
all do this — and some of that different text lands on the other side of the
acceptance boundary. This is the expected mechanism, it is a property of the
serving stack, and ADR-0024 is why the build is pinned.

**Acceptance drift.** The *same bytes* score differently on two runs. That is
not model noise at all; it is the harness being nondeterministic — a timeout, an
ordering, a hash seed — and it would put a floor under every contrast the bench
ever runs that no amount of extra tasks could lower. The two are separated here
because the headline ``d`` cannot tell them apart, and only one of them is
survivable.

    uv run --no-sync python tools/bench/null.py

Reads the two run directories named below and dispatches nothing.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
M = ROOT / "records" / "measurements"

sys.path.insert(0, str(ROOT / "tools" / "power"))
sys.path.insert(0, str(ROOT / "tools" / "bench"))

# #231 checks 3 and 6: every figure says which tier it describes and which
# product revision produced it, read off the manifests rather than asserted.
import mode  # noqa: E402
import product  # noqa: E402
from mde import exact_p  # noqa: E402

# One Wilson implementation for the campaign, not a second copy of the formula.
from responsiveness import wilson  # noqa: E402

# The pair this reads by default. It is the **gate-scored** null: #113 moved
# scoring from the contract's acceptance command to `Gate.run`, which is a
# different bar and therefore a different null. The 2026-08-12 pair below it was
# measured under the old grader and its figure cannot be recomputed into this
# one — `Gate.run` short-circuits, so a lint-rejected candidate never ran its
# test. It is kept named, not deleted: a superseded measurement that vanishes
# reads as one that was never taken.
RUN_A = "bench-null-gate-15b-a-2026-08-13"
RUN_B = "bench-null-gate-15b-b-2026-08-13"
SUPERSEDED = ("bench-null-15b-a-2026-08-12", "bench-null-15b-b-2026-08-12")
ARMS = ("bench-py", "bench-ts")

# ADR-0019's adoption bar, and #231 check 1's stop condition: if the bench's own
# drift reaches the smallest effect anyone would adopt on, an arm result cannot
# be told from the instrument.
STOP_CONDITION_PP = 3.0


def greedy_rows(run: str, arm: str) -> dict[str, dict[str, Any]]:
    path = M / run / arm / "results.jsonl"
    with path.open() as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return {r["task"]: r for r in rows if r.get("arm") == "greedy"}


def health(label: str, rows: dict[str, dict[str, Any]]) -> None:
    stop = collections.Counter(r.get("stop_reason") for r in rows.values())
    refused = sum(1 for r in rows.values() if r.get("parse_error"))
    lost = sum(1 for r in rows.values() if r.get("dispatch_error"))
    print(
        f"  {label:<10} {len(rows):>4} cells   "
        f"truncated {stop.get('truncated', 0):>3}   "
        f"parse-refused {refused:>3}   dispatch-lost {lost:>3}"
    )


def compare(arm: str, run_a: str = RUN_A, run_b: str = RUN_B) -> dict[str, Any]:
    a, b = greedy_rows(run_a, arm), greedy_rows(run_b, arm)
    shared = sorted(set(a) & set(b))
    same_bytes = [
        t for t in shared if a[t]["candidate_sha256"] == b[t]["candidate_sha256"]
    ]
    diff_bytes = [t for t in shared if t not in set(same_bytes)]
    flips = [t for t in shared if bool(a[t]["passed"]) != bool(b[t]["passed"])]
    # b gains: failed in A, passed in B. c losses: the other way.
    gains = [t for t in flips if not a[t]["passed"]]
    losses = [t for t in flips if a[t]["passed"]]
    return {
        "arm": arm,
        "a": a,
        "b": b,
        "shared": shared,
        "same_bytes": same_bytes,
        "diff_bytes": diff_bytes,
        "flips": flips,
        "gains": gains,
        "losses": losses,
        # The separation this script exists for.
        "acceptance_flips": [t for t in flips if t in set(same_bytes)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-a", default=RUN_A, help="first run directory name")
    parser.add_argument("--run-b", default=RUN_B, help="second run directory name")
    args = parser.parse_args()
    run_a, run_b = args.run_a, args.run_b

    for arm in ARMS:
        for run in (run_a, run_b):
            if not (M / run / arm / "results.jsonl").exists():
                print(f"missing: {run}/{arm}/results.jsonl", file=sys.stderr)
                return 2

    # The bar is read from the runs, never inferred from their names. The first
    # version of this keyed a dict on the *arguments*, so the first entry always
    # matched and every pair — including the superseded acceptance-only one —
    # was labelled "Gate.run". A tool whose whole claim is that a rate is never
    # quoted against an unstated bar stated the bar from the filename.
    bars = {}
    for run in (run_a, run_b):
        rungs = tuple(
            json.loads((M / run / arm / "run.json").read_text()).get("gate_rungs") or ()
            for arm in ARMS
        )
        bars[run] = rungs

    def named(rungs: tuple[Any, ...]) -> str:
        first = rungs[0] if rungs else ()
        return (
            "the acceptance command alone"
            if not first
            else "Gate.run [" + ", ".join(first) + "]"
        )

    if bars[run_a] != bars[run_b]:
        print(
            f"error: these two runs were scored by different bars — "
            f"{run_a} by {named(bars[run_a])}, {run_b} by {named(bars[run_b])}. "
            "Their disagreement is the scorer, not the model's drift, and a "
            "null read across that boundary reports the grader as instrument "
            "noise.",
            file=sys.stderr,
        )
        return 2
    bar = named(bars[run_a])
    read = mode.read(*[f"{run}/{arm}" for run in (run_a, run_b) for arm in ARMS])
    print(f"# Null calibration — {run_a} vs {run_b}\n")
    print(f"- scored by: {bar}")
    print(mode.banner(read))
    print(product.banner(read))
    print()

    print("## Rig health — both runs, before any drift is read\n")
    for arm in ARMS:
        print(f"{arm}:")
        health("run a", greedy_rows(run_a, arm))
        health("run b", greedy_rows(run_b, arm))

    print("\n## Drift, and what produced it\n")
    pooled: dict[str, list[str]] = collections.defaultdict(list)
    for arm in ARMS:
        r = compare(arm, run_a, run_b)
        n = len(r["shared"])
        for key in (
            "shared",
            "same_bytes",
            "diff_bytes",
            "flips",
            "gains",
            "losses",
            "acceptance_flips",
        ):
            pooled[key].extend(f"{arm}/{t}" for t in r[key])
        pa = sum(1 for t in r["shared"] if r["a"][t]["passed"])
        pb = sum(1 for t in r["shared"] if r["b"][t]["passed"])
        net = abs(pa - pb) / n * 100
        print(f"{r['arm']}  n = {n}")
        print(f"  pass          {pa}/{n} vs {pb}/{n}   net {net:.2f}pp")
        print(
            f"  d (flips)     {len(r['flips'])}  = {len(r['flips']) / n * 100:.2f}pp"
            f"   ({len(r['gains'])} gained, {len(r['losses'])} lost,"
            f" exact p = {exact_p(len(r['gains']), len(r['losses'])):.3f})"
        )
        print(
            f"  byte-identical {len(r['same_bytes'])}/{n}"
            f" = {len(r['same_bytes']) / n * 100:.1f}%"
        )
        if r["diff_bytes"]:
            rate = len(set(r["flips"]) & set(r["diff_bytes"])) / len(r["diff_bytes"])
            print(
                f"  of the {len(r['diff_bytes'])} cells whose text differed,"
                f" {len(set(r['flips']) & set(r['diff_bytes']))} flipped"
                f" ({rate * 100:.1f}%)"
            )
        # The number check 4 declares, printed where it is measured. The bound
        # is per arm (ADR-0019 D2 keys it to one tier), and this tool used to
        # print only the pooled interval — so the two entries actually written
        # into `reproducibility.json` were computed by hand off-screen. The
        # upper limit, never `d/n`: a bound of 0.00pp would claim the instrument
        # is exact, which 257 cells cannot establish.
        low, high = wilson(len(r["flips"]), n)
        print(
            f"  declarable bound {high * 100:.2f}pp"
            f"   (95% Wilson upper on {len(r['flips'])}/{n}, interval"
            f" [{low * 100:.2f}, {high * 100:.2f}] pp)"
        )
        print(
            f"  acceptance drift {len(r['acceptance_flips'])}"
            "  (identical bytes, different verdict)"
        )
        for t in r["acceptance_flips"]:
            print(f"      {t}: a={r['a'][t]['passed']} b={r['b'][t]['passed']}")
        print()

    n = len(pooled["shared"])
    d = len(pooled["flips"])
    print("both arms pooled")
    print(f"  n = {n} paired cells")
    print(
        f"  d = {d} = {d / n * 100:.2f}pp"
        f"   ({len(pooled['gains'])} gained, {len(pooled['losses'])} lost,"
        f" exact p = {exact_p(len(pooled['gains']), len(pooled['losses'])):.3f})"
    )
    print(
        f"  byte-identical {len(pooled['same_bytes'])}/{n}"
        f" = {len(pooled['same_bytes']) / n * 100:.1f}%"
    )
    print(f"  acceptance drift {len(pooled['acceptance_flips'])}")

    # #231 check 1's stop condition, evaluated here rather than in prose, so the
    # verdict cannot drift from the number it is a verdict about.
    drift_pp = d / n * 100
    lo, hi = (b * 100 for b in wilson(d, n))
    print("\n## The stop condition, evaluated\n")
    print(f"  d/n          {d}/{n} = {drift_pp:.2f}pp, 95% CI [{lo:.2f}, {hi:.2f}] pp")
    print(f"  bar          {STOP_CONDITION_PP:.1f}pp (ADR-0019's adoption bar)")
    ok = True
    if drift_pp >= STOP_CONDITION_PP:
        print(
            "  VERDICT      **STOP** — the bench's own drift reaches the "
            "smallest effect anyone would adopt on, so no arm result can be "
            "told from the instrument. Fix the instrument before any arm."
        )
        ok = False
    elif d == 0:
        # No "3000000000x": a zero point estimate is not an infinitely quiet
        # instrument, it is 514 cells that happened not to move. The interval is
        # what bounds the drift, and it is what the report should declare.
        print(
            "  VERDICT      the stop condition does NOT fire — no cell moved. "
            f"The drift is bounded by the interval, not by the zero: {hi:.2f}pp "
            "at 95%, which is what a declared bound must carry."
        )
    else:
        print(
            f"  VERDICT      the stop condition does NOT fire — d clears the "
            f"bar by {STOP_CONDITION_PP / drift_pp:.0f}x."
        )
    if pooled["acceptance_flips"]:
        print(
            "\n  Acceptance drift is NOT zero — identical bytes scored "
            "differently. That is the harness rather than the model, and it "
            "puts a floor under every contrast that no number of tasks lowers."
        )
        ok = False
    else:
        print(
            "  Acceptance drift is zero — no cell scored differently on "
            "identical bytes, which is the failure that would be unfixable."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
