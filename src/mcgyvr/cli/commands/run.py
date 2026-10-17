""

from __future__ import annotations

import argparse
import json
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

if TYPE_CHECKING:  #
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

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, SETUP_DOC, _add_repo, _named_path
from mcgyvr.cli.fleet_live import _admitted_live, _live
from mcgyvr.cli.sandbox import (
    _reads_the_tree,
    _sandbox_policy,
    _say_what_the_sandbox_leaves_out,
)


def _run(args: argparse.Namespace) -> int:
    ""
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.contract import ContractError
    from mcgyvr.contract import load as load_task_contract
    from mcgyvr.drive import Recording, gate_adapters
    from mcgyvr.result import (
        RunResult,
        result_path,
        run_stamp,
        session_path,
        session_record,
        write,
        write_session,
    )
    from mcgyvr.session import with_mcorch_transcript
    from mcgyvr.telemetry import run_tags

    session: Session = args.session

    try:
        contract = load_task_contract(Path(args.contract))
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 1
    #
    #
    #
    notes = _say_what_the_sandbox_leaves_out(repo) if _reads_the_tree(contract) else []

    #
    #
    #
    #e.
    config: Config | None = None
    config_error: ConfigError | None = None
    #
    #
    #
    #
    #ides
    #
    #
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
        #
        #
        #
        #
        #
        #
        print(f"error: {config_error} {SETUP_DOC} says how.", file=sys.stderr)
        return 1

    #
    # a
    #of
    #
    configured = config.get("journal.dir") if config is not None else None
    journal_dir = Path(configured or JOURNAL_DIR_DEFAULT).expanduser()
    #
    #
    session = with_mcorch_transcript(session, journal_dir)
    #b,
    #ds
    #
    #
    #
    #
    #
    #
    #id
    #ow
    #
    #
    #
    asked = Path(args.record).expanduser() if args.record is not None else None
    mirrors = (
        (asked,)
        if asked is not None and asked.resolve() != journal_dir.resolve()
        else ()
    )

    #
    #
    #
    #
    #
    stamp = run_stamp()
    #
    #
    #
    keep = result_path(journal_dir, contract.id, stamp)
    where = Path(args.result) if args.result else keep

    bare_install = isinstance(config_error, ConfigMissingError) and named is None
    if config_error is not None and not bare_install:
        #
        #be
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #mb
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #ts
        #
        reason = " ".join(str(config_error).split())
        print(
            f"note: {path or 'the config'} is not usable ({reason}); this run "
            "goes on without "
            f"a config and sends its result to {where}"
        )

    report = RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        #
        target="" if contract.is_session else contract.target,
        orchestrator=session.orchestrator,
        run=stamp,
        session_file=str(session.session_file) if session.session_file else None,
        journal=str(journal_dir),
        notes=notes,
    )

    #
    try:
        recording = Recording(
            path=journal_dir / f"{session.orchestrator}.jsonl",
            orchestrator=session.orchestrator,
            run=stamp,
            session_file=session.session_file,
            mirrors=mirrors,
        )
        #
        #
        run_tags()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    #
    #
    #
    #
    #
    #
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

    #
    #
    args.sandbox = _sandbox_mode(args.sandbox, contract, config)
    #
    #
    #
    #
    args.gate_adapters = gate_adapters(config)
    #
    #
    _settle_delivery(args, config)

    if contract.is_deterministic:
        code = _floor(args, contract, repo, report, config, recording=recording)
    else:
        assert config is not None  #
        code = _climb(args, contract, repo, config, recording=recording, report=report)

    report.exit_code = code
    #
    #
    #
    #he
    #t.
    for mirror, why in recording.copy_errors.items():
        report.copy_errors[str(mirror)] = why
        print(
            f"error: the copy of this run's journal asked for in {mirror} could "
            f"not be written ({why}). mcgyvr's own record under {journal_dir} is "
            f"complete and the run was not stopped for it.",
            file=sys.stderr,
        )

    #
    #
    #
    #
    #
    if contract.is_session:
        logged = session_path(journal_dir, contract.id, stamp)
        try:
            write_session(
                logged,
                session_record(
                    report,
                    contract_path=Path(args.contract).absolute(),
                    question=contract.task,
                    result=keep,
                    journal=recording.path,
                ),
            )
        except OSError as exc:
            print(
                f"error: this session could not be logged at {logged}: {exc}. "
                f"Its answer is in the result file.",
                file=sys.stderr,
            )
        else:
            report.session_record = str(logged)
            print(f"session: {logged}", file=sys.stderr)
            for mirror in mirrors:
                try:
                    _copy(logged, session_path(mirror, contract.id, stamp))
                except OSError as exc:
                    print(
                        f"error: this session could not be copied into {mirror}: "
                        f"{exc}. It is at {logged}.",
                        file=sys.stderr,
                    )

    #
    #
    #
    #ne
    #
    #
    failed = where
    try:
        written = write(where, report)
        if keep != where:
            failed = keep
            _copy(written, keep)
    except OSError as exc:
        #ge
        #:`
        #
        #
        #nt
        #
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

    #
    #
    #
    for mirror in mirrors:
        try:
            _copy(written, result_path(mirror, contract.id, stamp))
        except OSError as exc:
            print(
                f"error: this run's result could not be copied into {mirror}: "
                f"{exc}. It is at {written}.",
                file=sys.stderr,
            )
    print(f"result: {written}")
    return code


def _copy(source: Path, target: Path) -> None:
    ""
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(target, source.read_bytes())


def _sessions(args: argparse.Namespace) -> int:
    ""
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.result import SESSIONS_DIR, sessions

    if args.journal is not None:
        journal_dir = Path(args.journal).expanduser()
    else:
        chosen = Path(args.config) if args.config else None
        try:
            configured = load_config(chosen).get("journal.dir")
        except ConfigError as exc:
            #
            #
            bare = isinstance(exc, ConfigMissingError) and (
                chosen is None and named_config_path() is None
            )
            if not bare:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            configured = None
        journal_dir = Path(configured or JOURNAL_DIR_DEFAULT).expanduser()

    found = sessions(journal_dir)
    if args.id is None:
        if not found:
            print(f"no sessions in {journal_dir / SESSIONS_DIR}")
            return 0
        for path in found[: args.limit]:
            record = json.loads(path.read_text(encoding="utf-8"))
            asked = " ".join(str(record.get("question", "")).split())
            print(
                f"{path.stem}  [{record.get('task_type')}] "
                f"{record.get('outcome')}  {_clip(asked, 60)}"
            )
        return 0

    path = journal_dir / SESSIONS_DIR / f"{args.id}.json"
    #
    if Path(args.id).name != args.id or not path.is_file():
        print(
            f"error: no session {args.id!r} in {journal_dir / SESSIONS_DIR}; "
            f"`mcgyvr sessions` lists them.",
            file=sys.stderr,
        )
        return 1
    record = json.loads(path.read_text(encoding="utf-8"))
    contract = record.get("contract") or {}
    print(f"{record.get('session')}  [{record.get('task_type')}]")
    print(f"  outcome:   {record.get('outcome')} ({record.get('assurance')})")
    print(f"  unit:      {record.get('unit')}")
    print(f"  started:   {record.get('started')}")
    print(f"  finished:  {record.get('finished')}")
    print(f"  contract:  {contract.get('path')} (sha256 {contract.get('sha256')})")
    print(f"  result:    {record.get('result')}")
    print(f"  record:    {path}")
    print(f"\nasked:\n{record.get('question')}")
    answer = record.get("answer") or f"(none: {record.get('detail')})"
    print(f"\nanswer:\n{answer}")
    return 0


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


class FloorStoppedError(Exception):
    ""


def _floor(
    args: argparse.Namespace,
    contract: Contract,
    repo: Path,
    report: RunResult,
    config: Config | None,
    *,
    recording: Recording,
) -> int:
    ""
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
        #
        #
        #
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

    #��
    # a
    #
    rung = steps[0].tool.program or contract.kind.name
    attempt_id = recording.attempt_id(contract.id, rung, 1)

    #
    performed: list[str] = []

    def work() -> GateResult:
        for note in sandbox.notes:
            print(f"note: {note}")
        #
        #
        #
        ceiling = task_ceiling(config)
        for step in steps:
            outcome = run_tool_step(step, sandbox, timeout=ceiling)
            print(f"  {_ran(step)}")
            if not outcome.ran:
                raise FloorStoppedError(str(outcome.environment_issue))
            assert outcome.result is not None  #
            if not outcome.performed:
                raise FloorStoppedError(
                    (outcome.result.stderr or outcome.result.stdout).strip()
                )
            if not step.argv and outcome.result.stdout.strip():
                #or
                #
                #
                #
                #
                #
                said = outcome.result.stdout.strip()
                print(textwrap.indent(said, "    "))
                performed.append(f"{_ran(step)}\n{said}")
                report.notes.append(f"{_ran(step)}: {said}")
            if not outcome.ok:
                #
                #or
                #
                #
                #
                #
                #
                #
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
            #
            #
            #
            #
            #k.
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
        #s,
        #
        # a
        #
        #
        #
        #
        #
        #
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


def _runs_no_command(contract: Contract) -> bool:
    ""
    return contract.is_session and not (
        contract.acceptance_commands or contract.demonstration_commands
    )


def _sandbox_mode(typed: str | None, contract: Contract, config: Config | None) -> str:
    ""
    if typed:
        return typed
    key, unset = (
        ("sandbox.sessions", "tempdir")
        if _runs_no_command(contract)
        else ("sandbox.mode", "docker")
    )
    return str((config.get(key) if config is not None else None) or unset)


SESSION_SANDBOX_NOTE = (
    "This session runs no command, so its reply is staged in a throwaway "
    "checkout on this host and no container is built or started "
    "(`sandbox.sessions: tempdir`; `docker` gives sessions a container)."
)


def _ran(step: ToolStep) -> str:
    ""
    if step.argv:
        return f"$ {' '.join(step.argv)}"
    said = f"(in-process) {step.tool.operation}"
    if step.rename.stated:
        said += f" {step.rename.old} -> {step.rename.new}"
    return said


def _error(report: RunResult, detail: str, *, outcome: str = "error") -> int:
    ""
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
    ""
    from mcgyvr.availability import AvailabilityVerdict
    from mcgyvr.capacity import Capacity, CapacityError
    from mcgyvr.cooldown import Cooldown
    from mcgyvr.drive import DriveError, acceptance_for, worker_attempt
    from mcgyvr.escalate import Outcome, ascent, escalate
    from mcgyvr.fleet_manager import hook_for as fleet_hook_for
    from mcgyvr.local_pool import SourceUnavailableError, source_map
    from mcgyvr.route import RouteError
    from mcgyvr.sandbox.base import SandboxError, open_sandbox
    from mcgyvr.sandbox.tempdir import TempDirSandbox
    from mcgyvr.verify import reviewers_for

    #
    #e
    #
    #
    #
    #
    if _live(config):
        refused = _admitted_live(config)
        if refused is not None:
            report.outcome = "error"
            report.detail = refused
            return Exit.REFUSED

    #
    #
    #
    from mcgyvr import ladder_manager
    from mcgyvr.pressure import Board

    managed = ladder_manager.for_task(config, read_board=Board().read)
    config = managed.config
    if managed.note is not None:
        print(f"note: {managed.note}")

    #
    #
    #
    #
    #
    #ne
    #no
    #
    #
    #
    #
    pool = source_map(config)

    #
    #
    #
    #
    #
    #es
    #
    #
    #
    #
    from mcgyvr.pressure import server_counts

    try:
        capacity = Capacity.of(config, gauge=managed.gauge, busy=server_counts(pool))
    except CapacityError as exc:
        return _error(report, str(exc))

    #
    #
    #
    #
    #
    #
    #
    def _always_live(endpoint: object, timeout_s: float) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source,  #
            live=True,
            reason="",
            how="stub probe, no network",
            elapsed_s=0.0,
        )

    cooldown = Cooldown(probe=_always_live, shared=managed.held)
    try:
        route = ascent(config, pool, contract, capacity=capacity)
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

    #
    #
    #ys
    #ed
    #
    #
    #
    #
    #
    #
    #
    #
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
        #
        #
        #
        #s,
        #
        sandbox = (
            TempDirSandbox(repo, notes=(SESSION_SANDBOX_NOTE,))
            if _runs_no_command(contract) and args.sandbox == "tempdir"
            else open_sandbox(
                repo,
                mode=args.sandbox,
                image=config.get("sandbox.image"),
                setup=config.get("sandbox.setup") or (),
                #
                #
                #
                endpoints=tuple(unit.address for unit in config.units.values()),
                **_sandbox_policy(config),
            )
        )
    except SandboxError as exc:
        return _error(report, str(exc))

    try:
        with sandbox:
            for note in sandbox.notes:
                print(f"note: {note}")
            #
            #
            #
            #
            #
            #
            #
            acceptance = acceptance_for(contract, sandbox, config=config)
            if acceptance is not None:
                baseline = acceptance.baseline()
                for note in baseline.notes:
                    print(f"note: {note}")
                report.notes.extend(baseline.notes)
                issue = baseline.issue
                if issue is not None:
                    #
                    # a
                    #
                    #
                    #
                    return _error(report, str(issue))
            driver = worker_attempt(
                config,
                pool,
                contract,
                sandbox,
                recording=recording,
                cooldown=cooldown,
                reviewers=reviewers,
            )
            if _live(config):
                driver = _warning_pulled_steps(driver)

            outcome = escalate(
                config,
                pool,
                contract,
                driver,
                capacity=capacity,
                #
                #
                #
                #ll
                #
                wake_hook=fleet_hook_for(config, pool, cooldown=cooldown),
                presence=managed.presence,
            )
            return _report_climb(
                args, contract, sandbox, repo, outcome, recording, report
            )
    except (DriveError, SandboxError, CapacityError) as exc:
        return _error(report, str(exc))


def _warning_pulled_steps(
    attempt: Callable[[Try], Judgement],
) -> Callable[[Try], Judgement]:
    ""
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
) -> int:
    ""
    from mcgyvr.escalate import Assurance, Delivered
    from mcgyvr.result import AttemptResult
    from mcgyvr.route import Verdict
    from mcgyvr.telemetry import correct

    for step in outcome.history:
        word = RAISED if step.raised else step.verdict.value
        print(f"  {step.rung} #{step.attempt}: {word} — {step.detail}")
        for finding in step.findings:
            print(f"    ✗ {finding}")
        attempt_id: str | None = None
        #
        #
        #he
        #
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
                attempt_id=attempt_id,
                draw=step.draw,
                draws=step.draws,
                rows=step.rows,
            )
        )

    if not isinstance(outcome, Delivered):
        report.outcome = outcome.outcome.value
        report.detail = outcome.detail
        print(f"\n{contract.id}: {outcome.outcome.value}", file=sys.stderr)
        print(f"error: {outcome.detail}", file=sys.stderr)
        return 1

    spent = (
        f"on {outcome.rung} ({outcome.assurance.value}) "
        f"after {outcome.attempts_spent} attempt(s) and "
        f"{outcome.escalations} escalation(s)"
    )
    #
    #
    verdict = _Headline(
        headline=f"{contract.id}: accepted {spent}",
        passed=f"{contract.id}: checks passed {spent}",
    )
    report.outcome = "accepted"
    report.rung = outcome.rung
    report.assurance = outcome.assurance.value
    #m,
    #is
    #
    report.detail = outcome.judgement.detail
    if outcome.assurance is Assurance.UNVERIFIED:
        #
        #
        print(
            f"UNVERIFIED: {contract.id} is accepted with no independent review "
            f"approving it — {outcome.judgement.detail}",
            file=sys.stderr,
        )
    elif outcome.assurance in (Assurance.CHECKED, Assurance.UNCHECKED):
        print(f"note: {outcome.judgement.detail}", file=sys.stderr)
    bound = outcome.judgement.accepted
    if bound is None:
        #
        #
        #
        #
        #
        verdict.say()
        return _error(
            report,
            f"{contract.id} was accepted on {outcome.rung} without bound "
            f"content, so there is nothing a delivery could re-judge.",
        )
    if contract.output_schema in ("prose", "media_artifact"):
        #
        #
        #
        report.answer = bound.content
        verdict.say()
        print(f"\n{contract.id}: answer —\n{bound.content}")
        return 0
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
                #
                #
                #
                landed.draw or 0,
            )
            if recording is not None
            else None
        ),
    )


def _correction_detail(step: Attempted, each: int, subject: int | None) -> str:
    ""
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
    ""
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
        #ds
        #
        #
        #
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
        #
        #
        #is
        #
        #
        #
        #
        #
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
    #
    #
    #
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
    ""
    typed = (getattr(args, "branch", None) or "").strip()
    policy_commit = bool(config.get("delivery.commit")) if config is not None else False
    policy_branch = (
        config.get("delivery.branch") if config is not None else None
    ) or ""
    commit = getattr(args, "commit", None)
    args.commit = True if typed else (policy_commit if commit is None else commit)
    args.branch = typed or policy_branch


def _one_delivery_answer(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    ""
    branch = getattr(args, "branch", None)
    if branch is None:
        return
    if not branch.strip():
        parser.error(
            "--branch was given an empty name. Name the branch to commit onto, "
            "or leave the flag off to commit onto the one you have checked out."
        )
    if getattr(args, "commit", None) is False:
        parser.error(
            f"--branch {branch} asks for a commit onto {branch}, and --no-commit "
            f"asks for none. Pass one of them."
        )


COMMITTED = "committed"


NOT_COMMITTED = "not_committed"


DELIVERY_REFUSED = "delivery_refused"


NOTHING_TO_CHANGE = "nothing_to_change"


RAISED = "error"


DETERMINISTIC = "deterministic"


@dataclass(frozen=True)
class _Headline:
    ""

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
    ""
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
        #
        #
        #
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
                #he
                #
                report.findings = [str(finding) for finding in exc.findings]
            return _error(report, str(exc), outcome=DELIVERY_REFUSED)
        verdict.say()
        _say_reported(bound)
        left = ", ".join(path for path, _ in bound.files(contract))
        print(f"\nLeft in {left}, not committed (pass --commit to commit).")
        for path, _ in bound.files(contract):
            _say_not_rerun(adapters, path)
        #
        #
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
    ""
    from mcgyvr.deliver import not_rerun_here

    note = not_rerun_here(adapters, path)
    if note:
        print(f"  {note}")


def _say_reported(bound: Accepted) -> None:
    ""
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


def _name_the_writer(run: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    ""
    from mcgyvr.session import SessionError, resolve

    if args.orchestrator is not None and not args.orchestrator.strip():
        run.error(
            "--orchestrator was given an empty id: a row that cannot say which "
            "orchestrator produced it is the hole the field exists to close. "
            "Pass an ID, or leave the flag off to be named by the session "
            "that typed this command."
        )
    if args.orchestrator is not None and "/" in args.orchestrator:
        run.error(
            f"--orchestrator {args.orchestrator!r} cannot contain '/': the id "
            f"is the journal's file name, DIR/<ID>.jsonl"
        )
    try:
        args.session = resolve(args.orchestrator)
    except SessionError as exc:
        run.error(str(exc))


def add_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    ""

    run = sub.add_parser(
        "run",
        help="execute a contract — on the deterministic floor or up the ladder",
    )
    run.add_argument("contract", help="contract file to execute (YAML or JSON)")
    run.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=(
            "ladder to climb when the contract is not deterministic. Which rung "
            "runs is this file's — the ladder order, each unit's `attempts` and "
            "the `max_escalations` and `max_attempts` ceilings — never a flag "
            f"(default: {CONFIG_DEFAULT_HELP})"
        ),
    )
    _add_repo(run, "the git repository the work is done against")
    run.add_argument(
        "--sandbox",
        #
        #
        #
        #
        default=None,
        choices=("docker", "tempdir"),
        help=(
            "sandbox mode; defaults to `sandbox.mode` in the config, then to "
            "`docker`, which is refused when no daemon answers unless "
            "`sandbox.allow_fallback` is on"
        ),
    )
    run.add_argument(
        "--commit",
        #
        #
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "commit the change when the gate accepts it, or not (--no-commit), "
            "whatever `delivery.commit` says. Not committed — the default — the "
            "accepted change is left in the working tree and the repository is "
            "otherwise untouched: no commit, no branch. Committed, it goes onto "
            "the branch you have checked out, or onto `delivery.branch`"
        ),
    )
    run.add_argument(
        "--branch",
        default=None,
        metavar="NAME",
        help=(
            "commit onto branch NAME instead of the one you have checked out, "
            "which is left exactly as it was; implies --commit and overrides "
            "`delivery.branch`. Created from HEAD when absent"
        ),
    )
    run.add_argument(
        "--record",
        default=None,
        type=_named_path,
        metavar="DIR",
        help=(
            "also journal this run under DIR, as a complete second copy for "
            "your own reading: DIR/<ID>.jsonl, DIR/blobs/, DIR/results/ and "
            "DIR/sessions/, read "
            "back from DIR directly. This does not move mcgyvr's "
            "own record, which is always written under the config's "
            "`journal.dir` so that every run there has ever been can be counted "
            "in one place; a copy that cannot be written is reported and does "
            "not stop the run"
        ),
    )
    run.add_argument(
        "--orchestrator",
        default=None,
        metavar="ID",
        help=(
            "who is writing the journal. Names the sink, <ID>.jsonl, and is "
            "carried on every row, so two orchestrators sharing a directory "
            "stay distinguishable. Default: the session that typed this "
            "command — claude-<id> from CLAUDE_CODE_SESSION_ID, pi-<id> from "
            "PI_SESSION_FILE — and a refusal when there is none"
        ),
    )
    run.add_argument(
        "--result",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=(
            "where *you* read this run's result file (default: <journal "
            "dir>/results/<contract>-<utc stamp>.json). The path is printed as "
            "`result: PATH`; the caller reads the file. mcgyvr keeps its own "
            "copy under the journal directory either way"
        ),
    )
    run.set_defaults(func=_run)

    ses = sub.add_parser(
        "sessions",
        help="list the chat and agent sessions the journal keeps, or show one",
    )
    ses.add_argument(
        "id",
        nargs="?",
        default=None,
        help="show this session whole: question, answer, unit, outcome "
        "(default: list them, newest first)",
    )
    ses.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"whose `journal.dir` to read (default: {CONFIG_DEFAULT_HELP})",
    )
    ses.add_argument(
        "--journal",
        default=None,
        type=_named_path,
        metavar="DIR",
        help="read the sessions of this journal instead, e.g. a --record copy",
    )
    ses.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="list at most N sessions (default: 20)",
    )
    ses.set_defaults(func=_sessions)

    return run
