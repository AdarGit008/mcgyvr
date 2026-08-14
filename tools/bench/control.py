#!/usr/bin/env python3
"""#231 check 2 — the rule-ablation positive control, read to its pre-registration.

The pre-registration is
``records/sessions/lane/231/2026-08-13-positive-control-prereg.md``, declared
before a single ``norule`` draw. Everything decided there is applied here rather
than restated: the comparator is run **A** (run B is a sensitivity check, not an
alternative), recovery requires **direction and the mechanism's signature**, and
``m >= 6`` or no p-value is quoted.

**Why the rung counts are recomputed rather than read off ``rejected_by``.**
``Gate.run`` short-circuits, so ``rejected_by`` is the first rung that fired —
an ordering artefact. Comparing two conditions on it would show rungs trading
places whenever a candidate fails several, which is exactly what an ablation
does. ``fail_output`` carries every finding, so the rung *sets* below are the
real profile.

    uv run --no-sync python tools/bench/control.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import statistics
import sys
import types
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
M = ROOT / "records" / "measurements"

sys.path.insert(0, str(ROOT / "tools" / "power"))

from mde import MIN_DISCORDANT, exact_p  # noqa: E402

# #231 checks 3 and 6: the tier the figure describes, and the revision it ran
# against, read off the manifests rather than stated in prose beside them.
sys.path.insert(0, str(ROOT / "tools" / "bench"))
import mode  # noqa: E402
import product  # noqa: E402


def _by_path(name: str, path: pathlib.Path) -> types.ModuleType:
    """`tools/` is not a package, and two files here are called `report.py`."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


report = _by_path("bench_report_control", ROOT / "tools" / "bench" / "report.py")

# The pre-registration's runs, which are the 1.5B's. They are **defaults**
# rather than constants: #231 check 5 re-runs this same battery against a second
# tier with no design change, and a tool that can only be pointed at one model
# would have forced a copy — at which point "no design change" stops being
# checkable. What the pre-registration fixes is the *design* (comparator is run
# A, run B is a sensitivity check, recovery is direction plus an identified
# mechanism, m >= 6 or no p-value), and none of that moves with --stock.
# Named `*_RUN` because `STOCK` is already a *condition* name in
# `tools/breadth/measure.py` — one word for the render the matrix dispatches and
# for the directory a render was measured into. ADR-0026 lens 3: two meanings
# under one name is a collision a reader resolves by guessing.
STOCK_RUN = "bench-null-gate-15b-a-2026-08-13"
SENSITIVITY_RUN = "bench-null-gate-15b-b-2026-08-13"
NORULE_RUN = "bench-control-norule-15b-2026-08-13"
ARMS = ("bench-py", "bench-ts")

# CLM-0017, quoted as context and explicitly not as a target: different
# material, a different harness and a different model.
HISTORIC = {"pass": (7, 11, 20), "completion": (427.4, 121.5)}


def rows(run: str, arm: str) -> dict[str, dict[str, Any]]:
    path = M / run / arm / "results.jsonl"
    with path.open() as fh:
        every = [json.loads(line) for line in fh if line.strip()]
    return {r["task"]: r for r in every if r.get("arm") == "greedy"}


# The finding labels the gate emits. Fixed rather than discovered, because a
# finding's *message* routinely contains both "; " and ": " — acceptance findings
# carry whole Python tracebacks — so splitting on punctuation invents rungs out
# of stack frames. `check_vocabulary` below proves this list covers the data.
LABELS = (
    "acceptance",
    "adapters",
    "format",
    "lint",
    "scope",
    "secrets",
    "structure",
    "structured",
    "syntax",
)
_FINDING = re.compile(r"(?:\A|; )(" + "|".join(LABELS) + r"): ")

# The labels the adapters rung emits. It runs before acceptance and always runs,
# so a change in this set is a clean comparison; a change in `acceptance` is not.
ADAPTER_LABELS = {"format", "lint", "structure", "syntax"}


def rungs_of(row: dict[str, Any]) -> set[str]:
    """Every rung that reported a finding, not just the one that got there first.

    A finding begins at the start of ``fail_output`` or after a "; " separator,
    which is what distinguishes a real label from the same word appearing inside
    a traceback the acceptance rung captured.
    """
    return set(_FINDING.findall(row.get("fail_output") or ""))


def check_vocabulary(*runs: dict[str, Any]) -> list[str]:
    """Every row's own ``rejected_by`` must appear in the set parsed from its text.

    The counts below are only worth reading if the parse agrees with the field
    the runner wrote independently. A mismatch means LABELS is short a rung and
    the profile is under-reported — silently, and in the direction that makes an
    ablation look tidier than it is.
    """
    bad = []
    for run_rows in runs:
        for task, row in run_rows.items():
            rung = row.get("rejected_by")
            if rung and rung not in rungs_of(row):
                bad.append(f"{task}: rejected_by={rung!r} not parsed from fail_output")
    return bad


def paired(stock: dict[str, Any], norule: dict[str, Any]) -> dict[str, Any]:
    shared = sorted(set(stock) & set(norule))
    # gains: the ablation helped. losses: the rule was carrying the cell.
    gains = [t for t in shared if not stock[t]["passed"] and norule[t]["passed"]]
    losses = [t for t in shared if stock[t]["passed"] and not norule[t]["passed"]]
    return {
        "shared": shared,
        "gains": gains,
        "losses": losses,
        "m": len(gains) + len(losses),
        "p": exact_p(len(gains), len(losses)),
        "stock_pass": sum(1 for t in shared if stock[t]["passed"]),
        "norule_pass": sum(1 for t in shared if norule[t]["passed"]),
    }


def tokens(run_rows: dict[str, Any], only: list[str] | None = None) -> dict[str, float]:
    keys = only if only is not None else list(run_rows)
    vals = [
        run_rows[t]["completion_tokens"]
        for t in keys
        if isinstance(run_rows[t].get("completion_tokens"), (int, float))
    ]
    if not vals:
        return {"mean": 0.0, "median": 0.0, "n": 0}
    return {
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "n": len(vals),
    }


def health(label: str, run_rows: dict[str, Any]) -> None:
    refused = sum(1 for r in run_rows.values() if r.get("parse_error"))
    truncated = sum(1 for r in run_rows.values() if r.get("stop_reason") == "truncated")
    lost = sum(1 for r in run_rows.values() if r.get("dispatch_error"))
    print(
        f"  {label:<28} {len(run_rows):>4} cells   parse-refused {refused:>3}   "
        f"truncated {truncated:>3}   dispatch-lost {lost:>3}"
    )


def declared_bound(run: str, arm: str) -> tuple[float | None, str]:
    """The reproducibility bound for the run being read, or why there is none.

    Looked up per (model, tier, gate_rungs, serving_build) from
    ``tools/bench/reproducibility.json`` rather than carried as a constant. This
    file held ``BOUND_PP = 1.47`` — the 1.5B's number — and reading a second
    tier's contrast against it is exactly the borrowing ADR-0019 D2 forbids: a
    higher-pass-rate model has more cells near the boundary and therefore its
    own null. A tier with no null declared gets no "INSIDE the bound" annotation
    at all, which is the honest output; a delta smaller than an undeclared drift
    is an unknown effect, not a small one.
    """
    manifest = json.loads((M / run / arm / "run.json").read_text(encoding="utf-8"))
    entry, because = report.declared_bound(manifest, report.load_bounds())
    return (entry["bound_pp"] if entry else None), because


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--stock", default=STOCK_RUN, help="the comparator run (run A)")
    parser.add_argument(
        "--norule",
        default=NORULE_RUN,
        help="the rule-ablation run to compare against it",
    )
    parser.add_argument(
        "--sensitivity",
        default=SENSITIVITY_RUN,
        help="the second stock run, read as a sensitivity check and never as an "
        "alternative comparator",
    )
    args = parser.parse_args()
    stock_run, norule_run = args.stock, args.norule
    sensitivity_run = args.sensitivity

    for run in (stock_run, sensitivity_run, norule_run):
        for arm in ARMS:
            if not (M / run / arm / "results.jsonl").exists():
                print(f"missing: {run}/{arm}/results.jsonl", file=sys.stderr)
                return 2

    read = mode.read(
        *[
            f"{run}/{arm}"
            for run in (stock_run, sensitivity_run, norule_run)
            for arm in ARMS
        ]
    )
    print("# Check 2 — the rule-ablation positive control\n")
    print(f"comparator: {stock_run} (pre-registered as run A)")
    print(f"ablation:   {norule_run}")
    print(f"sensitivity: {sensitivity_run}")
    print(mode.banner(read))
    print(product.banner(read))
    print()

    print("## Rig health, before anything is read\n")
    for arm in ARMS:
        print(f"{arm}:")
        health("stock (comparator)", rows(stock_run, arm))
        health("norule", rows(norule_run, arm))
    print()

    print("## Direction — the paired contrast\n")
    pooled = {"gains": 0, "losses": 0, "n": 0, "stock": 0, "norule": 0}
    for arm in ARMS:
        s, nr = rows(stock_run, arm), rows(norule_run, arm)
        r = paired(s, nr)
        n = len(r["shared"])
        delta = (r["norule_pass"] - r["stock_pass"]) / n * 100
        pooled["gains"] += len(r["gains"])
        pooled["losses"] += len(r["losses"])
        pooled["n"] += n
        pooled["stock"] += r["stock_pass"]
        pooled["norule"] += r["norule_pass"]
        bound_pp, no_bound_because = declared_bound(stock_run, arm)
        inside = bound_pp is not None and abs(delta) <= bound_pp
        print(f"{arm}  n = {n}")
        print(
            f"  stock {r['stock_pass']}/{n} vs norule {r['norule_pass']}/{n}"
            f"   delta {delta:+.1f}pp"
            + (f"  INSIDE the declared bound ({bound_pp:.2f}pp)" if inside else "")
        )
        if bound_pp is None:
            print(f"  bound NOT DECLARED — {no_bound_because}")
        print(
            f"  m = {r['m']} discordant ({len(r['gains'])} the ablation gained,"
            f" {len(r['losses'])} it lost)"
        )
        if r["m"] < MIN_DISCORDANT:
            print(f"  p     NOT DECIDABLE — m < {MIN_DISCORDANT}")
        else:
            print(f"  exact two-sided p = {r['p']:.2e}")
        print()

    n = pooled["n"]
    delta = (pooled["norule"] - pooled["stock"]) / n * 100
    m = pooled["gains"] + pooled["losses"]
    p = exact_p(pooled["gains"], pooled["losses"])
    print("both arms pooled")
    print(f"  n = {n} paired cells")
    print(
        f"  stock {pooled['stock']}/{n} vs norule {pooled['norule']}/{n}"
        f"   delta {delta:+.1f}pp"
    )
    print(f"  m = {m} ({pooled['gains']} gained, {pooled['losses']} lost)")
    print(
        f"  exact two-sided p = {p:.2e}"
        if m >= MIN_DISCORDANT
        else f"  p NOT DECIDABLE — m < {MIN_DISCORDANT}"
    )

    print("\n## Sensitivity — the same contrast against the other stock run\n")
    for arm in ARMS:
        r = paired(rows(sensitivity_run, arm), rows(norule_run, arm))
        print(
            f"  {arm}  stock {r['stock_pass']} vs norule {r['norule_pass']}"
            f"   m = {r['m']}   p = {r['p']:.2e}"
        )

    print("\n## The mechanism's signature — completion tokens\n")
    print(
        f"  historic (CLM-0017, other material/harness/model): "
        f"{HISTORIC['completion'][1]:.1f} with the rule -> "
        f"{HISTORIC['completion'][0]:.1f} without"
        f"  ({HISTORIC['completion'][0] / HISTORIC['completion'][1]:.1f}x)"
    )
    signature = True
    for arm in ARMS:
        s, nr = rows(stock_run, arm), rows(norule_run, arm)
        ts_, tn = tokens(s), tokens(nr)
        ratio = tn["mean"] / ts_["mean"] if ts_["mean"] else 0.0
        print(
            f"  {arm:9} stock mean {ts_['mean']:.0f} / median {ts_['median']:.0f}"
            f"   ->  norule mean {tn['mean']:.0f} / median {tn['median']:.0f}"
            f"   ({ratio:.2f}x)"
        )
        if ratio < 1.5:
            signature = False

    print("\n## What actually rejected — every rung that fired, not the first\n")
    for arm in ARMS:
        s, nr = rows(stock_run, arm), rows(norule_run, arm)
        mismatches = check_vocabulary(s, nr)
        if mismatches:
            print(
                f"  REFUSED for {arm}: the parse disagrees with the runner's own "
                f"rejected_by on {len(mismatches)} rows, so this profile would "
                "under-report. First three:"
            )
            for line in mismatches[:3]:
                print(f"    {line}")
            print()
            continue
        every: set[str] = set()
        for run_rows in (s, nr):
            for row in run_rows.values():
                every |= rungs_of(row)
        print(f"{arm}:")
        print(f"  {'rung':<20}{'stock':>8}{'norule':>8}{'change':>9}")
        for rung in sorted(every):
            a = sum(1 for row in s.values() if rung in rungs_of(row))
            b = sum(1 for row in nr.values() if rung in rungs_of(row))
            print(f"  {rung:<20}{a:>8}{b:>8}{b - a:>+9}")
        # Gate.run short-circuits, and this pair of numbers is the proof: no row
        # in either run carries an adapter finding AND an acceptance finding. So
        # `acceptance` above is not "how many failed the test", it is "how many
        # got as far as the test and then failed it" — and a *fall* in it is
        # consistent with the ablation being worse, not better. The adapter row
        # is the uncontaminated comparison, because that rung always runs.
        for label, rung_set in (("any adapter finding", ADAPTER_LABELS),):
            a = sum(1 for row in s.values() if rungs_of(row) & rung_set)
            b = sum(1 for row in nr.values() if rungs_of(row) & rung_set)
            print(f"  {label:<20}{a:>8}{b:>8}{b - a:>+9}   <- always runs")
        reached_s = sum(1 for row in s.values() if not (rungs_of(row) & ADAPTER_LABELS))
        reached_n = sum(
            1 for row in nr.values() if not (rungs_of(row) & ADAPTER_LABELS)
        )
        print(
            f"  {'reached acceptance':<20}{reached_s:>8}{reached_n:>8}"
            f"{reached_n - reached_s:>+9}"
        )
        print()

    print("## The pre-registered verdict, evaluated\n")
    direction = pooled["norule"] < pooled["stock"]
    decidable = m >= MIN_DISCORDANT and p < 0.05
    print(f"  direction (stock accepts more)      {'YES' if direction else 'NO'}")
    verdict = "YES" if decidable else "NO"
    print(f"  decidable (m >= {MIN_DISCORDANT} and p < 0.05)     {verdict}")
    print(f"  mechanism signature (tokens)        {'YES' if signature else 'NO'}")
    if direction and decidable and signature:
        print("\n  VERDICT  check 2 PASSES as pre-registered.")
        return 0
    if direction and decidable and not signature:
        print(
            "\n  VERDICT  the effect is recovered and decidable, but NOT by the "
            "mechanism the pre-registration named. Per that document this is "
            "'not recovery, and reported as such' — it goes to the owner with "
            "the rung profile above, which is where the mechanism actually "
            "shows."
        )
        return 1
    print("\n  VERDICT  check 2 does NOT pass. See the rows above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
