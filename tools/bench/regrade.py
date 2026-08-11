#!/usr/bin/env python
"""#225 — re-score saved completions against the checkers as they stand now.

A sweep's rows are two different facts glued together: what the model wrote,
and what the checker made of it. Only the first costs tokens. When a checker is
found to be wrong — as ADR-0023's `ValueError` asymmetry was, where 104 bench
and 106 reserve py checkers accepted only `ValueError` while their ts twins
accept any `Error` — every rate the project has ever quoted from that arm is
recoverable by running the corrected acceptance over candidates already on
disk, at zero model cost.

**The original rows are never rewritten.** `results.jsonl` records what was
measured on the day, under the checker of the day, and a record that changes
when the tooling changes is not a record. The re-score lands beside it in
`regrade.jsonl` with the checker digests it was produced under, so the two can
always be told apart and neither can be mistaken for the other.

Rows that never reached acceptance are carried forward unchanged and marked
so. A dispatch error is a draw nobody saw, and a parse refusal happened before
any checker ran; re-scoring either would invent an observation. The candidate
text is re-parsed rather than trusted, so a row that used to parse and now does
not is surfaced rather than silently re-graded.

Usage::

    uv run tools/bench/regrade.py records/measurements/bench-*/**/bench-py
    uv run tools/bench/regrade.py --check <dir>   # re-score, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

from mcgyvr.runner import StopReason
from mcgyvr.worker.reply import ReplyError, parse_reply

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    """A tool module, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


breadth = _by_path("breadth_measure", REPO / "tools" / "breadth" / "measure.py")
bundle = breadth.bundle

#: Rows carrying either of these never reached a checker, so no checker change
#: can move them. They are copied into the re-score with the reason attached.
UNSCORED = ("dispatch_error", "parse_error")


def checker_digests(tier: str) -> dict[str, str]:
    """Per task, the digest of the acceptance script this re-score ran.

    The point of a re-score is that it is reproducible against a *stated*
    checker. Without this the file would claim a verdict and name nothing
    capable of producing it again.
    """
    digests: dict[str, str] = {}
    for task in breadth.load_tier_tasks(tier):
        digests[task.id] = hashlib.sha256(task.accept.read_bytes()).hexdigest()
    return digests


def rescore_row(
    row: dict[str, Any], task: Any, candidates: Path, workdir: Path
) -> dict[str, Any]:
    """One row's verdict under the current checker, or the row unchanged."""
    for key in UNSCORED:
        value = row.get(key)
        if value not in (None, "None", ""):
            return dict(row) | {"regraded": False, "regrade_skipped": key}

    candidate = candidates / str(row["task"]) / f"{row['arm']}-{row['draw']}.txt"
    if not candidate.is_file():
        return dict(row) | {"regraded": False, "regrade_skipped": "candidate missing"}

    text = candidate.read_text(encoding="utf-8")
    parsed = parse_reply(
        text,
        output_schema=task.contract.output_schema,
        stop_reason=StopReason(str(row.get("stop_reason", "complete"))),
    )
    if isinstance(parsed, ReplyError):
        # The row said this parsed on the day. If it does not now, the parser
        # moved under us and the re-score is not comparable — say so loudly
        # rather than record a fail that the checker did not produce.
        return dict(row) | {
            "regraded": False,
            "regrade_skipped": f"no longer parses: {parsed.code}",
        }

    acceptance = bundle.run_acceptance(
        task, parsed.content, workdir / f"{row['task']}-{row['arm']}-{row['draw']}"
    )
    was = str(row.get("passed")).lower() == "true"
    return dict(row) | {
        "regraded": True,
        "passed_before": was,
        "passed": acceptance.passed,
        "flipped": acceptance.passed != was,
        "fail_output": None if acceptance.passed else acceptance.output,
    }


def rescore_dir(measured: Path, write: bool = True) -> dict[str, Any]:
    """Re-score one measurement directory; return its summary."""
    measured = measured.resolve()
    manifest = json.loads((measured / "run.json").read_text(encoding="utf-8"))
    tier = str(manifest["tier"])
    tasks = {task.id: task for task in breadth.load_tier_tasks(tier)}
    rows = breadth.read_rows(measured / "results.jsonl")
    retired_path = HERE / "retired.json"
    withdrawn = (
        {
            str(entry["id"])
            for entry in json.loads(retired_path.read_text(encoding="utf-8"))["ids"]
        }
        if retired_path.is_file()
        else set()
    )

    rescored: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mcgyvr-regrade-") as tmp:
        for row in rows:
            task = tasks.get(str(row["task"]))
            if task is None:
                # A retired problem is also "not in tier" — its directory is
                # gone — but saying so by name keeps the re-score record from
                # reading like a missing file. See tools/bench/retired.json.
                why = "retired" if str(row["task"]) in withdrawn else "not in tier"
                rescored.append(dict(row) | {"regraded": False, "regrade_skipped": why})
                continue
            rescored.append(rescore_row(row, task, measured / "candidates", Path(tmp)))

    graded = [r for r in rescored if r.get("regraded")]
    flips = [r for r in graded if r.get("flipped")]
    summary = {
        "directory": str(measured.relative_to(REPO)),
        "tier": tier,
        "model": manifest.get("model"),
        "condition": manifest.get("condition"),
        "rows": len(rows),
        "regraded": len(graded),
        "skipped": len(rescored) - len(graded),
        "passed_before": sum(1 for r in graded if r["passed_before"]),
        "passed_after": sum(1 for r in graded if r["passed"]),
        "flipped": len(flips),
        "flipped_cells": sorted(
            f"{r['task']}/{r['arm']}-{r['draw']}{' +' if r['passed'] else ' -'}"
            for r in flips
        ),
        "checkers_sha256": checker_digests(tier),
    }
    if write:
        out = measured / "regrade.jsonl"
        out.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rescored),
            encoding="utf-8",
        )
        (measured / "regrade.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-score and report, writing nothing",
    )
    args = parser.parse_args(argv)

    if shutil.which("python") is None:
        print(
            "error: acceptance needs `python` on PATH — the contracts declare "
            "`python accept.py`. Run under `uv run`.",
            file=sys.stderr,
        )
        return 2

    moved = 0
    for directory in args.directories:
        summary = rescore_dir(directory, write=not args.check)
        delta = summary["passed_after"] - summary["passed_before"]
        moved += summary["flipped"]
        print(
            f"{summary['directory']}: {summary['passed_before']} -> "
            f"{summary['passed_after']} passing of {summary['regraded']} scored "
            f"({delta:+d}), {summary['skipped']} skipped"
        )
        for cell in summary["flipped_cells"]:
            print(f"    {cell}")
    print(f"\n{moved} cell(s) changed verdict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
