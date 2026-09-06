#!/usr/bin/env python3
"""#121 — the breadth campaign: every model on a rig, small to big, walked up
the difficulty ladder to where it genuinely fails, then swept for breadth.

The first run of `measure.py` measured the strongest model on the easiest set
and found a distribution pinned to its ceiling — informative about the ceiling,
not about breadth. The owner's correction defines this driver: start at the
*bottom* of the model list, and for each model find the difficulty tier where
it produces real logic failures before spending a single extra draw. Breadth's
sweet spot, if it exists, lives exactly there.

Per model, smallest first:

1. **Probe**: one greedy draw per task on the current tier. A model that
   passes "with ease" (pass rate >= --ease, default 0.9) moves up a tier and
   probes again; the ladder stops where the model stops passing, or at the
   last tier (recorded as ``ceiling_not_reached`` — the failure spot was not
   found, and the sweep there measures the ceiling, which is a labelled
   limitation rather than a hidden one).
2. **Sweep**: at the stopping tier, the full instrument — one greedy anchor
   plus --draws serial sampled draws (default 8), no early exit. pass@<=k for
   every k up to N falls out of one sweep, which is the 1->2->3->...->N
   escalation without re-running anything.

Failures are classified, because "cannot format a reply" is not "cannot solve
the task": a **logic failure** is a complete, parseable reply the declared
acceptance rejected; truncations and parse refusals are counted separately and
do not count as the "real logic failures" the ladder is climbing toward.

Every probe and sweep is an ordinary `measure.py` run directory (rows,
manifest, candidates, resume), so the campaign adds orchestration and takes
away nothing. `campaign.json` records every decision the driver made.

Usage::

    uv run --no-sync python tools/breadth/campaign.py \\
        --endpoint http://srv1:11434 --protocol openai \\
        --models qwen2.5-coder:1.5b,qwen2.5-coder:3b,llama3.2:3b,qwen2.5-coder:7b \\
        --out records/measurements/breadth-campaign-2026-08-06/srv1
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _measure_rig() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "breadth_measure", HERE / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


measure = _measure_rig()
bundle = measure.bundle

EASE_THRESHOLD = 0.9
SWEEP_DRAWS = 8


def slug(model: str) -> str:
    """A model name as a directory name."""
    return model.replace("/", "-").replace(":", "-")


def classify(rows: list[dict[str, Any]]) -> dict[str, int]:
    """What the failures were, because their kinds mean different things."""
    out = {"pass": 0, "logic": 0, "parse": 0, "truncated": 0, "dispatch": 0}
    for row in rows:
        if row.get("passed"):
            out["pass"] += 1
        elif row.get("dispatch_error"):
            out["dispatch"] += 1
        elif row.get("parse_error"):
            kind = "truncated" if row.get("stop_reason") == "truncated" else "parse"
            out[kind] += 1
        else:
            out["logic"] += 1
    return out


def run_stage(
    out: Path,
    worker: Any,
    runner: Any,
    tier: str,
    plan: list[tuple[str, int, float]],
    draws: int,
    sampled_temperature: float = measure.SAMPLED_TEMPERATURE,
) -> list[dict[str, Any]]:
    """One measure.py-shaped run (probe or sweep), resume-aware, rows returned.

    Rows already on disk from an interrupted campaign are loaded rather than
    re-dispatched, so the returned list is always the stage's complete picture.

    The resume, the circuit breaker and the completeness stamp are the rig's
    (#217), reached through ``measure`` rather than reimplemented — a campaign
    stage is an ordinary ``measure.py`` run directory and a second copy of this
    logic is a second place for it to be wrong. A stage that the breaker stops
    raises, because the driver's next act would be to climb a ladder on a rate
    computed over a hole.
    """
    tasks = measure.load_tier_tasks(tier)
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "results.jsonl"
    resume = measure.resume_state(out)
    already = resume.keys
    note = resume.note()
    if note is not None:
        print(f"  {tier} {note}", file=sys.stderr)
    invocation: dict[str, Any] = {
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "tasks": [task.id for task in tasks],
        "rig_revision": bundle.rig_revision(),
    }
    if resume.retrying and resume.sidecar is not None:
        invocation |= {
            "retried_dispatch_errors": resume.retrying,
            "quarantined_to": resume.sidecar.name,
        }
    measure.record_run(
        out,
        worker,
        invocation,
        tier=tier,
        draws=draws,
        sampled_temperature=sampled_temperature,
    )
    aborted = None
    dead_streak = 0
    with (
        tempfile.TemporaryDirectory(prefix="mcgyvr-campaign-") as tmp,
        rows_path.open("a", encoding="utf-8") as handle,
    ):
        for task in tasks:
            rows = measure.measure_task(
                task,
                runner,
                worker.model,
                Path(tmp),
                out / "candidates",
                already,
                plan=plan,
            )
            for row in rows:
                handle.write(json.dumps(row) + "\n")
            handle.flush()
            if rows:
                marks = "".join("P" if r.get("passed") else "." for r in rows)
                print(f"  {tier} {task.id} {marks}", file=sys.stderr)
            dead_streak = dead_streak + 1 if measure.task_lost_every_draw(rows) else 0
            if dead_streak >= measure.DEAD_TASKS_BEFORE_ABORT:
                aborted = task.id
                break
    measure.record_completeness(out)
    all_rows: list[dict[str, Any]] = measure.read_rows(rows_path)
    (out / "summary.md").write_text(
        measure.summarise(rows_path) + "\n", encoding="utf-8"
    )
    if aborted is not None:
        raise bundle.MeasureError(
            f"{worker.model}: the backend went away at {tier} task {aborted} — "
            f"{dead_streak} consecutive tasks lost every draw to transport. "
            f"{out} keeps what was measured; re-run the identical command once "
            "it is back."
        )
    return all_rows


def run_model(
    out_root: Path,
    worker: Any,
    tiers: list[str],
    ease: float,
    draws: int,
    sampled_temperature: float = measure.SAMPLED_TEMPERATURE,
) -> dict[str, Any]:
    """Walk one model up the ladder, then sweep it where it stopped."""
    runner = measure.runner_for(worker.as_endpoint())
    model_dir = out_root / slug(worker.model)
    decision: dict[str, Any] = {"model": worker.model, "probes": {}}

    stop_tier = tiers[-1]
    ceiling_not_reached = True
    probe_plan = [("greedy", 0, measure.GREEDY_TEMPERATURE)]
    for tier in tiers:
        print(f"{worker.model}: probing {tier}", file=sys.stderr)
        rows = run_stage(
            model_dir / f"probe-{tier}",
            worker,
            runner,
            tier,
            probe_plan,
            0,
            sampled_temperature,
        )
        kinds = classify(rows)
        total = len(rows)
        rate = kinds["pass"] / total if total else 0.0
        decision["probes"][tier] = kinds | {"n": total, "pass_rate": round(rate, 3)}
        if kinds["dispatch"] == total and total:
            raise bundle.MeasureError(
                f"{worker.model}: every probe dispatch failed on {tier} — "
                "endpoint or model unusable, campaign cannot continue with it"
            )
        if rate < ease:
            stop_tier = tier
            ceiling_not_reached = False
            break

    decision["stop_tier"] = stop_tier
    decision["ceiling_not_reached"] = ceiling_not_reached
    print(
        f"{worker.model}: sweeping {stop_tier} with {draws} sampled draws",
        file=sys.stderr,
    )
    sweep_rows = run_stage(
        model_dir / f"sweep-{stop_tier}",
        worker,
        runner,
        stop_tier,
        measure.draw_plan(draws, sampled_temperature),
        draws,
        sampled_temperature,
    )
    decision["sweep"] = classify(sweep_rows) | {
        "tier": stop_tier,
        "draws": draws,
        "first_pass_indices": measure.first_pass_indices(sweep_rows, draws),
    }
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--endpoint", required=True)
    parser.add_argument(
        "--protocol", choices=[p.value for p in bundle.Protocol], default="openai"
    )
    parser.add_argument(
        "--models",
        required=True,
        help="comma-separated model names, SMALLEST FIRST — the order is the method",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--tiers", default=",".join(measure.TIERS))
    parser.add_argument("--ease", type=float, default=EASE_THRESHOLD)
    parser.add_argument("--draws", type=int, default=SWEEP_DRAWS)
    parser.add_argument(
        "--sampled-temperature", type=float, default=measure.SAMPLED_TEMPERATURE
    )
    args = parser.parse_args()

    tiers = [t for t in args.tiers.split(",") if t]
    unknown = sorted(set(tiers) - set(measure.TIERS))
    if unknown:
        print(f"error: unknown tier(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    # #240 retired every rung this driver was written to climb, so unless it is
    # pointed at something new it stops here — ahead of the runtime check,
    # because whether this machine can score the arm has no bearing on whether
    # the project will measure it. The escalation method survives the ladder it
    # was demonstrated on; what it needs is a live set to climb.
    try:
        for tier in tiers:
            bundle.instruments.refuse_to_measure(tier=tier, what=f"--tiers {tier}")
    except bundle.instruments.RetiredError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    problem = bundle.JSTS.capability()
    if problem is not None:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out / "campaign.json"
    log: dict[str, Any] = (
        json.loads(log_path.read_text(encoding="utf-8"))
        if log_path.is_file()
        else {
            "endpoint": bundle.redact(args.endpoint),
            "tiers": tiers,
            "ease": args.ease,
            "draws": args.draws,
            "sampled_temperature": args.sampled_temperature,
            "models": [],
        }
    )

    for model in [m for m in args.models.split(",") if m]:
        worker = bundle.Worker(
            endpoint=args.endpoint,
            protocol=bundle.Protocol(args.protocol),
            model=model,
            api_key_env=args.api_key_env,
        )
        try:
            bundle.check_protocol_can_carry_a_measurement(worker)
            decision = run_model(
                args.out,
                worker,
                tiers,
                args.ease,
                args.draws,
                args.sampled_temperature,
            )
        except bundle.MeasureError as exc:
            decision = {"model": model, "error": str(exc)}
            print(f"error: {exc}", file=sys.stderr)
        log["models"] = [m for m in log["models"] if m.get("model") != model]
        log["models"].append(decision)
        log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(log, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
