#!/usr/bin/env python3
"""#225 — what the sibling screen is worth, and what the split costs.

`emit.py` refuses a draft whose reference shares >= 0.70 of an existing
problem's token skeleton, and warns from 0.55. The refusal was bought by a real
failure: `b080-brace-fill`, `b090-expand-markers` and `b168-badge-slots` were
one problem three times, two of them in the bench half, and the gate's *prose*
screen could not see it because the three delimiters share almost no vocabulary.
`b168` scores 0.74 of `b080`'s shape. The screen catches what burned us.

What was never checked is the premise underneath it: **that shape similarity
predicts measurement redundancy.** A duplicate is expensive because it occupies
two slots in the count while carrying one slot's information — under the paired
test it contributes a concordant pair, which is `n` without `m`. If two problems
that share a skeleton do *not* behave alike, the screen is defending the
statistic against nothing, and the authoring it costs is spent on an aesthetic.

The responsiveness run of 2026-08-11 makes that testable: 270 cells, nine draws
each. This tool reads it three ways.

* **saturation** — each admitted problem's nearest sibling *among those admitted
  before it*, by tranche. The trend that prompted the question.
* **redundancy** — does that similarity predict how alike two cells behave?
  Reported as a correlation over every within-arm pair, and as Fisher's exact
  test on the nearest pairs individually.
* **denominator** — what the instrument resolves, counted in cells that are
  actually swept. `split.py` sends ~half of every tranche to a reserve that
  `docs/bench-design-2026-08-10.md` states is never swept and no rig tier
  serves. ADR-0021's 2026-08-12 amendment fixed the `ts`/`py` denominator and
  did not reach this one.

**A limit that cannot be argued around.** No admitted pair scores >= 0.70 —
they were refused before emission or retired after it. So the redundancy read is
*censored at the refusal line*, and it says nothing about what a refused twin
would have done. It bears on the 0.55 warn band, which costs an author a read
every time it fires. It is not grounds for moving the refusal.

The converse limit is worse and is the reason this tool cannot certify anything:
two cells pinned at 0/8 are indistinguishable from each other whether they are
twins or unrelated, and 83 of 270 cells are pinned that way. **The test can
refute redundancy for a given pair. It can never establish it.**

    uv run python tools/bench/redundancy.py --run <dir>
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics as st
import sys
from math import comb, sqrt
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))

import emit as screen  # noqa: E402
from power.mde import detectable_delta  # noqa: E402

ADMISSIONS = HERE / "admissions.jsonl"
ARMS = ("ts", "py")

# The tranche a problem was authored in, from its id. `f1` runs b228 upward in
# forties, numbered from four — the same derivation responsiveness.py uses, and
# for the same reason: a problem cannot be filed under a tranche it was not
# authored in.
F1_FIRST = 228
F1_TRANCHE_SIZE = 40
F1_FIRST_TRANCHE = 4


def tranche_of(problem_id: str) -> int | None:
    """Which `f1` tranche `problem_id` was authored in, or None if not `f1`."""
    try:
        number = int(problem_id[1:4])
    except ValueError:
        return None
    if number < F1_FIRST:
        return None
    return F1_FIRST_TRANCHE + (number - F1_FIRST) // F1_TRANCHE_SIZE


def fisher(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact p for the 2x2 table ``[[a, b], [c, d]]``.

    Same shape as responsiveness.py's, kept separate rather than imported so a
    defect in one does not silently agree with the other.
    """
    total = a + b + c + d
    if total == 0 or min(a + b, c + d, a + c, b + d) < 0:
        return 1.0

    def probability(first: int) -> float:
        second = a + b - first
        third = a + c - first
        fourth = total - first - second - third
        if min(second, third, fourth) < 0:
            return 0.0
        return comb(a + b, first) * comb(c + d, third) / comb(total, a + c)

    observed = probability(a)
    return min(
        1.0,
        sum(
            probability(x)
            for x in range(0, min(a + b, a + c) + 1)
            if probability(x) <= observed + 1e-12
        ),
    )


def pearson(xs: list[float], ys: list[float]) -> float:
    """Correlation, or 0.0 where either series is constant."""
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if sx == 0.0 or sy == 0.0:
        return 0.0
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / len(xs)
    return cov / (sx * sy)


def admissions() -> list[dict[str, Any]]:
    return [json.loads(line) for line in ADMISSIONS.read_text().splitlines() if line]


def cells(run: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """``(arm, task) -> {"greedy": bool | None, "sampled": [bool, ...]}``."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for arm in ARMS:
        results = run / f"bench-{arm}" / "results.jsonl"
        if not results.is_file():
            continue
        for line in results.read_text().splitlines():
            if not line:
                continue
            row = json.loads(line)
            cell = out.setdefault((arm, row["task"]), {"greedy": None, "sampled": []})
            if row["arm"] == "greedy":
                cell["greedy"] = bool(row["passed"])
            else:
                cell["sampled"].append(bool(row["passed"]))
    return out


def saturation(band: str) -> None:
    """Nearest sibling among problems admitted *earlier*, by tranche.

    Prior-only rather than all-pairs: the question is what the corpus looked
    like to the author on the day, not what it looks like now.
    """
    known = screen.corpus()
    rows = [r for r in admissions()]
    seen: dict[str, dict[str, Any]] = {}
    per_tranche: dict[int, list[float]] = {}

    for row in rows:
        arms = known.get(row["id"])
        if arms is None:
            continue
        best = 0.0
        for arm, mine in arms.items():
            for other in seen.values():
                if arm in other:
                    best = max(best, screen._overlap(mine, other[arm]))
        seen[row["id"]] = arms
        if row["steering_band"] != band:
            continue
        index = tranche_of(row["id"])
        if index is not None:
            per_tranche.setdefault(index, []).append(best)

    print(f"\nNearest earlier sibling, band {band} — by tranche\n")
    print(
        f"{'tranche':>8}{'n':>5}{'mean':>8}{'median':>8}{'max':>7}"
        f"{'>=0.55':>8}{'>=0.65':>8}"
    )
    for index in sorted(per_tranche):
        scores = per_tranche[index]
        print(
            f"{index:>8}{len(scores):>5}{st.mean(scores):>8.3f}"
            f"{st.median(scores):>8.3f}{max(scores):>7.3f}"
            f"{sum(s >= 0.55 for s in scores):>8}"
            f"{sum(s >= 0.65 for s in scores):>8}"
        )
    print(
        "\n  Admitted scores are censored at emit.REFUSE_AT by construction:\n"
        "  a rising refusal count with a flat admitted mean is truncation,\n"
        "  not a corpus that has run out."
    )


def redundancy(run: Path) -> None:
    """Does skeleton similarity predict that two cells behave alike?"""
    measured = cells(run)
    known = screen.corpus()
    similarities: list[float] = []
    divergences: list[float] = []
    near: list[tuple[float, str, str, str]] = []

    for arm in ARMS:
        ids = sorted(task for (a, task) in measured if a == arm)
        for first, second in itertools.combinations(ids, 2):
            one = known.get(first, {}).get(arm)
            two = known.get(second, {}).get(arm)
            if not one or not two:
                continue
            a_draws = measured[(arm, first)]["sampled"]
            b_draws = measured[(arm, second)]["sampled"]
            if not a_draws or not b_draws:
                continue
            score = screen._overlap(one, two)
            similarities.append(score)
            divergences.append(
                abs(sum(a_draws) / len(a_draws) - sum(b_draws) / len(b_draws))
            )
            if score >= screen.WARN_AT:
                near.append((score, arm, first, second))

    n = len(similarities)
    if n == 0:
        print("\nNo measured pairs in this run.")
        return

    r = pearson(similarities, divergences)
    print(f"\nSimilarity vs. divergence of sampled pass rate — {n} within-arm pairs\n")
    print(f"  Pearson r = {r:+.4f}   (95% CI +-{1.96 / sqrt(n):.4f} around zero)")
    paired = list(zip(similarities, divergences, strict=True))
    high = [d for s, d in paired if s >= screen.WARN_AT]
    low = [d for s, d in paired if s < screen.WARN_AT]
    if high and low:
        spread = st.pstdev(divergences)
        gap = st.mean(high) - st.mean(low)
        error = 1.96 * spread / sqrt(len(high))
        print(
            f"  >= {screen.WARN_AT}: n={len(high)} mean={st.mean(high):.3f}   "
            f"< {screen.WARN_AT}: n={len(low)} mean={st.mean(low):.3f}"
        )
        print(
            f"  difference {gap:+.3f}, 95% CI [{gap - error:+.3f}, {gap + error:+.3f}]"
        )

    print("\nThe pairs the screen warns about, tested individually\n")
    print(f"{'sim':>6} {'arm':<4}{'pair':<44}{'counts':>12}{'Fisher p':>10}   verdict")
    for score, arm, first, second in sorted(near, reverse=True):
        one, two = measured[(arm, first)], measured[(arm, second)]
        x, y = sum(one["sampled"]), sum(two["sampled"])
        nx, ny = len(one["sampled"]), len(two["sampled"])
        p = fisher(x, nx - x, y, ny - y)
        verdict = "different" if p < 0.05 else "proves nothing"
        print(
            f"{score:>6.2f} {arm:<4}{f'{first} / {second}':<44}"
            f"{f'{x}/{nx} vs {y}/{ny}':>12}{p:>10.3f}   {verdict}"
        )
    print(
        "\n  A difference in counts is NOT evidence on its own: two cells with\n"
        "  the same true rate give different counts about four times in five at\n"
        "  eight draws. And no result here can show two problems are the SAME —\n"
        "  every pinned cell reads alike whatever it is."
    )


def denominator(band: str, targets: tuple[int, ...], psi: float) -> None:
    """What the instrument resolves, counted in cells that are actually swept."""
    rows = [r for r in admissions() if r["steering_band"] == band]
    if not rows:
        print(f"\nNo admitted problems in band {band}.")
        return
    swept = sum(1 for r in rows if r["split"] == "bench")
    share = swept / len(rows)

    print(
        f"\nBand {band}: {len(rows)} authored, {swept} bench ({share:.1%}), "
        f"{len(rows) - swept} reserve\n"
    )
    print("  The reserve is never swept (docs/bench-design-2026-08-10.md) and")
    print("  serves #222, so an authored problem enters the statistic only if")
    print("  the split rule sent it to the bench half.\n")
    print(f"{'authored':>9}{'bench':>7}{'swept cells':>13}{'MDE':>9}")
    for authored in targets:
        bench = round(authored * share)
        cells_swept = bench * 2
        delta = detectable_delta(cells_swept, psi)
        value = delta[1] if isinstance(delta, tuple) else delta
        shown = f"{float(value) * 100:.1f}pp" if value else "unreachable"
        print(f"{authored:>9}{bench:>7}{cells_swept:>13}{shown:>9}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--run",
        type=Path,
        default=REPO / "records/measurements/f1-responsiveness-15b-2026-08-11",
        help="a sweep whose results.jsonl carries repeated draws per cell",
    )
    parser.add_argument("--band", default="f1")
    parser.add_argument(
        "--psi",
        type=float,
        default=0.659,
        help="discordance rate; the default is psi_draw, which is NOT psi",
    )
    parser.add_argument(
        "--section",
        choices=("saturation", "redundancy", "denominator", "all"),
        default="all",
    )
    args = parser.parse_args(argv)

    if args.section in ("saturation", "all"):
        saturation(args.band)
    if args.section in ("redundancy", "all"):
        redundancy(args.run)
    if args.section in ("denominator", "all"):
        denominator(args.band, (280, 320, 360, 400, 500, 600, 800), args.psi)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
