"""The responsive fraction, per (model + bar) x stratum, from committed runs only.

Issue: `#224 <https://github.com/AdarGit008/mcgyvr/issues/224>`_, the first item
its 2026-08-14 amendment added — *"the responsive fraction is reported per
(model+bar) x stratum, never pooled, with the tool that derives it"* — and the
first of the amendment's four corrections: **the responsive fraction is
measured, not chosen.** A required effect size sets a floor on it
(``delta <= psi <= responsive fraction``); it does not define it.

**No pooled row, and that is not a formatting choice.** Both of
``tools/bench/resolution.py``'s objections are carried here unchanged, because
this module reads the same runs:

1. **Across arms.** ``bench-py`` and ``bench-ts`` are not a language contrast.
   They are two bars — 328 ruff rules against 66 eslint, prettier unconfigured
   on one side, no staged ``tsconfig.json`` so no type check at all (#262). A
   figure pooled over them describes neither instrument. This is why the row key
   here is (model + **bar**) rather than (model + language): the arm *is* the
   bar.
2. **Within an arm.** ``psi`` ranges 0.029 to 0.134 across task types inside a
   single arm — a 4.6x spread, the heterogeneity ADR-0026 forbids pooling over.

Arm-level rows are printed because a reader will otherwise compute them, and are
labelled so they cannot be quoted as the bench's resolution. Nothing is ever
pooled across tiers.

Three observables, and they are not the same number
---------------------------------------------------

The word "responsive" has been used for three distinct things in this project's
records, and they disagree here by an order of magnitude. Each row names which
one it is.

``headroom``    Cells passing under **either** condition of a named contrast.
                An **upper bound on m**, hence on ``psi``: a cell failing both
                ways is concordant whatever the lever does. Computed by
                ``eligibility.headroom``. It bounds nothing about a *different*
                lever, and nothing about a different bar.
``psi``         The measured discordance rate of a **named lever**. A property
                of the (instrument, lever) pair, never of "the bench"
                (ADR-0019 D5). ``delta <= psi`` is hard. Computed by
                ``resolution.measure``.
``psi_draw``    Cells whose verdict varies across sampled draws. Its own
                module's docstring is explicit and is preserved here: **it is
                not ``psi`` and is not a bound in either direction.** A cell
                that varies is demonstrably reachable by this model; a cell
                pinned across draws could still be unpinned by a lever that
                supplies information the model lacks.

**The two holes in the answer, named rather than smoothed over.** Every
``psi_draw`` figure below comes from a run that predates ``Gate.run`` scoring —
its rows carry no ``rejected_by`` — so it is measured against the *acceptance
proxy*, not the bench's bar. On the same 135 cells at the same tier that is the
difference between 55 greedy passes and 18. And no committed multi-draw run
covers the full corpus at any tier: the 1.5B's covers 135 of 257 tasks and two
of three strata, and the 7B's covers 34 of 257 and one stratum. Those are
holes A2 must close on the rigs and by re-scoring; they are not reasons to
withhold the table.

**What this module cannot key on yet.** The honest unit is a *signature* — the
model, bar and condition as content rather than as names (#265, ADR-0026's
consequence). Until those digests exist, the key is (tier, arm), which are
labels for the properties that actually differ.

    uv run --no-sync python tools/bench/responsive.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MEASUREMENTS = REPO / "records" / "measurements"


def _by_path(name: str, path: Path) -> types.ModuleType:
    """Load a sibling rig by path — `tools/` is not a package, and the
    convention `tools/bench/resolution.py` follows is followed rather than
    re-invented."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Composed, not copied. Each observable stays owned by the module that defined
# it, so a correction there moves this table too — #243's record is four quoted
# figures that survived until someone re-derived them by hand.
eligibility = _by_path("bench_eligibility_rf", HERE / "eligibility.py")
resolution = _by_path("bench_resolution_rf", HERE / "resolution.py")
responsiveness = _by_path("bench_responsiveness_rf", HERE / "responsiveness.py")

# #231 checks 3 and 6: this module states figures read off runs, so it declares
# the mode and the pinned revision they were produced under, per source.
mode = _by_path("bench_mode_rf", HERE / "mode.py")
revision = _by_path("bench_product_rf", HERE / "product.py")

ARMS = ("py", "ts")

# ADR-0019's wall: below six discordant pairs the exact test reaches p < 0.05 at
# no effect size at all. Taken from `resolution.py` rather than restated — two
# copies of a threshold are two chances for one of them to be edited (ADR-0026
# lens 3).
WALL = resolution.WALL

# The tiers #224 owes a band for: the floor unit, and the second tier ADR-0017's
# P3 and ADR-0018's Q4 require. A row from any other tier is context and is not
# counted as coverage — otherwise adding one reads as opening sixteen gaps.
BAND_TIERS = ("1.5B", "7B")

HEADROOM = "headroom"
PSI = "psi"
PSI_DRAW = "psi_draw"

# What each observable does and does not bound, printed beside every row so the
# three can never be read as one column.
BOUNDS = {
    HEADROOM: "upper bound on m, hence on psi, for THIS contrast's bar only",
    PSI: "this lever's discordance rate; delta <= psi is hard",
    PSI_DRAW: "NOT psi, and not a bound in either direction",
}

# Rungs `Gate.run` runs before the contract's acceptance command. A cell
# rejected here never reached acceptance, so its verdict is a statement about
# the bar and not about the problem's difficulty.
PRE_ACCEPTANCE = frozenset(
    {"syntax", "structure", "scope", "secrets", "format", "lint"}
)


@dataclass(frozen=True)
class Contrast:
    """A committed paired contrast: one lever, one tier, both arms, gate-scored."""

    tier: str
    lever: str
    stock: str
    ablated: str
    bar: str = "Gate.run"
    caveat: str = "greedy, one draw per condition"


@dataclass(frozen=True)
class DrawRun:
    """A committed multi-draw run, from which ``psi_draw`` can be read."""

    tier: str
    run: str
    draws: int
    bar: str
    caveat: str


# The committed material, declared here rather than passed in. Which run
# supplied a row decides that row's coverage caveat, so the run and its caveat
# have to travel together; a `--stock/--ablated` CLI would let a caller pair two
# runs whose caveats this table would then state wrongly.
CONTRASTS = (
    Contrast(
        tier="1.5B",
        lever="norule",
        stock="bench-null-gate-15b-a-2026-08-13",
        ablated="bench-control-norule-15b-2026-08-13",
    ),
    Contrast(
        tier="7B",
        lever="norule",
        stock="bench-null-gate-7b-a-2026-08-14",
        ablated="bench-control-norule-7b-2026-08-14",
    ),
)

DRAW_RUNS = (
    DrawRun(
        tier="1.5B",
        run="f1-responsiveness-15b-2026-08-11",
        draws=8,
        bar="acceptance only",
        caveat=(
            "f1 tranches (b228+) only, so no scaffolded cell is covered; "
            "predates Gate.run"
        ),
    ),
    DrawRun(
        tier="7B",
        run="bench-scaffold-ablation-7b-2026-08-11/stock",
        draws=7,
        bar="acceptance only",
        caveat="the 34 scaffold-eligible cells only; predates Gate.run",
    ),
    DrawRun(
        tier="3B",
        run="bench-scaffold-ablation-3b-2026-08-11/stock",
        draws=7,
        bar="acceptance only",
        caveat=(
            "the 34 scaffold-eligible cells only; predates Gate.run; a third "
            "tier, not one of #224's two"
        ),
    ),
)


@dataclass(frozen=True)
class Row:
    """One responsive fraction, and everything needed to not misread it."""

    tier: str
    arm: str
    stratum: str
    observable: str
    k: int
    n: int
    stratum_size: int
    source: str
    bar: str
    caveat: str

    @property
    def fraction(self) -> float:
        return self.k / self.n if self.n else 0.0

    @property
    def pooled(self) -> bool:
        """Whether this row is the arm-level aggregate rather than a stratum."""
        return self.stratum.startswith("ALL")


ARM_ROW = "ALL — not the bench's resolution"


@cache
def strata_of(arm: str) -> dict[str, set[str]]:
    """Task ids grouped by stratum, from ``resolution``'s definition of one.

    Cached: the grouping parses 257 contracts per arm and the corpus does not
    change inside a process, and this table reads it once per observable per
    source.
    """
    groups: dict[str, set[str]] = resolution.strata_of(arm)
    return groups


@cache
def _task_strata(arm: str) -> dict[str, tuple[str, bool]]:
    """``eligibility.strata`` for one arm, parsed once."""
    by_task: dict[str, tuple[str, bool]] = eligibility.strata(arm)
    return by_task


@cache
def headroom_and_psi(contrast: Contrast) -> list[Row]:
    """Both gate-scored observables off one committed contrast.

    ``headroom`` and ``psi`` are read from the same pair of runs, so they are
    derived together — a table where the two came from different pairs would
    silently compare a ceiling against a discordance rate it does not bound.
    """
    rows: list[Row] = []
    for arm in ARMS:
        stock = eligibility.greedy(MEASUREMENTS / contrast.stock, arm)
        ablated = eligibility.greedy(MEASUREMENTS / contrast.ablated, arm)
        groups = dict(strata_of(arm))
        groups[ARM_ROW] = set(stock)
        for stratum in sorted(groups):
            measured = eligibility.headroom(stock, ablated, groups[stratum])
            if not measured["n"]:
                continue
            size = len(groups[stratum])
            for observable, k in (
                (HEADROOM, measured["ceiling"]),
                (PSI, measured["m"]),
            ):
                rows.append(
                    Row(
                        tier=contrast.tier,
                        arm=arm,
                        stratum=stratum,
                        observable=observable,
                        k=k,
                        n=measured["n"],
                        stratum_size=size,
                        source=f"{contrast.stock} / {contrast.ablated}",
                        bar=contrast.bar,
                        caveat=f"lever `{contrast.lever}`; {contrast.caveat}",
                    )
                )
    return rows


@cache
def draw_rows(run: DrawRun) -> list[Row]:
    """``psi_draw`` per stratum, from one committed multi-draw run.

    ``responsiveness.cells`` and ``responsiveness.classify`` do the work; this
    only re-keys their output onto the strata ``resolution`` defines, so the
    three observables land on the same rows.
    """
    built = responsiveness.cells(MEASUREMENTS / run.run, run.draws)
    rows: list[Row] = []
    for arm in ARMS:
        by_task = _task_strata(arm)
        sizes = {name: len(ids) for name, ids in strata_of(arm).items()}
        seen: dict[str, list[str]] = defaultdict(list)
        for (cell_arm, task), cell in built.items():
            if cell_arm != arm or task not in by_task:
                continue
            kind, scaffolded = by_task[task]
            name = f"{kind}{'+scaffold' if scaffolded else ''}"
            seen[name].append(responsiveness.classify(cell))
            seen[ARM_ROW].append(responsiveness.classify(cell))
        for stratum in sorted(seen):
            kinds = seen[stratum]
            rows.append(
                Row(
                    tier=run.tier,
                    arm=arm,
                    stratum=stratum,
                    observable=PSI_DRAW,
                    k=sum(1 for k in kinds if k == "responsive"),
                    n=len(kinds),
                    stratum_size=sizes.get(stratum, sum(sizes.values())),
                    source=run.run,
                    bar=run.bar,
                    caveat=f"{run.draws} sampled draws + greedy; {run.caveat}",
                )
            )
    return rows


@cache
def never_reached_acceptance(contrast: Contrast) -> dict[tuple[str, str], int]:
    """Cells whose acceptance command never ran, under **either** condition.

    Not a fourth responsive fraction. It is the reconciliation between the other
    three: a cell rejected at ``lint`` or ``format`` failed before the problem
    was attempted, so its zero contribution to ``headroom`` is a fact about the
    bar. An **upper bound** on what a zero-token pre-gate formatting pass could
    recover — #113 measured +13.7pp for exactly that — and not a claim that any
    of these cells would then pass acceptance.
    """
    out: dict[tuple[str, str], int] = {}
    for arm in ARMS:
        verdicts: dict[str, list[str | None]] = defaultdict(list)
        for directory in (contrast.stock, contrast.ablated):
            path = MEASUREMENTS / directory / f"bench-{arm}" / "results.jsonl"
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("arm") == "greedy":
                    verdicts[row["task"]].append(row.get("rejected_by"))
        for stratum, ids in strata_of(arm).items():
            out[(arm, stratum)] = sum(
                1
                for task in ids
                if task in verdicts and all(v in PRE_ACCEPTANCE for v in verdicts[task])
            )
    return out


@cache
def derive() -> tuple[Row, ...]:
    """Every responsive fraction the committed runs support, no pooling."""
    rows: list[Row] = []
    for contrast in CONTRASTS:
        rows.extend(headroom_and_psi(contrast))
    for run in DRAW_RUNS:
        rows.extend(draw_rows(run))
    return tuple(rows)


def coverage_gaps(rows: tuple[Row, ...]) -> list[tuple[str, str, str, str]]:
    """(tier, arm, stratum, observable) cells no committed run can fill.

    Printed because an absent row is the finding A2 is scoped from, and an
    absent row is invisible in a table of present ones.
    """
    strata = sorted({r.stratum for r in rows if not r.pooled})
    have = {(r.tier, r.arm, r.stratum, r.observable) for r in rows}
    return [
        (tier, arm, stratum, observable)
        for tier in BAND_TIERS
        for arm in ARMS
        for stratum in strata
        for observable in (HEADROOM, PSI, PSI_DRAW)
        if (tier, arm, stratum, observable) not in have
    ]


def _banner(directories: list[Path]) -> list[str]:
    found = mode.read(*directories)
    return [mode.banner(found), revision.banner(found)]


def _row(row: Row) -> str:
    covered = (
        f"{row.n}" if row.n == row.stratum_size else f"{row.n} of {row.stratum_size}"
    )
    return (
        f"| {row.tier} | bench-{row.arm} | {row.stratum} | {row.observable} "
        f"| {covered} | {row.k} | {100 * row.fraction:.1f}% | {row.bar} "
        f"| {row.caveat} |"
    )


def report() -> list[str]:
    """The whole answer, as markdown, with no pooled figure anywhere in it."""
    lines: list[str] = [
        "# Responsive fraction, per (model + bar) x stratum — #224 A1",
        "",
        "Derived from committed runs only; no model was called. Every row names "
        "which of the three observables it is, because they disagree here by an "
        "order of magnitude and the disagreement is mostly the bar.",
        "",
        "| observable | what it is | what it bounds |",
        "|---|---|---|",
        f"| `{HEADROOM}` | cells passing under either condition of the named "
        f"contrast | {BOUNDS[HEADROOM]} |",
        f"| `{PSI}` | the named lever's measured discordance rate | {BOUNDS[PSI]} |",
        f"| `{PSI_DRAW}` | cells whose verdict varies across sampled draws | "
        f"{BOUNDS[PSI_DRAW]} |",
        "",
        "No row is pooled across tiers or across arms: `bench-py` and "
        "`bench-ts` are two bars, not a language contrast (ADR-0026, and "
        "`resolution.py`'s docstring). Rows marked "
        f"`{ARM_ROW}` are the arm aggregate and are printed only because a "
        "reader would otherwise compute one.",
    ]

    for contrast in CONTRASTS:
        lines += [
            "",
            f"## {contrast.tier}, gate-scored — lever `{contrast.lever}`",
            "",
        ]
        lines += _banner(
            [
                MEASUREMENTS / d / f"bench-{a}"
                for d in (contrast.stock, contrast.ablated)
                for a in ARMS
            ]
        )
        lines += [
            f"- `psi` is this lever's, not the bench's. Wall: m >= {WALL} (ADR-0019).",
            "",
            "| tier | bar | stratum | observable | n | k | fraction | scorer "
            "| coverage |",
            "|---|---|---|---|---:|---:|---:|---|---|",
        ]
        lines += [_row(r) for r in headroom_and_psi(contrast)]

    for run in DRAW_RUNS:
        lines += ["", f"## {run.tier}, draw-responsive — `{run.run}`", ""]
        lines += _banner([MEASUREMENTS / run.run / f"bench-{a}" for a in ARMS])
        lines += [
            f"- `{PSI_DRAW}` is {BOUNDS[PSI_DRAW]}. It is the cheapest "
            "available screen for dead cells, and it costs rig time rather "
            "than authoring.",
            "",
            "| tier | bar | stratum | observable | n | k | fraction | scorer "
            "| coverage |",
            "|---|---|---|---|---:|---:|---:|---|---|",
        ]
        lines += [_row(r) for r in draw_rows(run)]

    lines += [
        "",
        "## Why the three disagree — cells that never reached acceptance",
        "",
        "Not a fourth responsive fraction. Under `Gate.run` a cell rejected at "
        "`lint` or `format` never ran the contract's acceptance command, so its "
        "zero contribution to `headroom` is a fact about the bar rather than "
        "about the problem. This is an **upper bound** on what a zero-token "
        "pre-gate formatting pass could recover (#113 measured +13.7pp for "
        "exactly that), not a claim any of these cells would then pass.",
        "",
        "| tier | bar | stratum | n | never reached acceptance | share |",
        "|---|---|---|---:|---:|---:|",
    ]
    for contrast in CONTRASTS:
        blocked = never_reached_acceptance(contrast)
        for arm in ARMS:
            for stratum, ids in sorted(strata_of(arm).items()):
                count = blocked[(arm, stratum)]
                lines.append(
                    f"| {contrast.tier} | bench-{arm} | {stratum} | {len(ids)} "
                    f"| {count} | {100 * count / len(ids):.1f}% |"
                )

    gaps = coverage_gaps(derive())
    lines += [
        "",
        "## Coverage gaps — what no committed run can answer",
        "",
        f"{len(gaps)} of the {len(BAND_TIERS) * len(ARMS) * 3 * 3} "
        f"(tier x bar x stratum x observable) cells over #224's two tiers "
        f"({', '.join(BAND_TIERS)}) have no committed run behind them. An "
        "absent row is the finding A2 is scoped from, so it is printed rather "
        "than left as whitespace.",
        "",
        "| tier | bar | stratum | observable |",
        "|---|---|---|---|",
    ]
    lines += [f"| {t} | bench-{a} | {s} | {o} |" for t, a, s, o in gaps]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "The responsive fraction per (model + bar) x stratum, from "
            "committed runs (#224). Prints no pooled figure: see this module's "
            "docstring for why."
        )
    )
    parser.add_argument("--json", type=Path, help="write the derived rows here too")
    args = parser.parse_args(argv)

    print("\n".join(report()))
    if args.json:
        payload: list[dict[str, Any]] = [
            {
                "tier": r.tier,
                "arm": r.arm,
                "stratum": r.stratum,
                "observable": r.observable,
                "k": r.k,
                "n": r.n,
                "stratum_size": r.stratum_size,
                "fraction": r.fraction,
                "source": r.source,
                "bar": r.bar,
                "caveat": r.caveat,
            }
            for r in derive()
        ]
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
