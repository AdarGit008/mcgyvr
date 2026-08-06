#!/usr/bin/env python3
"""#121 — the first-pass index distribution: the measurement that settles breadth.

ADR-0008 decided that sampling breadth is configuration policy with a default
of 1, and named the one measurement that would settle whether 1 is right:
given that a gate-passing candidate exists among N draws, at what index does it
first appear? Concentrated at index 0, breadth is retired — the first draw is
where the passes already are, and extra draws buy wall clock and nothing else.
Spread out is the only evidence that would justify raising the default, and
everything else on offer is a pass@k bound: a ceiling on what selection could
achieve, not a measurement of what it does.

**The draws are serial and there is no early exit.** Production breadth (#119)
stops at the first gate pass; this instrument deliberately does not, because
the whole distribution is the result. An early exit would truncate every
observation at its own answer.

**Two arms, because sampling is not free.** A rung that takes more than one
draw must sample (identical greedy draws are one draw), and moving off greedy
temperature can lower the first draw's own pass rate before breadth pays
anything back. So each task runs once greedy (temperature 0.0 — the anchor,
comparable to the bundle sweep's rows) and N times sampled at temperature 0.7,
which is the operating point DEC-6 itself proposed and ADR-0008 rejected only
the selection half of. The variance cost is `greedy` against `sampled` draw 0;
the breadth benefit is draw 0 against draws 1..N-1.

**The prompt is the shipped assembly.** :func:`~mcgyvr.worker.prompt.build_prompt`
over each task's contract — the bundle selected by adapter, the user message
rendered from ``worker_view()`` — so the distribution describes what production
would dispatch, not a condition that exists only in an experiment.

**"Gate-passing" here is the contract's declared acceptance, executed.** The
same proxy the bundle sweep used and CLM-0012 is quoted on: parse refusals are
failures by their refusal code, and the declared ``node accept.mjs`` decides
the rest. The full ``Gate.run`` adds scope, secrets, structured-data and
adapter rungs plus the sandbox; for this task set those reject nothing the
acceptance run does not, but the label on the result is "acceptance-passing",
and the claim record says so.

**Every candidate is kept.** Raw completion text lands in ``candidates/``
beside the rows, pass or fail, parseable or refused — replies are the corpus
#184 observes gets discarded exactly where it is free.

The task set, the acceptance runner and the worker plumbing are the bundle
rig's (`tools/bundle/measure.py`), imported by path — the task set is pinned
by the same digests, so a row here and a row there describe the same twenty
contracts.

Usage::

    # verify the task set (no worker needed)
    uv run --no-sync python tools/breadth/measure.py --selftest

    # the sweep
    uv run --no-sync python tools/breadth/measure.py \\
        --endpoint http://srv2:11434 --protocol openai \\
        --model qwen2.5-coder:14b \\
        --out records/measurements/breadth-YYYY-MM-DD

    # the table, from rows already collected
    uv run --no-sync python tools/breadth/measure.py --out <dir> --summarise-only
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
import time
import types
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr.runner import Request, RunnerError, runner_for
from mcgyvr.worker.prompt import build_prompt
from mcgyvr.worker.reply import ReplyError, parse_reply

HERE = Path(__file__).resolve().parent


def _bundle_rig() -> types.ModuleType:
    """The bundle rig, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "bundle_measure", HERE.parent / "bundle" / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bundle = _bundle_rig()

# The variables of this experiment, all held fixed within a run.
#
# DRAWS is DEC-6's own N: the proposal ADR-0008 stripped to "a rung may take
# more than one draw" proposed exactly five, so five is the breadth whose value
# this measures. SAMPLED_TEMPERATURE is likewise DEC-6's 0.7 — the operating
# point the inherited claim was made at, not a number chosen here. The cap is
# the bundle sweep's, so "truncated" means the same thing in both instruments.
DRAWS = 5
GREEDY_TEMPERATURE = 0.0
SAMPLED_TEMPERATURE = 0.7
MAX_OUTPUT_TOKENS = 768

# Difficulty tiers. d1 is the bundle rig's pinned 20-task set unchanged; d2/d3
# are harder sets in this tool's own tree, same format, built because the top
# rungs pass d1 at its ceiling and a distribution measured at a ceiling cannot
# show where breadth starts paying (#121's first run demonstrated exactly
# that). A tier is a directory of task dirs, each contract.yaml + reference.ts
# + accept.mjs.
TIERS = ("d1", "d2", "d3")

# Variant sets: same format, but NOT rungs of the difficulty ladder, so the
# campaign driver never climbs into one. d1r is d1's t20 with the defect
# repaired — its contract declared repeated-key handling unstated while its
# acceptance asserted last-wins, so every worker that stopped where the
# contract told it to was scored as failing. d1 itself is left alone until the
# in-flight campaign finishes: repairing it changes the tier digest, which
# would refuse every existing run directory a resume.
VARIANT_TIERS = ("d1r",)
TIER_ROOT = HERE / "tasks"

# Where the machine-specific half lives, git-ignored — same contract as the
# bundle rig's worker file, kept beside this script so the two experiments can
# name different workers.
WORKER_FILE = HERE / "worker.local.json"


def draw_plan(
    draws: int = DRAWS, sampled_temperature: float = SAMPLED_TEMPERATURE
) -> list[tuple[str, int, float]]:
    """Every (arm, draw, temperature) one task runs, in order.

    One greedy draw first — the anchor a sampled arm is compared against —
    then the sampled draws. A single flat plan rather than nested loops so
    that resume, dispatch and the tests all agree on what "all draws" means.

    ``sampled_temperature`` is a parameter rather than only the module constant
    because 0.7 is DEC-6's inherited operating point and nothing has ever
    measured it. It stays in ``run.json``'s identity, so a directory measured
    at one temperature refuses to be resumed at another.
    """
    plan: list[tuple[str, int, float]] = [("greedy", 0, GREEDY_TEMPERATURE)]
    plan.extend(("sampled", i, sampled_temperature) for i in range(draws))
    return plan


def load_tier_tasks(tier: str, only: Sequence[str] = ()) -> list[Any]:
    """The tier's tasks, contracts validated by the real loader.

    d1 is the bundle rig's set, byte for byte — reusing it rather than copying
    it keeps the two instruments' rows describing the same twenty contracts.
    """
    if tier == "d1":
        return list(bundle.load_tasks(only))
    root = TIER_ROOT / tier
    if not root.is_dir():
        raise bundle.MeasureError(
            f"no such tier {tier!r}: {root} does not exist. "
            f"Known: {TIERS + VARIANT_TIERS}"
        )
    tasks = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or (only and directory.name not in only):
            continue
        tasks.append(
            bundle.Task(
                id=directory.name,
                contract=bundle.load(directory / "contract.yaml"),
                directory=directory,
            )
        )
    if only:
        missing = sorted(set(only) - {task.id for task in tasks})
        if missing:
            raise bundle.MeasureError(
                f"no such task(s) in {tier}: {', '.join(missing)}"
            )
    return tasks


def tier_digests(tier: str) -> dict[str, str]:
    """A hash per task over the contract's emitted form, whole tier always."""
    return {
        task.id: hashlib.sha256(bundle.dumps(task.contract).encode("utf-8")).hexdigest()
        for task in load_tier_tasks(tier)
    }


def measure_task(
    task: Any,
    runner: Any,
    model: str,
    workdir: Path,
    candidates: Path,
    already: set[tuple[str, str, int]],
    plan: list[tuple[str, int, float]] | None = None,
) -> list[dict[str, object]]:
    """Every draw of one task, each a row — and never an early exit.

    A draw that passes does not end the task: the index distribution *is* the
    result, and stopping at the first pass would truncate every observation at
    its own answer. Every failure mode is a row rather than an exception, for
    the bundle rig's reason — a vanished cell silently shrinks a denominator.
    """
    prompt = build_prompt(task.contract)
    rows: list[dict[str, object]] = []
    for arm, draw, temperature in plan if plan is not None else draw_plan():
        if (task.id, arm, draw) in already:
            continue
        row: dict[str, object] = {
            "task": task.id,
            "type": task.contract.task_type,
            "model": model,
            "arm": arm,
            "draw": draw,
            "temperature": temperature,
        }
        request = Request(
            prompt=prompt.user,
            system=prompt.system,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=temperature,
            quality_sensitive=True,
        )
        try:
            completion = runner.generate(model, request)
        except RunnerError as exc:
            rows.append(
                row
                | {
                    "passed": False,
                    "dispatch_error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        candidate = candidates / task.id / f"{arm}-{draw}.txt"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(completion.text, encoding="utf-8")

        row |= {
            "latency_s": round(completion.latency_s, 3),
            "prompt_tokens": completion.input_tokens,
            "completion_tokens": completion.output_tokens,
            "stop_reason": completion.stop_reason.value,
            "overran_cap": completion.overran_cap,
            "candidate_sha256": hashlib.sha256(
                completion.text.encode("utf-8")
            ).hexdigest(),
        }

        parsed = parse_reply(
            completion.text,
            output_schema=task.contract.output_schema,
            stop_reason=completion.stop_reason,
        )
        if isinstance(parsed, ReplyError):
            rows.append(row | {"passed": False, "parse_error": parsed.code})
            continue

        started = time.monotonic()
        acceptance = bundle.run_acceptance(
            task, parsed.content, workdir / f"{task.id}-{arm}-{draw}"
        )
        rows.append(
            row
            | {
                "passed": acceptance.passed,
                "parse_error": None,
                "acceptance_s": round(time.monotonic() - started, 3),
                "fail_output": None if acceptance.passed else acceptance.output,
            }
        )
    return rows


def done_keys(rows_path: Path) -> set[tuple[str, str, int]]:
    """The (task, arm, draw) cells an interrupted run already recorded."""
    if not rows_path.is_file():
        return set()
    keys: set[tuple[str, str, int]] = set()
    for line in rows_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        keys.add((row["task"], row["arm"], row["draw"]))
    return keys


def record_run(
    out: Path,
    worker: Any,
    invocation: dict[str, object],
    tier: str = "d1",
    draws: int = DRAWS,
    sampled_temperature: float = SAMPLED_TEMPERATURE,
) -> None:
    """Write, or extend, the provenance beside the rows.

    The identity a resume must match includes the sampling parameters: rows
    drawn at a different temperature or a different N are a different
    experiment, exactly as a different worker is. The prompt is pinned through
    the task digests (the user message is a function of the contract) plus the
    bundle each ``.ts`` target selects, hashed here once.
    """
    prompt = build_prompt(load_tier_tasks(tier)[0].contract)
    identity = {
        "endpoint": bundle.redact(worker.endpoint),
        "protocol": worker.protocol.value,
        "model": worker.model,
        "tier": tier,
        "draws": draws,
        "greedy_temperature": GREEDY_TEMPERATURE,
        "sampled_temperature": sampled_temperature,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "bundle_sha256": hashlib.sha256(prompt.system.encode("utf-8")).hexdigest(),
        "tasks_sha256": tier_digests(tier),
    }
    path = out / "run.json"
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        drift = sorted(k for k, v in identity.items() if previous.get(k) != v)
        if drift:
            raise bundle.MeasureError(
                f"{path} records a different run: {', '.join(drift)} changed. "
                "Rows already here were measured on another worker, another "
                "sampler or another task set; resuming would average two "
                "experiments into one distribution. Use a fresh --out directory."
            )
        previous["invocations"].append(invocation)
        path.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(
        json.dumps({**identity, "invocations": [invocation]}, indent=2) + "\n",
        encoding="utf-8",
    )


def first_pass_indices(
    rows: list[dict[str, Any]], draws: int = DRAWS
) -> dict[str, int | None]:
    """Per task: the sampled-arm draw index of the first pass, or None.

    A task appears only once all its sampled draws are recorded — a partial
    task has an unfinished observation, and "no pass in N" must mean N draws
    were actually looked at. Dispatch errors disqualify the task for the same
    reason: an errored draw is a draw nobody saw.
    """
    by_task: dict[str, dict[int, dict[str, Any]]] = {}
    for row in rows:
        if row["arm"] == "sampled":
            by_task.setdefault(row["task"], {})[row["draw"]] = row
    indices: dict[str, int | None] = {}
    for task, recorded in sorted(by_task.items()):
        if set(recorded) != set(range(draws)):
            continue
        if any(recorded[i].get("dispatch_error") for i in range(draws)):
            continue
        passing = [i for i in range(draws) if recorded[i].get("passed")]
        indices[task] = passing[0] if passing else None
    return indices


def summarise(rows_path: Path) -> str:
    """The distribution, its arms and its price, from the rows on disk.

    The intended draw count comes from ``run.json`` beside the rows when it
    exists (a resume must judge completeness against what was *meant* to run),
    falling back to the module default for rows produced without a manifest.
    """
    rows = [
        json.loads(line)
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        return "no rows"
    draws = DRAWS
    sampled_temperature = SAMPLED_TEMPERATURE
    manifest = rows_path.parent / "run.json"
    if manifest.is_file():
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        draws = int(recorded["draws"])
        sampled_temperature = float(
            recorded.get("sampled_temperature", SAMPLED_TEMPERATURE)
        )

    lines: list[str] = []
    greedy = [r for r in rows if r["arm"] == "greedy"]
    sampled = [r for r in rows if r["arm"] == "sampled"]
    if greedy:
        passed = sum(1 for r in greedy if r.get("passed"))
        lines.append(f"greedy (T={GREEDY_TEMPERATURE}): {passed}/{len(greedy)} pass")
    draw0 = [r for r in sampled if r["draw"] == 0]
    if draw0:
        passed = sum(1 for r in draw0 if r.get("passed"))
        lines.append(
            f"sampled draw 0 (T={sampled_temperature}): {passed}/{len(draw0)} pass"
        )

    indices = first_pass_indices(rows, draws)
    if indices:
        n = len(indices)
        covered = [i for i in indices.values() if i is not None]
        lines.append("")
        lines.append(
            f"first-pass index over {n} tasks with all {draws} sampled draws "
            f"recorded ({len(covered)} with any pass, {n - len(covered)} with "
            "none):"
        )
        lines.append("")
        lines.append("| index | tasks | cumulative pass@≤k |")
        lines.append("|:-----:|:-----:|:------------------:|")
        cumulative = 0
        for index in range(draws):
            at = sum(1 for i in covered if i == index)
            cumulative += at
            lines.append(f"| {index} | {at} | {cumulative}/{n} |")
        lines.append(f"| none | {n - len(covered)} | — |")

    priced = [r for r in sampled if isinstance(r.get("latency_s"), (int, float))]
    if priced:
        dispatch = sum(r["latency_s"] for r in priced) / len(priced)
        accepted = [
            r["acceptance_s"]
            for r in priced
            if isinstance(r.get("acceptance_s"), (int, float))
        ]
        acceptance = sum(accepted) / len(accepted) if accepted else 0.0
        lines.append("")
        lines.append(
            f"wall clock per additional candidate: {dispatch:.1f}s dispatch "
            f"+ {acceptance:.1f}s acceptance (mean over {len(priced)} sampled "
            "draws)"
        )

    dispatch_errors = sum(1 for r in rows if r.get("dispatch_error"))
    parse_errors = sum(1 for r in rows if r.get("parse_error"))
    lines.append("")
    lines.append(
        f"{len(rows)} rows. {parse_errors} replies the parser refused, "
        f"{dispatch_errors} draws lost to dispatch errors."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="measurement directory for the rows")
    parser.add_argument(
        "--endpoint", help="base URL of the worker, e.g. http://srv2:11434"
    )
    parser.add_argument("--model", help="model name as the backend knows it")
    parser.add_argument(
        "--protocol",
        choices=[p.value for p in bundle.Protocol],
        default=None,
        help="wire protocol the endpoint speaks",
    )
    parser.add_argument(
        "--api-key-env",
        help="NAME of the environment variable holding the endpoint's key, "
        "never the key",
    )
    parser.add_argument(
        "--worker-file",
        type=Path,
        default=WORKER_FILE,
        help="git-ignored defaults for --endpoint/--protocol/--model/"
        "--api-key-env. Flags win over the file.",
    )
    parser.add_argument(
        "--tasks", default="", help="comma-separated subset of task ids"
    )
    parser.add_argument(
        "--tier",
        choices=TIERS + VARIANT_TIERS,
        default="d1",
        help="difficulty tier to run (default d1, the bundle rig's set)",
    )
    parser.add_argument(
        "--draws",
        type=int,
        default=DRAWS,
        help=f"sampled draws per task (default {DRAWS}); pass@<=k for every "
        "k up to this falls out of one run",
    )
    parser.add_argument(
        "--sampled-temperature",
        type=float,
        default=SAMPLED_TEMPERATURE,
        help=f"temperature of the sampled arm (default {SAMPLED_TEMPERATURE}, "
        "DEC-6's inherited operating point). Part of the run identity: a "
        "directory measured at one temperature refuses another.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run every reference against its own acceptance and stop; needs no worker",
    )
    parser.add_argument(
        "--summarise-only",
        action="store_true",
        help="print the table from an existing results.jsonl, dispatching nothing",
    )
    args = parser.parse_args()

    try:
        tasks = load_tier_tasks(args.tier, [t for t in args.tasks.split(",") if t])
    except bundle.MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.summarise_only:
        problem = bundle.node_capability_error()
        if problem is not None:
            print(f"error: {problem}", file=sys.stderr)
            return 2

    if args.selftest:
        return int(bundle.selftest(tasks))

    if args.summarise_only:
        if args.out is None:
            print("error: --summarise-only needs --out", file=sys.stderr)
            return 2
        print(summarise(args.out / "results.jsonl"))
        return 0

    if args.out is None:
        print(
            "error: a sweep needs --out, a directory for its rows.\n"
            "       --selftest verifies the task set without a worker.",
            file=sys.stderr,
        )
        return 2

    try:
        worker = bundle.resolve_worker(
            {
                "endpoint": args.endpoint,
                "protocol": args.protocol,
                "model": args.model,
                "api_key_env": args.api_key_env,
            },
            bundle.load_worker_file(args.worker_file),
        )
        bundle.check_protocol_can_carry_a_measurement(worker)
    except bundle.MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    runner = runner_for(worker.as_endpoint())

    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "results.jsonl"
    already = done_keys(rows_path)
    if already:
        print(f"resuming: {len(already)} draws already recorded", file=sys.stderr)

    try:
        record_run(
            args.out,
            worker,
            {
                "started": datetime.now(UTC).isoformat(timespec="seconds"),
                "tasks": [task.id for task in tasks],
                "rig_revision": bundle.rig_revision(),
            },
            tier=args.tier,
            draws=args.draws,
            sampled_temperature=args.sampled_temperature,
        )
    except bundle.MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"measuring {worker.model} at {bundle.redact(worker.endpoint)} "
        f"({worker.protocol.value}), tier {args.tier}, {args.draws} sampled "
        f"draws per task at T={args.sampled_temperature}, no early exit",
        file=sys.stderr,
    )
    plan = draw_plan(args.draws, args.sampled_temperature)

    with (
        tempfile.TemporaryDirectory(prefix="mcgyvr-breadth-") as tmp,
        rows_path.open("a", encoding="utf-8") as handle,
    ):
        for task in tasks:
            rows = measure_task(
                task,
                runner,
                worker.model,
                Path(tmp),
                args.out / "candidates",
                already,
                plan=plan,
            )
            for row in rows:
                handle.write(json.dumps(row) + "\n")
            handle.flush()
            marks = "".join("P" if r.get("passed") else "." for r in rows)
            if rows:
                print(f"{task.id} {marks}", file=sys.stderr)

    summary = summarise(rows_path)
    (args.out / "summary.md").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
