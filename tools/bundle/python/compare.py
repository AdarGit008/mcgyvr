#!/usr/bin/env python3
"""#167 — the four readings of the bundle ladder, laid side by side.

CLM-0012 measured the JS/TS bundle flat and had to scope the finding, because
the data could not say which of two things it was about:

* **Language** — the bundle device works in Python and not in JS/TS.
* **Serving stack** — the device does not work *here*. CLM-0004 drove the
  Q4_K_M blob through bare ``llama-server``; CLM-0012 drove the same blob
  through Ollama's OpenAI-compatible path.

They have opposite consequences, so the difference is worth an arm. This tool
does no measuring; it reads rows that already exist and prints the comparison
the measurement record is written from. Four row sets, and the pairs between
them are what separate the readings:

======================  ==========  =========  ===============  =============
row set                 task set    stack      harness          isolates
======================  ==========  =========  ===============  =============
``clm0004``             Python      llama.cpp  local-ai         —
``original``            Python      Ollama     local-ai         **stack**
``rig``                 Python      Ollama     mcgyvr           **harness**
``jsts``                JS/TS       Ollama     mcgyvr           **language**
======================  ==========  =========  ===============  =============

Each row down that table changes exactly one thing from the row above it, which
is the only reason a difference between two of them can be attributed to
anything. ``clm0004`` → ``original`` is the control #167 was opened for.

All four use CLM-0004's columns, so one loader reads them all.

Usage::

    uv run --no-sync python tools/bundle/python/compare.py \\
        --out records/measurements/python-bundle-YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LADDER = ("c0", "c1", "c2", "c3")

# n=20, one greedy seed. CLM-0004's design declares +-1 task the noise floor and
# only direction-agreeing deltas signal; CLM-0012 then *measured* about that,
# 4 cells in 80 moving on a re-roll. Both arms here inherit it.
NOISE_FLOOR_TASKS = 1

Rows = list[dict[str, object]]


def load(path: Path) -> Rows:
    """Rows from a JSONL file, blank lines skipped."""
    if not path.is_file():
        raise SystemExit(f"no rows at {path}")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def by_condition(rows: Rows, condition: str) -> Rows:
    return [r for r in rows if r.get("condition") == condition]


def verdicts(rows: Rows, condition: str) -> dict[str, bool]:
    """``{task id: passed first attempt}`` for one condition."""
    return {str(r["task"]): bool(r.get("pass1")) for r in by_condition(rows, condition)}


def mean(rows: Rows, key: str) -> float | None:
    values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return sum(values) / len(values) if values else None  # type: ignore[arg-type]


def mcnemar_exact(
    before: dict[str, bool], after: dict[str, bool]
) -> tuple[int, int, float]:
    """Gains, losses, and the two-sided exact p over the discordant pairs.

    The paired test rather than two independent rates, because it is the same
    twenty tasks in both conditions: what a bundle is claimed to do is flip
    particular tasks, and a net that is built from flips in *both* directions is
    the signature of noise rather than of a small effect. Exact rather than
    chi-square — the discordant counts here are single digits, where the
    asymptotic form is not to be trusted.
    """
    shared = sorted(set(before) & set(after))
    gains = sum(1 for t in shared if not before[t] and after[t])
    losses = sum(1 for t in shared if before[t] and not after[t])
    n = gains + losses
    if n == 0:
        return gains, losses, 1.0
    k = min(gains, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return gains, losses, min(1.0, 2 * tail)


def condition_table(rows: Rows, title: str) -> str:
    """Per-condition pass@1, in the columns CLM-0004's summary reported."""
    lines = [
        f"**{title}**",
        "",
        "| Condition | pass@1 | after remediation | mean latency | mean prompt tok "
        "| mean completion tok |",
        "|---|:---:|:---:|---:|---:|---:|",
    ]
    for condition in LADDER:
        cells = by_condition(rows, condition)
        if not cells:
            continue
        total = len(cells)
        first = sum(1 for r in cells if r.get("pass1"))
        final = sum(1 for r in cells if r.get("pass_final"))

        def fmt(key: str, places: int = 0, cells: Rows = cells) -> str:
            value = mean(cells, key)
            return "n/a" if value is None else f"{value:.{places}f}"

        lines.append(
            f"| `{condition}` | **{first}/{total} ({round(100 * first / total)}%)** "
            f"| {final}/{total} | {fmt('latency_s', 2)} s | {fmt('prompt_tokens')} "
            f"| {fmt('completion_tokens', 1)} |"
        )
    return "\n".join(lines)


def paired_table(rows: Rows, title: str) -> str:
    """Every rung against c0, paired, with the flips that built the net."""
    base = verdicts(rows, "c0")
    if not base:
        return f"**{title}** — no c0 rows to pair against."
    lines = [
        f"**{title} — paired against `c0`**",
        "",
        "| | gains | losses | net | McNemar exact |",
        "|---|---|---|---:|---:|",
    ]
    for condition in LADDER[1:]:
        after = verdicts(rows, condition)
        if not after:
            continue
        shared = sorted(set(base) & set(after))
        gained = [t for t in shared if not base[t] and after[t]]
        lost = [t for t in shared if base[t] and not after[t]]
        _, _, p = mcnemar_exact(base, after)
        lines.append(
            f"| `{condition}` | {', '.join(gained) or '—'} | {', '.join(lost) or '—'} "
            f"| {len(gained) - len(lost):+d} | p = {p:.2f} |"
        )
    return "\n".join(lines)


def peak(rows: Rows) -> tuple[str, int]:
    """The best-scoring rung and its first-pass count."""
    scored = [
        (condition, sum(1 for r in by_condition(rows, condition) if r.get("pass1")))
        for condition in LADDER
        if by_condition(rows, condition)
    ]
    return max(scored, key=lambda pair: pair[1])


def spread_verdict(rows: Rows, label: str) -> str:
    """Whether any rung separated from c0 by more than the declared floor."""
    base = sum(1 for r in by_condition(rows, "c0") if r.get("pass1"))
    deltas = {
        condition: sum(1 for r in by_condition(rows, condition) if r.get("pass1"))
        - base
        for condition in LADDER[1:]
        if by_condition(rows, condition)
    }
    if not deltas:
        return f"- **{label}**: no rungs to compare."
    best = max(deltas.values())
    shape = ", ".join(f"{c} {d:+d}" for c, d in deltas.items())
    if best > NOISE_FLOOR_TASKS:
        return (
            f"- **{label}**: separates — best rung is {best:+d} tasks over `c0` "
            f"({shape}), outside the ±{NOISE_FLOOR_TASKS}-task floor."
        )
    return (
        f"- **{label}**: flat — no rung clears the ±{NOISE_FLOOR_TASKS}-task "
        f"floor over `c0` ({shape})."
    )


def report(sets: Sequence[tuple[str, str, Rows]]) -> str:
    """The whole comparison, as the measurement record prints it."""
    out: list[str] = []
    for _key, title, rows in sets:
        out.append(condition_table(rows, title))
        out.append("")
        out.append(paired_table(rows, title))
        out.append("")
    out.append("**Does any arm show the bundle doing anything?**")
    out.append("")
    for _key, title, rows in sets:
        out.append(spread_verdict(rows, title))
    out.append("")
    for _key, title, rows in sets:
        rung, count = peak(rows)
        total = len(by_condition(rows, rung))
        out.append(f"- **{title}**: best rung `{rung}` at {count}/{total}.")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="the measurement directory holding this run's rows",
    )
    parser.add_argument(
        "--jsts",
        type=Path,
        default=REPO / "records" / "measurements" / "jsts-bundle-2026-08-04",
        help="the JS/TS sweep to compare against (default: CLM-0012's)",
    )
    parser.add_argument(
        "--clm0004",
        type=Path,
        default=(
            REPO
            / "records"
            / "evidence"
            / "local-ai-2026-08-02"
            / "data"
            / "context_exp"
            / "results_q3b.jsonl"
        ),
        help="the vendored rows CLM-0004 was measured on",
    )
    args = parser.parse_args()

    sets = [
        (
            "clm0004",
            "CLM-0004 — Python, llama-server, local-ai harness",
            load(args.clm0004),
        ),
        (
            "original",
            "Arm B — Python, Ollama, local-ai harness unchanged",
            load(args.out / "original-harness" / "results_q3b.jsonl"),
        ),
        ("rig", "Arm A — Python, Ollama, mcgyvr rig", load(args.out / "results.jsonl")),
        (
            "jsts",
            "CLM-0012 — JS/TS, Ollama, mcgyvr rig",
            load(args.jsts / "results.jsonl"),
        ),
    ]
    print(report(sets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
