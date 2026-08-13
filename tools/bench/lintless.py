#!/usr/bin/env python3
"""Re-score the norule control with the language rung dropped — correctness only.

**The question this settles.** Check 2's ablation hurt the TypeScript arm more
than the Python arm, and the difference is real (24 problems hurt more on ts
against 10 on py, exact two-sided p = 0.024). Two explanations predict that same
asymmetry:

* **a language claim** — the rule declares output *shape*, and TypeScript needs
  more shape declared (imports, exports, type syntax), so removing it costs more
  there;
* **an instrument artefact** — the lint bar bites Python five times harder at
  baseline (154 of 257 cells against 32), so most Python cells are already
  rejected before the correctness test runs, and a cell that is already lost
  cannot be lost again.

They are separated by removing the rung that does the crushing. ``Gate.run``
takes its adapters by injection, so ``Gate(adapters=())`` keeps scope, secrets,
structured-data and acceptance and drops format/lint/structure/syntax entirely.
If the Python arm's sensitivity jumps once lint stops suppressing it, the
artefact explanation wins. If Python stays flat with room to move, the language
claim survives a real attempt to kill it.

**No model cost.** Every candidate is already on disk; this re-parses and
re-scores them. It writes nothing into the run directories — the rows record
what was measured on the day, under the bar of the day.

    uv run --no-sync python tools/bench/lintless.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
M = ROOT / "records" / "measurements"

sys.path.insert(0, str(ROOT / "tools" / "power"))

from mde import exact_p  # noqa: E402

from mcgyvr.gate.runner import Gate  # noqa: E402
from mcgyvr.runner import StopReason  # noqa: E402
from mcgyvr.worker.reply import ReplyError, parse_reply  # noqa: E402


def _by_path(name: str, path: pathlib.Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bench_score = _by_path("bench_score_lintless", ROOT / "tools" / "bench" / "score.py")
breadth = _by_path("breadth_lintless", ROOT / "tools" / "breadth" / "measure.py")

STOCK = "bench-null-gate-15b-a-2026-08-13"
NORULE = "bench-control-norule-15b-2026-08-13"
ARMS = ("bench-py", "bench-ts")


def candidate_text(run: str, arm: str, task: str) -> str | None:
    path = M / run / arm / "candidates" / task / "greedy-0.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def greedy_rows(run: str, arm: str) -> dict[str, dict[str, Any]]:
    path = M / run / arm / "results.jsonl"
    with path.open() as fh:
        every = [json.loads(line) for line in fh if line.strip()]
    return {r["task"]: r for r in every if r.get("arm") == "greedy"}


def rescore(run: str, arm: str, tasks: list[Any]) -> dict[str, bool | None]:
    """Correctness-only verdict per task. ``None`` = no observation to re-score."""
    gate = Gate(adapters=())
    rows = greedy_rows(run, arm)
    out: dict[str, bool | None] = {}
    for task in tasks:
        raw = candidate_text(run, arm, task.contract.id)
        row = rows.get(task.contract.id)
        if raw is None or row is None:
            out[task.contract.id] = None
            continue
        # The recorded stop reason, never the default: a truncated reply parsed
        # as if it were complete is an observation nobody made.
        parsed = parse_reply(
            raw,
            output_schema=task.contract.output_schema,
            stop_reason=StopReason(str(row.get("stop_reason", "complete"))),
            target=task.contract.target,
        )
        if isinstance(parsed, ReplyError):
            # A parse refusal happened before any checker ran; re-scoring it
            # would invent an observation rather than recover one.
            out[task.contract.id] = None
            continue
        with tempfile.TemporaryDirectory(prefix="mcgyvr-lintless-") as tmp:
            base = bench_score.stage_dir(
                task, task.contract.target_content, pathlib.Path(tmp) / "base"
            )
            with bench_score.TempDirSandbox(base) as sandbox:
                verdict = bench_score.score(task, parsed.content, sandbox, gate=gate)
        out[task.contract.id] = verdict.passed
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", type=pathlib.Path, help="also write the raw verdicts")
    args = parser.parse_args()

    print("# The norule control, re-scored with the language rung dropped\n")
    print(
        "gate: scope + secrets + structured + acceptance. No format/lint/structure.\n"
    )

    everything: dict[str, dict[str, dict[str, bool | None]]] = {}
    summary: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        tasks = breadth.load_tier_tasks(arm)
        everything[arm] = {
            "stock": rescore(STOCK, arm, tasks),
            "norule": rescore(NORULE, arm, tasks),
        }
        s, nr = everything[arm]["stock"], everything[arm]["norule"]
        shared = sorted(t for t in s if s[t] is not None and nr.get(t) is not None)
        gains = [t for t in shared if not s[t] and nr[t]]
        losses = [t for t in shared if s[t] and not nr[t]]
        summary[arm] = {
            "n": len(shared),
            "stock": sum(1 for t in shared if s[t]),
            "norule": sum(1 for t in shared if nr[t]),
            "gains": len(gains),
            "losses": len(losses),
            "m": len(gains) + len(losses),
            "p": exact_p(len(gains), len(losses)),
            "dropped": len(s) - len(shared),
        }

    print("## Correctness only — what the rule is worth once lint stops crushing\n")
    head = f"  {'arm':<10}{'n':>5}{'stock':>8}{'norule':>8}"
    print(head + f"{'delta':>9}{'m':>5}{'p':>10}")
    for arm in ARMS:
        r = summary[arm]
        delta = (r["norule"] - r["stock"]) / r["n"] * 100
        print(
            f"  {arm:<10}{r['n']:>5}{r['stock']:>8}{r['norule']:>8}"
            f"{delta:>+8.1f}pp{r['m']:>5}{r['p']:>10.3f}"
        )
    print()
    for arm in ARMS:
        r = summary[arm]
        if r["dropped"]:
            print(
                f"  ({arm}: {r['dropped']} cells carried no re-scorable "
                "observation — a parse refusal or a missing candidate.)"
            )

    print("\n## Beside the full-bar figures, which is the comparison that matters\n")
    print("  full bar:      py 23 -> 15 (-3.1pp, m=14, p=0.057)")
    print("                 ts 33 -> 11 (-8.6pp, m=26, p=1.05e-05)")
    print("  correctness:   see above")
    print()
    print(
        "  If py's m and delta rise sharply here, its insensitivity under the\n"
        "  full bar was the lint floor, not the language. If py stays flat while\n"
        "  ts still moves, the language claim survives."
    )

    if args.json:
        args.json.write_text(json.dumps({"verdicts": everything, "summary": summary}))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
