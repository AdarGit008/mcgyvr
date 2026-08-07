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

**Every reply is kept.** Raw reply text lands in ``replies/`` beside the rows,
parseable or refused, first attempt and remediation retry alike — the JS/TS
sweep ran the parser over 160 real replies and kept only their error codes,
which is the discard #184 names and ADR-0016 forbids repeating.

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

**The worker is configuration, not part of the experiment.** Which endpoint
serves the model is a fact about somebody's machine — a hostname, a tunnel port,
the name of a variable holding a key — so it lives in a git-ignored
``worker.local.json`` beside this script rather than in a command line that has
to be retyped correctly every time. Flags beat the file. What *is* part of the
experiment is that the reader can tell which worker produced a number, so a
sweep writes ``run.json`` next to its rows and refuses to resume into a
directory measured on a different one.

Usage::

    # verify the task set (no worker needed)
    uv run --no-sync python tools/bundle/measure.py --selftest

    # the sweep, with the worker in worker.local.json
    uv run --no-sync python tools/bundle/measure.py \\
        --out records/measurements/jsts-bundle-YYYY-MM-DD

    # the same, spelled out
    uv run --no-sync python tools/bundle/measure.py \\
        --endpoint http://localhost:11434 --protocol openai \\
        --model qwen2.5-coder:3b \\
        --out records/measurements/jsts-bundle-YYYY-MM-DD

    # the table, from rows already collected
    uv run --no-sync python tools/bundle/measure.py --out <dir> --summarise-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from mcgyvr.contract import Contract, dumps, load
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


# Where the machine-specific half of a sweep lives, git-ignored. An endpoint is
# a fact about somebody's infrastructure and not about the experiment: a
# hostname, a port a tunnel happens to land on, the name of the variable holding
# a key. None of it belongs in the repository, and all of it has to be somewhere
# other than a shell history if the sweep is to be re-runnable.
WORKER_FILE = HERE / "worker.local.json"

# The only keys that file may set. Anything else is a typo that would otherwise
# be silently ignored, and a silently ignored `mdoel` is a sweep against the
# wrong worker.
WORKER_KEYS = frozenset({"endpoint", "protocol", "model", "api_key_env", "note"})

# Keys whose presence means a key value was written into the file instead of the
# name of the variable holding it. Refused rather than ignored: git-ignored is
# not encrypted, and the whole project's credential rule is that the config
# records the NAME.
SECRET_KEYS = frozenset(
    {"api_key", "apikey", "key", "token", "secret", "password", "authorization"}
)


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
    """Write the worker's file into a fresh tree and run the contract's commands.

    The commands come from ``contract.demonstration`` and ``contract.acceptance``
    — after the change both lists must pass, which is the gate's own rule, and
    the bug-fix tasks carry their one command in ``demonstration`` because it
    fails on the task's base by design (#183). They run with the task directory
    as the working directory's ancestor only by copying — nothing reaches back
    into the repository, so a worker that writes a path traversal into its file
    still only touches a temp directory that is about to be deleted.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / SOLUTION).write_text(content, encoding="utf-8")
    shutil.copy(task.accept, workdir / task.accept.name)
    for command in (*task.contract.demonstration, *task.contract.acceptance):
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


@dataclass(frozen=True)
class Worker:
    """The resolved answer to "which worker is this sweep measuring?"."""

    endpoint: str
    protocol: Protocol
    model: str
    api_key_env: str | None

    def as_endpoint(self) -> Endpoint:
        """The pool's own endpoint, so dispatch runs the shipped path."""
        return Endpoint(
            source="measure",
            base_url=self.endpoint,
            protocol=self.protocol,
            max_parallel=1,
            credential_env=self.api_key_env,
        )


def load_worker_file(path: Path) -> dict[str, str]:
    """Read the git-ignored worker file, or return nothing if there is none.

    Absent is the ordinary case and not an error — the flags alone are a
    complete way to run a sweep. What is an error is a file that is present and
    wrong, because every failure mode there is silent: an unknown key does
    nothing, and a key value in a file is a leak that git-ignoring does not
    undo.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MeasureError(f"{path}: not valid JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise MeasureError(f"{path}: expected a JSON object")

    values = {k: v for k, v in data.items() if not k.startswith("_")}
    leaked = sorted(SECRET_KEYS & {k.lower() for k in values})
    if leaked:
        raise MeasureError(
            f"{path}: {', '.join(leaked)} looks like a credential value. This "
            "file holds `api_key_env` — the NAME of the variable holding the "
            "key — never the key itself. Git-ignored is not encrypted, and the "
            "value belongs in your environment or a .env you source."
        )
    unknown = sorted(set(values) - WORKER_KEYS)
    if unknown:
        raise MeasureError(
            f"{path}: unknown key(s) {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(WORKER_KEYS))}. Keys starting with `_` "
            "are comments and are ignored."
        )
    for key, value in values.items():
        if not isinstance(value, str):
            raise MeasureError(f"{path}: {key} must be a string")
    return values


def resolve_worker(explicit: dict[str, str | None], defaults: dict[str, str]) -> Worker:
    """Settle which worker to dispatch to, flags beating the file.

    Kept separate from argument parsing because precedence is the part worth
    testing: a file that could override a flag would make a command line a
    suggestion, and the flag is what ends up quoted in a record as how the
    sweep was run.
    """
    chosen = {
        key: explicit.get(key) or defaults.get(key)
        for key in ("endpoint", "protocol", "model", "api_key_env")
    }
    missing = [k for k in ("endpoint", "model") if not chosen[k]]
    if missing:
        raise MeasureError(
            f"a sweep needs {' and '.join('--' + m for m in missing)} — pass "
            f"them, or put them in {WORKER_FILE.name} beside this script "
            "(copy worker.example.json). --selftest verifies the task set "
            "without a worker."
        )

    protocol_name = chosen["protocol"] or Protocol.OLLAMA.value
    try:
        protocol = Protocol(protocol_name)
    except ValueError:
        raise MeasureError(
            f"unknown protocol {protocol_name!r}. "
            f"Known: {', '.join(p.value for p in Protocol)}"
        ) from None

    key_env = chosen["api_key_env"]
    if key_env and not os.environ.get(key_env):
        raise MeasureError(
            f"${key_env} is not set, and the worker is declared as needing it. "
            "Export it or source your .env; the sweep refuses rather than "
            "sending twenty unauthenticated requests."
        )

    endpoint = chosen["endpoint"]
    model = chosen["model"]
    assert endpoint is not None and model is not None  # settled by `missing`
    return Worker(endpoint, protocol, model, key_env)


def check_protocol_can_carry_a_measurement(worker: Worker) -> None:
    """Refuse a wire protocol this project will not let a measurement run on.

    Every request the rig sends is ``quality_sensitive=True``, because its
    output *is* a measurement of the model. ``runner.generate`` refuses such a
    request on a caveated path before sending it, so a sweep against Ollama's
    native ``/api/generate`` produces eighty dispatch errors and no
    measurement — the failure arriving one request at a time, an hour into a
    run, phrased as a transport problem.

    CAV-01 is why the path is caveated: it scored a model at 32.3% against a
    true 84.1%. The fix is not a different endpoint but a different protocol on
    the same one — Ollama serves ``/v1/chat/completions`` on the same port.
    """
    if runner_for(worker.as_endpoint()).quality_safe:
        return
    raise MeasureError(
        f"the {worker.protocol.value} protocol cannot carry this measurement. "
        "Every request here is quality-sensitive, and mcgyvr refuses those on "
        "that path under CAV-01, which measured it scoring a model at 32.3% "
        f"against a true 84.1%. Use --protocol {Protocol.OPENAI.value}: Ollama "
        "serves /v1/chat/completions on the same port, as do vLLM, "
        "llama-server, LM Studio and TGI."
    )


def redact(url: str) -> str:
    """A URL with any embedded credentials removed, for writing down."""
    parts = urlsplit(url)
    if not (parts.username or parts.password):
        return url
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def condition_digests() -> dict[str, str]:
    """A hash per condition, so a table can be tied to the bytes it measured."""
    return {
        name: hashlib.sha256(condition_text(name).encode("utf-8")).hexdigest()
        for name in LADDER
    }


def task_digests() -> dict[str, str]:
    """A hash per task, over the contract's emitted form.

    The conditions are hashed because a reworded bundle is a different
    experiment; a rewritten contract is the same thing on the other axis, and
    until #150 moved the starting code out of the ``task`` field and into
    ``target_content`` nothing here noticed a task set being edited between two
    halves of one sweep. Hashed as :func:`~mcgyvr.contract.dumps` emits it, not
    as the file reads: a re-indented YAML block or a comment changes the bytes
    on disk and not one character of what a worker is sent.

    Every task in the tree, never the ``--tasks`` subset — a digest that
    depended on which subset ran could not be compared across two resumes.
    """
    return {
        task.id: hashlib.sha256(dumps(task.contract).encode("utf-8")).hexdigest()
        for task in load_tasks()
    }


def rig_revision() -> str:
    """The commit the rig ran at, or ``"unknown"`` rather than a guess.

    Recorded because the ladder, the task set and the parser are all under
    version control and all affect the number. "unknown" is an honest answer
    for a checkout that is not a repository; a wrong hash would not be.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=ACCEPTANCE_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def record_run(out: Path, worker: Worker, invocation: dict[str, object]) -> None:
    """Write, or extend, the provenance beside the rows.

    A rate without its backend is not quotable — CAV-02 is precisely that a
    figure from another backend describes different weights, and now that the
    worker can be anything anyone can reach, the rows no longer imply it.

    Resuming into a directory measured on a *different* worker is refused. The
    resume path exists so an interrupted sweep can be finished, and blending two
    backends into one denominator would produce a table that looks like one
    measurement and is not.
    """
    path = out / "run.json"
    identity = {
        "endpoint": redact(worker.endpoint),
        "protocol": worker.protocol.value,
        "model": worker.model,
        "conditions_sha256": condition_digests(),
        "tasks_sha256": task_digests(),
    }
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        drift = sorted(k for k, v in identity.items() if previous.get(k) != v)
        if drift:
            raise MeasureError(
                f"{path} records a different run: {', '.join(drift)} changed. "
                "Rows already here were measured on another worker, another "
                "ladder or another task set; resuming would average two "
                "measurements into one table. Use a fresh --out directory."
            )
        previous["invocations"].append(invocation)
        path.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(
        json.dumps({**identity, "invocations": [invocation]}, indent=2) + "\n",
        encoding="utf-8",
    )


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
    replies: Path | None = None,
) -> dict[str, object]:
    """One (task, condition) run, from dispatch to a scored row.

    Every way this can fail is a row rather than an exception: a transport
    error, a reply the parser refuses, a file that does not run. A cell that
    disappeared from the results would silently shrink a denominator, and the
    rate is the whole output.

    With ``replies`` set, every reply body is written there verbatim before
    anything judges it — the parseable and the refused alike, the first
    attempt and the remediation retry. The replies are the parser's real
    input distribution, which the JS/TS sweep generated and threw away
    (#184); ADR-0016 fixes what is kept as the text itself plus the sha256
    that ties it to this row.
    """

    def keep(text: str, attempt: int) -> dict[str, object]:
        if replies is None:
            return {}
        replies.mkdir(parents=True, exist_ok=True)
        name = f"{task.id}-{condition}-{attempt}.txt"
        (replies / name).write_text(text, encoding="utf-8")
        key = "reply_sha256" if attempt == 1 else "retry_sha256"
        return {key: hashlib.sha256(text.encode("utf-8")).hexdigest()}

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
    row |= keep(completion.text, 1)

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
    # The retry's stop reason is what its parse verdict is judged with; a
    # captured retry without it could not be replayed (ADR-0016).
    row |= {"retry_stop_reason": second.stop_reason.value} | keep(second.text, 2)
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
        default=None,
        help=f"wire protocol the endpoint speaks (default: {Protocol.OLLAMA.value})",
    )
    parser.add_argument(
        "--api-key-env",
        help="NAME of the environment variable holding the endpoint's key, "
        "never the key. Omit for a keyless endpoint, which is the ordinary "
        "case for a local or tunnelled backend.",
    )
    parser.add_argument(
        "--worker-file",
        type=Path,
        default=WORKER_FILE,
        help=f"git-ignored defaults for --endpoint/--protocol/--model/"
        f"--api-key-env (default: {WORKER_FILE.name} beside this script). "
        "Flags win over the file.",
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

    if args.out is None:
        print(
            "error: a sweep needs --out, a directory for its rows.\n"
            "       --selftest verifies the task set without a worker.",
            file=sys.stderr,
        )
        return 2

    conditions = [c for c in args.conditions.split(",") if c]
    unknown = sorted(set(conditions) - set(LADDER))
    if unknown:
        print(f"error: unknown condition(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    try:
        check_c2_is_the_shipped_bundle()
        worker = resolve_worker(
            {
                "endpoint": args.endpoint,
                "protocol": args.protocol,
                "model": args.model,
                "api_key_env": args.api_key_env,
            },
            load_worker_file(args.worker_file),
        )
        check_protocol_can_carry_a_measurement(worker)
    except MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    runner = runner_for(worker.as_endpoint())

    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "results.jsonl"
    already = done_keys(rows_path)
    if already:
        print(f"resuming: {len(already)} cells already recorded", file=sys.stderr)

    try:
        record_run(
            args.out,
            worker,
            {
                "started": datetime.now(UTC).isoformat(timespec="seconds"),
                "conditions": conditions,
                "tasks": [task.id for task in tasks],
                "remediate": not args.no_remediate,
                "rig_revision": rig_revision(),
            },
        )
    except MeasureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"measuring {worker.model} at {redact(worker.endpoint)} "
        f"({worker.protocol.value})",
        file=sys.stderr,
    )

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
                    worker.model,
                    workdir,
                    remediate=not args.no_remediate,
                    replies=args.out / "replies",
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
