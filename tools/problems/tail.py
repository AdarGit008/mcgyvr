#!/usr/bin/env python3
"""#212 — is the pool's hard tail a harder set, or a set that is harder to state?

#197's 14B TypeScript sweep covered 269 problems. The 80 admitted in batches
6-7 read markedly harder than the 189 the earlier 7B sweep had seen, and they
refused the parser ~4x as often (12.1% against 3.2%). Two readings were on the
table: the problems are harder, or the problems are *stated* worse and the
model's replies show it.

This instrument reads sweeps already on disk and separates three things the
headline rate confounds.

**Refusal shape.** A refusal code is not a diagnosis. ``incomplete-reply`` is
raised by :func:`mcgyvr.worker.reply.parse_reply` on the *stop reason*, before
a single fence is scanned, so it says the backend ran out of room and says
nothing about the text. ``no-fenced-block`` and ``ambiguous-blocks`` are the
codes that read the reply. :func:`refusal_shape` re-reads the pinned candidate
(ADR-0016 keeps every one) and reports what the reply actually looks like —
how much prose precedes the first fence, how many fences there are, whether
the last one closes. A refusal set that is all stop-reason and no prose is an
output-cap finding; one with preambles and stray blocks is a reply-format
finding, and they belong to different issues.

**Size, held constant.** Reply length is what fills an output cap, and the
reference solution is the closest thing on disk to a lower bound on it. If the
newer batches simply contain bigger problems, then both their truncation rate
and their pass rate are predicted by size alone and batch membership adds
nothing. :func:`standardise` reweights one set's per-stratum rates to the
other's size distribution, so the two are compared at like size.

**A thin stratum is not evidence.** The reweighting is only as good as its
smallest cell, so :func:`standardise` is always reported with the bootstrap
interval from :func:`bootstrap_gap` and the per-stratum counts beside it. An
adjusted gap whose interval spans zero has not settled anything, and the point
estimate must not be quoted alone.

What no amount of re-reading can settle is whether the residual is difficulty:
that needs a second model over the same ids, which is a sweep, not an
analysis. ``--compare`` folds one in once it exists.

Usage::

    # the disk read: two sweeps, the newer one's extra tasks against its shared ones
    uv run --no-sync python tools/problems/tail.py \\
        --sweep records/measurements/pool-sweep-14b-2026-08-07/srv2-ts \\
        --baseline records/measurements/pool-sweep-2026-08-07/srv1-ts

    # with the confirming sweep of the same extra ids by the baseline's model
    uv run --no-sync python tools/problems/tail.py \\
        --sweep records/measurements/pool-sweep-14b-2026-08-07/srv2-ts \\
        --baseline records/measurements/pool-sweep-2026-08-07/srv1-ts \\
        --compare records/measurements/pool-sweep-7b-batch67-2026-08-08
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / "tools" / "problems" / "tasks"

#: Strata are reference-solution line counts. The edges are quartile-ish over
#: the 269-problem pool rather than round numbers, and they are fixed here so
#: that a rerun cannot tune them until the gap says what it wanted to say.
SIZE_EDGES: tuple[int, ...] = (0, 35, 50, 70)

#: Refusal codes raised before the reply text is read. Everything else in
#: :mod:`mcgyvr.worker.reply` is a judgement about the text itself.
STOP_REASON_CODES = frozenset({"incomplete-reply"})

BOOTSTRAP_RESAMPLES = 4000
BOOTSTRAP_SEED = 212

_FENCE = re.compile(r"^(`{3,}|~{3,})[ \t]*([^\s`~]*)", re.MULTILINE)


@dataclass(frozen=True)
class Shape:
    """What a reply looks like, independent of why it was refused."""

    preamble_chars: int
    """Characters before the first fence. ``-1`` when there is no fence."""

    fences: int
    """Count of fence markers — an opener and its closer are two."""

    info_string: str
    """Info string of the first fence, ``""`` for a bare fence."""

    closed: bool
    """Whether the reply ends on a fence marker."""

    @property
    def reads_as(self) -> str:
        if self.fences == 0:
            return "no fence: bare text"
        if self.preamble_chars > 0:
            return f"prose preamble ({self.preamble_chars} chars)"
        if not self.closed:
            return "fence opened, never closed"
        if self.fences > 2:
            return f"{self.fences // 2} blocks"
        return "one closed block"


def refusal_shape(text: str) -> Shape:
    """Classify a raw reply. Pure text: no contract, no stop reason."""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    markers = list(_FENCE.finditer(normalised))
    if not markers:
        return Shape(preamble_chars=-1, fences=0, info_string="", closed=False)
    return Shape(
        preamble_chars=markers[0].start(),
        fences=len(markers),
        info_string=markers[0].group(2),
        closed=normalised.rstrip().endswith(markers[-1].group(1)),
    )


def load_rows(directory: Path) -> list[dict[str, Any]]:
    path = directory / "results.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def reference_lines(task_id: str, arm: str = "ts") -> int:
    """Lines in the task's reference solution — the size proxy."""
    suffix = "ts" if arm == "ts" else "py"
    return len(
        (TASKS / suffix / task_id / f"reference.{suffix}").read_text().splitlines()
    )


def stratum(lines: int) -> int:
    """Index of the size stratum a task falls in."""
    for index in range(len(SIZE_EDGES) - 1, -1, -1):
        if lines >= SIZE_EDGES[index]:
            return index
    return 0


def per_task(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Collapse draws to one rate per task — the unit a stratum averages over."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        seen = out.setdefault(row["task"], {"draws": 0, "passed": 0, "truncated": 0})
        seen["draws"] += 1
        seen["passed"] += bool(row["passed"])
        seen["truncated"] += row["stop_reason"] == "truncated"
    for seen in out.values():
        seen["pass_rate"] = seen["passed"] / seen["draws"]
        seen["truncation_rate"] = seen["truncated"] / seen["draws"]
    return out


def standardise(
    rates: dict[str, float], sizes: dict[str, int], weights: dict[int, int]
) -> float | None:
    """Reweight ``rates`` to ``weights``' distribution over size strata.

    Strata the group does not populate are dropped from both numerator and
    denominator: an empty cell has no rate to carry, and inventing one would
    be the assumption the whole exercise is meant to avoid. ``None`` when no
    stratum is shared, which is not a small gap but no comparison at all.
    """
    total = 0.0
    weighed = 0.0
    for index, weight in weights.items():
        members = [task for task in rates if stratum(sizes[task]) == index]
        if not members or weight == 0:
            continue
        total += weight * statistics.mean(rates[task] for task in members)
        weighed += weight
    return total / weighed if weighed else None


def bootstrap_gap(
    baseline: dict[str, float],
    other: dict[str, float],
    sizes: dict[str, int],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Percentile interval for the size-adjusted gap, resampling both groups.

    The tasks are the sampling unit, not the draws: three draws of one problem
    are one observation of that problem's difficulty, and resampling rows
    would treat them as three.
    """
    rng = random.Random(seed)
    keys_a, keys_b = list(baseline), list(other)
    draws: list[float] = []
    for _ in range(resamples):
        pick_a = [rng.choice(keys_a) for _ in keys_a]
        pick_b = [rng.choice(keys_b) for _ in keys_b]
        gap = _adjusted_gap(
            {f"{key}#{i}": baseline[key] for i, key in enumerate(pick_a)},
            {f"{key}#{i}": other[key] for i, key in enumerate(pick_b)},
            {
                **{f"{key}#{i}": sizes[key] for i, key in enumerate(pick_a)},
                **{f"{key}#{i}": sizes[key] for i, key in enumerate(pick_b)},
            },
        )
        if gap is not None:
            draws.append(gap)
    draws.sort()
    low = draws[int(0.025 * len(draws))]
    high = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
    return low, high


def _adjusted_gap(
    baseline: dict[str, float], other: dict[str, float], sizes: dict[str, int]
) -> float | None:
    weights = {index: 0 for index in range(len(SIZE_EDGES))}
    for task in baseline:
        weights[stratum(sizes[task])] += 1
    reference = standardise(baseline, sizes, weights)
    adjusted = standardise(other, sizes, weights)
    if reference is None or adjusted is None:
        return None
    return reference - adjusted


def report(
    sweep: Path, baseline: Path, compare: Path | None = None
) -> tuple[str, dict[str, Any]]:
    """The whole read, as text for a human and a dict for a record."""
    rows = load_rows(sweep)
    base_rows = load_rows(baseline)
    manifest = json.loads((sweep / "run.json").read_text())

    extra = {row["task"] for row in rows} - {row["task"] for row in base_rows}
    shared = {row["task"] for row in rows} & {row["task"] for row in base_rows}
    if not extra:
        raise SystemExit(
            "the sweep covers no task the baseline missed: nothing to split"
        )

    sizes = {task: reference_lines(task) for task in extra | shared}
    lines: list[str] = []
    out: dict[str, Any] = {
        "model": manifest["model"],
        "cap": manifest["max_output_tokens"],
    }

    lines.append(
        f"# {sweep.name} — {manifest['model']}, cap {manifest['max_output_tokens']}"
    )
    lines.append(
        f"\n{len(shared)} tasks shared with {baseline.name}, {len(extra)} extra.\n"
    )

    # --- the headline split, and what survives conditioning on a whole reply
    lines.append(
        "| set | tasks | rows | passed | refused | pass, complete replies only |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for name, group in (("shared", shared), ("extra", extra)):
        sub = [row for row in rows if row["task"] in group]
        whole = [row for row in sub if row["stop_reason"] == "complete"]
        passed = sum(bool(row["passed"]) for row in sub)
        refused = sum(row["parse_error"] is not None for row in sub)
        conditional = sum(bool(row["passed"]) for row in whole) / len(whole)
        lines.append(
            f"| {name} | {len(group)} | {len(sub)} "
            f"| {passed} ({passed / len(sub):.1%}) "
            f"| {refused} ({refused / len(sub):.1%}) | {conditional:.1%} |"
        )
        out[name] = {
            "tasks": len(group),
            "rows": len(sub),
            "passed": passed,
            "refused": refused,
            "pass_rate": passed / len(sub),
            "pass_rate_complete_only": conditional,
        }

    # --- what the refusals are, before anyone calls them a parse problem
    refusals = [row for row in rows if row["parse_error"] is not None]
    codes: dict[str, int] = {}
    shapes: dict[str, int] = {}
    for row in refusals:
        codes[row["parse_error"]] = codes.get(row["parse_error"], 0) + 1
        candidate = (
            sweep / "candidates" / row["task"] / f"{row['arm']}-{row['draw']}.txt"
        )
        if candidate.exists():
            reads_as = refusal_shape(candidate.read_text()).reads_as
            shapes[reads_as] = shapes.get(reads_as, 0) + 1
    stop_reason_only = sum(
        count for code, count in codes.items() if code in STOP_REASON_CODES
    )
    lines.append(f"\n## The {len(refusals)} refusals\n")
    for code, count in sorted(codes.items(), key=lambda kv: -kv[1]):
        origin = (
            "raised on the stop reason"
            if code in STOP_REASON_CODES
            else "read the text"
        )
        lines.append(f"- `{code}` x{count} — {origin}")
    lines.append("\nWhat the replies look like:\n")
    for shape, count in sorted(shapes.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {shape} x{count}")
    ever = {row["task"] for row in refusals}
    never = sorted(set(sizes) - ever)
    if ever and never:
        lines.append(
            f"\n{len(ever)} of {len(sizes)} tasks refused at least once. Their "
            f"reference solutions run {statistics.median(sizes[t] for t in ever):.0f} "
            f"lines at the median against "
            f"{statistics.median(sizes[t] for t in never):.0f} "
            f"for the tasks that never refused."
        )
    out["refusals"] = {
        "total": len(refusals),
        "codes": codes,
        "shapes": shapes,
        "attributable_to_the_cap": stop_reason_only,
        "tasks_that_ever_refused": len(ever),
    }

    # --- size, and whether it explains the split
    tasks_shared = per_task([row for row in rows if row["task"] in shared])
    tasks_extra = per_task([row for row in rows if row["task"] in extra])
    lines.append("\n## Held at like size\n")
    lines.append(
        "| ref lines | shared: tasks, pass, refused | extra: tasks, pass, refused |"
    )
    lines.append("|---|---|---|")
    for index in range(len(SIZE_EDGES)):
        edge_low = SIZE_EDGES[index]
        edge_high = SIZE_EDGES[index + 1] if index + 1 < len(SIZE_EDGES) else None
        cells = []
        for collapsed in (tasks_shared, tasks_extra):
            members = [t for t in collapsed if stratum(sizes[t]) == index]
            if not members:
                cells.append("—")
                continue
            passing = statistics.mean(collapsed[t]["pass_rate"] for t in members)
            cut = statistics.mean(collapsed[t]["truncation_rate"] for t in members)
            cells.append(f"{len(members)}, {passing:.1%}, {cut:.1%}")
        lines.append(f"| {edge_low}-{edge_high or '+'} | {cells[0]} | {cells[1]} |")

    rates_shared = {t: v["pass_rate"] for t, v in tasks_shared.items()}
    rates_extra = {t: v["pass_rate"] for t, v in tasks_extra.items()}
    crude = statistics.mean(rates_shared.values()) - statistics.mean(
        rates_extra.values()
    )
    adjusted = _adjusted_gap(rates_shared, rates_extra, sizes)
    low, high = bootstrap_gap(rates_shared, rates_extra, sizes)
    if adjusted is None:
        tail = "Size-adjusted: no shared stratum — the sets do not overlap in size."
    else:
        tail = (
            f"Size-adjusted **{adjusted:+.1%}**, 95% bootstrap "
            f"[{low:+.1%}, {high:+.1%}] over {BOOTSTRAP_RESAMPLES} resamples "
            f"(seed {BOOTSTRAP_SEED}), tasks resampled, not draws."
        )
    lines.append(f"\nCrude gap **{crude:+.1%}**. {tail}")
    out["gap"] = {"crude": crude, "size_adjusted": adjusted, "ci95": [low, high]}

    # --- the second model over the same ids, if it has been run
    if compare is not None:
        compare_rows = load_rows(compare)
        compare_manifest = json.loads((compare / "run.json").read_text())
        covered = {row["task"] for row in compare_rows}
        if covered != extra:
            raise SystemExit(
                f"--compare covers {len(covered)} tasks, not the "
                f"{len(extra)} extra ones; a different task set is a "
                "different question"
            )
        base_shared = [row for row in base_rows if row["task"] in shared]
        passed_base = sum(bool(row["passed"]) for row in base_shared)
        passed_cmp = sum(bool(row["passed"]) for row in compare_rows)
        refused_cmp = sum(row["parse_error"] is not None for row in compare_rows)
        lines.append(
            f"\n## {compare_manifest['model']} over the same {len(extra)} ids\n"
        )
        lines.append("| set | rows | passed | refused |")
        lines.append("|---|---:|---:|---:|")
        lines.append(
            f"| its own {len(shared)} | {len(base_shared)} | {passed_base} "
            f"({passed_base / len(base_shared):.1%}) | "
            f"{sum(r['parse_error'] is not None for r in base_shared)} |"
        )
        lines.append(
            f"| the extra {len(extra)} | {len(compare_rows)} | {passed_cmp} "
            f"({passed_cmp / len(compare_rows):.1%}) | {refused_cmp} "
            f"({refused_cmp / len(compare_rows):.1%}) |"
        )
        out["compare"] = {
            "model": compare_manifest["model"],
            "shared_pass_rate": passed_base / len(base_shared),
            "extra_pass_rate": passed_cmp / len(compare_rows),
            "extra_refusal_rate": refused_cmp / len(compare_rows),
        }

    return "\n".join(lines), out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sweep", type=Path, required=True, help="the wider sweep")
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="the sweep whose task set is the subset",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        help="a sweep of exactly the extra ids by another model: "
        "the difficulty control",
    )
    parser.add_argument("--json", type=Path, help="also write the figures here")
    args = parser.parse_args()

    text, figures = report(args.sweep, args.baseline, args.compare)
    print(text)
    if args.json:
        args.json.write_text(json.dumps(figures, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
