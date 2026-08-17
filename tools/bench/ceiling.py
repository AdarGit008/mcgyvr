#!/usr/bin/env python3
"""What the acceptance ceiling is a bound on, measured rather than chosen (#262).

`ACCEPTANCE_TIMEOUT_S` was three numbers in three files — 120.0 in
`tools/bench/score.py`, 30.0 in `tools/bundle/measure.py`, 30.0 in
`tools/problems/admit.py` — under two comments each asserting they matched.
ADR-0035 reconciled the live pair to one, and this is the measurement it was
reconciled against, kept as a tool so the figure stays re-derivable rather than
becoming a number in a docstring citing a session nobody can re-run.

Two populations, and confusing them is how a ceiling gets picked badly:

* **references** — every admitted problem's acceptance command run against its
  own reference solution. This is what pool admission screens, and it is cheap:
  the slowest of 514 is well under a second, so any plausible ceiling clears it
  by two orders of magnitude and the population decides nothing.
* **candidates** — the `acceptance_s` field on every row in
  `records/measurements`. This is what the ceiling actually bounds, and the
  question it answers is not "how long does correct code take" but "how close
  did a **slow but correct** candidate come to being called a timeout".

The second question is the one with an answer: read `candidates.slowest_pass`
and `candidates.second_slowest_pass` off the summary.

Nothing here dispatches. References run locally against material on disk;
candidate durations are read out of records already written.

    uv run --no-sync python tools/bench/ceiling.py --out <dir>
    uv run --no-sync python tools/bench/ceiling.py --references   # skip the read
    uv run --no-sync python tools/bench/ceiling.py --recorded     # skip the sweep
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TASKS = HERE / "tasks"
MEASUREMENTS = REPO / "records" / "measurements"

#: How a timeout announces itself. Two phrasings because two scorers wrote
#: these rows: the acceptance-only path (`tools/bundle/measure.py`) and
#: `Gate.run` (#113). A row matched by neither is a completed run, so getting
#: this list wrong contaminates the population the ceiling is chosen from —
#: which is why the summary reports both counts and a reader can see the split.
TIMEOUT_MARKERS = ("timed out", "exceeded the task's time limit")

#: Well above anything a reference can legitimately take, and low enough that a
#: pathological one does not hang the sweep. Not the ceiling under test — this
#: tool must not apply the number it exists to inform.
SWEEP_CAP_S = 300.0


@dataclass(frozen=True)
class Arm:
    """One language's staging: what to copy where, and what to run."""

    name: str
    reference: str
    target: str
    checker: str
    argv: tuple[str, ...]


ARMS = (
    Arm("py", "reference.py", "solution.py", "accept.py", ("python3", "accept.py")),
    Arm("ts", "reference.ts", "solution.ts", "accept.mjs", ("node", "accept.mjs")),
)


def time_reference(arm: Arm, task: Path) -> dict[str, Any]:
    """Run one problem's checker against its own reference, and time it.

    The tree is the checker and the solution and nothing else — the same shape
    `tools/problems/admit.py` rehearses in, deliberately, because the number
    this produces is the one admission screens against.
    """
    with tempfile.TemporaryDirectory(prefix="mcgyvr-ceiling-") as tmp:
        workspace = Path(tmp)
        shutil.copyfile(task / arm.reference, workspace / arm.target)
        shutil.copyfile(task / arm.checker, workspace / arm.checker)
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                list(arm.argv),
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=SWEEP_CAP_S,
            )
            returncode: int | None = proc.returncode
        except subprocess.TimeoutExpired:
            returncode = None
        elapsed = time.perf_counter() - started
    return {
        "population": "reference",
        "arm": arm.name,
        "id": task.name,
        "seconds": round(elapsed, 4),
        "returncode": returncode,
    }


def sweep_references() -> Iterator[dict[str, Any]]:
    for arm in ARMS:
        root = TASKS / arm.name
        if not root.is_dir():
            continue
        for task in sorted(p for p in root.iterdir() if p.is_dir()):
            yield time_reference(arm, task)


def recorded_candidates() -> Iterator[dict[str, Any]]:
    """Every `acceptance_s` on disk, with the verdict and the run it came from.

    `passed` is carried through because it is the whole read: a ceiling is
    chosen against the **passing** rows, and the failing ones include the
    timeouts, which are censored at whatever ceiling produced them.
    """
    for path in sorted(MEASUREMENTS.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            seconds = row.get("acceptance_s")
            if not isinstance(seconds, int | float):
                continue
            blob = json.dumps(row)
            yield {
                "population": "candidate",
                "run": path.relative_to(MEASUREMENTS).parts[0],
                "file": str(path.relative_to(MEASUREMENTS)),
                "id": row.get("task"),
                "seconds": float(seconds),
                "passed": row.get("passed"),
                "timed_out": any(m in blob for m in TIMEOUT_MARKERS),
            }


def _band(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "min": None, "median": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": round(ordered[0], 4),
        "median": round(statistics.median(ordered), 4),
        "p95": round(ordered[min(int(0.95 * len(ordered)), len(ordered) - 1)], 4),
        "max": round(ordered[-1], 4),
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The four numbers ADR-0035 rests on, plus the censoring that qualifies them.

    `uncensored_*` is the honest caveat and is computed rather than asserted: a
    run measured at a 30 s ceiling **cannot** produce a row above it, so the
    emptiness of the [30, 120) band is only evidence in the runs whose ceiling
    was above 30. Those are identified by having produced a row above it —
    which is a fact about the rows and not a manifest field, because no
    manifest recorded the ceiling before this issue.
    """
    references = [r for r in rows if r["population"] == "reference"]
    candidates = [r for r in rows if r["population"] == "candidate"]
    passing = [r for r in candidates if r.get("passed") is True]
    timeouts = [r for r in candidates if r["timed_out"]]

    by_run: dict[str, list[float]] = {}
    for row in candidates:
        by_run.setdefault(row["run"], []).append(row["seconds"])
    wide = {run for run, seconds in by_run.items() if max(seconds) > 31.0}
    uncensored = [r for r in candidates if r["run"] in wide]

    slowest_pass = max(passing, key=lambda r: r["seconds"]) if passing else None
    runners_up = sorted((r["seconds"] for r in passing), reverse=True)[1:2]
    return {
        "references": {
            "all": _band([r["seconds"] for r in references]),
            **{
                arm.name: _band(
                    [r["seconds"] for r in references if r["arm"] == arm.name]
                )
                for arm in ARMS
            },
            "failed": [r["id"] for r in references if r["returncode"] != 0],
        },
        "candidates": {
            "all": _band([r["seconds"] for r in candidates]),
            "passing": _band([r["seconds"] for r in passing]),
            "timeouts": len(timeouts),
            "timeouts_that_passed": sum(1 for r in timeouts if r.get("passed")),
            "slowest_pass": slowest_pass
            and {
                "seconds": round(slowest_pass["seconds"], 4),
                "run": slowest_pass["run"],
                "id": slowest_pass["id"],
            },
            "second_slowest_pass": round(runners_up[0], 4) if runners_up else None,
        },
        "band_30_to_120": {
            "runs_that_could_observe_it": sorted(wide),
            "rows_that_could_observe_it": len(uncensored),
            "rows_in_the_band": sum(
                1 for r in uncensored if 30.0 <= r["seconds"] < 120.0
            ),
            "rows_censored_at_30": len(candidates) - len(uncensored),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="write units.jsonl and summary.json")
    parser.add_argument(
        "--references",
        action="store_true",
        help="sweep the references only, skipping the recorded rows",
    )
    parser.add_argument(
        "--recorded",
        action="store_true",
        help="read the recorded rows only, running nothing",
    )
    parser.add_argument(
        "--all-units",
        action="store_true",
        help="write the candidate rows too, duplicating records/measurements",
    )
    args = parser.parse_args(argv)

    rows: list[dict[str, Any]] = []
    if not args.recorded:
        rows.extend(sweep_references())
    if not args.references:
        rows.extend(recorded_candidates())
    summary = summarise(rows)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        # A record holds what was *measured*, not a copy of what was already
        # recorded. The reference rows are this tool's own observations and are
        # reproducible only by re-running it; the candidate rows are a
        # projection of `records/measurements`, 7.1 MB of it, already in the
        # tree and re-derivable in seconds. Writing them out would put a second
        # copy of the corpus in the repository and let the two disagree.
        # `--all-units` is for a caller working outside a checkout.
        units = (
            rows
            if args.all_units
            else [r for r in rows if r["population"] != "candidate"]
        )
        with (args.out / "units.jsonl").open("w", encoding="utf-8") as fh:
            for row in units:
                fh.write(json.dumps(row) + "\n")
        (args.out / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
