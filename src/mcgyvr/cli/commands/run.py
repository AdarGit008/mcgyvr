"""The `mcgyvr run` and `mcgyvr sessions` commands, and delivery settlement.

Only what is built is exposed.
"""

from __future__ import annotations


import argparse


import contextlib


import ipaddress


import json


import os


import signal


import sys


import textwrap


import threading


from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence


from dataclasses import dataclass


from pathlib import Path


from typing import TYPE_CHECKING, Any, TextIO


import yaml


from mcgyvr import __version__, atomic


from mcgyvr import recommend as recommend_module


from mcgyvr import scan as scan_module


from mcgyvr.availability import PROBE_TIMEOUT_S


from mcgyvr.capability import (
    ESTIMATES_NOTICE,
    GB_PER_GIB,
    CapabilityTableError,
    Model,
    load,
    table_path,
)


from mcgyvr.config import (
    API_OUTPUT_TOKENS,
    CONFIG_PATH_ENV,
    FLEET_FILENAME,
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)


from mcgyvr.config import config_path as resolve_config_path


from mcgyvr.config import load as load_config


from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for


from mcgyvr.emit import (
    Drift,
    EmitError,
    LockedLaunchError,
    check_all,
    check_locked,
    emit_all,
    emit_locked,
    is_locked,
    planned_locked_paths,
    planned_paths,
    resolved_launch,
    unplanned,
    unplanned_locked,
)


from mcgyvr.emit import sleep_mode as emit_sleep_mode


from mcgyvr.exits import Exit


from mcgyvr.fleet.files import FleetFileError, load_fleet


from mcgyvr.fleet.roots import (
    FLEETS_SHOWN,
    LIVE_FILE_SHOWN,
    RIGS_SHOWN,
    STAGING_SHOWN,
    FolderError,
)


from mcgyvr.initialize import (
    PRIORITIES,
    ApiSpecError,
    InitError,
    initialize,
    parse_api_unit,
    render_fleet,
    unit_names,
)


from mcgyvr.scan import ModelOnDisk, Scan


from mcgyvr.serving import (
    ModelSpec,
    Unit,
    UnitError,
    declared_models,
    hold_together,
    host_of,
    units_for,
)


if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.deliver import Accepted
    from mcgyvr.detect import Detection
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.drive import Recording
    from mcgyvr.escalate import Delivered, Halted, Judgement
    from mcgyvr.gate import GateResult
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.knowledge.record import ModelRecord
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer
    from mcgyvr.result import RunResult
    from mcgyvr.route import Attempted, Try
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.session import Session

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, SETUP_DOC, _add_repo, _named_path
from mcgyvr.cli.fleet_live import _admitted_live, _live
from mcgyvr.cli.sandbox import _reads_the_tree, _sandbox_policy, _say_what_the_sandbox_leaves_out


def _run(args: argparse.Namespace) -> int:
    """Drive one contract to a gated verdict, and optionally to a commit.

    Committing is opt-in. A gate verdict costs the user a sandbox that is torn
    down either way, and a commit is a write to a repository they did not hand
    over for one — so ``--commit`` is what makes the difference, and its absence
    leaves the accepted change in the working tree and nothing else in the
    repository: no commit, no branch, no receipt.

    Two paths, chosen by the contract rather than by a flag. A deterministic
    contract names a program and is run here; anything else climbs a ladder and
    is :func:`_climb`'s. The split is the contract's catalog entry (its
    ``operation``'s, or its ``task_type``'s) because that is where the catalog
    already records which family work of this kind may
    *begin* on, and a flag that let a caller override it would be a second,
    quieter answer to the question ``starts_on`` exists to settle.

    **A tool step has three outcomes here, not two**
    (:class:`~mcgyvr.drive.ToolOutcome`): the program **could not run**
    (126/127, an environment issue — the work is still doable on a dearer
    family); the program **ran and did the
    job its type describes** (:attr:`~mcgyvr.drive.ToolOutcome.performed`, which
    is where any residue it reported goes on to the gate, because the gate is
    the thing that judges a result and stopping here means the result is never
    judged); and the program **ran and failed** (fatal — a fixer that could not
    load its config applied the guarantee to nothing, and the gate reading that
    same config is broken in the same way).

    The test is the exit code, against the set of codes that invocation reports
    under — the rule :func:`mcgyvr.gate.adapter.trusted_stdout` applies to the
    gate's own invocations. What the program said it will not fix is printed
    here.

    **Every run is journaled, in one place, and nothing a caller passes moves
    it.** The journal is mcgyvr's own record — ``<journal.dir>/<orchestrator>.jsonl``
    with the prompts and replies content-addressed under ``blobs/``, each
    run's result under ``results/`` and each ``chat`` or ``agent`` session
    under ``sessions/``. It exists to be *compounded*: how often the
    floor finishes a task type on its own, what a rung costs per accepted
    change, whether escalating paid are all questions about every run there has
    been, and they can only be asked where every run is. ``--record DIR`` is a
    complete second copy for the caller's own reading, and a copy that cannot
    be written is a line on stderr rather than the end of a run mcgyvr has
    already recorded. ``--result PATH`` is the same bargain for the result file: it
    says where the *caller* reads it, and ours keeps its own.

    **Both paths, not only the dispatching one.** A deterministic contract
    sends nothing to a model and is journaled all the same: how often the floor
    finishes a task type on its own cannot be computed from a table missing the
    floor's runs. The floor writes one row naming the program that did the
    work, with ``tier: deterministic`` beside it and no prompt, reply or token
    counts, because it made no dispatch and must not look as though it did.

    The orchestrator is the session that typed the command
    (:mod:`mcgyvr.session`), resolved in :func:`main` before anything here runs,
    so a row can be followed back to the conversation. The only thing printed
    about the result is its path: the caller reads a file, not the scrollback.
    """
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
    # Warned, never refused: the sandbox is HEAD by design, and a dirty tree
    # only blocks delivery where the target itself is dirty. Said only where
    # the run reads the tree at all (e2e run 3, T4).
    notes = _say_what_the_sandbox_leaves_out(repo) if _reads_the_tree(contract) else []

    # The ladder path needs the config; the deterministic floor does not and
    # must keep running without one. Both need the journal dir, which is the
    # config's when there is one and the schema default when the floor runs
    # bare — a default the reference states, not one invented here.
    config: Config | None = None
    config_error: ConfigError | None = None
    # `--config` or nothing, handed on as it came: the loader locates the file
    # when nobody named one, because the remedy for a config that is not there
    # turns on who chose the path and a caller that resolves it first has
    # already lost that. What stays here is the question the loader cannot
    # answer — whether anybody named a path at all — because that decides
    # whether this run says anything: a default location with nothing in it is
    # the supported bare install, and a path someone typed is not.
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
        # `config_error` says `mcgyvr setup` and where the file would go, which
        # is the whole remedy for an operator who already knows what a config
        # is for. It is not the whole remedy for the reader this line actually
        # has: an agent following the skill, which names no setup verb and no
        # lever, onto a machine nobody has set up. So the message keeps the
        # loader's own remedy and adds where the rest of it is written down.
        print(f"error: {config_error} {SETUP_DOC} says how.", file=sys.stderr)
        return 1

    # Ours, and nothing a caller passes moves it. The journal is a corpus to be
    # compounded — how often the floor finishes a task type on its own, what a
    # rung costs per accepted change, whether escalating paid — and every one of
    # those questions is about *all* the runs there have been.
    configured = config.get("journal.dir") if config is not None else None
    journal_dir = Path(configured or JOURNAL_DIR_DEFAULT).expanduser()
    # An mcorch writer's transcript is under this directory and nowhere the
    # parser could have looked: attached now that the directory is known.
    session = with_mcorch_transcript(session, journal_dir)
    # Theirs, for their own reading. A complete copy — every line, every blob,
    # the result file — so a reader of the journal reads it exactly as it reads
    # ours, and a failure to write one is a note rather than the end of a
    # run we have already recorded correctly (`Recording.copy_failed`).
    #
    # A copy of the corpus *into* the corpus is dropped rather than made, and
    # this is not a nicety: the copy is written to `<dir>/<orchestrator>.jsonl`
    # by the same name ours is, so naming our own directory would append every
    # line to the same file twice. `fold` keeps both rows — a repeat attempt id
    # is a collision, not a supersede — so a reader that builds one table row
    # per folded attempt would count one dispatch as two.
    # Resolved before comparing, because `--record .` and an absolute
    # `journal.dir` are the same directory spelled two ways.
    asked = Path(args.record).expanduser() if args.record is not None else None
    mirrors = (
        (asked,)
        if asked is not None and asked.resolve() != journal_dir.resolve()
        else ()
    )

    # One stamp names the run: the result file carries it and every journal
    # row keys on it, so a re-run of the same contract is a second run and
    # not a second copy of the first (`Recording.run`). The destination is
    # settled here rather than at the end because the note below states it,
    # and a note may not state something the run has not decided.
    stamp = run_stamp()
    # Ours is written whatever else is; `--result` says where the *caller*
    # reads it, and that is the path the `result:` line names. The two are the
    # same file when the flag is off, and `write` is called once for it.
    keep = result_path(journal_dir, contract.id, stamp)
    where = Path(args.result) if args.result else keep

    bare_install = isinstance(config_error, ConfigMissingError) and named is None
    if config_error is not None and not bare_install:
        # Said, not swallowed. The floor runs without a config on purpose, so
        # this is not an error — but a config that is *there* and cannot be
        # used is not the same thing as none, and silence made the two
        # identical: whatever `journal.dir` that file names is not the
        # directory this run is about to write under, and the operator's only
        # clue was a result file somewhere they had configured away from. So
        # the note names the file, what is wrong with it, and where the answer
        # went instead.
        #
        # It names the result file because that is the path the caller reads;
        # the floor's row and mcgyvr's own copy of the result go under the
        # default journal dir. Only the floor reaches this line — a climb
        # without a ladder was refused above.
        #
        # The reason is flattened first: a YAML parse error is several lines,
        # and the tail of a multi-line message printed under a `note:` prefix
        # is not part of the note as far as anything reading this output is
        # concerned.
        #
        # "sends its result to", not "its result lands at": this line is
        # printed before the run, so the destination is all it has. Where the
        # result *arrives* is not settled until `write` below returns, and
        # `--result` at an unwritable path leaves the note having reported a
        # file that was never created. Moving the note after the write would
        # trade a false tense for a warning that arrives after the whole run,
        # and after the failures that end it early — so the note keeps its
        # place and states the fact it actually has.
        reason = " ".join(str(config_error).split())
        print(
            f"note: {path or 'the config'} is not usable ({reason}); this run "
            "goes on without "
            f"a config and sends its result to {where}"
        )

    report = RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        # A session writes nothing, so it has no target, whatever it gave.
        target="" if contract.is_session else contract.target,
        orchestrator=session.orchestrator,
        run=stamp,
        session_file=str(session.session_file) if session.session_file else None,
        journal=str(journal_dir),
        notes=notes,
    )

    # Every run, both paths: the floor dispatches nothing and is journaled too.
    try:
        recording = Recording(
            path=journal_dir / f"{session.orchestrator}.jsonl",
            orchestrator=session.orchestrator,
            run=stamp,
            session_file=session.session_file,
            mirrors=mirrors,
        )
        # Every row carries the caller's tags, so tags that cannot be read
        # are refused here, once, rather than as a failed row per attempt.
        run_tags()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # Asked before the run rather than discovered during it. Our sink raises on
    # an unwritable path (`telemetry.observe`), and a raise from inside a
    # dispatch reaches the caller as a traceback with no `result:` line; a
    # directory that is a file or a path with no permission is an
    # operator error that is free to state now and expensive to read later. A
    # full disk part-way through is still a raise; this is the cheap half.
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

    # Settled once, here, so both paths below open the same sandbox
    # (`_sandbox_mode` says who answers).
    args.sandbox = _sandbox_mode(args.sandbox, contract, config)
    # Settled once too, for delivery (`_commit`): it judges the bytes again,
    # and a gate that read a different setup from the sandbox's would refuse
    # where the change lands what the setup asked it to accept where it was
    # written (`gate.param_mutation`).
    args.gate_adapters = gate_adapters(config)
    # And whether, and onto which branch, an accepted change is committed: the
    # same precedence (`_settle_delivery`).
    _settle_delivery(args, config)

    if contract.is_deterministic:
        code = _floor(args, contract, repo, report, config, recording=recording)
    else:
        assert config is not None  # refused above when it could not load
        code = _climb(args, contract, repo, config, recording=recording, report=report)

    report.exit_code = code
    # Said once, at the end, and not per row: a directory that is a file fails
    # identically for every line of the run, and a thousand notes about one
    # mistake is a way of not reporting it. The result file carries it too, so
    # a caller who reads the file rather than the scrollback — which is what the
    # skill tells them to do — learns their copy is short.
    for mirror, why in recording.copy_errors.items():
        report.copy_errors[str(mirror)] = why
        print(
            f"error: the copy of this run's journal asked for in {mirror} could "
            f"not be written ({why}). mcgyvr's own record under {journal_dir} is "
            f"complete and the run was not stopped for it.",
            file=sys.stderr,
        )

    # A chat or agent run is a session, and its answer is kept (owner, e2e run
    # 1 F7: "answers are not throwaway nowhere"): a record of its own under
    # the journal, written before the result file so the result never names a
    # record that is not there. Not fatal when it cannot be written: the answer
    # is in the result file all the same, and the line says where it is not.
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

    # Serialised once and copied, never written twice. `write` stamps
    # ``finished`` from the clock on each call, so a second call would produce
    # a file that differs from the first in the one field a reader would use to
    # tell two runs apart — and these are one run. The caller's path is the one
    # written, because it is what the `result:` line names and what they would
    # notice missing; ours is a copy of those exact bytes.
    failed = where
    try:
        written = write(where, report)
        if keep != where:
            failed = keep
            _copy(written, keep)
    except OSError as exc:
        # Said, not thrown. By now the run has happened — an accepted change
        # is already in the working tree — and a traceback with no `result:`
        # line reads to the caller as a run that never started. One line that
        # names the path, the reason and what the run came to is the whole of
        # what the file would have said that matters — where the change went
        # included, which is `delivery`'s to say beside the judgement.
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

    # Their copy of the result, under their copy of the journal, so a directory
    # `--record` named is a whole journal and not a journal missing its answers.
    # Not fatal, for the reason none of their copies are: ours is written.
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
    """The same bytes at a second path, whole or not at all.

    Through a staging name and :func:`os.replace`, as
    :func:`~mcgyvr.result.write` does, so a reader never opens a half-written
    result — and the same tidy-up, so a copy that failed part-way leaves no
    ``.part`` for the next reader to wonder about.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(target, source.read_bytes())



def _sessions(args: argparse.Namespace) -> int:
    """List the session log, newest first, or show one session whole.

    The log is the journal's ``sessions/``: ``--journal DIR`` (a ``--record``
    copy, say), else the config's ``journal.dir``, else the schema default — a
    bare install has a journal too. One line per session in the listing, and
    the question and the answer in full when one is named.
    """
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.result import SESSIONS_DIR, sessions

    if args.journal is not None:
        journal_dir = Path(args.journal).expanduser()
    else:
        chosen = Path(args.config) if args.config else None
        try:
            configured = load_config(chosen).get("journal.dir")
        except ConfigError as exc:
            # No config where nobody named one is the bare install, whose
            # journal is the default; a config someone named is theirs to fix.
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
    # An id is a file name in the log, never a path out of it.
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
    """The floor's program did not do the work, and said why.

    A local exception rather than an early ``return``, because the run has to
    reach :func:`~mcgyvr.telemetry.observe`'s ``except`` to leave a row. A
    ``ruff`` that is not installed, and one that exits 2 on a config it cannot
    load, are both things the corpus has to be able to count — "the floor could
    not" is an answer to "how often does the floor finish this on its own", and
    a run that returned quietly was indistinguishable from one that never
    happened.
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
    """Run a deterministic contract's program, gate what it did, and record it.

    **The floor journals, on the same terms as a dispatch.** It writes no
    prompt and no reply because it sent none, but it is a run, and a corpus
    that held only the runs the floor did *not* handle could not answer the one
    question the deterministic tier exists to raise: how much work finishes
    here, for free and in one attempt, rather than on a model.

    The row is written once the program and the gate have both run inside
    :func:`~mcgyvr.telemetry.observe`, and is corrected afterwards with how the
    result was judged and where it went. ``rung`` is the program that did it —
    ``ruff``, not a model — and ``tier`` is ``deterministic`` beside it, so one
    query can count a floor run against a ladder attempt without the two
    vocabularies colliding in one column.

    What is deliberately outside the row: opening the sandbox. It is the
    floor's ``pool.bind`` — the step before the work that decides whether there
    is any — and the ladder does not journal a dispatch it could not make
    either. What is counted is what ran.
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
        # The floor dispatches nothing and journals all the same: the
        # `--record` directory gets this run's row, its verdict and a copy of
        # its result, and so does mcgyvr's own `journal.dir`.
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

    # One row per run, not per step: `tool_steps` returns one step or none —
    # "a tool fails identically on retry" — and a key per step would invent a
    # breadth the floor does not have.
    rung = steps[0].tool.program or contract.kind.name
    attempt_id = recording.attempt_id(contract.id, rung, 1)

    # What an in-process step said it did, for the journal's verdict row.
    performed: list[str] = []

    def work() -> GateResult:
        for note in sandbox.notes:
            print(f"note: {note}")
        # The run's own ceiling, as its acceptance commands get
        # (`acceptance_for`): left to `run_tool_step`, a step is timed by the
        # config at the default location rather than the one `--config` named.
        ceiling = task_ceiling(config)
        for step in steps:
            outcome = run_tool_step(step, sandbox, timeout=ceiling)
            print(f"  {_ran(step)}")
            if not outcome.ran:
                raise FloorStoppedError(str(outcome.environment_issue))
            assert outcome.result is not None  # `ran` is `result is not None`
            if not outcome.performed:
                raise FloorStoppedError(
                    (outcome.result.stderr or outcome.result.stdout).strip()
                )
            if not step.argv and outcome.result.stdout.strip():
                # An in-process step's own account of what it touched — for
                # `rename_symbol`, every file and line it renamed in and every
                # same-named occurrence it judged to be another symbol. A
                # program's stdout is its own business; this one is the only
                # record of which files the change spans, so it is printed,
                # kept in the result's notes and handed to the journal.
                said = outcome.result.stdout.strip()
                print(textwrap.indent(said, "    "))
                performed.append(f"{_ran(step)}\n{said}")
                report.notes.append(f"{_ran(step)}: {said}")
            if not outcome.ok:
                # Reported, not swallowed. The tool did what its type
                # guarantees and is telling us what it will not do — for
                # `lint_fix`, "a diagnostic the linter will not fix itself
                # is explicitly out of scope for this type". Printing it is
                # how the operator learns there is work left that no
                # deterministic rung is going to take, and it goes to stdout
                # beside the command rather than to stderr, because nothing
                # here failed.
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
            # The baseline `_climb` checks before a rung is charged, checked
            # here before the tool runs: a suite already red on the unchanged
            # tree is the contract's or the tree's problem, and judging it
            # after the tool would file it as the tool's change, `rejected`.
            # No row yet — the run has not started its work.
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
        # The row exists by now — `observe` writes one on both of its paths,
        # and everything caught here is raised from inside it or from the
        # sandbox closing around it — so the verdict is written the way a
        # climb's raised attempt's is. An uncorrected row reads as a run that
        # died before anything could judge it, and "the floor could not" is an
        # answer the corpus is being kept in order to count: a tier that
        # finishes nothing on this machine is a different fact from a tier
        # nobody asked. `open_sandbox` failing is caught above instead, where
        # there is no row yet and a correction would be an orphan.
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
    """Whether ``contract`` is a session that declares no command to run.

    Such a run only stages its reply for the output checks, so its sandbox is
    ``sandbox.sessions``'s to choose and not ``sandbox.mode``'s (owner, e2e
    run 2 R10: docker for chat and agent is opt-in at setup).
    """
    return contract.is_session and not (
        contract.acceptance_commands or contract.demonstration_commands
    )



def _sandbox_mode(typed: str | None, contract: Contract, config: Config | None) -> str:
    """The sandbox mode a run of ``contract`` opens.

    A flag typed at the terminal is a person overriding their own file and
    wins. With none, a session that runs no command reads `sandbox.sessions`
    (`tempdir` unset), and every other run reads `sandbox.mode` (`docker`
    unset): a session that declares a command runs it as any task does.
    """
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
    """The line that says what a floor step ran, as a person would retype it.

    A program is its command line. An in-process step has no command line —
    :attr:`~mcgyvr.deterministic.ToolStep.argv` is empty on purpose — and
    joining nothing printed a bare ``$``, which says a command ran and names
    none. It is said instead as what it is: mcgyvr's own operation, with the
    pair it was given.
    """
    if step.argv:
        return f"$ {' '.join(step.argv)}"
    said = f"(in-process) {step.tool.operation}"
    if step.rename.stated:
        said += f" {step.rename.old} -> {step.rename.new}"
    return said



def _error(report: RunResult, detail: str, *, outcome: str = "error") -> int:
    """Print an error the way every branch here does, and keep it for the result.

    The outcome is set here, not left to whatever the caller had written
    before things went wrong. A caller reporting under a more specific word
    passes it.
    """
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
    """Drive a model-executed contract up the ladder a config describes.

    **Which flag selects a rung: none, and that is the answer rather than a
    deferral.** Rung selection is already owned, in one place, by data this
    command does not get to second-guess. The contract's ``task_type`` names the
    family work of its kind may begin on; :func:`~mcgyvr.escalate.ascent` walks
    the catalog's families upward from there; :func:`~mcgyvr.route.plan` takes
    each family's rungs in the order the operator wrote them into the ladder
    and gives each the attempts the policy's ``attempts`` map declares for it,
    capped by the contract's ``limits.attempts``; and ``max_escalations`` with
    ``max_attempts`` bound how far the walk gets. A ``--rung`` flag would be a
    fourth party to a decision three files already settle, and the first time it
    disagreed with the ladder the operator would have two orderings and no way
    to tell which one ran.

    Hence ``--config`` and no rung flag. It resolves the same way every other
    command's does — ``$MCGYVR_CONFIG``, else the live fleet folder the
    config folder's ``live.json`` names — because a
    second resolution order for the same file is a
    second file as far as an operator debugging one is concerned. The config is
    loaded once, in :func:`_run`, because the journal dir is read off it before
    a rung is chosen.

    **An install that cannot run this contract is refused before a sandbox is
    opened.** :attr:`~mcgyvr.escalate.Ascent.reason` already carries the sentence
    each empty family wrote about itself — which rung was skipped, which variable
    is unset — and ``escalate`` would reach the same conclusion on its own. Doing
    it here is what keeps a container from being built for a task that was never
    going to dispatch.
    """
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

    # Live is admitted before anything here is built, opened or dispatched
    # (the lab's fleet-identity plan, §6): each rig of the live
    # fleet is read through the door and held to its lock
    # (`mcgyvr.fleet.admission`). At the
    # top, the conservative place: a refused run costs no pool, no capacity slot
    # and no sandbox. A run under a staged setup (`_live`) reads no rig.
    if _live(config):
        refused = _admitted_live(config)
        if refused is not None:
            report.outcome = "error"
            report.detail = refused
            return Exit.REFUSED

    # What the ladder manager (`mcgyvr manage`) has chosen for this ladder, if
    # it runs one: the config a task climbs with, and the hooks that let the
    # manager read the queue. An unmanaged ladder is handed back unchanged.
    from mcgyvr import ladder_manager
    from mcgyvr.pressure import Board

    managed = ladder_manager.for_task(config, read_board=Board().read)
    config = managed.config
    if managed.note is not None:
        print(f"note: {managed.note}")

    # Structural resolution, no probe: a live-reachability sweep costs one
    # timeout per source and answers a question the dispatch below is about to
    # ask for real. `mcgyvr local_pool --probe` is where an operator asks it in
    # advance, and paying for it here would charge every run for a diagnosis.
    #
    # `Availability.not_serving` — whether the model a rung declares is the one
    # its port holds — is not asked here either: `source_map(config)` takes no
    # probe, so this function resolves its ladder without a network. A wrong
    # model is caught at dispatch instead: llama-server answers a request
    # naming another model from the weights it holds, and the runner refuses a
    # reply whose `model` names other weights (`runner.WrongWeightsError`).
    pool = source_map(config)

    # The width `mcgyvr config` prints, actually applied. Built here, once, and
    # handed to both `ascent` and `escalate`: the reservations one makes are
    # the loads the other reads, so two capacities would be two tallies of one
    # rig. Its slot files are a host-wide rendezvous, which is what makes this
    # bound hold across concurrent `mcgyvr run` processes and not merely
    # within one — the case it exists for, since a single contract dispatches
    # one request at a time and never contends with itself. Its server reader
    # is what lets `fanout: idle` count a client that is not mcgyvr: a rung is
    # full by either count (Capacity.judge), and it is read only where that
    # question is asked.
    from mcgyvr.pressure import server_counts

    try:
        capacity = Capacity.of(config, gauge=managed.gauge, busy=server_counts(pool))
    except CapacityError as exc:
        return _error(report, str(exc))

    # The cooldown learns from dispatch failures, not from a probe, so its
    # liveness half is a stub that always reports live. Probing here would
    # charge every run for a diagnosis the dispatch below is about to make for
    # real, and `mcgyvr local_pool --probe` is where an operator asks it in advance.
    # The probe parameter is typed `object` rather than `Endpoint` because the
    # seam guard forbids importing `Endpoint` above the seam, and `object` is
    # accepted contravariantly.
    def _always_live(endpoint: object, timeout_s: float) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source=endpoint.source,  # type: ignore[attr-defined]
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

    # Before the sandbox, for the reason the paragraph above gives: an install
    # whose named verifier cannot serve is refused while refusing is still
    # free. `verifier.enabled` is acted on here — on unless the config says
    # `false` — and `reviewers_for` reads the rest once: the named
    # `verifier.unit` (or, for work its own model wrote, the fallback
    # `verify.stand_in_rung` picks), or, with none named, the next dearer
    # local rung with another model for each builder (never a hosted one). A
    # builder with no independent reviewer is not refused; its acceptance is
    # labelled unverified and says so. A reply (`chat`, `agent`, `media`) is never
    # reviewed, so none is resolved for it and a verifier the install cannot
    # serve does not refuse it (owner, e2e run 2 R11: "agent and chat have no
    # gates").
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
        # A session that runs no command and was not given a container is
        # staged on this host without `open_sandbox`: no daemon is probed, so
        # Docker need not be installed, and neither the weaker-mode note nor
        # `sandbox.network: none`'s refusal applies — both are about commands,
        # and none runs. Its workspace is a checkout of HEAD as in any mode.
        sandbox = (
            TempDirSandbox(repo, notes=(SESSION_SANDBOX_NOTE,))
            if _runs_no_command(contract) and args.sandbox == "tempdir"
            else open_sandbox(
                repo,
                mode=args.sandbox,
                image=config.get("sandbox.image"),
                setup=config.get("sandbox.setup") or (),
                # The worker runs outside the sandbox and the sandbox has to be
                # able to reach it: a container with no route to the source is
                # a task that gates fine and never gets an answer to gate.
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
            # The baseline, before the first rung: `Acceptance.baseline`
            # runs both lists against the unchanged tree, so a demonstration
            # that already passes or a suite that is already red is refused
            # here rather than charged to a model. The issue's own wording
            # tells the two apart, because the operator's next move differs:
            # one says fix the contract, the other says fix the tree. What the
            # commands left behind was cleaned up, and the notes say what.
            acceptance = acceptance_for(contract, sandbox, config=config)
            if acceptance is not None:
                baseline = acceptance.baseline()
                for note in baseline.notes:
                    print(f"note: {note}")
                report.notes.extend(baseline.notes)
                issue = baseline.issue
                if issue is not None:
                    # Filed under `error`, the word the result file
                    # documents for a run that reached no verdict — a
                    # preflight issue is an orchestration error and not
                    # a rejected change (gate/preflight.py). The detail
                    # names it as one.
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
                # The fleet-manager seam: a Jev difficulty judgment that may
                # route a hard task to an asleep smarter rung before the api.
                # ``None`` for an install with no asleep smarter rung, or one
                # that has not enabled sleep-wake — which is every install
                # that did not ask for the feature.
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
    """``attempt``, warning once on stderr before each pulled step is dispatched.

    Warned, not enforced. A step whose unit's combination is pulled
    (:func:`mcgyvr.fleet.alerts.live_pulled_units`) is named, with each pulled
    field and its count, and then dispatched exactly as it would have been:
    this wraps the attempt and never answers for it, so the rungs, the attempts
    and the outcome are the climb's own. Pulls that cannot be read are one
    warning, and the run goes on; nothing here fails a run.
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
) -> int:
    """Print what the climb spent, correct the journal, and commit when asked.

    Every attempt is printed, including the ones that failed, and under a failed
    one the gate's findings, one ``✗`` line each. A ladder walk that reported
    only its answer would leave an operator unable to tell one rung accepting
    immediately from three rungs spent and the dearest one succeeding, which is
    the difference the whole escalation policy is about; and a failure reported
    without its findings leaves the caller unable to write a better contract,
    which is the only thing a caller can do about it.

    **This is where the journal learns how each attempt landed.** Each row was
    written by :func:`~mcgyvr.telemetry.observe` before the gate ran, so it
    says what was asked and what came back and not whether it was any good.
    The verdict is appended now as a correction — ``passed``/``failed``, with
    the finding lines as the detail of a failure, or ``error`` for an attempt
    that raised — and :func:`_commit` appends a second one on the accepted
    attempt saying where the work went. A rung that declined dispatched
    nothing and has no row to correct. An attempt that drew more than once
    (``breadth.draws``) wrote one row per draw: the verdict lands on the draw
    it is about and every other draw of that attempt is ``failed``. ``best_of``
    does not stop early — it draws all of them, gates each and ranks the lot —
    so the rows beside the verdict's are draws whose work did not land, which
    is what ``failed`` says about them here whatever their own gate thought of
    them on its own.

    **An attempt that raised accounts for every row it wrote, and the result
    names the one it died in.** The entry's ``rows`` is how many rows the
    attempt wrote — what is iterated here — its ``draws`` is the breadth it was
    asked for, and its ``draw`` is the one that raised; all three are stated by
    the driver (:class:`~mcgyvr.escalate.DispatchRaisedError`) because nothing
    else knows: an exception carries no draw, and reading it back off the
    journal is inference that mis-attributes twice over — a raise after the
    draws lands on a dispatch that answered, and a draw whose row was lost
    shifts every draw down one. A raise before the first dispatch wrote no
    rows, so nothing is corrected; a correction appended for a row nobody wrote
    is an orphan :func:`~mcgyvr.telemetry.fold` returns and the live view
    drops.

    **Every one of those rows is ``error``, including the draws that answered
    before the raise.** They are not ``failed``: ``failed`` is a gate's word,
    and while the earlier draws may well have been gated, the *attempt* they
    belong to reached no verdict at all — writing one on them would report a
    judgement that never happened, the same coinage this project refuses for a
    draw that produced nothing. What distinguishes the row that actually raised
    is not a different word but ``attempt_id``: the result names it, and only
    it, and names nothing when the raise was no dispatch's.

    The accepted attempt is the last entry of the history: ``route.climb``
    returns the moment an attempt passes, right after recording it.
    """
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
        # The draw the entry is about: the one the gate judged, or the one the
        # attempt died in. `None` comes off a raised entry only, and says no
        # dispatch of the attempt is the subject — so there is no row for the
        # result to name, and every row it wrote is corrected all the same.
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
    # The headline waits for delivery when there is one: "accepted" is said
    # only of a change that was written (e2e run 2, R2).
    verdict = _Headline(
        headline=f"{contract.id}: accepted {spent}",
        passed=f"{contract.id}: checks passed {spent}",
    )
    report.outcome = "accepted"
    report.rung = outcome.rung
    report.assurance = outcome.assurance.value
    # How the work was judged, in the judgement's own words — verified by whom,
    # unverified and why, or a reply's checks — into the result file, which is
    # what a caller is told to read.
    report.detail = outcome.judgement.detail
    if outcome.assurance is Assurance.UNVERIFIED:
        # Said where it cannot be missed, because nothing else about the run
        # looks different: the change is accepted on the gate alone.
        print(
            f"UNVERIFIED: {contract.id} is accepted with no independent review "
            f"approving it — {outcome.judgement.detail}",
            file=sys.stderr,
        )
    elif outcome.assurance in (Assurance.CHECKED, Assurance.UNCHECKED):
        print(f"note: {outcome.judgement.detail}", file=sys.stderr)
    bound = outcome.judgement.accepted
    if bound is None:
        # `judge` only reaches PASSED through a gate that accepted, and
        # `worker_attempt` binds on exactly that branch. Refusing rather than
        # asserting because the alternative to a bound value is not a fallback:
        # there is nothing to deliver, and a commit assembled from anything else
        # would be bytes no gate read.
        verdict.say()
        return _error(
            report,
            f"{contract.id} was accepted on {outcome.rung} without bound "
            f"content, so there is nothing a delivery could re-judge.",
        )
    if contract.output_schema in ("prose", "media_artifact"):
        # A raw-text reply is the answer, not a file that gets committed: the
        # harness reads it off the result file rather than off a delivery. No
        # `_commit` is attempted and the accepted exit is returned.
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
                # An accepted attempt was judged, and a judged entry names the
                # draw it was judged on. Only a raised entry leaves this unset,
                # and a raise is never the last entry of a `Delivered`.
                landed.draw or 0,
            )
            if recording is not None
            else None
        ),
    )



def _correction_detail(step: Attempted, each: int, subject: int | None) -> str:
    """What the correction on one draw's row says, in this caller's vocabulary.

    Four sentences, because a row is corrected for four different reasons and a
    reader of the journal has only this line to tell them apart: the draw the
    verdict is about carries the gate's findings; a draw that lost to it says
    which draw won; the draw an attempt raised in carries the raise; and a draw
    of a raised attempt that is not that one says so and says where the raise
    was instead — on another draw, or past the last draw that answered.

    That last sentence is why the raised rows are not simply left alone. An
    attempt accounts for every row it wrote: a suffixed row that keeps ``ok:
    true`` and no outcome is indistinguishable from a run that died before it
    could be corrected, which is precisely the reading breadth's own telemetry
    must not invite.

    A raise with ``draw: null`` has three causes: a gate that died on an early
    draw, a draw whose ``pool.bind`` raised before it reached a row, and a raise
    after the last draw. This line is only ever written about a row that
    exists, so ``rows - 1`` is the last draw that answered, and naming that draw
    is true of all three.
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
    """Print the gate verdict, correct the row it is about, and commit when asked.

    ``recording`` and ``attempt_id`` arrive from :func:`_floor`, its only
    caller, which writes one row per run and needs it corrected the way
    :func:`_report_climb` corrects a climb's: the row says the program ran, and
    the correction says how the gate judged it. They are optional because the
    correcting is the only part of this a caller can decline, not because there
    is a second caller that declines it — a climb never comes through here, it
    reports itself and reaches :func:`_commit` directly.

    ``performed`` is what an in-process step said it did — a rename's files and
    lines — and goes into the verdict's correction beside the findings, so the
    journal keeps the one account of which files the change spans.

    **What is delivered is what the program changed.** The binding is minted
    over the sandbox's whole change set, the files the gate just judged, not
    over ``target`` alone: a ``rename_symbol`` that renamed a definition and its
    importers is one change in several files, and delivering only the target
    left the user's tree importing a name that no longer exists. Delivery then
    holds every file to the contract's scope and lands them in one commit, or
    none.
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
        # The gate's word for it, in the gate's vocabulary — the same two words
        # a climb's attempts are corrected with, so one query counts them
        # together. `_commit` appends a second correction on top saying where
        # the work went, and the folded row is that later one.
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
        # The program ran, the gate had nothing to object to, and the tree is
        # exactly as it was: the target already is what the task type asks for.
        # Delivery would refuse it as a change identical to its base — which is
        # right for a model that answered with its target unchanged, and wrong
        # for a program that did its job and found nothing to do. The floor's
        # no-op ends on its own word, exit 0, with or without --commit, and
        # nothing is written or committed. Checked after binding: a target
        # that cannot be read is an error whatever changed.
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
    # Only now: `accepted` tells the caller the change is in the target, and
    # until the bytes are bound there is nothing to put there. A tool's change
    # on the gate is what `deterministic` labels.
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
    """Settle ``args.commit`` to a bool and ``args.branch`` to a name or ``""``.

    The precedence ``--sandbox`` has: a flag typed at the terminal is a person
    overriding their own file for one run and wins; with no flag the policy
    answers (``delivery.commit``, ``delivery.branch``); with neither, nothing is
    committed. ``--branch NAME`` implies ``--commit`` — naming where to commit
    is asking for a commit — while ``delivery.branch`` does not: it is where
    commits go once something turns them on. ``--branch`` with ``--no-commit``
    is refused at parse time (:func:`_one_delivery_answer`) and never reaches
    here. A run with no usable config commits only when a flag says so.
    """
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
    """Refuse ``--branch`` that is blank, or typed beside ``--no-commit``.

    At parse time, through the parser's own ``error``, so it exits 2 like every
    other usage error and before a config is read or a sandbox opened. The two
    flags ask for opposite things; picking one would be guessing which the
    person meant.
    """
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
    """The stdout lines that say how a run's change was judged and where it went.

    Built by the two reporters (:func:`_report_run`, :func:`_report_climb`)
    and said once, by whichever path ends the run: :func:`_commit` after
    delivery has answered, or the reporter itself on a path that delivers
    nothing. ``headline`` is the line of a change that landed (or of a run
    that never reached delivery); ``passed`` opens the line of one delivery
    refused, which goes on to say ``but not written`` and why (e2e run 2, R2).
    ``below`` is what is printed under either — the gate's findings and
    environment issues.
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
    """Deliver an accepted change into the user's repository, when asked to.

    Shared by both halves of ``run`` so that "what ``--commit`` does" has one
    answer. ``bound`` is an :class:`~mcgyvr.deliver.Accepted` in both cases and
    never a string: the deterministic path mints it off the workspace the gate
    read, the ladder path carries the one its attempt minted there, and delivery
    re-judges either in the repository the commit lands in.

    Whether to commit and onto which branch are ``args.commit`` and
    ``args.branch`` as :func:`_settle_delivery` left them — the flags typed,
    else ``delivery.commit`` and ``delivery.branch``, else no commit — the same
    on both paths, whether or not the contract climbed a ladder. An empty
    branch is the one checked out.

    What *is* handed over is the gate's adapters as the run's setup built them
    (``args.gate_adapters``, settled in :func:`_run`), so delivery judges by the
    same ``gate`` settings the sandbox did. A caller that settled none is
    refused by name rather than delivered under the strict default it did not
    choose.

    **The default is the working tree, and that is not a lack.** Not committing
    — the shipped policy — leaves the accepted change in the target and the
    repository otherwise untouched: no commit, no branch, no receipt. The journal row
    of the accepted attempt is told so (``not_committed``), and told
    ``committed <sha> on <branch>`` or ``delivery_refused`` otherwise, so the
    folded outcome is how the work finally landed.

    **The verdict's headline is printed here, once delivery has answered.**
    A change delivery refused was not written, and a stdout that said
    ``gate accepted`` above a refusal on stderr read as an acceptance (e2e
    run 2, R2). So ``verdict`` is said as it was when the change landed, and
    as ``<id>: checks passed, but not written: <reason>`` for every reason
    delivery refuses; the exit code, the result file and the ``error:`` line
    on stderr are unchanged.
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
        # The refusal is the run's outcome, so `detail` carries it too (set by
        # the caller with the outcome); `delivery` says it where every other
        # delivery says where the change went.
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
                # The checks behind the refusal, not only its sentence — the
                # same lines a gate rejection leaves in `findings`.
                report.findings = [str(finding) for finding in exc.findings]
            return _error(report, str(exc), outcome=DELIVERY_REFUSED)
        verdict.say()
        _say_reported(bound)
        left = ", ".join(path for path, _ in bound.files(contract))
        print(f"\nLeft in {left}, not committed (pass --commit to commit).")
        for path, _ in bound.files(contract):
            _say_not_rerun(adapters, path)
        # Beside the judgement, never over it: `detail` stays how the work
        # was judged, and where it went is `delivery`'s (#183).
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
    """Print which checker delivery left out because it loads ``path`` as code."""
    from mcgyvr.deliver import not_rerun_here

    note = not_rerun_here(adapters, path)
    if note:
        print(f"  {note}")



def _say_reported(bound: Accepted) -> None:
    """Print once each finding the gate reported only because the setup said so.

    Under ``gate.param_mutation: report`` a function that changes its argument
    is accepted, and the finding travels as one of the gate's observations,
    which nothing else here prints. It is the one observation a user turned
    from a refusal into a report, so it is the only one printed; the others
    (style, repair notes) are not. Unset or ``refuse``, an accepted change
    carries no such finding and nothing is printed. The behaviour lives in this
    function and its one call in :func:`_commit`.
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



def _name_the_writer(run: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Resolve who is writing the journal, or refuse at parse time.

    Before a config is read, a sandbox opened or a directory created, through
    the subparser's own ``error`` so the refusal reads like every other usage
    error and exits 2. The writer is the session that typed the command
    (:mod:`mcgyvr.session`): ``--orchestrator ID`` if given, else the Claude
    Code or Pi session in the environment, else a refusal whose message names
    all three. A default derived from the process is a single-orchestrator
    assumption (the lab's port-from-local-ai note, §9), so there
    is no default, only a flag and two variables to ask for.

    An id containing ``/`` is refused here too, because the id *is* the file
    name — ``DIR/<ID>.jsonl`` — and ``agent/a`` would write ``DIR/agent/a.jsonl``
    with its blobs under ``DIR/agent/blobs``, where an index over ``DIR`` finds
    neither.

    A blank id is refused here as well, at parse time and exit 2. The
    environment's session does not stand in for it: a
    caller who typed the flag was naming the writer, and an empty value is that
    caller getting the name wrong rather than declining to give one.
    """
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


def add_parser(sub: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Register `run` and `sessions`; returns the `run` subparser."""

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
        # No default. `sandbox.mode` in the config is declared as where this
        # comes from, and a flag that is never absent is a flag the config can
        # never lose to. `_run` settles the precedence: typed flag, else the
        # file, else `docker`.
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
        # No default, as for `--sandbox`: `delivery.commit` answers when no flag
        # is typed (`_settle_delivery`).
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

