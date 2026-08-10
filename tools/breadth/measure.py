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

**A cell without an observation is not a filled cell (#217).** A
``dispatch_error`` row records that a draw was never seen, so a resume
re-dispatches it rather than skipping it forever; the rows it displaces are
kept verbatim in a sidecar, and the act is recorded in ``run.json``. Every run
directory then states whether an observation reached every cell it set out to
fill — in ``run.json``, at the head of ``summary.md`` and in the exit code —
because the failure this guards against is quiet: the sweep exits 0, the rows
file has the expected line count, and only a summary line that scrolled past
hours ago distinguishes a complete run from one missing a fifth of its draws.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr.runner import Request, RunnerError, runner_for
from mcgyvr.worker.prompt import build_prompt
from mcgyvr.worker.reply import ReplyError, parse_reply

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


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
#
# MAX_OUTPUT_TOKENS is inherited three hops and derived at none of them:
# from tools/bundle/measure.py, which took it from CLM-0004's local-ai
# instrument (records/evidence/local-ai-2026-08-02/instrument/context_exp.py),
# where it is a bare `MAX_TOKENS = 768`. It stays the default so every existing
# run directory keeps its identity, but it is now a parameter: #212 measured 47
# refusals that were entirely this number, and #216 exists to derive it per task
# type. Note that contracts carry their own `limits.max_output_tokens` (schema
# default 1024) which this rig does NOT read — a deliberate choice for a
# comparative instrument, and one #216 asks to revisit.
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

# The problem pool (#197), one tier per language arm. The arm lives in the
# tier *name* so the existing run identity carries it: run.json's "tier"
# plus "tasks_sha256" already refuse a resume across task sets, and two
# arms of the pool are two task sets. Not difficulty rungs — the campaign
# driver climbs TIERS only and never arrives here, like the variants.
POOL_ROOT = HERE.parent / "problems" / "tasks"
POOL_MANIFEST = HERE.parent / "problems" / "admissions.jsonl"
POOL_TIERS = ("pool-ts", "pool-py")

# Where the machine-specific half lives, git-ignored — same contract as the
# bundle rig's worker file, kept beside this script so the two experiments can
# name different workers.
WORKER_FILE = HERE / "worker.local.json"

# Where a resume parks the rows it displaces (#217). Named for the invocation
# that produced them, matching the file the manual recovery of the 2026-08-08
# srv2 outage already left beside its rows in
# records/measurements/pool-sweep-14b-cap2048-2026-08-08/.
DISPATCH_ERROR_SIDECAR = "dispatch-errors-invocation-{n}.jsonl"

# How many consecutive tasks may lose *every* draw to transport before the run
# stops (#217). The srv2 outage cost 51 tasks x 3 draws of identical 120s
# timeouts — about five hours spent learning one fact the first three tasks had
# already established. Three is chosen rather than tuned: it cannot fire on a
# healthy backend, because it requires every draw of three consecutive tasks to
# fail below the model, which is not a thing a model does. This is a *run*-level
# breaker and it does not change the row-level rule — a failed draw is still a
# row, and the rows already written are what the resume then refills.
DEAD_TASKS_BEFORE_ABORT = 3


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


def pinned_pool_ids() -> frozenset[str]:
    """The problems the pool's manifest admits, superseded ones excluded.

    The pool grows in batches, so its directories hold candidates that have
    not passed admission yet — a half-written arm, or a finished one waiting
    on its pair. A tier's digest map covers whatever it serves, so serving
    the directory would put unadmitted work into a run's identity and make
    two runs a week apart incomparable for a reason nobody chose. The
    manifest is the pool; the directory is where it lives.
    """
    if not POOL_MANIFEST.is_file():
        return frozenset()
    admitted: set[str] = set()
    for line in POOL_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if not entry.get("superseded_by"):
            admitted.add(str(entry["id"]))
    return frozenset(admitted)


def load_tier_tasks(tier: str, only: Sequence[str] = ()) -> list[Any]:
    """The tier's tasks, contracts validated by the real loader.

    d1 is the bundle rig's set, byte for byte — reusing it rather than copying
    it keeps the two instruments' rows describing the same twenty contracts.
    """
    if tier == "d1":
        return list(bundle.load_tasks(only))
    admitted: frozenset[str] | None = None
    if tier in POOL_TIERS:
        root = POOL_ROOT / tier.removeprefix("pool-")
        language = bundle.PYTHON if tier == "pool-py" else bundle.JSTS
        admitted = pinned_pool_ids()
    else:
        root = TIER_ROOT / tier
        # Every tier in this rig's own tree is JS/TS, d1 because it *is* the
        # bundle rig's set. #167 made the arm explicit on a Task rather than
        # implied by a module constant; the pool tiers above are the first
        # time this rig carries a second one.
        language = bundle.JSTS
    if not root.is_dir():
        raise bundle.MeasureError(
            f"no such tier {tier!r}: {root} does not exist. "
            f"Known: {TIERS + VARIANT_TIERS + POOL_TIERS}"
        )
    tasks = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or (only and directory.name not in only):
            continue
        if admitted is not None and directory.name not in admitted:
            continue
        tasks.append(
            bundle.Task(
                id=directory.name,
                contract=bundle.load(directory / "contract.yaml"),
                directory=directory,
                language=language,
            )
        )
    if only:
        missing = sorted(set(only) - {task.id for task in tasks})
        if missing:
            unadmitted = (
                " (present but not admitted by the pool's manifest)"
                if admitted is not None
                and all((root / name).is_dir() for name in missing)
                else ""
            )
            raise bundle.MeasureError(
                f"no such task(s) in {tier}: {', '.join(missing)}{unadmitted}"
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
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
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
            max_output_tokens=max_output_tokens,
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


def read_rows(rows_path: Path) -> list[dict[str, Any]]:
    """The rows on disk, one per line, blank lines ignored."""
    if not rows_path.is_file():
        return []
    return [
        json.loads(line)
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def done_keys(rows_path: Path) -> set[tuple[str, str, int]]:
    """The (task, arm, draw) cells an interrupted run actually observed.

    A ``dispatch_error`` row is **not** a recorded cell (#217). It is the
    record of a draw nobody saw, and counting it as done is what made a hole
    permanent: re-running the identical command printed ``resuming: 807 draws
    already recorded`` and dispatched nothing, so a run that lost 18.8% of its
    draws to a backend that came back forty minutes later stayed lost — at exit
    0, with the expected line count.

    Excluding them here is only half of it. The rows file is append-only, so a
    caller that resumes must first move the displaced rows out of it; that is
    :func:`resume_state`, which is what both drivers call.
    """
    return {
        (row["task"], row["arm"], row["draw"])
        for row in read_rows(rows_path)
        if not row.get("dispatch_error")
    }


@dataclass(frozen=True, eq=False)
class ResumeState:
    """What a resume found, and what it had to move to be able to refill it."""

    keys: set[tuple[str, str, int]]
    retrying: int
    sidecar: Path | None

    def note(self) -> str | None:
        """One line for stderr, or ``None`` when nothing was displaced."""
        if not self.retrying or self.sidecar is None:
            return None
        return (
            f"retrying {self.retrying} draw(s) that reached no worker; their "
            f"rows are kept verbatim in {self.sidecar.name}"
        )


def resume_state(out: Path) -> ResumeState:
    """Prepare ``out`` for a resume: quarantine unfillable rows, report the rest.

    **Why the rows file is rewritten rather than appended to.** Three
    mechanisms could let a resume refill a cell whose only row is a dispatch
    error, and this is the one taken:

    * *Last-row-wins in every reader* is the worst of the three, because it
      makes each reader carry the rule and there are already three. ``summarise``
      and ``campaign.classify`` would double-count the cell; worse,
      ``tools/replies/pin.py`` joins a capture to the **first** matching row
      (``_join_candidate``), and a dispatch-error row carries no ``stop_reason``
      at all — so the corpus would die on ``KeyError`` rather than on the
      diagnosable ``PinError`` that module raises for every other provenance
      failure.
    * *A flag* (``--retry-dispatch-errors``) keeps the rewrite explicit, but it
      reproduces the defect's own first failure mode: it requires noticing.
      Nothing fails, and the number that would tell you to pass the flag is in a
      summary line that scrolled past hours ago.
    * *Rewrite on resume*, taken here. The deliberateness the run-identity
      discipline asks for is bought by preserving and recording rather than by
      requiring foreknowledge: the displaced rows are written verbatim to
      :data:`DISPATCH_ERROR_SIDECAR` beside the rows, the act is announced on
      stderr, and ``run.json`` records it under the invocation that does it.
      Nothing is destroyed and the run says what happened to it.

    The join ``pin.py`` depends on stays total either way: a dispatch error
    writes no candidate file, so no capture ever pointed at a row this removes.
    """
    rows_path = out / "results.jsonl"
    rows = read_rows(rows_path)
    lost = [row for row in rows if row.get("dispatch_error")]
    if not lost:
        return ResumeState(done_keys(rows_path), 0, None)

    manifest = out / "run.json"
    invocation = 1
    if manifest.is_file():
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        invocation = max(1, len(recorded.get("invocations", [])))
    sidecar = out / DISPATCH_ERROR_SIDECAR.format(n=invocation)
    with sidecar.open("a", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(row) + "\n" for row in lost))

    kept = [row for row in rows if not row.get("dispatch_error")]
    # Sidecar first, then a replace: an interrupted quarantine must never be
    # the state where the rows are in neither file.
    scratch = rows_path.with_suffix(".jsonl.partial")
    scratch.write_text(
        "".join(json.dumps(row) + "\n" for row in kept), encoding="utf-8"
    )
    scratch.replace(rows_path)
    return ResumeState(
        {(row["task"], row["arm"], row["draw"]) for row in kept}, len(lost), sidecar
    )


def task_lost_every_draw(rows: list[dict[str, object]]) -> bool:
    """Whether a task produced rows and every one of them reached no worker.

    A task the resume skipped entirely produces no rows, which is not the same
    thing and must not advance the circuit breaker.
    """
    return bool(rows) and all(row.get("dispatch_error") for row in rows)


def expected_cells(meta: Mapping[str, Any]) -> set[tuple[str, str, int]]:
    """Every cell a run's own manifest says it set out to fill.

    Derived from what ``run.json`` already records rather than from a new
    field, so the question can be asked of every run directory ever written by
    this rig: the union of the task lists its invocations name, crossed with
    the plan its recorded ``draws`` implies. A manifest with no ``draws`` is
    not this rig's — the bundle rig's runs are shaped by condition, not by draw
    — and answers empty rather than inventing cells for it.
    """
    if "draws" not in meta:
        return set()
    plan = draw_plan(int(meta["draws"]))
    tasks = {
        str(task)
        for invocation in meta.get("invocations", [])
        for task in invocation.get("tasks", [])
    }
    return {(task, arm, draw) for task in tasks for arm, draw, _ in plan}


def missing_cells(out: Path) -> list[tuple[str, str, int]] | None:
    """The cells a run meant to fill and has no observation for.

    ``None`` when the directory cannot be judged — no manifest, or one this rig
    did not write. That is deliberately distinct from ``[]``: "complete" and
    "unanswerable" are different verdicts and the second must not read as the
    first.
    """
    manifest = out / "run.json"
    if not manifest.is_file():
        return None
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    expected = expected_cells(meta)
    if not expected:
        return None
    return sorted(expected - done_keys(out / "results.jsonl"))


def record_completeness(out: Path) -> list[tuple[str, str, int]] | None:
    """Stamp into ``run.json`` whether every cell holds an observation.

    Written where a reader cannot scroll past it, because the summary line is
    exactly what did get scrolled past. The cells are listed rather than
    counted: a hole that names itself is one a resume can be checked against.
    """
    missing = missing_cells(out)
    manifest = out / "run.json"
    if missing is None or not manifest.is_file():
        return missing
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    expected = len(expected_cells(meta))
    meta["completeness"] = {
        "expected": expected,
        "recorded": expected - len(missing),
        "missing": len(missing),
        "complete": not missing,
        "missing_cells": [f"{task}/{arm}/{draw}" for task, arm, draw in missing],
    }
    manifest.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return missing


def record_run(
    out: Path,
    worker: Any,
    invocation: dict[str, object],
    tier: str = "d1",
    draws: int = DRAWS,
    sampled_temperature: float = SAMPLED_TEMPERATURE,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
) -> None:
    """Write, or extend, the provenance beside the rows.

    The identity a resume must match includes the sampling parameters: rows
    drawn at a different temperature or a different N are a different
    experiment, exactly as a different worker is. The prompt is pinned through
    the task digests (the user message is a function of the contract) plus the
    bundle each ``.ts`` target selects, hashed here once.

    A retired tier is refused here rather than warned about (#240). This is the
    seam every dispatching path passes through — ``main`` below and
    ``campaign.run_stage`` both write the provenance before the first draw — so
    the refusal lands before a token is spent, and adding a fourth driver
    cannot route around it without also deciding not to record what it did.
    """
    bundle.instruments.refuse_to_measure(tier=tier, what=f"{out}/run.json")
    prompt = build_prompt(load_tier_tasks(tier)[0].contract)
    identity = {
        "endpoint": bundle.redact(worker.endpoint),
        "protocol": worker.protocol.value,
        "model": worker.model,
        "tier": tier,
        "draws": draws,
        "greedy_temperature": GREEDY_TEMPERATURE,
        "sampled_temperature": sampled_temperature,
        "max_output_tokens": max_output_tokens,
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

    **Completeness leads rather than trails (#217).** The old summary counted
    lost draws in its last line, which is where a reader stops looking and
    where a multi-hour run's operator was never looking at all. A run missing
    an observation says so in its first line, before any rate it might be
    quoted for; a run that is whole says *that* in its first line, so the
    statement's absence from an older summary is itself informative.
    """
    rows = read_rows(rows_path)
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
    missing = missing_cells(rows_path.parent)
    if missing:
        tasks_holed = sorted({task for task, _, _ in missing})
        shown = ", ".join(tasks_holed[:5]) + ("…" if len(tasks_holed) > 5 else "")
        lines.append(
            f"**INCOMPLETE — {len(missing)} cell(s) hold no observation**, "
            f"across {len(tasks_holed)} task(s): {shown}. Every rate below is "
            "over the cells that were filled, so this directory is not a "
            "measurement of the task set its manifest names. Re-run the "
            "identical command to fill them."
        )
        lines.append("")
    elif missing is not None:
        lines.append("complete: an observation reached every cell.")
        lines.append("")

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


def audit(root: Path) -> int:
    """Name every run directory under ``root`` that is missing an observation.

    The per-run stamp makes a *new* holed run impossible to cite unknowingly.
    This answers the same question of the runs already on disk, which were
    written before anything asked it and whose summaries therefore do not say.
    """
    judged = holed = 0
    for manifest in sorted(root.rglob("run.json")):
        missing = missing_cells(manifest.parent)
        if missing is None:
            continue
        judged += 1
        if missing:
            holed += 1
            tasks = sorted({task for task, _, _ in missing})
            print(
                f"HOLED {manifest.parent.relative_to(root)}: "
                f"{len(missing)} cell(s) over {len(tasks)} task(s)"
            )
    print(f"{judged} run directories judged, {holed} holed", file=sys.stderr)
    return 1 if holed else 0


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
        choices=TIERS + VARIANT_TIERS + POOL_TIERS,
        default="d1",
        help="difficulty tier to run (default d1, the bundle rig's set); "
        "pool-ts/pool-py are the #197 problem pool's arms, not rungs",
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
        "--max-output-tokens",
        type=int,
        default=MAX_OUTPUT_TOKENS,
        help=f"hard cap on each reply (default {MAX_OUTPUT_TOKENS}, inherited "
        "from the bundle sweep and derived nowhere — see #216). Part of the run "
        "identity: a directory measured at one cap refuses another.",
    )
    parser.add_argument(
        "--abort-after-dead-tasks",
        type=int,
        default=DEAD_TASKS_BEFORE_ABORT,
        metavar="N",
        help=f"stop once N consecutive tasks lose every draw to transport "
        f"(default {DEAD_TASKS_BEFORE_ABORT}, 0 disables). The rows already "
        "written stay, so the resume refills them.",
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
        "--audit",
        action="store_true",
        help="report which run directories under records/measurements/ hold a "
        "cell with no observation, and stop. Exits 1 if any does.",
    )
    args = parser.parse_args()

    if args.audit:
        return audit(REPO / "records" / "measurements")

    try:
        tasks = load_tier_tasks(args.tier, [t for t in args.tasks.split(",") if t])
    except bundle.MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Said here as well as in record_run, so a retired tier costs an error
    # message rather than a resolved worker and a half-built directory. Ahead
    # of the runtime check on purpose: whether this machine can score the arm
    # has no bearing on whether the project will measure it. --selftest checks
    # the contracts against their own acceptance and --summarise-only reads
    # rows already collected; neither is a measurement, and both survive.
    if not args.selftest and not args.summarise_only:
        try:
            bundle.instruments.refuse_to_measure(
                tier=args.tier, what=f"--tier {args.tier}"
            )
        except bundle.instruments.RetiredError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if not args.summarise_only:
        language = bundle.PYTHON if args.tier == "pool-py" else bundle.JSTS
        problem = language.capability()
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
        # A read of a holed directory exits non-zero for the same reason the
        # sweep does: a caller that only checks the status of the command that
        # printed the table still learns the table is over a hole.
        return 1 if missing_cells(args.out) else 0

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
    resume = resume_state(args.out)
    already = resume.keys
    if already:
        print(f"resuming: {len(already)} draws already recorded", file=sys.stderr)
    note = resume.note()
    if note is not None:
        print(note, file=sys.stderr)

    invocation: dict[str, object] = {
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "tasks": [task.id for task in tasks],
        "rig_revision": bundle.rig_revision(),
    }
    if resume.retrying and resume.sidecar is not None:
        # The rewrite is recorded where the run's provenance is, so a reader who
        # notices the rows file is shorter than the invocations imply is told
        # why, by the run, rather than having to reconstruct it.
        invocation |= {
            "retried_dispatch_errors": resume.retrying,
            "quarantined_to": resume.sidecar.name,
        }

    try:
        record_run(
            args.out,
            worker,
            invocation,
            tier=args.tier,
            draws=args.draws,
            max_output_tokens=args.max_output_tokens,
            sampled_temperature=args.sampled_temperature,
        )
    except bundle.MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"measuring {worker.model} at {bundle.redact(worker.endpoint)} "
        f"({worker.protocol.value}), tier {args.tier}, {args.draws} sampled "
        f"draws per task at T={args.sampled_temperature}, "
        f"cap {args.max_output_tokens}, no early exit",
        file=sys.stderr,
    )
    plan = draw_plan(args.draws, args.sampled_temperature)

    aborted = None
    dead_streak = 0
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
                max_output_tokens=args.max_output_tokens,
            )
            for row in rows:
                handle.write(json.dumps(row) + "\n")
            handle.flush()
            marks = "".join("P" if r.get("passed") else "." for r in rows)
            if rows:
                print(f"{task.id} {marks}", file=sys.stderr)
            dead_streak = dead_streak + 1 if task_lost_every_draw(rows) else 0
            limit = args.abort_after_dead_tasks
            if limit and dead_streak >= limit:
                aborted = task.id
                break

    if aborted is not None:
        print(
            f"error: the backend went away at task {aborted} — "
            f"{dead_streak} consecutive tasks lost every draw to transport. "
            "Stopping rather than spending the rest of the run learning the "
            "same fact; re-run the identical command once it is back and the "
            "resume will fill what is missing.",
            file=sys.stderr,
        )

    missing = record_completeness(args.out)
    summary = summarise(rows_path)
    (args.out / "summary.md").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 1 if missing or aborted is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
