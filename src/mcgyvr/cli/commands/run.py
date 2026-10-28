"""The `run` subcommand, and everything a run does.

`run` loads a contract, refuses a repository that is not a git checkout, settles
the session, the config, the journal directory and the delivery policy, and then
takes one of two paths: a deterministic contract runs the program its task type
binds and is judged by the gate (`_floor`), while any other contract climbs the
ladder of units until a rung is accepted or a ceiling stops it (`_climb`). Either
way the run becomes a `RunResult` written into the journal's results directory,
copied into the `--record` and `--result` mirrors the caller asked for, and the
run's own exit code is returned.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr import atomic
from mcgyvr.config import (
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)
from mcgyvr.config import config_path as resolve_config_path
from mcgyvr.config import load as load_config
from mcgyvr.exits import Exit

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.deliver import Accepted
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.drive import Recording
    from mcgyvr.escalate import Delivered, Halted, Judgement
    from mcgyvr.gate import GateResult
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.result import RunResult
    from mcgyvr.route import Attempted, Try
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.session import Session

from mcgyvr.cli.common import (
    setup_doc,
)
from mcgyvr.cli.fleet_live import _admitted_live, _live
from mcgyvr.cli.sandbox import (
    _sandbox_policy,
    _say_what_the_sandbox_leaves_out,
)


def _run(args: argparse.Namespace) -> int:
    """Run one contract and write its result.

    The contract is loaded and the repository checked first, then the session
    and the config are settled, the journal directory is made, and the result's
    skeleton is filled in before any work starts. A deterministic contract goes
    to `_floor` and every other one to `_climb`. Afterwards the mirror copies
    are reported, and the result is written to `--result` (or the journal's
    copy) and copied into every mirror. The exit code returned is the run's.
    """
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.contract import ContractError
    from mcgyvr.contract import load as load_task_contract
    from mcgyvr.deliver import between_deliveries
    from mcgyvr.drive import Recording, gate_adapters
    from mcgyvr.notes import CarriedNotes, NotesError, primed, seeded
    from mcgyvr.result import (
        RunResult,
        result_path,
        run_stamp,
        write,
    )
    from mcgyvr.telemetry import run_tags

    session: Session = args.session

    try:
        contract = load_task_contract(Path(args.contract))
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # An earlier run's failure notes, read and checked before anything else is
    # spent: a seed that is not a sound result of this contract stops the run
    # here rather than send a climb told something it should not have been.
    # `delegate --run` builds its own arguments and names no seed.
    args.notes_from = getattr(args, "notes_from", None)
    seed: tuple[CarriedNotes, ...] = ()
    if args.notes_from is not None:
        try:
            seed = seeded(Path(args.notes_from), contract=contract.id)
        except NotesError as exc:
            print(f"error: --notes-from {args.notes_from}: {exc}", file=sys.stderr)
            return 1
    args.notes_seed = seed

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 1
    # The sandbox holds the committed tree, so uncommitted and untracked files
    # the contract's commands need are not in it. Say so once here, where the
    # note is printed and kept for the result, rather than inside each gate.
    # Beside other runs of one batch (`delegate --run --jobs`), the working
    # tree is read between two of their deliveries, never in the middle of one.
    with (
        between_deliveries(repo)
        if getattr(args, "beside_others", False)
        else contextlib.nullcontext()
    ):
        notes = _say_what_the_sandbox_leaves_out(repo)

    # The floor needs no units, so a deterministic contract can run with no
    # config at all; a contract that climbs cannot. `path` is kept only so a
    # message can name the setup, and `named` records whether the caller named
    # one, which is what tells a bare install from a setup that is there and
    # broken.
    config: Config | None = None
    config_error: ConfigError | None = None
    # `chosen` is what the caller named with `--config`; `named` is that, or the
    # path the environment names. Discovery is `load`'s own job, since it is
    # handed `chosen` and finds the live fleet folder itself, while
    # `resolve_config_path` is called only to have something to name in a
    # message, and its failure is swallowed because "no setup" is reported by the
    # load below. `config` stays None when that load fails, and `config_error`
    # carries the reason why.
    chosen = Path(args.config) if args.config else None
    named = chosen if chosen is not None else named_config_path()
    try:
        path: Path | None = named if named is not None else resolve_config_path()
    except ConfigError:
        path = None
    try:
        config = load_config(chosen)
    except ConfigError as exc:
        config_error = exc
    if config is None and not contract.is_deterministic:
        # No config and a contract that has to climb: there is no ladder, no unit
        # to ask and no reviewer, so nothing could run or judge the work. Stop
        # here and point at the document that sets a setup up, rather than climb
        # something the caller never declared.
        print(f"error: {config_error} {setup_doc()} says how.", file=sys.stderr)
        return 1

    # Where the journal lives: `journal.dir` from the config, or the default
    # under the state directory when there is no config or the key is unset. `~`
    # is expanded because the default names it, and every path recorded below is
    # built inside this directory.
    configured = config.get("journal.dir") if config is not None else None
    journal_dir = Path(configured or JOURNAL_DIR_DEFAULT).expanduser()
    # `--record` asks for a second, complete copy of this run in a directory of
    # the caller's own: the same journal rows, blobs and results the journal
    # gets. It is a mirror only when it resolves somewhere other than the
    # journal directory itself, since naming the journal would be a copy onto
    # itself, and that case is dropped instead of written twice. `mirrors` is
    # that decision, threaded through everything that writes: `Recording` copies
    # each journal row and blob to every mirror as it appends it, the result is
    # copied once it is written. mcgyvr's own copy under `journal.dir` is never
    # moved or replaced by any of it. A mirror that cannot be written is
    # reported where it failed and never stops the run, and the failures are
    # carried out on `Recording.copy_errors` for the result file.
    asked = Path(args.record).expanduser() if args.record is not None else None
    mirrors = (
        (asked,)
        if asked is not None and asked.resolve() != journal_dir.resolve()
        else ()
    )

    # One stamp for the whole run: UTC to the microsecond, so two runs of the
    # same contract never share a result file name. It names this run's result
    # below, and it is the `run` field carried on the journal
    # rows, which is how the rows of one run are told from those of the next.
    stamp = run_stamp()
    # `keep` is the journal's own copy, under results/, written for every run.
    # `where` is where the caller asked to read it (`--result`), the same path
    # unless the flag names another one, and both are written below.
    keep = result_path(journal_dir, contract.id, stamp)
    where = Path(args.result) if args.result else keep

    bare_install = isinstance(config_error, ConfigMissingError) and named is None
    if config_error is not None and not bare_install:
        # A setup that exists but does not read is not fatal here: the floor needs
        # no units, so a deterministic contract can run without one. The one case
        # that stays quiet is a bare install, a ConfigMissingError with no setup
        # named by flag or environment, because that is a machine where no fleet
        # has been set up yet rather than a run with a mistake in it.
        # Every other failure is said out loud: an unreadable or invalid file, or
        # a `--config`/$MCGYVR_CONFIG path that is not there. The run is about to
        # go without the journal, sandbox, gate and delivery settings that setup
        # declared, so the caller is told which setup was refused and where the
        # result will be. It is a note and not a refusal because the gate can
        # still judge this contract without any of it, and refusing would throw
        # away work the floor is able to do. `reason` flattens the error to one
        # line so the note reads as one sentence.
        reason = " ".join(str(config_error).split())
        print(
            f"note: {path or 'the config'} is not usable ({reason}); this run "
            "goes on without "
            f"a config and sends its result to {where}"
        )

    report = RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        target=contract.target,
        session=session.name,
        run=stamp,
        session_file=str(session.session_file) if session.session_file else None,
        journal=str(journal_dir),
        notes=notes,
    )
    if args.notes_from is not None:
        # What the seed was and how much of it the climb opens with: all of it
        # under `retry_notes: climb`, none under the other modes or on the
        # floor, which has no climb to tell.
        handing = (
            str(config.get("retry_notes", "climb"))
            if config is not None and not contract.is_deterministic
            else "none"
        )
        report.seeded = {
            "from": str(args.notes_from),
            "handed": len(primed(seed, handing)),
            "records": [record.carried_json() for record in seed],
        }

    # The journal sink for this run: DIR/<session>.jsonl, plus every mirror.
    try:
        recording = Recording(
            path=journal_dir / f"{session.name}.jsonl",
            orchestrator=session.name,
            run=stamp,
            session_file=session.session_file,
            mirrors=mirrors,
        )
        # MCGYVR_RUN_TAGS is parsed and validated before any work runs: a tag that
        # is not a flat JSON object is refused rather than copied onto rows.
        run_tags()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # Every run has to be recorded, so the journal directory is made now, before
    # any work: a run whose rows cannot be written is refused here instead of run
    # unrecorded. `Recording` above is built without touching the filesystem,
    # which is why this check is here and not there.
    try:
        journal_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            f"error: the journal at {journal_dir} cannot be written ({exc}). "
            f"Every run is recorded there, so this one is refused rather than "
            f"run unrecorded. Fix the directory, or set `journal.dir` to one "
            f"that works.",
            file=sys.stderr,
        )
        return 1
    print(f"journal: {recording.path}", file=sys.stderr)

    # Settle the sandbox mode before either path opens one: `--sandbox` when it
    # was given, else `sandbox.mode` from the config, else its built-in default.
    args.sandbox = _sandbox_mode(args.sandbox, config)
    # The language adapters the gate judges a change with, taken from the
    # config's `gate` settings. Settled once and put on the args so that delivery
    # re-judges the change with the adapters the gate used, without a second read
    # of the config.
    args.gate_adapters = gate_adapters(config)
    # `--commit`/`--no-commit`/`--branch` settled against `delivery.commit` and
    # `delivery.branch`, so delivery sees one answer, not a flag and a policy.
    _settle_delivery(args, config)

    if contract.is_deterministic:
        code = _floor(args, contract, repo, report, config, recording=recording)
    else:
        assert config is not None  # a climbing contract with none was refused above
        code = _climb(args, contract, repo, config, recording=recording, report=report)

    report.exit_code = code
    # A mirror that failed while the run was going was recorded rather than
    # raised, and the run continued. Put the failures on the result as well, so a
    # reader of the result file learns that its mirror is short a row or a
    # result, and say them here, next to the line that names the run's outcome.
    for mirror, why in recording.copy_errors.items():
        report.copy_errors[str(mirror)] = why
        print(
            f"error: the copy of this run's journal asked for in {mirror} could "
            f"not be written ({why}). mcgyvr's own record under {journal_dir} is "
            f"complete and the run was not stopped for it.",
            file=sys.stderr,
        )

    # The result file, last, so it carries everything the run learned. It goes to
    # `where` and, when the caller named a different path, to the journal's own
    # copy under results/ as well. A result that cannot be written is the one
    # failure that leaves nothing behind but the journal rows, so it is reported
    # with what the run came to and exits 1: a run whose outcome the caller
    # cannot read is not a success.
    failed = where
    try:
        written = write(where, report)
        if keep != where:
            failed = keep
            _copy(written, keep)
    except OSError as exc:
        # `failed` names the file that could not be written: `where` if that is
        # what failed, else the journal's own copy, which is written second.
        # `went` keeps the delivery text from being printed twice, since a
        # delivery that refused sets the detail and the delivery to the same
        # words.
        went = report.delivery if report.delivery != report.detail else ""
        print(
            f"error: the result could not be written to {failed}: {exc}. "
            f"The run came to {report.outcome}"
            + (f": {report.detail}" if report.detail else "")
            + (f"; {went}" if went else "")
            + f" (exit {code}).",
            file=sys.stderr,
        )
        return 1

    # The result the caller was told about is copied into every mirror too. A
    # mirror that refuses it is reported with the path the result is really at,
    # and does not change the run's exit code.
    for mirror in mirrors:
        try:
            _copy(written, result_path(mirror, contract.id, stamp))
        except OSError as exc:
            print(
                f"error: this run's result could not be copied into {mirror}: "
                f"{exc}. It is at {written}.",
                file=sys.stderr,
            )
    # The pointer is for whoever typed `mcgyvr run`. In a batch the result is
    # read in process (the Board, the re-planner), so nothing is printed.
    if not getattr(args, "in_batch", False):
        print(f"result: {written}")
    return code


def _copy(source: Path, target: Path) -> None:
    """Write `source`'s bytes to `target`, making its parent directories first."""
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(target, source.read_bytes())


class FloorStoppedError(Exception):
    """A deterministic step could not run or did not perform; carries the reason.

    Raised inside the observed work so it ends the attempt as a recorded error
    result rather than as an unhandled exception.
    """


def _floor(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    report: RunResult,
    config: Config | None,
    *,
    recording: Recording,
) -> int:
    """Run a deterministic contract: the bound program, then the gate.

    No model is dispatched and no rung is climbed. A task type with no program
    bound is an error naming the dearer family this command does not take, and a
    program that cannot run on this host stops the run with the reason it could
    not. Each step's own output is printed and kept, and a non-zero exit is not
    itself a refusal: the gate judges what the program left behind. The work runs
    inside `observe`, so the attempt has a journal row even when a step stops it.
    """
    from mcgyvr.deterministic import tool_steps
    from mcgyvr.drive import (
        DriveError,
        acceptance_for,
        gate_workspace,
        run_tool_step,
        task_ceiling,
    )
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.telemetry import correct, observe

    if args.record is not None:
        # A deterministic run dispatches nothing, so a `--record` copy holds one
        # row naming the program that did the work and a copy of the result. Say
        # that once, rather than let the copy read as a run whose prompt is
        # missing.
        print(
            f"note: {contract.id} is a {contract.kind.name!r} contract and runs "
            f"on the deterministic floor; it dispatches nothing, so the copy in "
            f"{args.record} is a row naming the program that did the work and a "
            f"copy of this run's result, with no prompt or reply beside them"
        )
    steps = tool_steps(contract)
    if not steps:
        return _error(
            report,
            f"no program is bound to {contract.kind.name!r} for "
            f"{contract.target}. The work is still doable on a dearer "
            f"family, which this command does not climb to.",
        )

    try:
        sandbox = open_sandbox(repo, mode=args.sandbox, **_sandbox_policy(config))
    except SandboxError as exc:
        return _error(report, str(exc))

    # The floor has one rung, named after the program the task type binds, or the
    # type itself when no program is named, and it is tried once, so its attempt
    # id is fixed before any work is done.
    rung = steps[0].tool.program or contract.kind.name
    attempt_id = recording.attempt_id(contract.id, rung, 1)

    # What the steps printed, kept so the attempt's correction row carries it.
    performed: list[str] = []

    def work() -> GateResult:
        for note in sandbox.notes:
            print(f"note: {note}")
        # What the sandbox collected while being set up, then the ceiling that
        # bounds each step: `task_timeout_s` from the config, or no ceiling.
        ceiling = task_ceiling(config)
        for step in steps:
            outcome = run_tool_step(step, sandbox, timeout=ceiling)
            print(f"  {_ran(step)}")
            if not outcome.ran:
                raise FloorStoppedError(str(outcome.environment_issue))
            assert outcome.result is not None  # `ran` is exactly this test
            if not outcome.performed:
                raise FloorStoppedError(
                    (outcome.result.stderr or outcome.result.stdout).strip()
                )
            if not step.argv and outcome.result.stdout.strip():
                # An in-process step has no command line, so whatever it writes
                # to stdout is its report and there is nowhere else for that to
                # go. Print it, keep it for the attempt's journal detail, and put
                # it on the result's notes: a check that says what it changed
                # should not be reduced to its exit code.
                said = outcome.result.stdout.strip()
                print(textwrap.indent(said, "    "))
                performed.append(f"{_ran(step)}\n{said}")
                report.notes.append(f"{_ran(step)}: {said}")
            if not outcome.ok:
                # The step applied its fixes and still exited non-zero, which is
                # what a fixing linter does: what it does not fix is left behind
                # for the gate to judge. Show what it left and carry on; the exit
                # code is not a refusal by itself, and stopping here would lose a
                # change the gate may still accept.
                left = (outcome.result.stdout or outcome.result.stderr).strip()
                print(
                    f"  note: {step.tool.program} applied its fixes and left "
                    f"what it does not fix (exit {outcome.result.exit_code}); "
                    f"the gate judges what remains:"
                )
                print(textwrap.indent(left, "    "))
        return gate_workspace(contract, sandbox, config=config)

    try:
        with sandbox:
            # The contract's own acceptance and demonstration commands are run
            # once against the untouched workspace before any work: one that
            # cannot run, or a demonstration that already fails, is an environment
            # problem, and it is reported before a program is run instead of being
            # charged to the change. The notes from that pass are kept.
            acceptance = acceptance_for(contract, sandbox, config=config)
            if acceptance is not None:
                baseline = acceptance.baseline()
                for note in baseline.notes:
                    print(f"note: {note}")
                report.notes.extend(baseline.notes)
                if baseline.issue is not None:
                    return _error(report, str(baseline.issue))
            result = observe(
                work,
                path=recording.path,
                attempt_id=attempt_id,
                orchestrator=recording.orchestrator,
                rung=rung,
                task_type=contract.task_type,
                operation=contract.operation,
                session_file=recording.session_file,
                tier=DETERMINISTIC,
                mirrors=recording.mirrors,
                on_copy_error=recording.copy_failed,
            )
            return _report_run(
                args,
                contract,
                sandbox,
                repo,
                result,
                report,
                recording=recording,
                attempt_id=attempt_id,
                performed="\n".join(performed),
            )
    except (FloorStoppedError, DriveError, SandboxError) as exc:
        # A step that stopped, or a drive or sandbox failure, leaves an attempt
        # row with no verdict. Record the raise against the attempt id already
        # written, so the journal says why no verdict arrived, and then turn it
        # into an error result: the reason reaches stderr and the result file, and
        # the run exits 1.
        correct(
            path=recording.path,
            attempt_id=attempt_id,
            outcome=RAISED,
            detail=str(exc),
            orchestrator=recording.orchestrator,
            mirrors=recording.mirrors,
            on_copy_error=recording.copy_failed,
        )
        return _error(report, str(exc))


def _sandbox_mode(typed: str | None, config: Config | None) -> str:
    """The sandbox mode to open: what the caller typed, else `sandbox.mode`,
    else `docker`."""
    if typed:
        return typed
    return str((config.get("sandbox.mode") if config is not None else None) or "docker")


def _ran(step: ToolStep) -> str:
    """How a step is shown in the transcript.

    Its command line when it has one, else the in-process operation it performs
    and, where the step renames a symbol, the old and new names.
    """
    if step.argv:
        return f"$ {' '.join(step.argv)}"
    said = f"(in-process) {step.tool.operation}"
    if step.rename.stated:
        said += f" {step.rename.old} -> {step.rename.new}"
    return said


def _error(report: RunResult, detail: str, *, outcome: str = "error") -> int:
    """Report `detail` on stderr, stamp it on the result, and return exit 1."""
    print(f"error: {detail}", file=sys.stderr)
    report.outcome = outcome
    report.detail = detail
    return 1


def _climb(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    config: Config,
    *,
    recording: Recording | None = None,
    report: RunResult,
) -> int:
    """Climb the ladder for a contract the deterministic floor cannot run.

    The setup is admitted when it is live, and the pool, capacity, cooldown and
    route are built from its config.
    A route with nothing runnable, or a verifier that is enabled and cannot run,
    is an error before any dispatch. The contract's own commands are baselined
    against the untouched workspace, then `worker_attempt` drives `escalate` up
    the ladder inside one sandbox until a rung is accepted or a ceiling stops it,
    and `_report_climb` reports what happened and delivers an accepted change.
    """
    from mcgyvr.availability import AvailabilityVerdict
    from mcgyvr.capacity import Capacity, CapacityError
    from mcgyvr.cooldown import Cooldown
    from mcgyvr.drive import DriveError, acceptance_for, worker_attempt
    from mcgyvr.escalate import Outcome, ascent, escalate, redundant_relief
    from mcgyvr.local_pool import SourceUnavailableError, source_map
    from mcgyvr.replan import max_replans
    from mcgyvr.route import RouteError
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.triage import stated
    from mcgyvr.verify import reviewers_for
    from mcgyvr.wake_judge import WakeJudgeError
    from mcgyvr.wake_judge import hook_for as wake_hook_for

    # A live setup drives real rigs: containers are built, units are woken and
    # models are served. The fleet has to read as locked before any of that, and
    # when it does not, nothing is cleaned or restored and the run is refused with
    # Exit.REFUSED rather than touch machines someone else is using.
    if _live(config):
        refused = _admitted_live(config)
        if refused is not None:
            report.outcome = "error"
            report.detail = refused
            return Exit.REFUSED

    # The pool: every ladder unit and relief rung that can actually run, with its
    # model, its endpoint and the role bindings, plus the rungs skipped and why.
    # It is built once and handed to everything below, the route, the capacity,
    # the reviewers, the driver and the climb itself, so they all agree on which
    # sources exist.
    pool = source_map(config)

    # Relief rungs that duplicate a unit this install already serves are said
    # once, before any dispatch: riding them re-sends to what the user has, so
    # the note spares a journal read to discover it after the fact.
    for note in redundant_relief(config):
        print(f"note: {note}", file=sys.stderr)
        report.notes.append(note)

    # How many dispatches each source can take, from the width each unit
    # declares, with the count of servers already busy on each source to judge
    # how full it is. Where mcgyvr may sleep and wake units, a gauge counts the
    # dispatches waiting on each one host-wide, which is what a swap asks before
    # it puts a unit down to make room for a sleeper. This is what holds the
    # climb to what the fleet can serve, and a declaration that admits nothing
    # is a CapacityError, refused before a single dispatch.
    from mcgyvr.pressure import Gauge, server_counts

    try:
        capacity = Capacity.of(
            config,
            gauge=Gauge() if config.get("serving.enable_sleep_wake") else None,
            busy=server_counts(pool),
        )
    except CapacityError as exc:
        return _error(report, str(exc))

    # Liveness is not probed over the network from here: every endpoint this
    # probe is handed is reported live. The sources actually dropped are the ones
    # that failed during this run and are cooling down, so no dispatch pays a
    # probe round trip to learn what the dispatch itself will show.
    def _always_live(endpoint: object, timeout_s: float) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source,  # type: ignore[attr-defined]
            live=True,
            reason="",
            how="stub probe, no network",
            elapsed_s=0.0,
        )

    cooldown = Cooldown(probe=_always_live)
    try:
        route = ascent(config, pool, contract, capacity=capacity)
        if contract.start_rung:
            # A start decided ahead of time is checked against this ladder
            # before the sandbox opens: one it does not offer is refused here,
            # not found out after the baseline ran.
            stated(config, pool, contract, route.rungs)
    except RouteError as exc:
        return _error(report, str(exc))
    if not route:
        return _error(
            report,
            f"{contract.id} is a {contract.task_type!r} contract and "
            f"starts on the {route.floor.name!r} family; nothing in {config.path} "
            f"can run it. {route.reason}",
            outcome=Outcome.NOTHING_TO_RUN.value,
        )

    # A contract whose kind judges a change is reviewed by a fresh context: the
    # reviewer comes from the config's `verifier` settings, through the same pool
    # and capacity as the work. A verifier that is enabled and cannot run is
    # refused here with the keys that would fix it, because accepting the change
    # without it would report an assurance the run does not have. Kinds that do
    # not judge a change get no reviewers at all.
    try:
        reviewers = (
            reviewers_for(config, pool, capacity=capacity)
            if contract.kind.judges_a_change
            else None
        )
    except SourceUnavailableError as exc:
        return _error(
            report,
            f"verification is enabled and the verifier role cannot run: "
            f"{exc}. Bind `verifier.unit` to a usable unit, or set "
            f"`verifier.enabled: false` to accept on the deterministic gate.",
        )

    try:
        # The sandbox, with the config's image, setup commands and network
        # policy.
        sandbox = open_sandbox(
            repo,
            mode=args.sandbox,
            image=config.get("sandbox.image"),
            setup=config.get("sandbox.setup") or (),
            # Every unit's address, so a container that can reach out is told
            # where the models this host serves are listening.
            endpoints=tuple(unit.address for unit in config.units.values()),
            **_sandbox_policy(config),
        )
    except SandboxError as exc:
        return _error(report, str(exc))

    try:
        with sandbox:
            for note in sandbox.notes:
                print(f"note: {note}")
            # The sandbox's own setup notes, then the contract's commands run once
            # against the untouched workspace: one that cannot run, or a
            # demonstration that already fails, is an environment problem and is
            # reported here, before an attempt is dispatched and charged with it.
            # The notes from that pass are kept on the result.
            acceptance = acceptance_for(contract, sandbox, config=config)
            if acceptance is not None:
                baseline = acceptance.baseline()
                for note in baseline.notes:
                    print(f"note: {note}")
                report.notes.extend(baseline.notes)
                issue = baseline.issue
                if issue is not None:
                    # The baseline says the commands that judge this contract do
                    # not run here as the workspace stands. Stop: no attempt could
                    # be judged, so dispatching one would spend a model on a change
                    # nothing could check.
                    return _error(report, str(issue))
            driver = worker_attempt(
                config,
                pool,
                contract,
                sandbox,
                recording=recording,
                cooldown=cooldown,
                reviewers=reviewers,
                seed=args.notes_seed,
            )
            if _live(config):
                driver = _warning_pulled_steps(driver)

            outcome = escalate(
                config,
                pool,
                contract,
                driver,
                capacity=capacity,
                # The wake hook, when sleep and wake are enabled and the ladder has
                # a fast rung to judge with: a rung that does not answer may only be
                # asleep, and `escalate` calls this before giving up on it. It cools
                # sources through the same hold this run uses.
                wake_hook=wake_hook_for(config, pool, cooldown=cooldown),
            )
            return _report_climb(
                args,
                contract,
                sandbox,
                repo,
                outcome,
                recording,
                report,
                # A batch re-plans the contract itself and says so on the
                # result, so the hint is for a run on its own.
                replans=0 if getattr(args, "in_batch", False) else max_replans(config),
            )
    except (DriveError, SandboxError, CapacityError, WakeJudgeError) as exc:
        return _error(report, str(exc))


def _warning_pulled_steps(
    attempt: Callable[[Try], Judgement],
) -> Callable[[Try], Judgement]:
    """Warn once about each pulled rung, then dispatch it anyway.

    A pull is announced in `mcgyvr fleet alerts` and does not stop the run: the
    wrapped attempt prints the pulled fields for a rung the first time it is
    tried, and calls through. Pulls that cannot be read are one warning, after
    which every step is dispatched as if nothing were pulled.
    """
    from mcgyvr.fleet.alerts import live_pulled_units

    try:
        units = live_pulled_units()
    except Exception as exc:
        print(
            f"warning: pulls could not be read ({exc}); every step is dispatched "
            f"without them — see `mcgyvr fleet alerts`",
            file=sys.stderr,
        )
        units = {}
    warned: set[str] = set()

    def warning(this: Try) -> Judgement:
        name = this.rung.name
        entries = units.get(name)
        if entries and name not in warned:
            warned.add(name)
            fields = ", ".join(
                (
                    f"{entry['field']} x{entry['count']}"
                    if entry["unit"] == name
                    else f"{entry['unit']} {entry['field']} x{entry['count']}"
                )
                for entry in entries
            )
            print(
                f"warning: step {name} is pulled: {fields}; dispatched anyway — "
                f"see `mcgyvr fleet alerts`",
                file=sys.stderr,
            )
        return attempt(this)

    return warning


def _report_climb(
    args: argparse.Namespace,
    contract: Contract,
    sandbox: Sandbox,
    repo: Path,
    outcome: Delivered | Halted,
    recording: Recording | None,
    report: RunResult,
    *,
    replans: int = 0,
) -> int:
    """Print the climb, record it, and deliver whatever it accepted.

    Each attempt in the history is printed and given a correction row per draw,
    then copied into the result's attempts. A halt sets the result's outcome and
    detail and exits 1; a spent ladder notes, when `replans` (`max_replans`) is
    above zero, that a batch re-plans such a contract and this run does not. A
    delivery says which rung it landed on, what it cost in attempts and
    escalations, and what the assurance is, then commits a change; a judgement
    that bound no content is an error, because there would be nothing to
    deliver.
    """
    from mcgyvr.escalate import Assurance, Delivered, Outcome
    from mcgyvr.replan import hint as replan_hint
    from mcgyvr.result import AttemptResult
    from mcgyvr.route import Verdict
    from mcgyvr.telemetry import correct

    triaged = outcome.triage
    if triaged is not None:
        # Where the climb started and who decided it, kept for a later reading
        # of the run: jev's pick with every rung's probability, why it fell
        # back, or the start the contract stated.
        report.triage = triaged.as_json()
        if triaged.rung is None:
            said = triaged.fallback
        elif triaged.source == "contract":
            said = f"the contract starts the climb on {triaged.rung}"
        else:
            said = (
                f"jev started the climb on {triaged.rung} "
                f"(confidence {triaged.confidence or 0.0:.2f})"
            )
        print(f"  triage: {said}")
    for step in outcome.history:
        word = RAISED if step.raised else step.verdict.value
        print(f"  {step.rung} #{step.attempt}: {word} — {step.detail}")
        for finding in step.findings:
            print(f"    ✗ {finding}")
        attempt_id: str | None = None
        # An attempt can have several rows, one per draw of the same dispatch, and
        # the journal names them `<attempt>#<draw>`. `step.draw` is the draw whose
        # content was judged, and the only one the verdict belongs to. A declined
        # attempt was refused before any draw, so nothing is corrected for it.
        subject = step.draw
        if recording is not None and step.verdict is not Verdict.DECLINED:
            if subject is not None:
                attempt_id = recording.attempt_id(
                    contract.id, step.rung, step.attempt, subject
                )
            for each in range(step.rows):
                correct(
                    path=recording.path,
                    attempt_id=recording.attempt_id(
                        contract.id, step.rung, step.attempt, each
                    ),
                    outcome=(
                        word if step.raised or each == subject else Verdict.FAILED.value
                    ),
                    detail=_correction_detail(step, each, subject),
                    orchestrator=recording.orchestrator,
                    mirrors=recording.mirrors,
                    on_copy_error=recording.copy_failed,
                )
        report.attempts.append(
            AttemptResult(
                rung=step.rung,
                attempt=step.attempt,
                verdict=word,
                detail=step.detail,
                findings=list(step.findings),
                notes=step.notes.as_json() if step.notes is not None else None,
                attempt_id=attempt_id,
                draw=step.draw,
                draws=step.draws,
                rows=step.rows,
                relief=step.relief,
                model=step.model,
                address=step.address,
            )
        )

    if not isinstance(outcome, Delivered):
        report.outcome = outcome.outcome.value
        report.detail = outcome.detail
        print(f"\n{contract.id}: {outcome.outcome.value}", file=sys.stderr)
        print(f"error: {outcome.detail}", file=sys.stderr)
        if outcome.outcome is Outcome.LADDER_SPENT and replans > 0:
            said = replan_hint(replans)
            print(f"note: {said}", file=sys.stderr)
            report.notes.append(said)
        return 1

    spent = (
        f"on {outcome.rung} ({outcome.assurance.value}) "
        f"after {outcome.attempts_spent} attempt(s) and "
        f"{outcome.escalations} escalation(s)"
    )
    # The headline has two readings: accepted outright, or accepted with nothing
    # written, which is how delivery reports a refusal of a change the gate passed.
    verdict = _Headline(
        headline=f"{contract.id}: accepted {spent}",
        passed=f"{contract.id}: checks passed {spent}",
    )
    report.outcome = "accepted"
    report.rung = outcome.rung
    report.assurance = outcome.assurance.value
    # The judgement's own words become the result's detail, so a reader sees why
    # the accepted rung was accepted, the reviewer's note or the checks that
    # passed, and not only the verdict.
    report.detail = outcome.judgement.detail
    if outcome.assurance is Assurance.UNVERIFIED:
        # No independent review approved this: say so on stderr, because an
        # acceptance with no reviewer behind it is the one a caller can miss.
        print(
            f"UNVERIFIED: {contract.id} is accepted with no independent review "
            f"approving it — {outcome.judgement.detail}",
            file=sys.stderr,
        )
    elif outcome.assurance is Assurance.UNCHECKED:
        print(f"note: {outcome.judgement.detail}", file=sys.stderr)
    bound = outcome.judgement.accepted
    if bound is None:
        # Accepted with nothing bound: the judgement approved no content, so there
        # is nothing a delivery could carry. Say the checks passed and
        # then report the error here, because a success line for a run with no
        # product would name an outcome the caller cannot use.
        verdict.say()
        return _error(
            report,
            f"{contract.id} was accepted on {outcome.rung} without bound "
            f"content, so there is nothing a delivery could re-judge.",
        )
    landed = outcome.history[-1]
    return _commit(
        args,
        contract,
        repo,
        sandbox.source_base_commit(),
        bound,
        report,
        verdict=verdict,
        recording=recording,
        attempt_id=(
            recording.attempt_id(
                contract.id,
                landed.rung,
                landed.attempt,
                # The draw the accepted content came from. `attempt_id` numbers
                # draw 0 as the attempt's own row, and `or 0` maps a missing draw
                # onto that same row.
                landed.draw or 0,
            )
            if recording is not None
            else None
        ),
    )


def _correction_detail(step: Attempted, each: int, subject: int | None) -> str:
    """The detail for one draw row of an attempt that may have made several draws.

    The draw that was judged gets the attempt's own detail, or its findings when
    there are any; the other draws are marked as losing draws, or, when the
    attempt raised part way through, as draws no verdict was reached for, naming
    the draw the raise is attributed to.
    """
    if step.raised:
        if each == subject:
            return step.detail
        where = (
            f"on draw {subject}"
            if subject is not None
            else f"after draw {step.rows - 1} answered"
        )
        return f"the attempt raised {where}; no verdict was reached for this draw"
    if each == subject:
        return "\n".join(step.findings) or step.detail
    return f"a losing draw; the attempt's verdict is on draw {subject}"


def _report_run(
    args: argparse.Namespace,
    contract: Contract,
    sandbox: Sandbox,
    repo: Path,
    result: GateResult,
    report: RunResult,
    *,
    recording: Recording | None = None,
    attempt_id: str | None = None,
    performed: str = "",
) -> int:
    """Report the gate's verdict on a deterministic run's work.

    The headline is the gate's own word, accepted or rejected, with its findings
    and environment issues under it, and the attempt's journal row is corrected
    with the same words. A rejected result stops here with exit 1. An accepted one
    is bound to the files the workspace actually changed: no change at all is
    reported as `nothing_to_change` and succeeds without delivering, and a real
    change is delivered, committed or left in the working tree.
    """
    from mcgyvr.deliver import Accepted, DeliveryError
    from mcgyvr.escalate import Assurance
    from mcgyvr.gate.changeset import ChangeSet
    from mcgyvr.route import Verdict
    from mcgyvr.telemetry import correct

    verdict = _Headline(
        headline=f"{contract.id}: gate {'accepted' if result.accepted else 'rejected'}",
        passed=f"{contract.id}: checks passed",
        below=(
            *(f"  ✗ {finding}" for finding in result.findings),
            *(f"  ? {issue}" for issue in result.environment_issues),
        ),
    )
    report.findings = [str(finding) for finding in result.findings]
    if recording is not None and attempt_id is not None:
        # The floor's attempt is corrected with what the gate found, plus what the
        # in-process step printed, so the journal's row says what the run learned
        # rather than only that it passed or failed.
        said = [str(finding) for finding in result.findings]
        if performed:
            said.append(performed)
        correct(
            path=recording.path,
            attempt_id=attempt_id,
            outcome=(Verdict.PASSED if result.accepted else Verdict.FAILED).value,
            detail="\n".join(said),
            orchestrator=recording.orchestrator,
            mirrors=recording.mirrors,
            on_copy_error=recording.copy_failed,
        )
    if not result.accepted:
        verdict.say()
        report.outcome = "rejected"
        return 1

    changed = ChangeSet.detect(sandbox.workspace)
    try:
        bound = Accepted.read(
            repo=sandbox.workspace,
            contract=contract,
            result=result,
            paths=[change.path for change in changed] or None,
        )
    except DeliveryError as exc:
        verdict.say()
        return _error(report, str(exc))
    if not changed:
        # The gate accepted and nothing changed: the workspace was already what
        # the contract asks for, so there was nothing to do and nothing to
        # deliver. An empty commit would claim work that did not happen, so this is
        # reported as `nothing_to_change` and succeeds. The detail, the result and
        # the journal row all say it, because a run that changed nothing would
        # otherwise look like a bug.
        detail = (
            f"{contract.target} already is what {contract.kind.name!r} asks for; "
            f"nothing was written"
        )
        verdict.say()
        print(f"\n{contract.id}: {NOTHING_TO_CHANGE} — {detail}")
        report.outcome = NOTHING_TO_CHANGE
        report.detail = detail
        if recording is not None and attempt_id is not None:
            correct(
                path=recording.path,
                attempt_id=attempt_id,
                outcome=NOTHING_TO_CHANGE,
                detail=detail,
                orchestrator=recording.orchestrator,
                mirrors=recording.mirrors,
                on_copy_error=recording.copy_failed,
            )
        return 0
    # The gate accepted and files did change: this is a deterministic acceptance,
    # and the change is handed to delivery.
    report.outcome = "accepted"
    report.assurance = Assurance.DETERMINISTIC.value
    return _commit(
        args,
        contract,
        repo,
        sandbox.source_base_commit(),
        bound,
        report,
        verdict=verdict,
        recording=recording,
        attempt_id=attempt_id,
    )


def _settle_delivery(args: argparse.Namespace, config: Config | None) -> None:
    """Settle what delivery does from the flags and the config.

    A named branch implies a commit; a typed `--commit`/`--no-commit` beats
    `delivery.commit` while an untyped one takes the policy; an unnamed branch
    falls back to `delivery.branch`.
    """
    typed = (getattr(args, "branch", None) or "").strip()
    policy_commit = bool(config.get("delivery.commit")) if config is not None else False
    policy_branch = (
        config.get("delivery.branch") if config is not None else None
    ) or ""
    commit = getattr(args, "commit", None)
    args.commit = True if typed else (policy_commit if commit is None else commit)
    args.branch = typed or policy_branch


def _delivery_problem(args: argparse.Namespace) -> str | None:
    """Why `--branch` cannot be honoured as given, or None when it can."""
    branch = getattr(args, "branch", None)
    if branch is None:
        return None
    if not branch.strip():
        return (
            "--branch was given an empty name. Name the branch to commit onto, "
            "or leave the flag off to commit onto the one you have checked out."
        )
    if getattr(args, "commit", None) is False:
        return (
            f"--branch {branch} asks for a commit onto {branch}, and --no-commit "
            f"asks for none. Pass one of them."
        )
    return None


COMMITTED = "committed"


NOT_COMMITTED = "not_committed"


DELIVERY_REFUSED = "delivery_refused"


NOTHING_TO_CHANGE = "nothing_to_change"


RAISED = "error"


DETERMINISTIC = "deterministic"


@dataclass(frozen=True)
class _Headline:
    """The line that reports how a run ended, and what is printed under it.

    `say` prints the headline, or the reworded one saying the checks passed but
    nothing was written, so delivery never prints an acceptance for a change it
    refused. `below` is the findings and environment issues the gate named.
    """

    headline: str
    passed: str
    below: tuple[str, ...] = ()

    def say(self, *, refused: str | None = None) -> None:
        line = (
            self.headline
            if refused is None
            else (f"{self.passed}, but not written: {refused}")
        )
        print(f"\n{line}")
        for each in self.below:
            print(each)


def _commit(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    base: str,
    bound: Accepted,
    report: RunResult,
    *,
    verdict: _Headline,
    recording: Recording | None = None,
    attempt_id: str | None = None,
) -> int:
    """Deliver an accepted change, committed or left in the working tree.

    Without `--commit`, `place` writes the change and leaves the repository
    otherwise untouched; with it, `deliver` commits onto the checked-out branch or
    onto the branch named. Either can refuse, on an uncommitted copy of a file the
    change touches or on a gate that rejects it a second time, and a refusal is
    reported as such: the checks passed, but nothing was written. Every outcome is
    written into the journal as a correction on the accepted attempt.
    """
    from mcgyvr.deliver import DeliveryError, DeliveryRefusedError, deliver, place
    from mcgyvr.telemetry import correct

    def landed(outcome: str, detail: str) -> None:
        if recording is not None and attempt_id is not None:
            correct(
                path=recording.path,
                attempt_id=attempt_id,
                outcome=outcome,
                detail=detail,
                orchestrator=recording.orchestrator,
                mirrors=recording.mirrors,
                on_copy_error=recording.copy_failed,
            )

    def refused(reason: str) -> None:
        # The change passed and was not written: the headline is the reworded one,
        # the gate's non-refusing observations are said again, and the reason
        # becomes the delivery line and the correction row.
        verdict.say(refused=reason)
        _say_reported(bound)
        landed(DELIVERY_REFUSED, reason)
        report.delivery = reason

    adapters = getattr(args, "gate_adapters", None)
    if adapters is None:
        verdict.say()
        return _error(
            report,
            "delivery was reached with no `gate_adapters` settled for this run, "
            "so it cannot judge the change by the setup's `gate` settings; "
            "nothing was written",
        )

    if not args.commit:
        try:
            place(
                repo=repo,
                contract=contract,
                content=bound,
                base=base,
                adapters=adapters,
            )
        except DeliveryError as exc:
            refused(str(exc))
            if isinstance(exc, DeliveryRefusedError):
                # The gate refused the change on the second look, so its findings
                # are carried onto the result; a plain DeliveryError has none.
                report.findings = [str(finding) for finding in exc.findings]
            return _error(report, str(exc), outcome=DELIVERY_REFUSED)
        verdict.say()
        _say_reported(bound)
        left = ", ".join(path for path, _ in bound.files(contract))
        print(f"\nLeft in {left}, not committed (pass --commit to commit).")
        for path, _ in bound.files(contract):
            _say_not_rerun(adapters, path)
        # Left in the working tree: the paths are named, the result records where,
        # and the run succeeds, because the change is there to be read and
        # committed.
        report.delivery = f"not committed; change left in {left}"
        landed(NOT_COMMITTED, report.delivery)
        return 0

    try:
        delivery = deliver(
            repo=repo,
            contract=contract,
            content=bound,
            base=base,
            branch=getattr(args, "branch", None) or "",
            adapters=adapters,
        )
    except DeliveryError as exc:
        refused(str(exc))
        return _error(report, str(exc), outcome=DELIVERY_REFUSED)

    if not delivery.committed:
        refused(delivery.reason)
        report.outcome = DELIVERY_REFUSED
        report.detail = delivery.reason
        report.findings = [str(finding) for finding in delivery.findings]
        return 1
    verdict.say()
    _say_reported(bound)
    print(f"\n{delivery}")
    for path in delivery.paths:
        _say_not_rerun(adapters, path)
    report.committed = delivery.committed
    report.commit = delivery.commit
    report.branch = delivery.branch
    report.handoff = delivery.handoff
    report.delivery = str(delivery)
    landed(COMMITTED, f"{delivery.commit[:12]} on {delivery.branch or 'HEAD'}")
    return 0


def _say_not_rerun(adapters: Sequence[LanguageAdapter], path: str) -> None:
    """Say that no adapter here will re-run its tool on `path`.

    A path an adapter's tool loads as code is checked only inside the task's
    sandbox, and this prints the note that says so beside the change.
    """
    from mcgyvr.deliver import not_rerun_here

    note = not_rerun_here(adapters, path)
    if note:
        print(f"  {note}")


def _say_reported(bound: Accepted) -> None:
    """Print the gate's non-refusing observations, one line each.

    These are findings the gate reported instead of refusing, which is what
    `gate.param_mutation: report` produces, so the caller is told the same thing
    the delivery decision was made on.
    """
    from mcgyvr.gate.typecheck import PARAM_MUTATION, ParamMutation

    for finding in bound.observations:
        if finding.code != PARAM_MUTATION:
            continue
        where = (
            finding.path if finding.line is None else f"{finding.path}:{finding.line}"
        )
        print(
            f"  reported: {where} [{finding.code}] {finding.message} "
            f"(not refused: gate.param_mutation is {ParamMutation.REPORT.value})"
        )


def _unusable_writer(args: argparse.Namespace) -> str | None:
    """Why `args.session_id` cannot name a writer, or None once it is resolved.

    On success the resolved `Session` is put in `args.session`.
    """
    from mcgyvr.session import SessionError, resolve

    named = args.session_id
    if named is not None and not named.strip():
        return (
            "--session was given an empty id: a row that cannot say which "
            "session produced it is the hole the field exists to close. "
            "Pass an ID, or leave the flag off to be named by the session "
            "that typed this command."
        )
    if named is not None and "/" in named:
        return (
            f"--session {named!r} cannot contain '/': the id is the journal's "
            f"file name, DIR/<ID>.jsonl"
        )
    try:
        args.session = resolve(named)
    except SessionError as exc:
        return str(exc)
    return None
