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

**The two holes in the answer, and which of them is now closed.** A2 named two.

*Hole 1 — the bar — is closed, offline.* Every multi-draw run predates
``Gate.run`` scoring and its rows carry no ``rejected_by``, so every ``psi_draw``
this project has quoted was measured against the *acceptance proxy* rather than
the bench's bar, while ``headroom`` and ``psi`` beside it were gate-scored. The
candidate texts were on disk and a bar is a pure function of them, so
``tools/bench/gate_rescore.py`` re-scored all of them under ``Gate.run`` at zero
token cost. Both readings are reported below, per (tier, bar, stratum), and the
"How much of the gap was the scorer" table is the separation #224 asked for.

*Hole 2 — coverage — is not, and it needs the rigs.* No committed multi-draw run
covers the full corpus at any tier: the 1.5B's covers 135 of 257 tasks and two
of three strata, and the 7B's covers 34 of 257 and one stratum. Re-scoring
cannot manufacture a draw that was never dispatched, so this one stays open and
``coverage_gaps`` keeps printing it.

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
    caveat: str


# The two scorers the same draws can be read under. `psi_draw` was only ever
# available at the first until #224 A2 re-scored the saved candidates offline;
# both are reported, because the *difference* between them is the finding and a
# table showing only the second would hide it.
ACCEPTANCE_BAR = "acceptance only"
GATE_BAR = "Gate.run"

BARS: tuple[tuple[str, str, str], ...] = (
    (
        ACCEPTANCE_BAR,
        responsiveness.ACCEPTANCE_ROWS,
        "the scorer of the day; NOT the bench's bar",
    ),
    (
        GATE_BAR,
        responsiveness.GATE_ROWS,
        "same draws, re-scored offline by tools/bench/gate_rescore.py (#224 A2)",
    ),
)


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
        caveat="f1 tranches (b228+) only, so no scaffolded cell is covered",
    ),
    DrawRun(
        tier="7B",
        run="bench-scaffold-ablation-7b-2026-08-11/stock",
        draws=7,
        caveat="the 34 scaffold-eligible cells only",
    ),
    DrawRun(
        tier="3B",
        run="bench-scaffold-ablation-3b-2026-08-11/stock",
        draws=7,
        caveat=(
            "the 34 scaffold-eligible cells only; a third tier, not one of #224's two"
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
    #: For a ``psi_draw`` row: how many of the cell's draws passed anywhere in
    #: this stratum. Zero is the case that matters — see :meth:`readable`.
    passing_draws: int | None = None

    @property
    def fraction(self) -> float:
        return self.k / self.n if self.n else 0.0

    @property
    def pooled(self) -> bool:
        """Whether this row is the arm-level aggregate rather than a stratum."""
        return self.stratum.startswith("ALL")

    @property
    def readable(self) -> bool:
        """Whether this row's fraction carries information at all.

        A ``psi_draw`` of 0.0 has two completely different causes and the number
        cannot tell them apart. Either the cells were drawn repeatedly and never
        changed their verdict — a real finding about the material — or **not one
        draw in the stratum passed**, in which case every cell is pinned-fail by
        arithmetic and the zero is a restatement of the pass rate rather than a
        measurement of responsiveness.

        Under a strict enough bar the second is what happens, and it happened
        here: five of the six re-scored ablation *condition* directories fall to
        zero or near-zero passes under ``Gate.run``. A table that printed
        "psi_draw 0.0%" for those would report the instrument's silence as the
        material's deadness, so this says so instead.
        """
        return self.observable != PSI_DRAW or bool(self.passing_draws)

    @property
    def thin(self) -> bool:
        """Whether the numerator is below ADR-0019's wall of six.

        Not a validity threshold for ``psi_draw`` itself — it is a descriptive
        rate and is what it is. It is the threshold below which the *decision*
        the rate is quoted toward cannot be reached at any effect size, so a row
        under it must not be read as sizing evidence.
        """
        return self.observable == PSI_DRAW and self.k < WALL


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


def bars_available(run: DrawRun) -> tuple[tuple[str, str, str], ...]:
    """The bars this run's rows exist for, on disk, right now.

    A bar is offered only when **both** arms carry its rows file. A `psi_draw`
    read from one gate-scored arm and one acceptance-scored arm would be a
    figure whose two halves were produced by different scorers, and the arm is
    the bar — that is this module's own first objection to pooling.
    """
    return tuple(
        (label, rows_name, note)
        for label, rows_name, note in BARS
        if all(
            (MEASUREMENTS / run.run / f"bench-{arm}" / rows_name).is_file()
            for arm in ARMS
        )
    )


@cache
def draw_rows(run: DrawRun) -> list[Row]:
    """``psi_draw`` per stratum, from one committed multi-draw run, per bar.

    ``responsiveness.cells`` and ``responsiveness.classify`` do the work; this
    only re-keys their output onto the strata ``resolution`` defines, so the
    three observables land on the same rows.

    Both bars are emitted where both exist. The gate-scored rows are the ones
    comparable with ``headroom`` and ``psi``; the acceptance-only rows are kept
    beside them because every ``psi_draw`` this project has quoted is one of
    them, and a table that silently replaced them would leave those quotes
    looking merely stale rather than measured against a different bar.
    """
    rows: list[Row] = []
    for bar, rows_name, note in bars_available(run):
        built = responsiveness.cells(MEASUREMENTS / run.run, run.draws, rows_name)
        for arm in ARMS:
            by_task = _task_strata(arm)
            sizes = {name: len(ids) for name, ids in strata_of(arm).items()}
            seen: dict[str, list[str]] = defaultdict(list)
            # Passing draws per stratum, counted alongside the classification.
            # A `psi_draw` of zero means one of two opposite things and only
            # this number separates them — see `Row.readable`.
            passing: dict[str, int] = defaultdict(int)
            for (cell_arm, task), cell in built.items():
                if cell_arm != arm or task not in by_task:
                    continue
                kind, scaffolded = by_task[task]
                name = f"{kind}{'+scaffold' if scaffolded else ''}"
                seen[name].append(responsiveness.classify(cell))
                seen[ARM_ROW].append(responsiveness.classify(cell))
                drew = int(cell["greedy"]) + sum(cell["sampled"])
                passing[name] += drew
                passing[ARM_ROW] += drew
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
                        bar=bar,
                        passing_draws=passing[stratum],
                        caveat=(
                            f"{run.draws} sampled draws + greedy; {run.caveat}; {note}"
                        ),
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
def scorer_effect() -> tuple[dict[str, Any], ...]:
    """How much of the ``psi_draw`` / ``headroom`` gap was the scorer, per stratum.

    This is #224 A2 hole 1's answer and the reason the re-score was worth doing.
    Until it existed the project compared a ``psi_draw`` measured by the
    acceptance command alone against a ``headroom`` measured by ``Gate.run``,
    and could not say what share of the distance between them was the
    observable and what share was the bar. Now the same draws are read under
    both scorers, so the two effects separate.

    Reported per (tier, bar, stratum) and never pooled — ADR-0019 D2 and
    ADR-0026, and both of ``resolution.py``'s objections apply here unchanged.
    The ``headroom`` column is drawn from the contrast at the **same** tier and
    arm, and is left absent rather than substituted when there is none: a
    ratio against another tier's ceiling would be arithmetic, not evidence.
    """
    ceilings = {
        (r.tier, r.arm, r.stratum): r
        for contrast in CONTRASTS
        for r in headroom_and_psi(contrast)
        if r.observable == HEADROOM
    }
    out: list[dict[str, Any]] = []
    for run in DRAW_RUNS:
        by_key = {
            (r.arm, r.stratum, r.bar): r
            for r in draw_rows(run)
            if r.observable == PSI_DRAW
        }
        for arm, stratum, bar in sorted(by_key):
            if bar != ACCEPTANCE_BAR:
                continue
            before = by_key[(arm, stratum, ACCEPTANCE_BAR)]
            after = by_key.get((arm, stratum, GATE_BAR))
            if after is None:
                continue
            ceiling = ceilings.get((run.tier, arm, stratum))
            # The arm-level row is never given a ratio against `headroom`, and
            # not only because it is pooled. Its two sides are measured over
            # *different material*: `headroom` spans all 257 tasks while this
            # run's draws cover 34 or 135 of them, so the quotient divides a
            # rate on one set by a rate on another. Left blank rather than
            # printed with a warning — a printed number gets quoted.
            if before.pooled:
                ceiling = None
            out.append(
                {
                    "tier": run.tier,
                    "arm": arm,
                    "stratum": stratum,
                    "n": before.n,
                    "before_k": before.k,
                    "before": before.fraction,
                    "after_k": after.k,
                    "after": after.fraction,
                    # Percentage points of `psi_draw` that were the scorer
                    # rather than the draw. Signed: a re-score can only remove
                    # passes, but removing passes can *create* a responsive cell
                    # (a cell pinned-pass under acceptance becomes mixed once
                    # some draws are rejected), so the sign is not decidable in
                    # advance and is read rather than assumed.
                    "scorer_pp": 100 * (after.fraction - before.fraction),
                    # The direct answer to "how much of the gap was the
                    # scorer": the share of the distance between `psi_draw` and
                    # `headroom` that closed when the two were put on one bar.
                    # Measured in percentage points of that distance, not as a
                    # ratio of ratios — a ratio of two ratios is not a share of
                    # anything, and this number is quoted as a share.
                    "scorer_share": (
                        (before.fraction - after.fraction)
                        / (before.fraction - ceiling.fraction)
                        if ceiling and before.fraction > ceiling.fraction
                        else None
                    ),
                    # Whether the re-scored figure carries information at all,
                    # and whether its numerator clears ADR-0019's wall. Under a
                    # strict bar a stratum can be driven to zero passing draws,
                    # and a `psi_draw` of 0.0 read off that is the instrument's
                    # silence rather than the material's deadness.
                    "after_readable": after.readable,
                    "after_thin": after.thin,
                    "after_passing_draws": after.passing_draws,
                    "headroom": ceiling.fraction if ceiling else None,
                    "gap_before": (
                        before.fraction / ceiling.fraction
                        if ceiling and ceiling.fraction
                        else None
                    ),
                    "gap_after": (
                        after.fraction / ceiling.fraction
                        if ceiling and ceiling.fraction
                        else None
                    ),
                    "pooled": before.pooled,
                }
            )
    return tuple(out)


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

    **Only gate-scored rows count as coverage**, and that is the correction #224
    A2 forced. An acceptance-only ``psi_draw`` is a real measurement of a real
    thing, but it is not the quantity the table's other two columns are: laying
    it in the same cell would report a hole as filled by a figure measured
    against a different bar, which is the exact error the re-score exists to
    remove. A stratum whose only ``psi_draw`` is acceptance-scored is still a
    gap.
    """
    strata = sorted({r.stratum for r in rows if not r.pooled})
    have = {
        (r.tier, r.arm, r.stratum, r.observable)
        for r in rows
        if r.bar != ACCEPTANCE_BAR and r.readable
    }
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
    # A fraction is printed only where it means something. An unreadable row
    # shows the reason in the fraction's own column rather than a number with a
    # footnote, because the number is what gets quoted.
    if not row.readable:
        fraction = "unreadable — no draw passed"
    elif row.thin:
        fraction = f"{100 * row.fraction:.1f}% (k<{WALL})"
    else:
        fraction = f"{100 * row.fraction:.1f}%"
    return (
        f"| {row.tier} | bench-{row.arm} | {row.stratum} | {row.observable} "
        f"| {covered} | {row.k} | {fraction} | {row.bar} "
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

    effect = scorer_effect()
    if effect:
        lines += [
            "",
            "## How much of the gap was the scorer — #224 A2, hole 1",
            "",
            "The same saved draws, read twice: once under the acceptance "
            "command alone (the scorer of the day) and once under `Gate.run` "
            "(the bench's bar), by `tools/bench/gate_rescore.py`. No model was "
            "called and no rig was touched — the candidates were already on "
            "disk, and a bar is a pure function of them.",
            "",
            "`gap` is `psi_draw / headroom` at the **same** tier and bar. It is "
            "the quantity #224 could not previously interpret, because its "
            "numerator and denominator were measured by different scorers. "
            "Where no contrast covers a cell the ratio is left blank rather "
            "than taken against another tier's ceiling.",
            "`share` is the answer in one number: the fraction of the distance "
            "between `psi_draw` and `headroom` that closed when the two were "
            "put on one bar. It is **not** one figure for the bench — it ranges "
            "from a fifteenth to two thirds across the strata below, which is "
            "why ADR-0019 D2 and ADR-0026 forbid a pooled answer here.",
            "",
            "| tier | bar | stratum | n | `psi_draw` acceptance | `psi_draw` "
            "`Gate.run` | scorer | share of gap | `headroom` | gap before "
            "| gap after |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in effect:
            ceiling = (
                f"{100 * row['headroom']:.1f}%" if row["headroom"] is not None else "—"
            )
            before = (
                f"{row['gap_before']:.1f}x" if row["gap_before"] is not None else "—"
            )
            after = f"{row['gap_after']:.1f}x" if row["gap_after"] is not None else "—"
            share = (
                f"{100 * row['scorer_share']:.0f}%"
                if row["scorer_share"] is not None
                else "—"
            )
            if not row["after_readable"]:
                shown = "unreadable — no draw passed"
            elif row["after_thin"]:
                shown = f"{100 * row['after']:.1f}% ({row['after_k']}, k<{WALL})"
            else:
                shown = f"{100 * row['after']:.1f}% ({row['after_k']})"
            lines.append(
                f"| {row['tier']} | bench-{row['arm']} | {row['stratum']} "
                f"| {row['n']} | {100 * row['before']:.1f}% ({row['before_k']}) "
                f"| {shown} "
                f"| {row['scorer_pp']:+.1f}pp | {share} | {ceiling} | {before} "
                f"| {after} |"
            )
        lines += [
            "",
            "**Two things the re-scored column says that the acceptance column "
            "could not.** First, `pinned-pass` falls to **zero in every stratum "
            "here**: under the bench's own bar not one cell passes on every "
            "draw, so gate-scored `psi_draw` is no longer distinguishable from "
            "*cells that ever pass at all*. Second, the gap **never closes** — "
            "after both are put on one bar `psi_draw` still runs 2.2x to 6.0x "
            "`headroom`, so the two remain different quantities and neither "
            "substitutes for the other.",
        ]

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
                # Carried into the machine-readable form too. A consumer that
                # read `fraction` alone could quote a 0.0 that means "nothing
                # passed, so responsiveness is unobservable" as though it meant
                # "nothing responded" — the exact confusion the printed table
                # refuses to allow.
                "passing_draws": r.passing_draws,
                "readable": r.readable,
                "below_wall": r.thin,
            }
            for r in derive()
        ]
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        effects = args.json.with_name(args.json.stem + "-scorer-effect.json")
        effects.write_text(
            json.dumps(list(scorer_effect()), indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
