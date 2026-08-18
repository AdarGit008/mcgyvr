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
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from mcgyvr.gate.preflight import check_prompt_fits
from mcgyvr.orchestrator.read import estimate_tokens
from mcgyvr.runner import Request, RunnerError, runner_for
from mcgyvr.sandbox.tempdir import TempDirSandbox
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


def _bench_matrix() -> types.ModuleType:
    """The condition matrix, imported by path for the same reason."""
    spec = importlib.util.spec_from_file_location(
        "bench_matrix", HERE.parent / "bench" / "matrix.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


matrix = _bench_matrix()


def _bench_score() -> types.ModuleType:
    """The bench's scorer — Gate.run, not the acceptance command alone."""
    spec = importlib.util.spec_from_file_location(
        "bench_score", HERE.parent / "bench" / "score.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


score = _bench_score()


def _bench_product() -> types.ModuleType:
    """The pinned product revision and the round it belongs to (#231 check 3)."""
    spec = importlib.util.spec_from_file_location(
        "bench_product", HERE.parent / "bench" / "product.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


product = _bench_product()


def _bench_mode() -> types.ModuleType:
    """Single-tier or full-ladder, recorded rather than asserted (#231 check 6)."""
    spec = importlib.util.spec_from_file_location(
        "bench_mode", HERE.parent / "bench" / "mode.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mode = _bench_mode()


def _bench_identity() -> types.ModuleType:
    """Run identity, and the three digests it computes for us (ADR-0027, #285).

    Shared through the ``sys.modules`` slot with the bundle rig's copy (#287):
    two loads of the contract would be the five-lists problem rebuilt one
    level down, and the bundle module above has already loaded it by the time
    this runs.
    """
    cached = sys.modules.get("bench_identity")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "bench_identity", HERE.parent / "bench" / "identity.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


identity_module = _bench_identity()


def _bench_observed() -> types.ModuleType:
    """The `observed` block's writer (#286, ADR-0027 D7).

    A sibling of the identity contract rather than part of it, because the two
    blocks are opposite: that one is compared and must stay diffable, this one
    is compared by nothing and must be comprehensive. Nothing in this file
    reads what it writes.
    """
    spec = importlib.util.spec_from_file_location(
        "bench_observed", HERE.parent / "bench" / "observed.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


observed_module = _bench_observed()

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

# How long the serving-build probe waits before recording "unknown". Short on
# purpose: this runs once per invocation against a host the sweep is about to
# dispatch thousands of draws to, so an endpoint that cannot answer in seconds
# has a problem the sweep is about to hit anyway.
BUILD_PROBE_TIMEOUT = 3.0

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

# The bench (#225), one tier per language arm — the pool's pattern exactly:
# the arm lives in the tier name, run identity carries it, and the campaign
# driver never climbs into either. Served manifest-pinned only, filtered to
# the bench half: the reserve half is training capacity (#222), never a tier,
# and an unadmitted candidate directory is not part of any run's identity.
BENCH_ROOT = HERE.parent / "bench" / "tasks"
BENCH_MANIFEST = HERE.parent / "bench" / "admissions.jsonl"
BENCH_TIERS = ("bench-ts", "bench-py")

# Prompt conditions (#225's driver question, answered paired rather than as
# separate cohorts). `stock` renders what production would dispatch;
# `noscaffold` removes the target's current content from the user message, so
# the model must produce the whole file instead of completing a partial one.
# Same problem, same checker, same prose — only the volume of required output
# moves, which is what makes the comparison paired and the pairs discordant.
#
# A condition is part of run identity, not a local flag: the ablated render is
# a different experiment on the same material, exactly the cap's argument, and
# `bundle_sha256` would not notice because it hashes the *system* prompt while
# the ablation lands in the *user* message. Names stay hyphen-free so they can
# never collide with `pin.py`'s stem parsing if a capture path ever carries
# one.
#
# #113 has now subsumed these into `tools/bench/matrix.json`, and the runner
# reads the cells rather than knowing them. The three names below are kept as
# constants because run identity is recorded under them and every existing run
# directory on disk carries one; they are asserted against the matrix at import
# so a rename in the data can never silently orphan a run.
STOCK = "stock"
PLAN_ONLY = "planonly"
NO_SCAFFOLD = "noscaffold"

MATRIX = matrix.load()
CONDITIONS = tuple(MATRIX.cells)

assert MATRIX.baseline.id == STOCK, "the matrix baseline must stay `stock`"
assert {STOCK, PLAN_ONLY, NO_SCAFFOLD} <= set(CONDITIONS), (
    "matrix.json dropped a cell that runs on disk are recorded under"
)

# Comment openers, by the two languages the bench arms speak.
_COMMENT = ("//", "#")

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


def pinned_bench_ids() -> frozenset[str]:
    """The bench half of the bench manifest — the only ids a bench tier serves.

    Same argument as :func:`pinned_pool_ids`, plus the split: the manifest
    records each admitted problem's half under the pre-declared rule
    (``tools/bench/split.py``), and only ``split == "bench"`` is instrument
    material. The reserve half lives outside the declared roots and is never
    served; an entry here saying otherwise would be caught by
    ``admit.py --verify`` long before a sweep.
    """
    if not BENCH_MANIFEST.is_file():
        return frozenset()
    admitted: set[str] = set()
    for line in BENCH_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if not entry.get("superseded_by") and entry.get("split") == "bench":
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
    elif tier in BENCH_TIERS:
        root = BENCH_ROOT / tier.removeprefix("bench-")
        language = bundle.PYTHON if tier == "bench-py" else bundle.JSTS
        admitted = pinned_bench_ids()
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
            f"Known: {TIERS + VARIANT_TIERS + POOL_TIERS + BENCH_TIERS}"
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


def ablate(contract: Any, condition: str) -> Any:
    """The contract as the named condition renders it.

    ``stock`` is the contract untouched. ``noscaffold`` empties
    ``target_content``, which is the single field
    :func:`~mcgyvr.worker.prompt.render_user_message` turns into the "CURRENT
    CONTENT OF <target>" section — so the ablation removes exactly one
    section and changes nothing else about the task, the interface, the stop
    conditions or the checker.

    On a contract that carries no ``target_content`` the ablation is a no-op
    by construction, which is why the eligible set has to be selected by the
    caller: an ineligible task would contribute a concordant pair to a paired
    test and dilute it. ``bug_fix`` is ineligible for a stronger reason — its
    ``target_content`` is the buggy file the task exists to fix, so removing
    it does not lighten the task, it deletes it.

    The cell's levers, their order and their conflicts are
    ``tools/bench/matrix.json``'s (#113); what stays here is the runner's own
    knowledge of the scaffold's comment syntax, which the matrix injects rather
    than duplicates.
    """
    try:
        cell = MATRIX.cell(condition)
    except matrix.MatrixError as exc:
        raise bundle.MeasureError(str(exc)) from None
    return matrix.apply_contract(cell, contract, plan_of=plan_of)


def render_for(condition: str, contract: Any) -> Any:
    """Assemble the dispatch, then apply the cell's message-stage levers.

    Split from :func:`ablate` because the two stages answer different
    questions: a contract lever changes the task the worker is given, a message
    lever changes only how it is asked. A cell naming no message lever returns
    exactly what ``build_prompt`` returned, so the baseline path is untouched.

    The re-cost is not cosmetic. ``norule`` *removes* text, so carrying the
    assembled token count forward would price the ablation as free on the cost
    axis #113 asks the report to carry.
    """
    prompt = build_prompt(contract)
    return matrix.apply_message(
        MATRIX.cell(condition),
        prompt,
        contract=contract,
        estimate=estimate_tokens,
        check_fits=check_prompt_fits,
    )


def plan_of(target_content: str) -> str:
    """The scaffold's comment lines alone — its plan, with its code removed.

    Every scaffold in this bench states an approach in a comment ("build a
    prefix-sum table, then validate each query", "find the cheapest
    combination of passes covering every trip"), which means ``noscaffold``
    removes *two* things at once: the code the model would have typed, and
    the recipe telling it what to do. That is the two-knob confound this
    experiment exists to avoid, and it would have been reported as a size
    effect.

    Keeping the comments and dropping the code splits the difference into
    two paired contrasts on the same problems: ``stock`` against
    ``planonly`` is the code the scaffold saved, and ``planonly`` against
    ``noscaffold`` is the plan it stated.

    One honest limit: these comments often name what to *validate* as well
    as what to compute, so the plan contrast is "being told the approach,
    including its rejections" rather than pure algorithmic insight. A
    scaffold with no comments at all degenerates to ``noscaffold``, which is
    a concordant pair and dilutes the test — the caller selects the eligible
    set, exactly as for ``noscaffold``.
    """
    kept = [
        line
        for line in target_content.splitlines()
        if line.strip().startswith(_COMMENT)
    ]
    return "\n".join(kept) + "\n" if kept else ""


def measure_task(
    task: Any,
    runner: Any,
    model: str,
    workdir: Path,
    candidates: Path,
    already: set[tuple[str, str, int]],
    plan: list[tuple[str, int, float]] | None = None,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    condition: str = STOCK,
) -> list[dict[str, object]]:
    """Every draw of one task, each a row — and never an early exit.

    A draw that passes does not end the task: the index distribution *is* the
    result, and stopping at the first pass would truncate every observation at
    its own answer. Every failure mode is a row rather than an exception, for
    the bundle rig's reason — a vanished cell silently shrinks a denominator.

    ``condition`` names the ablation the prompt is rendered under. It is part
    of the run identity rather than a local flag, because the ablated render
    is a different experiment on the same material — the cap's argument.
    """
    ablated = ablate(task.contract, condition)
    prompt = render_for(condition, ablated)
    rows: list[dict[str, object]] = []
    with _task_sandbox(task, ablated, workdir) as sandbox:
        rows = _draws(
            task,
            runner,
            model,
            candidates,
            already,
            plan,
            max_output_tokens,
            prompt,
            sandbox,
        )
    return rows


@contextmanager
def _task_sandbox(task: Any, ablated: Any, workdir: Path) -> Iterator[Any]:
    """One sandbox per task, holding the pre-worker tree the gate diffs against.

    The base is staged from the *ablated* contract, so the state the changeset
    is computed against is the state the worker was shown. Opened once per task
    and reset per draw: the workspace, its git base commit and the reset are
    E4's, and paying for them per draw would multiply the cost by the plan.
    """
    base = score.stage_dir(task, ablated.target_content, workdir / f"{task.id}-base")
    with TempDirSandbox(base) as sandbox:
        yield sandbox


def _draws(
    task: Any,
    runner: Any,
    model: str,
    candidates: Path,
    already: set[tuple[str, str, int]],
    plan: list[tuple[str, int, float]] | None,
    max_output_tokens: int,
    prompt: Any,
    sandbox: Any,
) -> list[dict[str, object]]:
    """The draw loop, with the sandbox already open."""
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
        verdict = score.score(task, parsed.content, sandbox)
        rows.append(
            row
            | {
                "passed": verdict.passed,
                "parse_error": None,
                "acceptance_s": round(time.monotonic() - started, 3),
                # Which rung rejected, and whether the acceptance command ran
                # at all. The gate short-circuits, so a candidate rejected at
                # lint never reached acceptance and this row cannot say what it
                # would have done — the acceptance-only rate every earlier
                # figure was measured at is NOT recoverable from a gate run.
                # That is why #231 re-runs rather than recomputes.
                "rejected_by": verdict.rejected_by,
                "rejected_before_acceptance": verdict.rejected_before_acceptance,
                "fail_output": None if verdict.passed else "; ".join(verdict.findings),
                "environment_issues": list(verdict.environment_issues) or None,
                # Which rungs could not say what bar they applied (#261). A row
                # with this set was scored by fewer rungs than the tier
                # declares; a rate that pools it is not the rate it names.
                "inconclusive": list(verdict.inconclusive) or None,
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


@cache
def serving_build(endpoint: str) -> str | None:
    """The serving stack's build at ``endpoint``, or ``None`` when it won't say.

    ADR-0024: two rates are only comparable if the same build produced them.
    This is not hypothetical. The scaffold ablation ran the 3B against srv1 and
    the 7B against srv2 while those two hosts sat on ollama 0.32.4 and 0.32.5,
    so the one cross-model contrast the campaign most wanted to draw had a
    serving-build difference folded into it that no manifest recorded.

    Best-effort by design. An endpoint that does not answer ``/api/version`` is
    not one this project refuses to measure — it is one whose build is unknown,
    and ``None`` says exactly that rather than inventing a value. Cached per
    endpoint because a sweep records its provenance once per invocation and the
    answer cannot change underneath a run without invalidating the run anyway.
    """
    url = endpoint.rstrip("/") + "/api/version"
    try:
        with urllib.request.urlopen(url, timeout=BUILD_PROBE_TIMEOUT) as response:
            version = json.loads(response.read()).get("version")
    except Exception:
        return None
    return str(version) if version else None


def stage_bar(into: Path) -> None:
    """Stage the workspace a candidate is scored in, minus the candidate.

    ``score.stage_config`` and nothing else, *called* rather than restated. The
    bench's bar is not this repository's ``make lint`` bar: it is whatever a
    workspace carries, which is a ``pyproject.toml`` rendered from the project's
    ``[tool.ruff]`` beside ``eslint.config.mjs``, ``prettier.config.mjs`` and a
    linked ``node_modules``. Resolving the repository's own settings instead
    would digest a bar no candidate is ever scored against.

    This used to hold its own copy of those steps, which is how a bar digest
    comes to describe a workspace nothing is scored in: #262's defect, one
    level in. The seam is now ``score.stage_config`` and the drift is not
    available.
    """
    score.stage_config(into)


def content_identity(
    tasks: Sequence[Any], *, condition: str, worker: Any
) -> tuple[dict[str, Any], dict[str, str]]:
    """The three digests ADR-0026 asked for, computed by `identity` (#285).

    Returns ``(fields, refusals)``. Every field is always present — ``null``
    where the world would not answer, with the reason in ``refusals`` — because
    an **absent** key means the record predates the contract (ADR-0027 D2) and a
    run made from here on must never claim that about itself.

    Nothing here assembles a hash. This function's whole job is to hand
    ``identity`` raw material: the tasks as this condition renders them, the
    staging a candidate is scored under, and an endpoint to ask.

    **The prompt is hashed over every task, not the first one.** ``record_run``
    already builds the first task's prompt for ``bundle_sha256``, and that is
    the curated-subset defect at a smaller scale: a 498-task sweep is not
    described by task one. Rendering all of them is pure CPU and happens once
    per run, against hours of dispatch.
    """
    fields: dict[str, Any] = {}
    refusals: dict[str, str] = {}

    rendered: dict[str, tuple[str, str]] = {}
    try:
        for task in tasks:
            prompt = render_for(condition, ablate(task.contract, condition))
            rendered[task.id] = (prompt.system, prompt.user)
    except (bundle.MeasureError, matrix.MatrixError) as error:
        rendered = {}
        refusals["prompt_sha256"] = f"this tier's tasks would not render: {error}"
    fields["prompt_sha256"] = (
        identity_module.prompt_digest(rendered) if rendered else None
    )

    language = tasks[0].language.name if tasks else ""
    # One resolution, hashed and recorded, rather than two calls that could
    # answer differently. `bar_sha256` is the comparability key; the readable
    # block beside it is what lets a reader of a ts/py contrast see *what*
    # differed between the bars and not only that something did (#262).
    material, why = identity_module.bar_material(
        rungs=score.GATE_RUNGS, language=language, stage_workspace=stage_bar
    )
    fields["bar_sha256"] = (
        None if material is None else identity_module.digest(material)
    )
    fields[identity_module.BAR] = material
    if why is not None:
        refusals["bar_sha256"] = why

    model_fields, model_refusals = identity_module.probe_model(
        worker.endpoint, worker.model
    )
    fields.update(model_fields)
    refusals.update(model_refusals)
    return fields, refusals


#: Every identity field this rig's ``record_run`` writes, declared beside it so
#: the resume check is over a named set rather than the keys of the local dict
#: it just assembled (#287, ADR-0027 D1). Derived from the new dict, the check
#: could never notice a field added to ``identity.GROUPS`` that this rig fails
#: to write, nor a field ``previous`` carries that a resume no longer does — a
#: test asserts a freshly assembled manifest's keys, minus the two annotations,
#: equal this tuple, and that every name here is in ``identity.RECORDED``.
#:
#: ``round`` and ``product_sha256`` are written for bench tiers only; on a
#: `d1`-`d3` or `pool-*` resume both sides are absent, which
#: ``identity.drift`` reads as agreement rather than drift.
IDENTITY_FIELDS: tuple[str, ...] = (
    "endpoint",
    "protocol",
    "model",
    "serving_build",
    "tier",
    "draws",
    "greedy_temperature",
    "sampled_temperature",
    "max_output_tokens",
    "condition",
    "gate_rungs",
    "gate_semantic",
    "mode",
    "bundle_sha256",
    "tasks_sha256",
    "prompt_sha256",
    "bar_sha256",
    "model_sha256",
    "vocabulary_sha256",
    "merges_sha256",
    "template_sha256",
    "round",
    "product_sha256",
)


def record_run(
    out: Path,
    worker: Any,
    invocation: dict[str, object],
    tier: str = "d1",
    draws: int = DRAWS,
    sampled_temperature: float = SAMPLED_TEMPERATURE,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    condition: str = STOCK,
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

    **The serving build is probed here rather than passed in.** ``--condition``
    was a caller-supplied identity field, it reached dispatch and not this
    function, and eight manifests described a render nobody had run. A field
    this function derives from the world cannot be forgotten by a fourth
    driver, so this one is derived. A manifest written before the field existed
    carries none, and adopts the current value instead of refusing: the
    protection is for runs made from here on, and a spurious refusal on every
    directory already on disk would buy nothing.
    """
    bundle.instruments.refuse_to_measure(tier=tier, what=f"{out}/run.json")
    tasks = load_tier_tasks(tier)
    prompt = build_prompt(tasks[0].contract)
    content, refusals = content_identity(tasks, condition=condition, worker=worker)
    identity = {
        "endpoint": bundle.redact(worker.endpoint),
        "protocol": worker.protocol.value,
        "model": worker.model,
        "serving_build": serving_build(worker.endpoint),
        "tier": tier,
        "draws": draws,
        "greedy_temperature": GREEDY_TEMPERATURE,
        "sampled_temperature": sampled_temperature,
        "max_output_tokens": max_output_tokens,
        "condition": condition,
        # The bar the rates in this directory were measured against. A run
        # scored by a different set of rungs is a different instrument, and
        # every figure on disk before 2026-08-12 was "acceptance" alone —
        # so a reader can tell the two apart without knowing the date.
        "gate_rungs": list(score.GATE_RUNGS),
        "gate_semantic": False,
        # Whether the rates here are one tier's or the ladder's (#231 check 6).
        # This rig dispatches to a single worker and never escalates, so it can
        # only ever write `single-tier`; the field exists so a *report* reads
        # the fact off the run instead of printing a string literal that would
        # survive unchanged into the first run that does escalate.
        "mode": mode.SINGLE_TIER,
        "bundle_sha256": hashlib.sha256(prompt.system.encode("utf-8")).hexdigest(),
        "tasks_sha256": tier_digests(tier),
        # The bar, the prompt and the weights as CONTENT rather than as names
        # (#285). `gate_rungs` above is five names both arms write identically,
        # `bundle_sha256` hashes the system half of a prompt whose user half is
        # what the ablation edits, and `model` is a mutable tag. Each of these is
        # computed inside `tools/bench/identity.py` and never assembled here:
        # a runner that builds a hash and passes it in is `--condition` with a
        # longer hex string.
        **content,
    }
    # `null` is a state, and D2 says it comes with a reason. The reason cannot
    # live in the field without being the sentinel string D2 forbids, so it
    # lives in one sibling block a reader finds where they found the null.
    if refusals:
        identity[identity_module.REFUSALS] = refusals
    # The round, and the product revision it pins (#231 check 3, ADR-0018).
    #
    # `bundle_sha256` hashes the system prompt and `tasks_sha256` the task set;
    # between them sat the user-message render, the reply parser and the whole
    # of `Gate.run` — everything that decides what a worker is sent and whether
    # its answer passes. Two arms could be scored by two different bars and laid
    # in one table with nothing on disk to say so.
    #
    # Bench tiers only. A round is ADR-0018's unit for *the bench*, where arms
    # are compared against each other; `d1`-`d3` and `pool-*` are other
    # instruments with their own questions, and stamping a revision they do not
    # compare across would refuse their resumes for a boundary that does not
    # apply to them. The refusal below is what stops a change landing mid-round.
    if tier in BENCH_TIERS:
        try:
            round_id, revision = product.require_pinned()
        except product.ProductError as error:
            raise bundle.MeasureError(str(error)) from error
        identity["round"] = round_id
        identity["product_sha256"] = revision
    path = out / "run.json"
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        previous.setdefault("serving_build", identity["serving_build"])
        # `mode` is adopted forward where `product_sha256` below is not, and the
        # difference is whether the missing value is knowable. No rig in this
        # tree has ever escalated, so a manifest without the field was
        # single-tier and saying so adds a true fact; a manifest without a
        # product revision was measured against a revision nobody recorded, and
        # stamping today's onto it would invent one.
        previous.setdefault("mode", identity["mode"])
        # The #285 digests are adopted forward on ABSENCE and never on `null`,
        # and the two are different facts about a directory. Absent is a
        # manifest written before there was a writer — refusing to resume it on
        # a key it could not have carried is a spurious refusal, which is
        # `serving_build`'s argument above. `null` is a run whose endpoint or
        # toolchain was asked and would not say; if it answers on the resume,
        # the directory would hold rows measured under a bar or a set of weights
        # nobody recorded beside rows measured under ones somebody did, and
        # appending is exactly what must not happen quietly. That is drift, and
        # it refuses below.
        for field in (
            *identity_module.MODEL_PROBE_FIELDS,
            "prompt_sha256",
            "bar_sha256",
        ):
            previous.setdefault(field, identity[field])
        # The reasons block is an annotation on the fields, not a field. Two
        # invocations that both failed to reach an endpoint may phrase it
        # differently — a timeout on one, a refused connection on the next —
        # and that is not a second run. What must agree is what the fields say.
        # `bar_resolved` joins the reasons block in being an annotation rather
        # than a field: it is the material `bar_sha256` hashes, so comparing
        # both would refuse a resume twice for one change — and would refuse it
        # for a cosmetic edit to a config comment, which the digest also catches
        # but which reads very differently in a 250-rule diff. Neither is in
        # IDENTITY_FIELDS, which is how they stay out of the comparison (#287).
        drift = identity_module.drift(previous, identity, fields=IDENTITY_FIELDS)
        if drift:
            # A bench directory written before rounds existed carries no
            # revision, so `round` and `product_sha256` show as drift here. That
            # is the right answer and not a migration gap: those rows were
            # measured against a revision nobody recorded, and appending rows
            # measured against `r1` would put two revisions in one distribution
            # — the exact confound check 3 exists to prevent. Unlike
            # `serving_build`, this one is not adopted forward.
            raise bundle.MeasureError(
                f"{path} records a different run: {', '.join(drift)} changed. "
                "Rows already here were measured on another worker, another "
                "sampler or another task set; resuming would average two "
                "experiments into one distribution. Use a fresh --out directory."
            )
        # Adopted forward, never overwritten. A directory written before this
        # block existed gains the bar it was measured against — the digest it
        # already carries proves the bar has not moved, since drift refused
        # above otherwise — and a directory that already states one keeps its
        # own words, so a resume never rewrites the description of rows it did
        # not measure.
        previous.setdefault(identity_module.BAR, identity[identity_module.BAR])
        previous["invocations"].append(invocation)
        path.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(
        json.dumps({**identity, "invocations": [invocation]}, indent=2) + "\n",
        encoding="utf-8",
    )
    # The second block (#286, ADR-0027 D7): everything the endpoint will answer
    # about itself, beside the block that gets compared. Written here — on the
    # branch that OPENS the directory — and not on the resume above, because it
    # describes the server the rows were started against. A resume writes
    # nothing: capturing again would restate rows this invocation did not
    # measure, and a resume against a materially different server is refused by
    # the keyed drift check above, which is where a refusal belongs. A directory
    # opened before this contract existed therefore never gains one, which is
    # the same "absent means predates the contract" reading D2 gives run.json.
    #
    # Nothing in this file reads what this writes.
    observed_module.write(out, worker.endpoint, worker.model)


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


# The facts a rate has to be quoted with (#113).
#
# `serving_build` is deliberately NOT among them. ADR-0024 makes the build part
# of a run's identity, but `serving_build()` already decided what an unreachable
# probe means: "an endpoint that does not answer /api/version is not one this
# project refuses to measure — it is one whose build is unknown, and None says
# exactly that rather than inventing a value." A recorded "unknown" is a
# statement, so the header prints it and flags the limit. The risk ADR-0024
# actually guards — two builds inside one contrast — is caught where it lives,
# in `report.require_comparable`, which refuses a table mixing them.
REQUIRED_PROVENANCE = ("model", "endpoint", "tier", "condition")


def missing_provenance(recorded: Mapping[str, Any]) -> list[str]:
    """Which of the facts a quotable rate needs are absent from a manifest."""
    return [k for k in REQUIRED_PROVENANCE if not recorded.get(k)]


def describe_run(recorded: Mapping[str, Any]) -> list[str] | None:
    """The header every figure in a report is quoted under, or ``None``.

    ``None`` means the run cannot be described, and a report that cannot
    describe its subject must not state a rate for it.

    Two of the lines are declarations the manifest is read for rather than
    sentences this function knows: the **mode** (#231 check 6 — a floor failure
    rescued by a higher rung makes the floor invisible, so a rate must say which
    of the two it is), and the **round** (#231 check 3 — which product revision
    produced it). Both were string literals here until the fields existed to
    read, which is a claim the code could not check.
    """
    if missing_provenance(recorded):
        return None
    rungs = recorded.get("gate_rungs")
    bar = (
        "acceptance command only (pre-#113 scorer)"
        if not rungs
        else "Gate.run [" + ", ".join(rungs) + "]"
    )
    build = recorded.get("serving_build")
    lines = [
        f"**{recorded['model']}** on {bundle.redact(recorded['endpoint'])} "
        f"(build {build or 'unknown'}), tier `{recorded['tier']}`, "
        f"condition `{recorded['condition']}`",
        "",
        f"- scored by: {bar}",
        mode.declare(recorded),
        product.declare(recorded),
    ]
    if not build:
        lines.append(
            "- **the serving build is unknown** — the endpoint did not answer "
            "`/api/version`, so this run cannot be laid beside one from a "
            "different build (ADR-0024)"
        )
    return lines


def cost_axis(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Tokens spent per candidate — the outcome axis beside acceptance.

    Reported over every row that reached a worker, passing or not: the price of
    a condition is what it costs to *ask*, and a condition that fails cheaply is
    a different proposition from one that fails expensively.
    """
    scored = [
        r
        for r in rows
        if isinstance(r.get("prompt_tokens"), (int, float))
        and isinstance(r.get("completion_tokens"), (int, float))
    ]
    if not scored:
        return []
    prompt = sum(r["prompt_tokens"] for r in scored) / len(scored)
    completion = sum(r["completion_tokens"] for r in scored) / len(scored)
    return [
        "",
        f"cost per candidate: {prompt:.0f} prompt + {completion:.0f} completion "
        f"tokens (mean over {len(scored)} dispatched draws)",
    ]


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
    recorded: dict[str, Any] = {}
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

    # Provenance sits between completeness and the first rate, and that order is
    # two requirements meeting rather than a preference. #217 fixed completeness
    # as the *first* line, because a holed run's warning is what gets scrolled
    # past. #113 requires that no rate be stated without a model, a rig and a
    # bar. Both hold: the hole leads, the subject precedes every figure.
    provenance = describe_run(recorded)
    if provenance is None:
        lines.append(
            "**NO RATE — this directory cannot say what produced it.** "
            f"Missing from run.json: {', '.join(missing_provenance(recorded))}. "
            "A pass rate names a model on a rig under a bar or it names "
            "nothing, so none is stated below."
        )
        lines.append("")
        lines.append(f"{len(rows)} rows on disk.")
        return "\n".join(lines)
    lines.extend(provenance)
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

    # The second outcome axis (#113, ADR-0018): a pass rate alone cannot rank
    # levers, because the levers differ far more in price than in effect. Tokens
    # rather than wall clock, because tokens are what the north star's
    # denominator counts and what transfers across rigs.
    lines.extend(cost_axis(rows))

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
        choices=TIERS + VARIANT_TIERS + POOL_TIERS + BENCH_TIERS,
        default="d1",
        help="difficulty tier to run (default d1, the bundle rig's set); "
        "pool-ts/pool-py are the #197 problem pool's arms, not rungs; "
        "bench-ts/bench-py are the #225 bench's arms, manifest-pinned",
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
        "--condition",
        choices=CONDITIONS,
        default=STOCK,
        help=f"condition cell (default {STOCK}, the baseline — what production "
        "dispatches). The cells and the levers they name are data in "
        "tools/bench/matrix.json, not choices this runner knows (#113); a cell "
        "may name more than one lever, and two levers writing the same slot are "
        "refused when the matrix loads. Part of the run identity: a directory "
        "measured under one cell refuses another.",
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
        language = (
            bundle.PYTHON if args.tier in ("pool-py", "bench-py") else bundle.JSTS
        )
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
            condition=args.condition,
        )
    except bundle.MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Before a single draw is dispatched: can every rung this run declares
    # actually execute on this material? A missing linter is an *environment
    # issue* to the gate and not a finding, so the candidate passes and the run
    # is scored by a quietly smaller bar. That is right for production and
    # silently wrong for an instrument — see score.preflight.
    try:
        score.require_rungs(tasks)
    except score.RungUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"measuring {worker.model} at {bundle.redact(worker.endpoint)} "
        f"({worker.protocol.value}), tier {args.tier}, {args.draws} sampled "
        f"draws per task at T={args.sampled_temperature}, "
        f"cap {args.max_output_tokens}, no early exit, "
        f"scored by Gate.run [{', '.join(score.GATE_RUNGS)}]",
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
                condition=args.condition,
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
