#!/usr/bin/env python3
"""What the second language arm buys, measured on verdicts already recorded.

The bench authors every problem twice — one prose, a TypeScript rendering and a
Python one — and ADR-0021's denominator is the paired cell. That doubles the
expensive axis: lane/225's record puts authoring at "160 problems" against rig
time that "cost 65 minutes for 8x". The question this tool answers is whether
the second arm earns it.

**It is a recomputation, not a run.** Every paired cell already on disk carries
a `ts` verdict and a `py` verdict for the same problem under the same condition.
Joining them is arithmetic over `results.jsonl`; nothing is dispatched and no
model is served. That is the same argument #289 made for subset reproducibility
bounds — a figure a subset of an already-paired set can be recomputed from is
never worth a new dispatch.

**What is reported, and why not one number.** Per run: how many cells the two
arms agree on, and how the disagreements split. Agreement alone is the wrong
read on its own — two arms that both fail everything agree perfectly and
distinguish nothing — so the phi coefficient sits beside it, which is zero when
one arm's verdict carries no information about the other's, and McNemar's exact
p, which asks whether the disagreements lean one way rather than scattering.
A high agreement with a phi near zero and a lopsided McNemar is a different
finding from a high agreement with a phi near one.

**Pooling is refused.** Runs differ by model, condition and bar, and #263
records a confirmed pooling defect in this repository already. Each run is its
own row; the totals line is a count of rows, never a pooled rate.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MEASUREMENTS = REPO / "records" / "measurements"

# The two directory names a paired bench run writes. A run holding one of them
# is a single-arm sweep and is skipped rather than counted as total agreement.
ARMS = ("bench-py", "bench-ts")


class ArmsError(Exception):
    """The recorded runs cannot be read as pairs."""


@dataclass(frozen=True)
class Pairing:
    """One run's two arms, joined cell by cell."""

    run: str
    both_pass: int
    both_fail: int
    py_only: int
    ts_only: int

    @property
    def cells(self) -> int:
        return self.both_pass + self.both_fail + self.py_only + self.ts_only

    @property
    def agree(self) -> int:
        return self.both_pass + self.both_fail

    @property
    def agreement(self) -> float:
        """The share of cells where the two arms return the same verdict."""
        return self.agree / self.cells if self.cells else 0.0

    @property
    def solved_anywhere(self) -> int:
        """Cells at least one arm passed."""
        return self.both_pass + self.py_only + self.ts_only

    @property
    def pass_concordance(self) -> float:
        """Of the cells solved at all, the share solved on *both* arms.

        The number `agreement` hides. At the pass rates this bench runs at,
        most cells fail on both arms, so agreement is dominated by mutual
        failure — `bench-control-norule-15b` agrees on 93.8% of cells and 236
        of those 257 are both-fail. Two arms that agree only by failing
        together are not evidence that the second arm is redundant. This asks
        the question the other way: where there was anything to agree about,
        did they?
        """
        return self.both_pass / self.solved_anywhere if self.solved_anywhere else 0.0

    @property
    def phi(self) -> float:
        """Correlation between the two arms' verdicts, on the 2x2 table.

        Zero when one arm's verdict says nothing about the other's; one when
        they are identical. Returns 0.0 when a margin is empty — every cell
        passing on one arm makes the coefficient undefined rather than perfect,
        and reporting it as perfect is the read this tool exists to prevent.
        """
        a, b = self.both_pass, self.py_only  # py passed: ts passed, ts failed
        c, d = self.ts_only, self.both_fail  # py failed: ts passed, ts failed
        margins = (a + b) * (c + d) * (a + c) * (b + d)
        if margins == 0:
            return 0.0
        return (a * d - b * c) / math.sqrt(margins)

    @property
    def mcnemar_p(self) -> float:
        """Exact two-sided p on the discordant cells.

        Under "the arms are equally hard", each disagreement is a fair coin, so
        the discordant split is binomial at 1/2. A small p means one arm is
        systematically harder — which is a language finding — where a large p
        with many discordants means the two disagree at random, which is noise
        in one arm or the other rather than an effect.
        """
        n = self.py_only + self.ts_only
        if n == 0:
            return 1.0
        smaller = min(self.py_only, self.ts_only)
        # `2 ** n` is typed as Any for a non-literal exponent, so the division
        # would silently widen the return; the annotation keeps it a float.
        outcomes: float = float(2**n)
        tail = sum(math.comb(n, k) for k in range(smaller + 1)) / outcomes
        return min(1.0, 2.0 * tail)


def verdicts(results: Path) -> dict[tuple[str, str, int], bool]:
    """Every greedy-comparable verdict in one arm's run, keyed by cell.

    The key is (task, draw arm, draw index) rather than task alone: a run with
    replication holds several draws per task, and joining on task alone would
    pair a task's first `ts` draw with whichever `py` draw sorted first.
    """
    out: dict[tuple[str, str, int], bool] = {}
    with results.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row: dict[str, Any] = json.loads(line)
            key = (row["task"], row.get("arm", "greedy"), int(row.get("draw", 0)))
            if key in out:
                raise ArmsError(f"{results}: two rows for cell {key}")
            out[key] = bool(row["passed"])
    return out


def pair(run: Path) -> Pairing | None:
    """Join a run's two arms. ``None`` when it is not a paired bench run."""
    files = {arm: run / arm / "results.jsonl" for arm in ARMS}
    if not all(path.is_file() for path in files.values()):
        return None
    py, ts = verdicts(files["bench-py"]), verdicts(files["bench-ts"])
    shared = sorted(set(py) & set(ts))
    if not shared:
        return None
    tally: Counter[str] = Counter()
    for key in shared:
        match (py[key], ts[key]):
            case (True, True):
                tally["both_pass"] += 1
            case (True, False):
                tally["py_only"] += 1
            case (False, True):
                tally["ts_only"] += 1
            case _:
                tally["both_fail"] += 1
    return Pairing(
        run.name,
        tally["both_pass"],
        tally["both_fail"],
        tally["py_only"],
        tally["ts_only"],
    )


def survey(root: Path = MEASUREMENTS) -> list[Pairing]:
    """Every paired bench run under ``root``, oldest name first."""
    if not root.is_dir():
        raise ArmsError(f"{root} is not a directory of measurement runs")
    found = [pair(run) for run in sorted(root.iterdir()) if run.is_dir()]
    return [p for p in found if p is not None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "What the second language arm buys (#225/#268 research). Reads "
            "recorded verdicts, dispatches nothing, states no new rate."
        )
    )
    parser.add_argument("--json", action="store_true", help="machine-readable")
    args = parser.parse_args(argv)

    rows = survey()
    if not rows:
        print("no paired bench run found", file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "run": row.run,
                        "cells": row.cells,
                        "both_pass": row.both_pass,
                        "both_fail": row.both_fail,
                        "py_only_pass": row.py_only,
                        "ts_only_pass": row.ts_only,
                        "agreement": round(row.agreement, 4),
                        "solved_anywhere": row.solved_anywhere,
                        "pass_concordance": round(row.pass_concordance, 4),
                        "phi": round(row.phi, 4),
                        "mcnemar_p": round(row.mcnemar_p, 6),
                    }
                    for row in rows
                ],
                indent=2,
            )
        )
        return 0

    header = (
        f"{'run':44} {'cells':>6} {'agree':>7} {'both+':>6} {'both-':>6} "
        f"{'py+':>5} {'ts+':>5} {'solved':>7} {'conc':>6} {'phi':>7} {'mcnemar':>9}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.run:44} {row.cells:6} {row.agreement:6.1%} {row.both_pass:6} "
            f"{row.both_fail:6} {row.py_only:5} {row.ts_only:5} "
            f"{row.solved_anywhere:7} {row.pass_concordance:5.1%} {row.phi:7.3f} "
            f"{row.mcnemar_p:9.4f}"
        )
    print(f"\n{len(rows)} paired runs. Not pooled: model, condition and bar differ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
