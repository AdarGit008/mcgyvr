#!/usr/bin/env python3
"""#144 — the bundle-size condition ladder, repeated over a JS/TS task set.

CLM-0004 measured a ~2 KB skill bundle taking qwen2.5-coder:3b from 45% to 70%
first-pass acceptance at ~2.5x the speed, and an 8 KB bundle giving ten points
back. Its confidence note bars quoting those percentages for "other models,
task sets or languages until re-measured", and ``src/mcgyvr/prompts/javascript.md``
is shipped on exactly that unquotable prediction. This is the re-measurement for
the language half.

**Two things are unmeasured, and the ladder separates them.** Whether a bundle
helps in JS/TS at all is c0 against c1/c2; whether 2 KB is the right ceiling
*for this language* is c2 against c3. ``MAX_BUNDLE_BYTES`` is the peak of a
Python curve, and the shipped JS/TS file sits 27 bytes under it — pinned against
a limit nothing has shown applies to it.

**The conditions differ only in the system prompt.** The user message is
:func:`~mcgyvr.worker.prompt.render_user_message` over the contract's
``worker_view()`` in every condition, which is the shape CLM-0004 held fixed
("the contract is always the user message, unchanged across conditions") and
also the real assembly path #25 ships. c0 sends no system prompt at all.

**c2 is the shipped bundle, byte for byte, and this refuses to run if it is
not.** That is the property that makes a result quotable about
``prompts/javascript.md`` rather than about a file that resembles it — the same
discipline that keeps ``prompts/python.md`` equal to the measured ``c2.md``.
:func:`check_c2_is_the_shipped_bundle` is called before the first dispatch.

**Dispatch is mcgyvr's own.** :class:`~mcgyvr.runner.Request` through
:func:`~mcgyvr.runner.runner_for`, so the measurement runs through the code that
ships rather than a benchmark's private HTTP client — including the cap, the
refusal to send stop sequences (ADR-0009), and truncation read from the
backend's own stop reason. Replies are parsed by
:func:`~mcgyvr.worker.reply.parse_reply` with that real stop reason, so a reply
this project would refuse is scored as a failure here too, by its refusal code.
``quality_sensitive=True`` marks every request: this output is read as a
measurement of the model, so a caveated source may not serve it.

**Acceptance is the contract's, executed, never inspected.** Each task declares
``acceptance: ["node accept.mjs"]``; the runner writes the worker's file as
``solution.ts`` beside a copy of ``accept.mjs`` in a fresh temp directory and
runs the declared command there. Node 24 executes TypeScript directly by
stripping types, so a task needs no toolchain, no install and no network — which
is what lets acceptance stay stdlib-only and isolated per CLM-0004's design.

**--selftest is a precondition, not a convenience.** Every reference solution is
run against its own acceptance script; the experiment is invalid unless that is
100% green, exactly as the Python run required. It needs no worker and no
endpoint, so the task set can be verified on a machine that cannot run the
sweep — which is the machine this was written on.

Usage::

    # verify the task set (no worker needed)
    uv run --no-sync python tools/bundle/measure.py --selftest

    # the sweep, against a served qwen2.5-coder:3b
    uv run --no-sync python tools/bundle/measure.py \\
        --endpoint http://localhost:11434 --protocol ollama \\
        --model qwen2.5-coder:3b \\
        --out records/measurements/jsts-bundle-YYYY-MM-DD

    # the table, from rows already collected
    uv run --no-sync python tools/bundle/measure.py --out <dir> --summarise-only
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.contract import Contract, load
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.runner import Request, RunnerError, runner_for
from mcgyvr.worker.bundle import bundle_for
from mcgyvr.worker.prompt import render_user_message
from mcgyvr.worker.reply import ReplyError, parse_reply

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
CONDITIONS = HERE / "conditions"

# The ladder. c0 is the absence of a system prompt rather than an empty file:
# CLM-0004's c0 is "none — contract only", which is also what `bundle_for`
# returns for a language with no bundle, so the condition is a real production
# state and not a control that only exists in an experiment.
LADDER = ("c0", "c1", "c2", "c3")

# CLM-0004's sampler and cap, held fixed so the only variable is the bundle.
# Greedy because the gate is deterministic and a sampled worker would put
# variance in the numerator; 768 because that is what the Python run allowed and
# a different cap would change what "truncated" means between the two.
MAX_OUTPUT_TOKENS = 768
TEMPERATURE = 0.0

# Per acceptance command. The Python design's number, and generous for a task
# set whose slowest reference runs in well under a second.
ACCEPTANCE_TIMEOUT_S = 30.0

# The file the worker writes and the acceptance script imports. Every contract
# names it as its target, so the JS/TS adapter owns it and the c2 condition is
# the bundle production would have selected.
SOLUTION = "solution.ts"


class MeasureError(Exception):
    """The experiment cannot be run as specified."""


@dataclass(frozen=True)
class Task:
    """One task: its contract, its reference solution and its acceptance script."""

    id: str
    contract: Contract
    directory: Path

    @property
    def reference(self) -> Path:
        return self.directory / "reference.ts"

    @property
    def accept(self) -> Path:
        return self.directory / "accept.mjs"


@dataclass(frozen=True)
class Acceptance:
    """What running a task's declared acceptance command reported."""

    passed: bool
    output: str


def load_tasks(only: Sequence[str] = ()) -> list[Task]:
    """Every task in the set, or the named subset, contracts already validated.

    Loading through :func:`mcgyvr.contract.load` rather than a private parser is
    deliberate: a task whose contract this project would reject is not a task
    this project can dispatch, so the task set is held to the same schema the
    public API is.
    """
    tasks: list[Task] = []
    for directory in sorted(TASKS.iterdir()):
        if not directory.is_dir() or (only and directory.name not in only):
            continue
        tasks.append(
            Task(
                id=directory.name,
                contract=load(directory / "contract.yaml"),
                directory=directory,
            )
        )
    if only:
        missing = sorted(set(only) - {task.id for task in tasks})
        if missing:
            raise MeasureError(f"no such task(s): {', '.join(missing)}")
    return tasks


def condition_text(condition: str) -> str:
    """The system prompt for one condition; ``""`` for c0, which has none."""
    if condition == "c0":
        return ""
    path = CONDITIONS / f"{condition}.md"
    if not path.is_file():
        raise MeasureError(f"no bundle file for condition {condition!r}: {path}")
    return path.read_text(encoding="utf-8")


def check_c2_is_the_shipped_bundle() -> None:
    """Refuse to run unless c2 is ``prompts/javascript.md``'s body, byte for byte.

    ``Bundle.text`` is already the body: the shipped file's provenance marker is
    stripped at load, so what this compares is exactly the string a worker would
    receive. If the two ever diverge, every number this tool produces would
    describe a prompt nobody ships, which is the failure the equivalent Python
    test exists to prevent.
    """
    shipped = bundle_for(SOLUTION)
    if shipped is None:  # unreachable while the JS/TS adapter owns .ts
        raise MeasureError(f"no bundle is registered for {SOLUTION}")
    measured = condition_text("c2")
    if shipped.text != measured:
        raise MeasureError(
            "the c2 condition is not the shipped bundle. "
            f"conditions/c2.md is {len(measured.encode('utf-8'))} bytes; the "
            f"shipped prompts/javascript.md body is {shipped.size_bytes}. "
            "Re-derive c2.md from the shipped file, or the result describes a "
            "prompt that is not shipped."
        )


def build_messages(task: Task, condition: str) -> tuple[str, str]:
    """The (system, user) pair for one cell of the matrix.

    The user message goes through ``worker_view()`` and
    :func:`~mcgyvr.worker.prompt.render_user_message` — the shipped assembly —
    rather than being rendered here, so what is measured is what would be sent.
    :func:`~mcgyvr.worker.prompt.build_prompt` itself is not used because it
    selects the bundle by adapter, and the whole experiment is the substitution
    of that one choice.
    """
    return condition_text(condition), render_user_message(task.contract.worker_view())


def run_acceptance(task: Task, content: str, workdir: Path) -> Acceptance:
    """Write the worker's file into a fresh tree and run the contract's command.

    The commands come from ``contract.acceptance`` and are run with the task
    directory as the working directory's ancestor only by copying — nothing
    reaches back into the repository, so a worker that writes a path traversal
    into its file still only touches a temp directory that is about to be
    deleted.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / SOLUTION).write_text(content, encoding="utf-8")
    shutil.copy(task.accept, workdir / task.accept.name)
    for command in task.contract.acceptance:
        try:
            proc = subprocess.run(
                command.split(),
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=ACCEPTANCE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return Acceptance(
                False, f"{command}: timed out after {ACCEPTANCE_TIMEOUT_S}s"
            )
        except OSError as exc:
            return Acceptance(False, f"{command}: could not be run: {exc}")
        if proc.returncode != 0:
            return Acceptance(
                False, f"{command}: {(proc.stderr or proc.stdout).strip()}"
            )
    return Acceptance(True, "")


def node_runs_typescript() -> bool:
    """Whether the Node on PATH executes TypeScript directly.

    Presence is the wrong predicate, and assuming it is the failure this
    function exists to prevent: ``accept.mjs`` imports ``./solution.ts``, so a
    Node without type stripping fails every task for a reason that is about the
    runner rather than about the code — twenty red rows misattributed to a
    model, or to a bundle. Stripping is unflagged from Node 23.6 and 22.18, so
    this runs the capability rather than parsing a version out of
    ``--version``.
    """
    if shutil.which("node") is None:
        return False
    with tempfile.TemporaryDirectory(prefix="mcgyvr-bundle-probe-") as tmp:
        probe = Path(tmp) / "probe.ts"
        probe.write_text("const n: number = 1;\n", encoding="utf-8")
        try:
            proc = subprocess.run(
                ["node", str(probe)],
                capture_output=True,
                timeout=ACCEPTANCE_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0


def node_capability_error() -> str | None:
    """Why acceptance cannot run here, or ``None`` if it can."""
    if node_runs_typescript():
        return None
    return (
        "acceptance needs a Node that runs TypeScript directly — `node "
        "accept.mjs` imports ./solution.ts. Type stripping is unflagged from "
        "Node 23.6; the task set was built on 24."
    )


def selftest(tasks: Iterable[Task]) -> int:
    """Run every reference solution against its own acceptance script.

    CLM-0004's design: "the experiment is invalid unless selftest is 100%
    green". A red row here is a defect in the task set, not a result about a
    model, and it has to be findable without a worker — so this path dispatches
    nothing.
    """
    failures = 0
    with tempfile.TemporaryDirectory(prefix="mcgyvr-bundle-selftest-") as tmp:
        root = Path(tmp)
        for task in tasks:
            reference = task.reference.read_text(encoding="utf-8")
            result = run_acceptance(task, reference, root / task.id)
            status = "ok  " if result.passed else "FAIL"
            print(f"{status} {task.id}  {task.contract.task_type}")
            if not result.passed:
                failures += 1
                print(f"     {result.output.splitlines()[0] if result.output else ''}")
    total = len(list(tasks))
    print(f"\n{total - failures}/{total} references pass their own acceptance")
    return 1 if failures else 0


def measure_cell(
    task: Task,
    condition: str,
    runner: Any,
    model: str,
    workdir: Path,
    *,
    remediate: bool,
) -> dict[str, object]:
    """One (task, condition) run, from dispatch to a scored row.

    Every way this can fail is a row rather than an exception: a transport
    error, a reply the parser refuses, a file that does not run. A cell that
    disappeared from the results would silently shrink a denominator, and the
    rate is the whole output.
    """
    system, user = build_messages(task, condition)
    row: dict[str, object] = {
        "task": task.id,
        "type": task.contract.task_type,
        "model": model,
        "condition": condition,
        "bundle_bytes": len(system.encode("utf-8")),
    }
    request = Request(
        prompt=user,
        system=system,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        temperature=TEMPERATURE,
        quality_sensitive=True,
    )
    try:
        completion = runner.generate(model, request)
    except RunnerError as exc:
        # Not a model result. Recorded as its own outcome so a run degraded by a
        # flaky endpoint cannot be read as a run where the model failed.
        return row | {
            "pass1": False,
            "pass_final": False,
            "remediation_used": False,
            "dispatch_error": f"{type(exc).__name__}: {exc}",
        }

    row |= {
        "latency_s": round(completion.latency_s, 3),
        "prompt_tokens": completion.input_tokens,
        "completion_tokens": completion.output_tokens,
        "stop_reason": completion.stop_reason.value,
        "raw_stop_reason": completion.raw_stop_reason,
        "overran_cap": completion.overran_cap,
    }

    parsed = parse_reply(
        completion.text,
        output_schema=task.contract.output_schema,
        stop_reason=completion.stop_reason,
    )
    if isinstance(parsed, ReplyError):
        row |= {
            "pass1": False,
            "pass_final": False,
            "remediation_used": False,
            "parse_error": parsed.code,
            "fail_output": parsed.message,
        }
        return row

    first = run_acceptance(task, parsed.content, workdir / f"{task.id}-{condition}-1")
    row |= {"pass1": first.passed, "parse_error": None}
    if first.passed or not remediate:
        return row | {
            "pass_final": first.passed,
            "remediation_used": False,
            "fail_output": None if first.passed else first.output,
        }

    # One remediation round, as the Python run allowed: the acceptance output is
    # handed back and the same rung retried once. CLM-0004 found this rescued 2
    # of 35 attempts, so it is measured rather than assumed useful.
    retry = Request(
        prompt=(
            f"{user}\n\nYour previous answer failed its acceptance check with:\n"
            f"{first.output}\n\nReturn the corrected complete file."
        ),
        system=system,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        temperature=TEMPERATURE,
        quality_sensitive=True,
    )
    try:
        second = runner.generate(model, retry)
    except RunnerError as exc:
        return row | {
            "pass_final": False,
            "remediation_used": True,
            "dispatch_error": f"{type(exc).__name__}: {exc}",
            "fail_output": first.output,
        }
    reparsed = parse_reply(
        second.text,
        output_schema=task.contract.output_schema,
        stop_reason=second.stop_reason,
    )
    if isinstance(reparsed, ReplyError):
        return row | {
            "pass_final": False,
            "remediation_used": True,
            "fail_output": reparsed.message,
        }
    final = run_acceptance(task, reparsed.content, workdir / f"{task.id}-{condition}-2")
    return row | {
        "pass_final": final.passed,
        "remediation_used": True,
        "fail_output": None if final.passed else final.output,
    }


def done_keys(rows_path: Path) -> set[tuple[str, str]]:
    """The (task, condition) cells an interrupted run already recorded."""
    if not rows_path.is_file():
        return set()
    keys: set[tuple[str, str]] = set()
    for line in rows_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        keys.add((row["task"], row["condition"]))
    return keys


def summarise(rows_path: Path) -> str:
    """The per-condition table, in the columns CLM-0004's summary reported.

    Completion tokens are carried because they are what made the Python latency
    result independent of machine-load noise: a bundle that makes a small model
    stop rambling wins wall-clock through the token count, and the token count
    is the backend's own.
    """
    rows = [
        json.loads(line)
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        return "no rows"
    lines = [
        "| Condition | pass@1 | final | mean latency | mean prompt tok "
        "| mean completion tok |",
        "|-----------|:------:|:-----:|:------------:|:---------------:|:-------------------:|",
    ]
    for condition in LADDER:
        cells = [r for r in rows if r["condition"] == condition]
        if not cells:
            continue
        total = len(cells)
        first = sum(1 for r in cells if r.get("pass1"))
        final = sum(1 for r in cells if r.get("pass_final"))
        lines.append(
            f"| {condition} | {first}/{total} ({100 * first // total}%) | "
            f"{final}/{total} | {_mean(cells, 'latency_s')} | "
            f"{_mean(cells, 'prompt_tokens')} | {_mean(cells, 'completion_tokens')} |"
        )
    dispatch_errors = sum(1 for r in rows if r.get("dispatch_error"))
    parse_errors = sum(1 for r in rows if r.get("parse_error"))
    lines.append("")
    lines.append(
        f"{len(rows)} rows. {parse_errors} replies the parser refused, "
        f"{dispatch_errors} cells lost to dispatch errors."
    )
    return "\n".join(lines)


def _mean(rows: Sequence[dict[str, Any]], key: str) -> str:
    """The mean of a column, or ``n/a`` when the backend reported none of it."""
    values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    if not values:
        return "n/a"
    mean = sum(values) / len(values)
    return f"{mean:.1f}" if key == "latency_s" else f"{mean:.0f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="measurement directory for the rows")
    parser.add_argument(
        "--endpoint", help="base URL of the worker, e.g. http://localhost:11434"
    )
    parser.add_argument("--model", help="model name as the backend knows it")
    parser.add_argument(
        "--protocol",
        choices=[p.value for p in Protocol],
        default=Protocol.OLLAMA.value,
        help="wire protocol the endpoint speaks",
    )
    parser.add_argument(
        "--conditions",
        default=",".join(LADDER),
        help=f"comma-separated subset of the ladder (default: {','.join(LADDER)})",
    )
    parser.add_argument(
        "--tasks", default="", help="comma-separated subset of task ids"
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
    parser.add_argument(
        "--no-remediate",
        action="store_true",
        help="skip the one remediation round "
        "(it rescued 2 of 35 attempts in the Python run)",
    )
    args = parser.parse_args()

    try:
        tasks = load_tasks([t for t in args.tasks.split(",") if t])
    except MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Every path that runs a task needs a Node that strips types; summarising
    # rows already on disk does not. Refused here rather than discovered as a
    # uniform failure twenty tasks in.
    if not args.summarise_only:
        problem = node_capability_error()
        if problem is not None:
            print(f"error: {problem}", file=sys.stderr)
            return 2

    if args.selftest:
        return selftest(tasks)

    if args.summarise_only:
        if args.out is None:
            print("error: --summarise-only needs --out", file=sys.stderr)
            return 2
        print(summarise(args.out / "results.jsonl"))
        return 0

    if not (args.out and args.endpoint and args.model):
        print(
            "error: a sweep needs --out, --endpoint and --model.\n"
            "       --selftest verifies the task set without a worker.",
            file=sys.stderr,
        )
        return 2

    try:
        check_c2_is_the_shipped_bundle()
    except MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    conditions = [c for c in args.conditions.split(",") if c]
    unknown = sorted(set(conditions) - set(LADDER))
    if unknown:
        print(f"error: unknown condition(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    endpoint = Endpoint(
        source="measure",
        base_url=args.endpoint,
        protocol=Protocol(args.protocol),
        max_parallel=1,
        credential_env=None,
    )
    runner = runner_for(endpoint)

    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "results.jsonl"
    already = done_keys(rows_path)
    if already:
        print(f"resuming: {len(already)} cells already recorded", file=sys.stderr)

    with (
        tempfile.TemporaryDirectory(prefix="mcgyvr-bundle-") as tmp,
        rows_path.open("a", encoding="utf-8") as handle,
    ):
        workdir = Path(tmp)
        for condition in conditions:
            for task in tasks:
                if (task.id, condition) in already:
                    continue
                row = measure_cell(
                    task,
                    condition,
                    runner,
                    args.model,
                    workdir,
                    remediate=not args.no_remediate,
                )
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                mark = "pass" if row.get("pass1") else "fail"
                print(f"{condition} {task.id} {mark}", file=sys.stderr)

    summary = summarise(rows_path)
    (args.out / "summary.md").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
