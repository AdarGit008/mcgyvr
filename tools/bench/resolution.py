"""What the bench can resolve, per stratum, and never pooled.

Issue: `#266 <https://github.com/AdarGit008/mcgyvr/issues/266>`_.
Doctrine: ADR-0019 D2 (the null is measured per target tier and does not
transfer up the ladder) and ADR-0026's consequence — *a report refuses a pooled
figure across a stratum where the effect is heterogeneous, and reports per
stratum instead*.

``tools/power/mde.py`` holds the arithmetic. This module supplies it the two
things it needs from a real contrast — the eligible cell count and the measured
discordance rate ``psi`` — **per stratum**, and prints what each can and cannot
resolve.

**Why there is no pooled row, and why that is not a formatting choice.** Pooling
was tried on 2026-08-14 and produced a figure that describes nothing. Two
separate objections, either sufficient:

1. **Across arms.** ``bench-py`` and ``bench-ts`` are not a language contrast.
   They are two bars — 328 ruff rules against 66 eslint, prettier unconfigured on
   one side, no staged ``tsconfig.json`` so no type check at all (#262). A figure
   pooled over them describes neither instrument.
2. **Within an arm.** Measured over the committed ``norule`` contrasts, ``psi``
   ranges **0.029 to 0.134 across task types inside a single arm** — a 4.6x
   spread. That is the heterogeneity ADR-0026 forbids pooling over, and the
   pooled number is readable only because a dead stratum averaged with a live one
   lands somewhere plausible.

The arm-level row is printed because a reader will otherwise compute it, and it
is marked so it cannot be quoted as the bench's resolution.

**``psi`` belongs to the pair, not to the task set.** It is a property of
(instrument, lever): the rate at which *this* lever flips *this* material. A
resolution computed from ``norule`` describes what a ``norule``-sized
manipulation can be read at, and a new arm computes its own. There is no single
number for "the bench".

**What this module cannot key on yet.** The honest unit is a *signature* — the
model, bar and condition as content rather than as names (#265, ADR-0026's
consequence). Until those digests exist, the columns below are keyed on
``tier`` and ``arm``, which are labels for the properties that actually differ.
Two runs agreeing on both labels and differing in the bar would be laid side by
side here without complaint.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _by_path(name: str, path: Path) -> types.ModuleType:
    """Load a sibling rig by path — `tools/` is not a package, and the
    convention `tools/bench/report.py` set is followed rather than re-invented."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# #231 checks 3 and 6: this module states figures read off runs, so it declares
# the mode and the pinned revision they were produced under.
eligibility = _by_path("bench_eligibility_res", HERE / "eligibility.py")
mde = _by_path("power_mde_res", REPO / "tools" / "power" / "mde.py")
mode = _by_path("bench_mode_res", HERE / "mode.py")
revision = _by_path("bench_product_res", HERE / "product.py")

ARMS = ("py", "ts")

# The wall below which no split of discordant pairs reaches significance, from
# ADR-0019: the best-case two-sided exact p is 2 / 2**m.
WALL = 6


@dataclass(frozen=True)
class Resolution:
    """One stratum's power to resolve a contrast of the lever it was measured on."""

    tier: str
    arm: str
    stratum: str
    n: int
    discordant: int
    psi: float
    detectable: float | None

    @property
    def reachable(self) -> bool:
        """Whether any effect size at all could clear ADR-0019's wall here."""
        return self.detectable is not None


def strata_of(arm: str) -> dict[str, set[str]]:
    """Task ids grouped by the stratum that actually moves ``psi``.

    Task type, and whether a scaffold is present — the pair #266 measured a
    19x pass-rate spread over. Not language: language is the axis these groups
    are computed *within*.
    """
    groups: dict[str, set[str]] = {}
    for task, (kind, scaffolded) in eligibility.strata(arm).items():
        groups.setdefault(f"{kind}{'+scaffold' if scaffolded else ''}", set()).add(task)
    return groups


def measure(
    tier: str, arm: str, stock: Path, ablated: Path
) -> tuple[list[Resolution], Resolution]:
    """Every stratum on one arm, plus the arm-level row it must not be reduced to."""
    before = eligibility.greedy(stock, arm)
    after = eligibility.greedy(ablated, arm)

    def one(name: str, ids: set[str]) -> Resolution:
        paired = sorted(t for t in ids if t in before and t in after)
        discordant = sum(1 for t in paired if before[t] != after[t])
        psi = discordant / len(paired) if paired else 0.0
        detectable = mde.detectable_delta(len(paired), psi) if psi > 0 else None
        return Resolution(tier, arm, name, len(paired), discordant, psi, detectable)

    groups = strata_of(arm)
    return (
        [one(name, groups[name]) for name in sorted(groups)],
        one("ALL — not the bench's resolution", set(before)),
    )


def _row(r: Resolution) -> str:
    reach = f"{r.detectable * 100:.1f}pp" if r.detectable else "**not reachable**"
    return (
        f"| {r.tier} | bench-{r.arm} | {r.stratum} | {r.n} | {r.psi:.3f} "
        f"| {r.discordant} | {reach} |"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Per-stratum resolution of a paired contrast (#266). Prints no "
            "pooled figure: see this module's docstring for why."
        )
    )
    parser.add_argument("--tier", required=True, help="label for the model under test")
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--ablated", type=Path, required=True)
    parser.add_argument(
        "--lever", default="unnamed", help="the lever psi was measured on"
    )
    args = parser.parse_args(argv)

    found = mode.read(
        *[d / f"bench-{a}" for d in (args.stock, args.ablated) for a in ARMS]
    )
    print(f"## Resolution — {args.tier}, lever `{args.lever}`\n")
    print(mode.banner(found))
    print(revision.banner(found))
    print(
        f"- psi is this lever's, not the bench's: a contrast of a different "
        f"lever resolves differently. Wall: m >= {WALL} (ADR-0019).\n"
    )
    print("| tier | arm | stratum | n | psi | m | detectable at 80% |")
    print("|---|---|---|---:|---:|---:|---:|")
    rows: list[Resolution] = []
    for arm in ARMS:
        per_stratum, arm_row = measure(args.tier, arm, args.stock, args.ablated)
        rows.extend(per_stratum)
        for r in per_stratum:
            print(_row(r))
        print(_row(arm_row))

    live = [r for r in rows if r.reachable]
    spread = max(r.psi for r in rows) / min(r.psi for r in rows if r.psi > 0)
    print(
        f"\n**{len(live)} of {len(rows)} strata can resolve anything at all.** "
        f"psi spreads {spread:.1f}x across strata, which is why no pooled figure "
        f"is printed (ADR-0026)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
