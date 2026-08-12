"""What each instrument this repository owns can actually resolve.

Reads the checked-in measurement records, derives the discordance structure of
every paired contrast in them, and reports the effect each one could have
detected. Nothing here is hand-entered: every figure in the ADR-0019 tables is
recomputed by ``python tools/power/report.py`` from ``records/measurements/``,
so a re-run is the check.

Two distinct questions, and the report answers both because they get confused:

*Responsiveness* — over a whole condition matrix, how many tasks ever change
verdict at all. This is the ``13 of 20 condition-insensitive`` figure CLM-0012
reports, stated the other way up.

*Discordance* — for one contrast, how many tasks differ between exactly two
conditions. This is what carries the power, and it is smaller.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from mde import (
    MIN_DISCORDANT,
    Contrast,
    detectable_delta,
    required_n,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
M = ROOT / "records" / "measurements"

# Condition-matrix instruments: one row per (task, condition), paired by task.
MATRICES = [
    ("bundle JS/TS, srv1", "jsts-bundle-2026-08-04/results.jsonl"),
    (
        "bundle JS/TS, srv2",
        "jsts-bundle-2026-08-04/replication-srv2/results.jsonl",
    ),
    ("bundle Python arm A", "python-bundle-2026-08-07/results.jsonl"),
    (
        "bundle Python arm B",
        "python-bundle-2026-08-07/original-harness/results_q3b.jsonl",
    ),
]

# Two runs of the 269-problem pool at 14B, differing only in output cap. Not a
# null — the cap is a lever — but the cap-explained flips can be removed, and
# what is left is drift. Truncation is read from ``stop_reason``, never from
# ``overran_cap``: that field asks whether the backend returned *more* than it
# was allowed (``runner.py:242``), it is correctly False on all 12,466 rows in
# ``records/measurements/``, and filtering on it silently keeps every truncated
# cell. Doing so here turns the drift below from 1 problem into 3.
POOL_DRIFT = (
    "pool @ qwen2.5-coder:14b",
    "pool-sweep-14b-2026-08-07/srv2-ts/results.jsonl",
    "pool-sweep-14b-cap2048-2026-08-08/results.jsonl",
)

# Greedy re-runs of a byte-identical configuration. The drift between them is
# the instrument's own null: no lever is applied, so any flip is noise.
REPLICATES = [
    ("d1 @ llama3.2:3b", "breadth-batch-b-2026-08-06/srv1/llama3.2-3b"),
    (
        "d1 @ qwen2.5-coder:1.5b",
        "breadth-batch-b-2026-08-06/srv1/qwen2.5-coder-1.5b",
    ),
    ("d1 @ qwen2.5-coder:3b", "breadth-batch-b-2026-08-06/srv1/qwen2.5-coder-3b"),
    ("d1 @ qwen2.5-coder:7b", "breadth-batch-b-2026-08-06/srv1/qwen2.5-coder-7b"),
    ("d2 @ qwen3-coder:30b", "breadth-batch-b-2026-08-06/srv2/qwen3-coder-30b"),
]

# The same null on the #225 bench, which is the instrument #231 commissions.
# The breadth rows above hold their replicates as ``sweep-*`` subdirectories of
# one run; the bench's are two whole run directories, one per replicate, so
# they are listed as explicit pairs rather than discovered. Both replicates ran
# back to back against one loaded model, which is what "one backend session"
# in #231's check 1 means: no unload, no build change, no host change.
BENCH_REPLICATES = [
    (
        "bench-py @ qwen2.5-coder:1.5b",
        (
            "bench-null-15b-a-2026-08-12/bench-py/results.jsonl",
            "bench-null-15b-b-2026-08-12/bench-py/results.jsonl",
        ),
    ),
    (
        "bench-ts @ qwen2.5-coder:1.5b",
        (
            "bench-null-15b-a-2026-08-12/bench-ts/results.jsonl",
            "bench-null-15b-b-2026-08-12/bench-ts/results.jsonl",
        ),
    ),
]


def _rows(rel: str) -> list[dict[str, Any]]:
    with (M / rel).open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _by_condition(rel: str) -> dict[str, dict[str, bool]]:
    by: dict[str, dict[str, bool]] = collections.defaultdict(dict)
    for row in _rows(rel):
        by[row["task"]][row["condition"]] = bool(row["pass1"])
    return by


def responsiveness() -> None:
    print("## Responsiveness — tasks that ever change verdict across the matrix\n")
    print(
        f"{'instrument':<22}{'n':>4}{'always pass':>13}"
        f"{'always fail':>13}{'responsive':>12}"
    )
    for label, rel in MATRICES:
        by = _by_condition(rel)
        n = len(by)
        pins_pass = sum(1 for d in by.values() if all(d.values()))
        pins_fail = sum(1 for d in by.values() if not any(d.values()))
        moving = n - pins_pass - pins_fail
        print(
            f"{label:<22}{n:>4}{pins_pass:>13}{pins_fail:>13}"
            f"{moving:>7} ({moving / n:.0%})"
        )
    print()


def contrasts() -> list[Contrast]:
    out: list[Contrast] = []
    print("## Discordance per contrast — what the statistic was built from\n")
    print(
        f"{'contrast':<32}{'n':>4}{'gain':>6}{'loss':>6}{'m':>4}"
        f"{'net':>6}{'p':>8}   resolvable?"
    )
    for label, rel in MATRICES:
        by = _by_condition(rel)
        conds = sorted({c for d in by.values() for c in d})
        base = conds[0]
        for cond in conds[1:]:
            gained = sum(1 for d in by.values() if not d[base] and d[cond])
            lost = sum(1 for d in by.values() if d[base] and not d[cond])
            k = Contrast(f"{label} {base}->{cond}", len(by), gained, lost)
            out.append(k)
            verdict = (
                "yes"
                if k.can_ever_reject
                else f"NO — m={k.discordant} < {MIN_DISCORDANT}, p>=.05 at any split"
            )
            print(
                f"{k.label:<32}{k.n:>4}{k.gained:>6}{k.lost:>6}"
                f"{k.discordant:>4}{k.net:>+6}{k.p_value:>8.3f}   {verdict}"
            )
    out.extend(bench_contrasts())
    print()
    return out


def bench_contrasts() -> list[Contrast]:
    """Per-lever discordance measured on the #225 bench itself.

    Everything above is a retired instrument (ADR-0020). These rows are the
    only contrasts this project has run *on the bench*, and they matter
    because ADR-0021's sizing table has no measured ``psi`` in it at all: its
    rightmost column is ``psi_draw`` = 0.659, which is resampling sensitivity
    at temperature and not the discordance rate of a greedy lever contrast.

    These are the **scaffold** lever, not #231's commissioning contrast, and
    each condition cell is 34 tasks. They anchor the range; they are not D2's
    ``psi`` input, which must come from the contrast being commissioned.
    """
    out: list[Contrast] = []
    for model in ("3b", "7b"):
        for arm in ("bench-py", "bench-ts"):
            root = M / f"bench-scaffold-ablation-{model}-2026-08-11"
            base_path = root / "stock" / arm / "results.jsonl"
            if not base_path.exists():
                continue
            base, _ = _greedy(base_path)
            for cond in ("planonly", "noscaffold"):
                path = root / cond / arm / "results.jsonl"
                if not path.exists():
                    continue
                other, _ = _greedy(path)
                shared = sorted(set(base) & set(other))
                gained = sum(1 for t in shared if not base[t] and other[t])
                lost = sum(1 for t in shared if base[t] and not other[t])
                k = Contrast(
                    f"{arm} @ {model} stock->{cond}", len(shared), gained, lost
                )
                out.append(k)
                unresolvable = (
                    f"NO — m={k.discordant} < {MIN_DISCORDANT}, p>=.05 at any split"
                )
                verdict = "yes" if k.can_ever_reject else unresolvable
                print(
                    f"{k.label:<32}{k.n:>4}{k.gained:>6}{k.lost:>6}"
                    f"{k.discordant:>4}{k.net:>+6}{k.p_value:>8.3f}   {verdict}"
                )
    if out:
        by_model: dict[str, list[Contrast]] = {}
        for k in out:
            by_model.setdefault(k.label.split(" @ ")[1].split(" ")[0], []).append(k)
        print("\n  measured psi on the bench, pooled over both arms and both levers:")
        for model, ks in by_model.items():
            m = sum(k.discordant for k in ks)
            n = sum(k.n for k in ks)
            print(f"    {model}: m = {m} of n = {n} cells, psi = {m / n:.3f}")
        print(
            "  Every one is far below psi_draw = 0.659. They are the scaffold\n"
            "  lever at 34 tasks a cell, so they bound the range rather than\n"
            "  settling it — #231's commissioning contrast supplies D2's psi."
        )
    return out


def _greedy(path: pathlib.Path) -> tuple[dict[str, bool], dict[str, str]]:
    with path.open() as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    greedy = {r["task"]: bool(r["passed"]) for r in rows if r.get("arm") == "greedy"}
    shas = {r["task"]: r["candidate_sha256"] for r in rows if r.get("arm") == "greedy"}
    return greedy, shas


def _drift_row(
    label: str, runs: int, n: int, rates: list[int], worst: int, byte_id: float
) -> None:
    spread = (max(rates) - min(rates)) / n
    rate_txt = "-".join(str(r) for r in rates) + f"/{n}"
    print(
        f"{label:<32}{runs:>5}{n:>5}{rate_txt:>13}"
        f"{worst:>9} task{'s' if worst != 1 else ' '}"
        f"{spread * 100:>7.1f}pp{byte_id:>9.0%}"
    )


def null_drift() -> None:
    print("## Measured null — greedy re-runs of a byte-identical configuration\n")
    print(
        f"{'instrument':<32}{'runs':>5}{'n':>5}{'pass rate':>13}"
        f"{'worst pair':>12}{'drift':>8}{'byte-id':>9}"
    )
    for label, rel in REPLICATES:
        runs = sorted(
            p for p in (M / rel).iterdir() if p.is_dir() and p.name.startswith("sweep-")
        )
        if len(runs) < 2:
            continue
        verdicts: dict[str, dict[str, bool]] = {}
        shas: dict[str, dict[str, str]] = {}
        for run in runs:
            verdicts[run.name], shas[run.name] = _greedy(run / "results.jsonl")
        names = list(verdicts)
        n = len(verdicts[names[0]])
        worst = 0
        ident: list[float] = []
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                worst = max(
                    worst,
                    sum(1 for t in verdicts[a] if verdicts[a][t] != verdicts[b].get(t)),
                )
                ident.append(
                    sum(1 for t in shas[a] if shas[a][t] == shas[b].get(t)) / n
                )
        _drift_row(
            label,
            len(names),
            n,
            sorted({sum(verdicts[k].values()) for k in names}),
            worst,
            sum(ident) / len(ident),
        )

    label, old_rel, new_rel = POOL_DRIFT
    old = {r["task"]: r for r in _rows(old_rel) if r["arm"] == "greedy"}
    new = {r["task"]: r for r in _rows(new_rel) if r["arm"] == "greedy"}
    shared = [t for t in old if t in new]
    kept = [t for t in shared if old[t]["stop_reason"] != "truncated"]
    flips = sum(1 for t in kept if old[t]["passed"] != new[t]["passed"])
    same = sum(
        1 for t in shared if old[t]["candidate_sha256"] == new[t]["candidate_sha256"]
    )
    _drift_row(
        label,
        2,
        len(kept),
        sorted({sum(1 for t in kept if r[t]["passed"]) for r in (old, new)}),
        flips,
        same / len(shared),
    )
    print(
        f"\n  ({len(shared) - len(kept)} of {len(shared)} pool problems were "
        f"truncated under the old cap and are\n   excluded; their flips are the "
        f"cap, not drift.)\n"
    )
    bench_null()


def bench_null() -> None:
    """The #231 null on the bench, per arm and over both arms pooled.

    ADR-0019's D2 asks for ``d`` **per target tier**, and ``bench-py`` and
    ``bench-ts`` are two tiers; the pooled row is the same number over the
    denominator ADR-0021's fourth amendment fixes — paired cells actually
    swept, both arms. It is reported because that is the denominator the
    sizing table uses, not because it replaces the per-tier rows.
    """
    pooled_a: dict[str, bool] = {}
    pooled_b: dict[str, bool] = {}
    pooled_sha_a: dict[str, str] = {}
    pooled_sha_b: dict[str, str] = {}
    rows: list[tuple[str, int, int, list[int], int, float]] = []

    for label, (rel_a, rel_b) in BENCH_REPLICATES:
        path_a, path_b = M / rel_a, M / rel_b
        if not (path_a.exists() and path_b.exists()):
            continue
        va, sa = _greedy(path_a)
        vb, sb = _greedy(path_b)
        shared = [t for t in va if t in vb]
        flips = sum(1 for t in shared if va[t] != vb[t])
        same = sum(1 for t in shared if sa[t] == sb.get(t))
        rows.append(
            (
                label,
                2,
                len(shared),
                sorted({sum(va[t] for t in shared), sum(vb[t] for t in shared)}),
                flips,
                same / len(shared) if shared else 0.0,
            )
        )
        arm = label.split(" @ ")[0]
        for t in shared:
            pooled_a[f"{arm}/{t}"] = va[t]
            pooled_b[f"{arm}/{t}"] = vb[t]
            pooled_sha_a[f"{arm}/{t}"] = sa[t]
            pooled_sha_b[f"{arm}/{t}"] = sb[t]

    if not rows:
        return
    print("\n## The bench's own null (#231 check 1)\n")
    print(
        f"{'instrument':<32}{'runs':>5}{'n':>5}{'pass rate':>13}"
        f"{'worst pair':>12}{'drift':>8}{'byte-id':>9}"
    )
    for row in rows:
        _drift_row(*row)
    if len(rows) > 1:
        keys = list(pooled_a)
        _drift_row(
            "both arms pooled",
            2,
            len(keys),
            sorted({sum(pooled_a.values()), sum(pooled_b.values())}),
            sum(1 for k in keys if pooled_a[k] != pooled_b[k]),
            sum(1 for k in keys if pooled_sha_a[k] == pooled_sha_b[k]) / len(keys),
        )
    print(
        "\n  d is the 'worst pair' column — a count of flipped verdicts, which\n"
        "  is ADR-0019 D1's layer 2. 'drift' is the net pass-rate spread, and\n"
        "  it is the smaller number because opposed flips cancel. D2's `d < b`\n"
        "  compares a bar in pp against a count, so read d as d/n; both are\n"
        "  printed above and the session record states which one is used.\n"
    )


def wall(sizes: tuple[int, ...], psis: tuple[float, ...]) -> None:
    print("## What a given instrument size can resolve at all\n")
    print(f"{'n':>6}" + "".join(f"{f'psi={p:.2f}':>16}" for p in psis))
    for n in sizes:
        cells = ""
        for psi in psis:
            d = detectable_delta(n, psi)
            got = "unreachable" if d is None else f"+{round(d * n)} = +{d * 100:.0f}pp"
            cells += f"{got:>16}"
        print(f"{n:>6}{cells}")
    print()


def sizing(psis: tuple[float, ...], bars: tuple[float, ...]) -> None:
    print("## Sizing — paired tasks needed, by bar and discordance rate\n")
    print("(alpha 0.05 two-sided, power 0.80; '>100k' means out of reach)\n")
    head = "".join(f"{f'psi={p:.2f}':>10}" for p in psis)
    print(f"{'bar':>7}{head}{'quantum':>10}")
    for bar in bars:
        cells = ""
        for psi in psis:
            got = required_n(bar, psi)
            cells += f"{'>100k' if got is None else f'{got:,}':>10}"
        quantum = f"n>={-(-1 // bar):.0f}"
        print(f"{bar * 100:>6.0f}pp{cells}{quantum:>10}")
    print()
    print("The quantum column is the constraint no power calculation removes:")
    print("one task is 1/n, so an instrument cannot report an effect finer than")
    print("that however quiet it is.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section",
        choices=("all", "responsive", "contrasts", "null", "sizing", "wall"),
        default="all",
    )
    args = parser.parse_args()
    section = args.section
    if section in ("all", "responsive"):
        responsiveness()
    if section in ("all", "contrasts"):
        contrasts()
    if section in ("all", "null"):
        null_drift()
    if section in ("all", "wall"):
        wall((20, 40, 100, 200, 400), (0.10, 0.20, 0.35))
    if section in ("all", "sizing"):
        sizing((0.10, 0.20, 0.35), (0.01, 0.02, 0.03, 0.05, 0.10))


if __name__ == "__main__":
    main()
