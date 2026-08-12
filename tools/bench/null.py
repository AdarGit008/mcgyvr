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

from mde import exact_p  # noqa: E402

RUN_A = "bench-null-15b-a-2026-08-12"
RUN_B = "bench-null-15b-b-2026-08-12"
ARMS = ("bench-py", "bench-ts")


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


def compare(arm: str) -> dict[str, Any]:
    a, b = greedy_rows(RUN_A, arm), greedy_rows(RUN_B, arm)
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
    parser.parse_args()

    for arm in ARMS:
        for run in (RUN_A, RUN_B):
            if not (M / run / arm / "results.jsonl").exists():
                print(f"missing: {run}/{arm}/results.jsonl", file=sys.stderr)
                return 2

    print("## Rig health — both runs, before any drift is read\n")
    for arm in ARMS:
        print(f"{arm}:")
        health("run a", greedy_rows(RUN_A, arm))
        health("run b", greedy_rows(RUN_B, arm))

    print("\n## Drift, and what produced it\n")
    pooled: dict[str, list[str]] = collections.defaultdict(list)
    for arm in ARMS:
        r = compare(arm)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
