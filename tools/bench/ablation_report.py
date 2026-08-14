#!/usr/bin/env python3
"""#225 — reading the scaffold ablation: two knobs, paired, per language.

The question is what makes a bench problem hard for a floor model. It was
first asked as two separately authored cohorts and could not be answered:
unpaired comparisons spend power like independent samples, which is
ADR-0019's wall in a new costume (`strata.json` block 3). This reads the
paired form, where the same problem is dispatched under three renders:

* ``stock``      — the scaffold as production ships it: plan comment + partial code
* ``planonly``   — the scaffold's comments only; the code removed
* ``noscaffold`` — no scaffold at all

which splits one confounded contrast into two clean ones:

* **code**      ``stock`` vs ``planonly``   — what the partial code was worth,
  with the plan held constant in both arms
* **plan**      ``planonly`` vs ``noscaffold`` — what being told the approach was
  worth, with the whole file to write in both arms
* **whole**     ``stock`` vs ``noscaffold`` — both together; the contrast that
  would have been reported as a size effect had the plan not been noticed

**Why pass counts rather than pass/fail.** A problem that fails every draw
under both conditions is concordant and carries no information no matter how
the test is designed; with one greedy draw per cell, 25 of 34 problems were
that. Eight draws per cell turn the outcome into a count, so a problem that
moves from 6/8 to 2/8 contributes what a binary outcome would have thrown
away. This is ADR-0019 D6's replication, and it is the only reason the
question is askable on this material at all.

**The tests are exact and the direction is not assumed.** The sign test over
problems whose count changed is reported as the primary, because it needs no
distributional assumption and its p-value is honest at the sample sizes here.
Wilcoxon signed-rank is reported beside it (exact by enumeration when the
number of non-zero differences allows) because it uses the size of each
change, not only its direction. ``m`` — the count of problems that moved — is
printed for every contrast, because ADR-0019's wall is stated in exactly that
quantity: below m = 6 no result can reach significance however large the
effect looks.

**The analysis set was fixed before any of these numbers existed**, and it
lives in ``ablation-sets.json`` rather than in whoever ran the command. Seven
of the 34 dispatched problems have task prose that says the helper "is already
written", so ablating them yields a prompt contradicting itself — those are
excluded, not because of what they showed but because of what the prompt says.
Four more the eligibility audit flagged as carrying information the prose does
not are dropped in ``--set strict``, reported alongside so that a conclusion
resting on them is visible as such.

This is not a formality. Read over all 34 the 7B whole-scaffold contrast is
significant on both arms; read over the pre-registered 27 it is not, and the
difference is the seven self-contradicting prompts. The default here is the
pre-registered set for that reason, and ``--set dispatched`` is available for
anyone who wants the other number with its name attached.

**Two sets of verdicts exist for these rows, and the reader names which it
used.** ``--rows as-measured`` (the default) reads what the sweep recorded on
the day. ``--rows regraded`` reads ``tools/bench/regrade.py``'s re-score of the
same saved completions under the checkers as they stand now — the same model
output judged again. That is not a hypothetical: ADR-0023 found 104 bench py
checkers accepting only ``ValueError`` where their ts twins accept any
``Error``, and correcting it moved 40 py cells and no ts cell at all. Both
numbers are real and they answer different questions, so neither is silently
preferred and the heading always says which one is on screen.

Usage::

    uv run --no-sync python tools/bench/ablation_report.py \\
        --run records/measurements/bench-scaffold-ablation-3b-2026-08-11

    # the same rows under the corrected checkers
    uv run --no-sync python tools/bench/ablation_report.py --rows regraded \\
        --run records/measurements/bench-scaffold-ablation-3b-2026-08-11
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from itertools import product
from math import comb
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

sys.path.insert(0, str(HERE))

# #231 checks 3 and 6. `product` here would shadow `itertools.product`, which
# this module uses to walk the condition x arm grid, so the pin is imported
# under the name of what it records.
import mode  # noqa: E402
import product as revision  # noqa: E402

CONDITIONS = ("stock", "planonly", "noscaffold")
ARMS = ("bench-ts", "bench-py")
CONTRASTS = (
    ("code", "stock", "planonly", "what the partial code was worth"),
    ("plan", "planonly", "noscaffold", "what being told the approach was worth"),
    ("whole", "stock", "noscaffold", "both together (the confounded contrast)"),
)

# ADR-0019's wall, in the quantity it is stated in: fewer than six problems
# that moved and no effect size can reach two-sided significance.
DISCORDANT_WALL = 6

# The sets, declared beside the bench rather than passed in on a command line —
# a set that lives in the invocation is a set the next reader has to be told,
# and this one changes the answer (see the declaration's own `why`).
SETS = HERE / "ablation-sets.json"

# Problems withdrawn from the bench after they were measured. Their rows stay
# in the run records, which are evidence of what ran on the day; they are
# dropped here, where a figure is derived. See tools/bench/retired.json.
RETIRED = HERE / "retired.json"


def retired_ids() -> frozenset[str]:
    """Ids withdrawn after admission, whose rows no figure may count."""
    if not RETIRED.is_file():
        return frozenset()
    doc = json.loads(RETIRED.read_text(encoding="utf-8"))
    return frozenset(str(entry["id"]) for entry in doc["ids"])


def declared_sets() -> dict[str, list[str]]:
    """The three sets, two of them derived so they cannot drift apart.

    `analysis` is the pre-registered one: every dispatched problem whose prompt
    still makes sense with the scaffold removed. `strict` drops the four the
    eligibility audit flagged as carrying information the prose does not.
    `dispatched` is every problem the run holds, which is a fact about the run
    and not a question anyone registered.
    """
    doc = json.loads(SETS.read_text(encoding="utf-8"))
    withdrawn = retired_ids()
    # A retired problem leaves every set, including `dispatched`. That set is
    # "a fact about the run", but a withdrawn problem is a fact about the
    # bench, and the two disagreeing would put a permanently empty cell in
    # every table.
    dispatched = [i for i in doc["dispatched"]["ids"] if i not in withdrawn]
    excluded = {entry["id"] for entry in doc["excluded"]["ids"]}
    borderline = {entry["id"] for entry in doc["borderline"]["ids"]}
    analysis = [i for i in dispatched if i not in excluded]
    return {
        "dispatched": dispatched,
        "analysis": analysis,
        "strict": [i for i in analysis if i not in borderline],
    }


#: Which file a cell's verdicts are read from. ``as-measured`` is the row the
#: sweep wrote on the day, under the checker of the day. ``regraded`` is
#: ``tools/bench/regrade.py``'s re-score of the same saved completions under the
#: checkers as they stand now — the same model output, a different judge. They
#: are separate files and separate options because they answer different
#: questions, and because a reader that silently preferred one would make the
#: choice invisible in the output.
ROW_SOURCES = {"as-measured": "results.jsonl", "regraded": "regrade.jsonl"}


def counts(
    run: Path, condition: str, arm: str, rows: str = "as-measured"
) -> dict[str, tuple[int, int]]:
    """Per problem: (passes, draws) for one cell, or {} if it has not run."""
    path = run / condition / arm / ROW_SOURCES[rows]
    if not path.is_file():
        return {}
    withdrawn = retired_ids()
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("dispatch_error"):
            continue  # a draw nobody saw is not a draw (#217)
        if row["task"] in withdrawn:
            continue  # withdrawn after the run; see tools/bench/retired.json
        tally[row["task"]][0] += bool(row.get("passed"))
        tally[row["task"]][1] += 1
    return {task: (p, n) for task, (p, n) in tally.items()}


def sign_test(diffs: list[int]) -> tuple[int, int, float]:
    """Exact two-sided sign test over the non-zero differences.

    Returns (m, positives, p). Assumes nothing about the size of a change,
    which is what makes it the honest primary here: a count of 8 draws is
    not an interval scale and the differences are bounded and lumpy.
    """
    moved = [d for d in diffs if d != 0]
    m = len(moved)
    up = sum(1 for d in moved if d > 0)
    if m == 0:
        return 0, 0, 1.0
    tail = sum(comb(m, k) for k in range(min(up, m - up) + 1))
    return m, up, min(1.0, 2 * tail / 2**m)


def wilcoxon(diffs: list[int]) -> tuple[float, float | None]:
    """Signed-rank statistic and an exact two-sided p when enumeration is sane.

    Ties are mid-ranked. Exact enumeration over sign assignments is used up
    to 18 non-zero differences (262,144 assignments); beyond that the p is
    returned as None rather than approximated, because a normal
    approximation at these sample sizes would be the kind of number this
    project has already been burned reporting.
    """
    moved = [d for d in diffs if d != 0]
    m = len(moved)
    if m == 0:
        return 0.0, 1.0
    order = sorted(range(m), key=lambda i: abs(moved[i]))
    ranks = [0.0] * m
    i = 0
    while i < m:
        j = i
        while j + 1 < m and abs(moved[order[j + 1]]) == abs(moved[order[i]]):
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, moved, strict=True) if d > 0)
    observed = min(w_plus, sum(ranks) - w_plus)
    if m > 18:
        return observed, None
    hits = 0
    for signs in product((0, 1), repeat=m):
        plus = sum(r for r, s in zip(ranks, signs, strict=True) if s)
        if min(plus, sum(ranks) - plus) <= observed + 1e-9:
            hits += 1
    return observed, min(1.0, hits / 2**m)


def report_contrast(
    name: str,
    left: str,
    right: str,
    blurb: str,
    run: Path,
    keep: set[str],
    rows: str = "as-measured",
) -> list[dict[str, Any]]:
    """One contrast, per language arm and pooled per problem."""
    print(f"\n### {name}: {left} vs {right} — {blurb}")
    out: list[dict[str, Any]] = []
    pooled: dict[str, int] = defaultdict(int)
    pooled_seen: dict[str, int] = defaultdict(int)

    for arm in ARMS:
        a, b = counts(run, left, arm, rows), counts(run, right, arm, rows)
        shared = sorted(
            t for t in keep if t in a and t in b and a[t][1] == b[t][1] and a[t][1] > 0
        )
        if not shared:
            print(f"  {arm}: not yet measured")
            continue
        diffs = [a[t][0] - b[t][0] for t in shared]
        draws = a[shared[0]][1]
        left_rate = sum(a[t][0] for t in shared) / (draws * len(shared))
        right_rate = sum(b[t][0] for t in shared) / (draws * len(shared))
        m, up, p_sign = sign_test(diffs)
        _, p_wil = wilcoxon(diffs)
        for t, d in zip(shared, diffs, strict=True):
            pooled[t] += d
            pooled_seen[t] += 1
        wall = (
            "" if m >= DISCORDANT_WALL else f"  << below the m>={DISCORDANT_WALL} wall"
        )
        p_w = "n/a" if p_wil is None else f"{p_wil:.4f}"
        print(
            f"  {arm}: {100 * left_rate:5.1f}% vs {100 * right_rate:5.1f}% "
            f"({100 * (left_rate - right_rate):+5.1f}pp)  n={len(shared)}  "
            f"moved m={m} ({up} toward {left})  sign p={p_sign:.4f}  "
            f"wilcoxon p={p_w}{wall}"
        )
        out.append(
            {
                "contrast": name,
                "arm": arm,
                "n": len(shared),
                "left_rate": left_rate,
                "right_rate": right_rate,
                "m": m,
                "toward_left": up,
                "p_sign": p_sign,
                "p_wilcoxon": p_wil,
            }
        )

    both = [t for t, seen in pooled_seen.items() if seen == len(ARMS)]
    if both:
        diffs = [pooled[t] for t in sorted(both)]
        m, up, p_sign = sign_test(diffs)
        _, p_wil = wilcoxon(diffs)
        wall = (
            "" if m >= DISCORDANT_WALL else f"  << below the m>={DISCORDANT_WALL} wall"
        )
        p_w = "n/a" if p_wil is None else f"{p_wil:.4f}"
        print(
            f"  pooled per problem (both arms summed, so the arms' pairing is "
            f"respected): n={len(both)}  moved m={m} ({up} toward {left})  "
            f"sign p={p_sign:.4f}  wilcoxon p={p_w}{wall}"
        )
        out.append(
            {
                "contrast": name,
                "arm": "pooled",
                "n": len(both),
                "m": m,
                "toward_left": up,
                "p_sign": p_sign,
                "p_wilcoxon": p_wil,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True, help="measurement dir")
    parser.add_argument(
        "--set",
        default="analysis",
        metavar="NAME|FILE",
        help="which problems to read over: a name from ablation-sets.json "
        f"({', '.join(declared_sets())}) or a file of comma-separated ids. "
        "Default: analysis, the pre-registered set. `dispatched` is every "
        "problem in the run and answers a different question — see the "
        "declaration.",
    )
    parser.add_argument(
        "--rows",
        choices=sorted(ROW_SOURCES),
        default="as-measured",
        help="which verdicts to read. `as-measured` is what the sweep recorded "
        "on the day. `regraded` is tools/bench/regrade.py's re-score of the "
        "same saved completions under the checkers as they stand now — same "
        "model output, different judge. Default: as-measured.",
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="also write the rows here"
    )
    args = parser.parse_args(argv)

    sets = declared_sets()
    if args.set in sets:
        keep, source = set(sets[args.set]), f"{args.set}, declared"
    else:
        path = Path(args.set)
        if not path.is_file():
            parser.error(
                f"--set {args.set!r} is neither a declared set "
                f"({', '.join(sets)}) nor a readable file"
            )
        # Split then strip: a set file an editor has newline-terminated would
        # otherwise lose its last id to a trailing "\n" and say nothing.
        keep = {i.strip() for i in path.read_text(encoding="utf-8").split(",")}
        keep.discard("")
        source = f"from {path}"

    # A set file is written by hand and may still name a withdrawn problem.
    # Dropping it silently would be the "no silent caps" rule broken by the
    # tool that reports the caps.
    if dropped := sorted(keep & retired_ids()):
        keep -= set(dropped)
        print(f"# retired, dropped from this set: {', '.join(dropped)}")

    read = mode.read(
        *[args.run / condition / arm for condition, arm in product(CONDITIONS, ARMS)]
    )
    print(f"# scaffold ablation — {args.run.name}")
    print("# " + mode.banner(read).removeprefix("- "))
    print("# " + revision.banner(read).removeprefix("- "))
    print(f"# verdicts: {args.rows} ({ROW_SOURCES[args.rows]})")
    print(f"# analysis set: {len(keep)} problems ({source})")
    print("# cells present:")
    for condition, arm in product(CONDITIONS, ARMS):
        cell = counts(args.run, condition, arm, args.rows)
        got = sum(n for _, n in cell.values())
        if cell:
            print(f"#   {condition}/{arm}: {len(cell)} problems, {got} draws")

    rows: list[dict[str, Any]] = []
    for name, left, right, blurb in CONTRASTS:
        rows += report_contrast(name, left, right, blurb, args.run, keep, args.rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
