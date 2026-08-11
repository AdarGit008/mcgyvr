#!/usr/bin/env python3
"""#225 — is `f1` an instrument, or is it merely in band?

A band's pass rate is a statement about **level**. ADR-0019 measured what that
does and does not tell you, and the answer was severe: the bundle's Python arm A
sat at 65-70%, dead centre of any band one would declare, with **one task in
twenty responsive**. Nineteen were pinned under every condition the matrix ran.
Its conclusion is the reason this tool exists — *"being in band is not the same
as having resolution, and level cannot reveal the difference."*

`f1` reads 38.9% greedy on the floor unit and no rule in its brief fires. This
reads the other axis: of the cells the band is made of, how many can move at
all? A cell that fails every draw is concordant under any lever, contributes no
discordant mass, and under ADR-0019's ``m >= 6`` wall is worth less toward the
bench's 400 than its nominal count.

**What is measured, and what is inferred.** The observable is variation across
draws — one greedy draw plus N sampled at a fixed temperature, the same
replication ADR-0019 D6 licenses as a substitute for material. A cell that
varies is demonstrably reachable by this model, so a lever that shifts its odds
has something to shift. The converse is weaker: a cell pinned across every draw
could still be unpinned by a lever that supplies information the model lacks.
So ``psi_draw`` is **not** ``psi`` and is not a bound in either direction. It is
the cheapest available screen for dead cells, and it costs rig time rather than
authoring. The per-lever ``psi`` stays #231's to measure.

Pre-registration, fixed before the draws existed:
``records/sessions/lane/225/2026-08-11-f1-responsiveness-prereg.md``.

    uv run python tools/bench/responsiveness.py --run <dir> --baseline <dir>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tools"))

from power.mde import detectable_delta  # noqa: E402

# Problems withdrawn after they were measured. Their rows stay in the run
# records, which are evidence of what ran on the day; they are dropped here,
# where a figure is derived. Same rule and same file as ablation_report.py.
RETIRED = HERE / "retired.json"

ARMS = ("ts", "py")

# `f1` runs b228 upward in tranches of forty, numbered from four because
# tranches one to three were the bands this one replaced. Derived from the id
# rather than stored, so a problem cannot be filed under a tranche it was not
# authored in.
FIRST_ID = 228
FIRST_TRANCHE = 4
TRANCHE_SIZE = 40

# The pre-registered comparison: the tranche the earlier look named, against
# the pool of those that preceded it. Named here rather than passed in, so the
# figure cannot be produced for a different split once the numbers are visible.
FOCUS_TRANCHE = 8
REFERENCE_TRANCHES = (4, 5, 6, 7)

# From the pre-registration, anchored in ADR-0019's measured psi range (0.05 at
# arm A, 0.45 at arm B, with 0.10-0.35 the planning prior D5's table spans).
PSI_HEALTHY = 0.20
PSI_WEAK = 0.10

# Greedy re-runs at this model size drifted zero tasks across eight repeats
# (ADR-0019's determinism table). Two cells is slack, not a tolerance.
DRIFT_ALLOWANCE = 2


def retired_ids() -> frozenset[str]:
    """Ids withdrawn after admission, whose rows no figure may count."""
    if not RETIRED.is_file():
        return frozenset()
    doc = json.loads(RETIRED.read_text(encoding="utf-8"))
    return frozenset(str(entry["id"]) for entry in doc["ids"])


def tranche(task: str) -> int:
    """The authoring tranche an `f1` id belongs to."""
    return FIRST_TRANCHE + (int(re.match(r"b(\d+)", task).group(1)) - FIRST_ID) // TRANCHE_SIZE


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Every recorded row, minus the draws nobody saw."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("dispatch_error"):
            continue  # a draw nobody saw is not a draw (#217)
        out.append(row)
    return out


def cells(run: Path, draws: int) -> dict[tuple[str, str], dict[str, Any]]:
    """Per (arm, task): the greedy verdict and the sampled verdict list.

    A cell missing any of its draws is dropped and named by the caller rather
    than silently completed. "No pass in N" has to mean N draws were looked at,
    or the pinned-fail count is an artefact of a short run.
    """
    withdrawn = retired_ids()
    built: dict[tuple[str, str], dict[str, Any]] = {}
    for arm in ARMS:
        rows = read_rows(run / f"bench-{arm}" / "results.jsonl")
        greedy: dict[str, bool] = {}
        sampled: dict[str, dict[int, bool]] = defaultdict(dict)
        for row in rows:
            task = row["task"]
            if task in withdrawn:
                continue  # withdrawn after the run; tools/bench/retired.json
            if row["arm"] == "greedy":
                greedy[task] = bool(row.get("passed"))
            else:
                sampled[task][int(row["draw"])] = bool(row.get("passed"))
        for task, g in greedy.items():
            seen = sampled.get(task, {})
            if set(seen) != set(range(draws)):
                continue
            built[(arm, task)] = {
                "greedy": g,
                "sampled": [seen[i] for i in range(draws)],
            }
    return built


def classify(cell: dict[str, Any]) -> str:
    """pinned-fail, pinned-pass, or responsive, over greedy plus the sampled draws.

    The greedy draw is counted. Responsiveness in ADR-0019's sense is variation
    across the matrix a task was dispatched under, and the greedy condition is
    part of this one's matrix.
    """
    verdicts = [cell["greedy"], *cell["sampled"]]
    if not any(verdicts):
        return "pinned-fail"
    if all(verdicts):
        return "pinned-pass"
    return "responsive"


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for the 2x2 table [[a, b], [c, d]].

    Exact rather than a z approximation because the cell counts here are in the
    tens, which is where a normal approximation starts writing cheques the
    sample cannot cash. Two-sided by summing every table at or below the
    observed probability, which is the convention the sign test above it uses.
    """
    n = a + b + c + d
    row1, col1 = a + b, a + c
    total = comb(n, col1)

    def prob(x: int) -> float:
        return comb(row1, x) * comb(n - row1, col1 - x) / total

    observed = prob(a)
    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)
    # 1e-9 relative slack: equally extreme tables differing only in float dust
    # must land on the same side of the comparison.
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= observed * (1 + 1e-9)))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — the campaign's standard, valid near 0 and 1."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def baseline_greedy(run: Path) -> dict[tuple[str, str], bool]:
    """The greedy verdicts of an earlier run, for the validity gate."""
    withdrawn = retired_ids()
    out: dict[tuple[str, str], bool] = {}
    for arm in ARMS:
        for row in read_rows(run / f"bench-{arm}" / "results.jsonl"):
            if row["arm"] != "greedy" or row["task"] in withdrawn:
                continue
            out[(arm, row["task"])] = bool(row.get("passed"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", type=Path, required=True, help="the replicated run")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="an earlier greedy run this one's draw 0 must reproduce; the "
        "validity gate refuses to read a run that fails it",
    )
    parser.add_argument("--draws", type=int, default=8, help="sampled draws per cell")
    parser.add_argument("--json", type=Path, help="write the figures here too")
    args = parser.parse_args()

    built = cells(args.run, args.draws)
    if not built:
        print("no complete cells", file=sys.stderr)
        return 2

    print(f"# f1 responsiveness — {args.run.name}")
    print(f"# cells complete at {args.draws} sampled draws + greedy: {len(built)}")

    report: dict[str, Any] = {"run": args.run.name, "cells": len(built)}

    # --- validity gate -----------------------------------------------------
    if args.baseline:
        base = baseline_greedy(args.baseline)
        shared = sorted(set(base) & set(built))
        drift = [k for k in shared if base[k] != built[k]["greedy"]]
        base_pass = sum(base[k] for k in shared)
        now_pass = sum(built[k]["greedy"] for k in shared)
        print(f"# validity gate vs {args.baseline.name}:")
        print(f"#   shared cells {len(shared)}, greedy {base_pass} -> {now_pass}, drift {len(drift)}")
        report["validity"] = {
            "baseline": args.baseline.name,
            "shared": len(shared),
            "baseline_passes": base_pass,
            "run_passes": now_pass,
            "drift_cells": sorted(f"{a}/{t}" for a, t in drift),
        }
        if len(drift) > DRIFT_ALLOWANCE:
            print(
                f"# VOID — {len(drift)} cells drifted, allowance {DRIFT_ALLOWANCE}. "
                "This is rig or build drift, not noise; nothing below is read.",
            )
            report["void"] = True
            if args.json:
                args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            return 1
        if drift:
            print(f"#   drifted (within allowance): {', '.join(f'{a}/{t}' for a, t in drift)}")

    # --- primary: psi_draw -------------------------------------------------
    kinds = {k: classify(v) for k, v in built.items()}
    tally = defaultdict(int)
    for kind in kinds.values():
        tally[kind] += 1
    n = len(built)
    responsive = tally["responsive"]
    psi_draw = responsive / n
    lo, hi = wilson(responsive, n)

    print()
    print("## responsiveness — cells that ever change verdict across the draws")
    print()
    print(f"{'cells':>8}  {'pinned-fail':>12}  {'pinned-pass':>12}  {'responsive':>12}")
    print(
        f"{n:>8}  {tally['pinned-fail']:>12}  {tally['pinned-pass']:>12}  "
        f"{responsive:>12} ({100 * psi_draw:.1f}%)"
    )
    print()
    print(f"psi_draw = {psi_draw:.3f}, 95% Wilson {lo:.3f}-{hi:.3f}")
    verdict = (
        "at or above the planning prior's middle; sizing holds"
        if psi_draw >= PSI_HEALTHY
        else "the prior's pessimistic end; sizing holds at the weak end"
        if psi_draw >= PSI_WEAK
        else "arm A territory; the 400 will not buy what D5 priced"
    )
    print(f"pre-registered reading: {verdict}")
    report["psi_draw"] = {
        "responsive": responsive,
        "pinned_fail": tally["pinned-fail"],
        "pinned_pass": tally["pinned-pass"],
        "n": n,
        "value": psi_draw,
        "wilson": [lo, hi],
        "reading": verdict,
    }

    # --- what that buys, at both readings of D5's denominator --------------
    # ADR-0021 was written because D5 stated 400 without stating its
    # denominator. The same ambiguity survives one level down: `f1` counts
    # problems, the sweep dispatches cells, and a problem carries two arms. Both
    # are reported rather than resolved here, because resolving it silently is
    # the error ADR-0021 already had to correct once.
    print()
    print("## what psi_draw would buy, if a lever moved exactly the reachable cells")
    print("#  optimistic by construction — see the module docstring")
    print()
    print(f"{'n':>8}  {'unit':<10}  {'MDE':>8}")
    for size, unit in ((n, "cells today"), (400, "problems"), (800, "cells at 400")):
        mde = detectable_delta(size, psi_draw)
        print(f"{size:>8}  {unit:<10}  {('%.1fpp' % (100 * mde)) if mde else 'none':>8}")
    report["mde"] = {
        str(size): detectable_delta(size, psi_draw) for size in (n, 400, 800)
    }

    # --- secondary: per tranche -------------------------------------------
    per: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (arm, task), kind in kinds.items():
        t = tranche(task)
        per[t][kind] += 1
        per[t]["n"] += 1
        per[t]["greedy"] += built[(arm, task)]["greedy"]

    print()
    print("## per tranche — all six reported, not only the one named in advance")
    print()
    print(f"{'tranche':>8}  {'cells':>6}  {'greedy':>8}  {'pinned-fail':>12}  {'responsive':>12}")
    for t in sorted(per):
        row = per[t]
        print(
            f"{('t%d' % t):>8}  {row['n']:>6}  "
            f"{('%.1f%%' % (100 * row['greedy'] / row['n'])):>8}  "
            f"{('%d (%.1f%%)' % (row['pinned-fail'], 100 * row['pinned-fail'] / row['n'])):>12}  "
            f"{('%d (%.1f%%)' % (row['responsive'], 100 * row['responsive'] / row['n'])):>12}"
        )
    report["tranches"] = {
        str(t): {k: v for k, v in row.items()} for t, row in sorted(per.items())
    }

    # --- the pre-registered test -------------------------------------------
    focus = per[FOCUS_TRANCHE]
    ref_fail = sum(per[t]["pinned-fail"] for t in REFERENCE_TRANCHES)
    ref_n = sum(per[t]["n"] for t in REFERENCE_TRANCHES)
    p = fisher_two_sided(
        focus["pinned-fail"],
        focus["n"] - focus["pinned-fail"],
        ref_fail,
        ref_n - ref_fail,
    )
    print()
    print(f"## pre-registered: t{FOCUS_TRANCHE} vs t{'/'.join(str(t) for t in REFERENCE_TRANCHES)} pooled, pinned-fail")
    print()
    print(
        f"  t{FOCUS_TRANCHE}: {focus['pinned-fail']}/{focus['n']} "
        f"({100 * focus['pinned-fail'] / focus['n']:.1f}%)"
    )
    print(f"  pooled: {ref_fail}/{ref_n} ({100 * ref_fail / ref_n:.1f}%)")
    print(f"  Fisher exact, two-sided: p = {p:.3f}")
    print(
        "  reading: "
        + (
            "materially above — the thinning is manufacturing dead cells"
            if p < 0.05 and focus["pinned-fail"] / focus["n"] > ref_fail / ref_n
            else "not materially above — the problems are reachable, merely harder"
        )
    )
    print()
    print(
        f"# t{FOCUS_TRANCHE} was named by a post-hoc look at six tranches. This tests a "
        "different quantity on draws that did not exist when it was named, so the "
        "prediction is out of sample; it is not evidence that t8 is unusual among "
        "tranches. Every other tranche in the table above is observational and "
        "carries no p-value."
    )
    report["prereg_test"] = {
        "focus": FOCUS_TRANCHE,
        "focus_pinned_fail": focus["pinned-fail"],
        "focus_n": focus["n"],
        "reference_pinned_fail": ref_fail,
        "reference_n": ref_n,
        "p": p,
    }

    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
