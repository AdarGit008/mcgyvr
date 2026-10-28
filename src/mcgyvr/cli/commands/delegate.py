"""The `delegate` subcommand: turn a prompt and a repository into contracts.

`_delegate` loads the config the orchestrator role is bound in — a bare install,
with no setup named or found, is refused rather than failed — resolves it into a
`SourceMap`, and picks a proposer from `orchestrator.authoring`. It attaches the
repository, says once what a sandbox built from it leaves out, builds the index,
and hands the evidence to `decompose`. The contracts that come back are reported,
written as `DIR/<id>.json` or printed, and, with `--run`, run through the
machinery `run` already has, in the order their dependency tree allows, up to
`--jobs` of them at once — a contract whose provider did not land is held, not
run, and one whose ladder is spent is handed back to the orchestrator to be
re-planned (`mcgyvr.replan`, up to `max_replans`), what comes back taking its
place.
With `--log PATH` how the command ended is written there as one
`mcgyvr.delegate_log` record, on every exit. `add_parser` registers the
subcommand and its arguments.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.config import (
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)
from mcgyvr.config import load as load_config
from mcgyvr.delegate_log import DelegateKind, LoggedContract, LoggedRefusal, logged
from mcgyvr.delegate_log import write as write_log
from mcgyvr.exits import Exit

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.board import Board, GitSource
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer
    from mcgyvr.replan import Replanner, Spent
    from mcgyvr.session import Session
    from mcgyvr.tree import Hold

from mcgyvr.cli.commands.run import _copy, _run
from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _add_repo, _named_path, add_session
from mcgyvr.cli.sandbox import _say_what_the_sandbox_leaves_out


class _Logbook:
    """What `--log PATH` will say: kept as the command goes, written at its end.

    Each exit path names its kind and sentence (`ended`), a decomposition its
    contracts and refusals (`decomposed`), a batch what it held (`held`); `write`
    puts the record at the path once, whatever the exit. With no `--log` it
    keeps the same facts and writes nothing.
    """

    def __init__(self, path: str | None) -> None:
        self.path = Path(path) if path else None
        self.kind = DelegateKind.INTERNAL_ERROR
        self.message = ""
        self.detail: dict[str, Any] = {}
        self.raw_reply_present = False
        self.contracts: tuple[LoggedContract, ...] = ()
        self.refusals: tuple[LoggedRefusal, ...] = ()

    def ended(self, kind: DelegateKind, message: str, **detail: Any) -> None:
        self.kind = kind
        self.message = message
        self.detail = dict(detail)

    def decomposed(self, dec: Decomposition, written: Sequence[Path]) -> None:
        """What the decomposition came to; `written` is `--output`'s paths."""
        # `--output` wrote one path per contract; printed ones have none.
        paths: list[str | None] = (
            [str(p) for p in written] if written else [None] * len(dec.contracts)
        )
        self.contracts = tuple(
            LoggedContract(c.id, c.task_type, c.target, path)
            for c, path in zip(dec.contracts, paths, strict=True)
        )
        self.refusals = tuple(
            LoggedRefusal(r.subject, r.reason, r.field, r.what_to_change)
            for r in dec.refusals
        )
        if not dec.contracts:
            self.ended(DelegateKind.NONE_EMITTED, "No contracts were emitted.")
        elif dec.refusals:
            self.ended(
                DelegateKind.EMITTED_WITH_REFUSALS,
                f"{len(dec.contracts)} contract(s) proposed, "
                f"{len(dec.refusals)} refused.",
            )
        else:
            self.ended(
                DelegateKind.EMITTED, f"{len(dec.contracts)} contract(s) proposed."
            )

    def held(self, ids: Sequence[str], tree_state: Path | None) -> None:
        """A batch held `ids`; the Board's state file says the rest."""
        self.ended(
            DelegateKind.BATCH_HELD,
            f"{len(ids)} contract(s) held and never sent: {', '.join(ids)}.",
            held=list(ids),
            tree_state=str(tree_state) if tree_state is not None else None,
        )

    def write(self, exit_code: int) -> None:
        """Write the record, if asked for; a failure is said, never raised."""
        if self.path is None:
            return
        record = logged(
            self.kind,
            self.message,
            int(exit_code),
            contracts=self.contracts,
            refusals=self.refusals,
            raw_reply_present=self.raw_reply_present,
            detail=self.detail,
        )
        try:
            write_log(self.path, record)
        except OSError as exc:
            print(
                f"error: the delegate log could not be written to {self.path}: "
                f"{exc}. The command came to {self.kind} (exit {exit_code}).",
                file=sys.stderr,
            )


def _refuse_before_delegating(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    """Refuse, through `parser` (exit 2), what the parsed arguments cannot do.

    A `--branch` that cannot be honoured is `usage_invalid`; under `--run`, a
    session that cannot be named (`_unusable_writer`, the check `run` makes) is
    `session_unresolved`, and on success it is resolved into `args.session`.
    Either refusal is logged to `--log` before the parser exits.
    """
    from mcgyvr.cli.commands.run import _delivery_problem, _unusable_writer

    kind = DelegateKind.USAGE_INVALID
    problem = _delivery_problem(args)
    if problem is None and args.run:
        kind = DelegateKind.SESSION_UNRESOLVED
        problem = _unusable_writer(args)
    if problem is None:
        return
    book = _Logbook(args.log)
    book.ended(kind, problem)
    book.write(Exit.USAGE)
    parser.error(problem)


def _delegate(args: argparse.Namespace) -> int:
    """Turn one prompt into contracts, and run them when asked to.

    The work is `_delegate_logged`'s; this keeps the `--log` record and writes
    it once the command has ended, whichever way. An exception nothing there
    names is logged as `internal_error` and raised on, so the traceback and
    exit 1 are what they were.
    """
    book = _Logbook(args.log)
    try:
        code = _delegate_logged(args, book)
    except Exception as exc:
        book.ended(
            DelegateKind.INTERNAL_ERROR,
            f"{type(exc).__name__}: {exc}",
            error_class=type(exc).__name__,
        )
        book.write(Exit.ERROR)
        raise
    book.write(code)
    return code


def _delegate_logged(args: argparse.Namespace, book: _Logbook) -> int:
    """Turn one prompt into contracts, run them when asked to, and log the end.

    The config is loaded before anything else: `--config` when it is given,
    otherwise whatever the environment names and discovery finds. A missing
    setup is a bare install only when nothing named one; a bare install has no
    orchestrator role to ask, so it is refused, while any other load failure is
    an error. The config is resolved into a `SourceMap`, and the proposer
    `orchestrator.authoring` asks for is built, so a role declared but not
    runnable is reported as a failure and a missing one as a refusal.

    `attach` yields the root every step below reads: a local checkout in place,
    a clone kept in `--into`, or a clone in a temporary directory removed when
    the block exits. The sandbox note is printed, the index is built, and
    `decompose` turns the prompt into contracts from that index, the proposer,
    the config and `--budget`. The contracts are reported and written, or
    printed when `--output` is not given, and `--run` runs each of them,
    re-planning a contract whose ladder is spent through the prose proposer on
    the same checkout. The exit code is 0 when contracts were emitted; 3
    (`Exit.REFUSED`) when there is no orchestrator role to ask or no contract
    came of the request; 1 when the config, attaching, indexing or proposing
    failed; and under `--run` the batch's, the last non-zero exit of its runs
    (3 for a contract held `blocked`). A `--run` with no session to file it
    under never gets here: `_refuse_before_delegating` refuses it first, exit
    2. A reply that cannot be read as proposals is printed whole, delimited, on
    stderr after its error. Every return names its `mcgyvr.delegate_log` kind
    in `book` first.
    """

    from mcgyvr.config import ConfigError
    from mcgyvr.delegate import (
        NO_ORCHESTRATOR_ROLE,
        DelegationError,
        UnreadableProposalError,
    )
    from mcgyvr.local_pool import SourceUnavailableError, source_map
    from mcgyvr.orchestrator import (
        AttachError,
        IndexBuildError,
        attach,
        build_index,
        decompose,
    )
    from mcgyvr.runner import RunnerError

    chosen = Path(args.config) if args.config else None
    named = chosen if chosen is not None else named_config_path()
    config: Config | None = None
    config_error: ConfigError | None = None
    try:
        config = load_config(chosen)
    except ConfigMissingError as exc:
        config_error = exc
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        book.ended(DelegateKind.CONFIG_INVALID, str(exc), path=_str_or_none(named))
        return 1

    # `chosen` is the path `--config` names and `named` is that, or the setup
    # the environment names, so a None `named` means nothing was named here.
    # A missing setup is a bare install only when nothing named one: that is
    # refused as no orchestrator role, while any other load failure is an error.
    bare_install = isinstance(config_error, ConfigMissingError) and named is None
    if config is None and not bare_install:
        print(f"error: {config_error}", file=sys.stderr)
        book.ended(
            DelegateKind.CONFIG_MISSING, str(config_error), path=_str_or_none(named)
        )
        return 1
    if config is None:
        print(NO_ORCHESTRATOR_ROLE, file=sys.stderr)
        book.ended(
            DelegateKind.CONFIG_NO_ORCHESTRATOR, NO_ORCHESTRATOR_ROLE, bare_install=True
        )
        return Exit.REFUSED

    pool = source_map(config)
    try:
        propose = _proposer_for_delegate(config, pool)
    except SourceUnavailableError as exc:
        said = (
            f"the orchestrator role is declared but cannot run: {exc}. "
            f"Bind `orchestrator.unit` to a usable unit, or author contracts "
            f"yourself and run them with `mcgyvr run`."
        )
        print(f"error: {said}", file=sys.stderr)
        book.ended(
            DelegateKind.ORCHESTRATOR_UNRUNNABLE,
            said,
            error_class=type(exc).__name__,
        )
        return 1
    if propose is None:
        print(NO_ORCHESTRATOR_ROLE, file=sys.stderr)
        book.ended(
            DelegateKind.CONFIG_NO_ORCHESTRATOR,
            NO_ORCHESTRATOR_ROLE,
            bare_install=False,
            path=_str_or_none(getattr(config, "path", None)),
        )
        return Exit.REFUSED

    into = Path(args.into) if args.into else None
    try:
        with attach(args.repo, into=into) as repo:
            # One checkout, read by every step below: a local directory in place,
            # or a clone kept in `--into` and otherwise removed with this block.
            # The sandbox note is said once, before the index and `decompose` run.
            _say_what_the_sandbox_leaves_out(repo.root)
            index = build_index(repo.root)
            decomposition = decompose(
                index,
                args.prompt,
                propose=propose,
                config=config,
                budget=args.budget,
            )
            _report_decomposition(decomposition)
            written = _write_delegated(
                decomposition, Path(args.output) if args.output else None
            )
            book.decomposed(decomposition, written)
            if decomposition.empty:
                # The request was read and nothing came of it: refused, not done.
                return Exit.REFUSED
            if args.run:
                return _run_delegated(
                    args,
                    repo.root,
                    decomposition,
                    written,
                    config,
                    replan=_replanner(args, repo.root, config, pool, propose),
                    book=book,
                )
            return 0
    except AttachError as exc:
        print(f"error: {exc}", file=sys.stderr)
        book.ended(DelegateKind.REPO_ATTACH_FAILED, str(exc), repo=str(args.repo))
        return 1
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        book.ended(DelegateKind.REPO_INDEX_FAILED, str(exc), repo=str(args.repo))
        return 1
    except (DelegationError, RunnerError, SourceUnavailableError) as exc:
        # A delegation, runner or pool failure leaves nothing to run: report it
        # on stderr and exit 1, the same answer an attach or index failure gets.
        print(f"error: {exc}", file=sys.stderr)
        if isinstance(exc, DelegationError):
            book.ended(exc.kind, str(exc), **exc.detail)
        elif isinstance(exc, RunnerError):
            book.ended(
                DelegateKind.ORCHESTRATOR_DISPATCH_FAILED,
                str(exc),
                error_class=type(exc).__name__,
            )
        else:
            book.ended(
                DelegateKind.SOURCE_UNAVAILABLE,
                str(exc),
                error_class=type(exc).__name__,
            )
        if isinstance(exc, UnreadableProposalError) and exc.reply is not None:
            _print_raw_reply(exc.reply)
            book.raw_reply_present = True
            book.detail["raw_reply_chars"] = len(exc.reply)
        return 1


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _print_raw_reply(reply: str) -> None:
    """Print the orchestrator's unreadable reply, whole and delimited, on stderr.

    Nothing else keeps it — no journal is open before the contracts exist — so
    a caller capturing only the command's output still has the reply to read.
    The lines between the two markers are the reply verbatim, plus a closing
    newline when it lacks one.
    """
    print(f"--- the orchestrator's raw reply ({len(reply)} chars) ---", file=sys.stderr)
    print(reply, end="" if reply.endswith("\n") else "\n", file=sys.stderr)
    print("--- end of the orchestrator's raw reply ---", file=sys.stderr)


def _proposer_for_delegate(config: Config, pool: SourceMap) -> Proposer | None:
    """The proposer `orchestrator.authoring` asks for, or None if none can run.

    The prose proposer on the `orchestrator` role is always built. The typed
    classifier is built only when the strategy is "classifier" — refined until
    each proposal is on one file and jev says it cannot be split further, within
    `max_refine_depth` and `max_refine_fanout` — and `proposer_by_authoring`
    then puts it in front of the prose one, which stands in when the classifier
    declines. A strategy that is not a string is passed as None, which selects
    prose. None comes back when nothing can propose.
    """
    from mcgyvr import refine
    from mcgyvr.delegate import (
        proposer_by_authoring,
        proposer_for,
        refining_proposer_for,
    )

    strategy = config.get("orchestrator.authoring")
    typed = (
        refining_proposer_for(
            pool,
            max_depth=refine.max_depth(config),
            max_fanout=refine.max_fanout(config),
        )
        if strategy == "classifier"
        else None
    )
    return proposer_by_authoring(
        None if not isinstance(strategy, str) else strategy,
        typed=typed,
        prose=proposer_for(pool),
    )


def _replanner(
    args: argparse.Namespace,
    root: Path,
    config: Config,
    pool: SourceMap,
    propose: Proposer,
) -> Replanner:
    """What re-plans a spent contract: the orchestrator, asked again on `root`.

    The index is built again, since what landed before the spend is in the
    tree now — under `--jobs`, between two deliveries of the runs beside it —
    and the spent contract's own work is decomposed with its failure notes on
    the evidence. The prose proposer is asked, since it is the one
    that is shown the notes; `propose` stands in when no prose one is bound.
    """
    from contextlib import nullcontext

    from mcgyvr.delegate import proposer_for
    from mcgyvr.deliver import between_deliveries
    from mcgyvr.orchestrator import build_index, decompose
    from mcgyvr.replan import request_for

    asked = proposer_for(pool) or propose
    # With other runs delivering beside it (`--jobs`), the tree is read
    # between two deliveries, never in the middle of one.
    beside = getattr(args, "jobs", 1) != 1

    def replan(spent: Spent) -> Decomposition:
        with between_deliveries(root) if beside else nullcontext():
            index = build_index(root)
        dec = decompose(
            index,
            request_for(spent.contract),
            propose=asked,
            config=config,
            budget=args.budget,
            spent=spent,
        )
        _report_decomposition(dec)
        return dec

    return replan


def _report_decomposition(dec: Decomposition) -> None:
    """Report what one decomposition produced, on stderr.

    The contract count and one `id  [task_type] target` line per contract, or
    "No contracts were emitted." when there are none, then a `refused:` line for
    each refusal, since a decomposition can hold both.
    """
    if dec.contracts:
        print(f"{len(dec.contracts)} contract(s) proposed:", file=sys.stderr)
        for contract in dec.contracts:
            print(
                f"  {contract.id}  [{contract.task_type}] {contract.target}",
                file=sys.stderr,
            )
    else:
        print("No contracts were emitted.", file=sys.stderr)
    for refusal in dec.refusals:
        print(f"  refused: {refusal}", file=sys.stderr)


def _write_delegated(dec: Decomposition, output: Path | None) -> list[Path]:
    """Write each emitted document, or print them when no directory is given.

    With no `--output` the documents go to stdout and nothing is written, so the
    returned list is empty. Otherwise the directory is created, each contract's
    document is written beside it as `<id>.json`, each path is reported on
    stderr, and the paths written come back in the proposer's order.
    """
    if output is None:
        for document in dec.documents:
            print(document)
        return []
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for contract, document in zip(dec.contracts, dec.documents, strict=True):
        path = output / f"{contract.id}.json"
        path.write_text(document + "\n", encoding="utf-8")
        written.append(path)
        print(f"wrote {path}", file=sys.stderr)
    return written


def _run_delegated(
    args: argparse.Namespace,
    repo: Path,
    dec: Decomposition,
    written: Sequence[Path],
    config: Config,
    *,
    replan: Replanner | None = None,
    book: _Logbook | None = None,
) -> int:
    """Run the emitted contracts through `_run`, `--jobs` at once, as the tree allows.

    Nothing runs when no contract was emitted. Documents already written to
    `--output` are run in place; when they were printed instead, they are staged
    into a temporary directory first, so either way every run reads a contract
    file. The session the runs are filed under is `args.session`, resolved from
    `--session` before the orchestrator role was asked (`_name_the_writer`).

    The contracts go on the repository's live dependency tree (`mcgyvr.tree`,
    `Board.live`) read against its committed tree: a fresh one, or the one
    another batch on the repository still has contracts in flight on, which
    they join, their edges read against every contract there. What runs next
    is what the tree says is ready of this batch's own, first ready first. A
    contract another batch already has in flight is left to it and waited on,
    never run twice, and counts in the exit as it ended there. When nothing
    of this batch's is ready but one of its contracts waits on another
    batch's work in flight, the batch waits for that batch's next write
    rather than seal it. A contract left in flight by
    a batch that is gone is freed from its result (`_came_to`), or as
    `abandoned`. Each run's result settles it there as soon as
    the run ends: it landed when it was accepted with a commit HEAD now holds,
    the tree the next sandbox starts from. Under `dependents: hold`, the
    default, a contract whose provider did not land is held, and once nothing
    more is ready each held one gets a result with outcome `blocked` and no
    attempt spent, and exit 3. Under `dependents: run` every contract runs once
    what it waits on has come to anything.

    `--jobs` is how many run at once (`_width`): 1, the default, runs each on
    this thread in turn; more run on threads (`capacity.run_eager`), the tree
    asked again after every settle, so a dependent starts as soon as what it
    waits on has settled. Two whose scopes can write one file never run at
    once (`Scope.meets`), so the second starts from what the first landed, as
    it would one at a time; the delivery lock (`mcgyvr.deliver`) is the net
    under that. Beside others, a run's output is held and written whole when
    it ends (`mcgyvr.cli.streams`). The tree, the board and the source are
    read and changed on this thread only, under the repository's delivery
    lock, which serialises them with every other batch on it.

    A contract whose run came to `ladder_spent` is handed to `replan` with the
    failure notes its result carries, while its `replan` round is below
    `max_replans` (`mcgyvr.replan`). The contracts that come back, each
    carrying the spent one's id and the round, are written beside the others
    and take its place on the tree, which frees what it held; the spent result
    says so under `replanned`. The last non-zero exit code, in the order the
    runs ended, is returned, not counting a run whose contract was re-planned,
    since its work goes on. When anything was held, `book` is told which and
    where the tree's state file is (`batch_held`). A run that raises stops the
    batch: nothing more is started, the runs beside it are waited for and
    settled, and the error is raised.
    """
    if not dec.contracts:
        return 0

    import shutil
    import tempfile
    from contextlib import nullcontext

    from mcgyvr.board import Board, GitSource
    from mcgyvr.capacity import run_eager
    from mcgyvr.cli import streams
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.replan import SPENT
    from mcgyvr.tree import State

    paths = list(written)
    staging: Path | None = None
    if not paths:
        staging = Path(tempfile.mkdtemp(prefix="mcgyvr-delegate-"))
        for contract, document in zip(dec.contracts, dec.documents, strict=True):
            path = staging / f"{contract.id}.json"
            path.write_text(document + "\n", encoding="utf-8")
            paths.append(path)
    path_of = {c.id: p for c, p in zip(dec.contracts, paths, strict=True)}
    # Where a re-planned contract is written: beside the batch's own.
    folder = staging if staging is not None else paths[0].parent

    session: Session = args.session
    journal = Path(config.get("journal.dir") or JOURNAL_DIR_DEFAULT).expanduser()
    source = GitSource(repo)

    def came_to(contract_id: str, started: str) -> dict[str, Any] | None:
        return _came_to(journal, contract_id, started, source)

    board = Board.live(journal, repo, found=came_to)
    width = _batch_width(getattr(args, "jobs", 1), config)

    codes: dict[str, int] = {}
    running: dict[str, Contract] = {}
    before: dict[str, set[Path]] = {}
    # Handed out by `ready` but no longer ready when `start` asked the tree
    # again (another batch changed it between): never run, never settled.
    skipped: set[str] = set()
    # Runs started and not yet returned, on whatever thread.
    flying: set[str] = set()

    def ready() -> list[Contract]:
        # What the tree says is ready, less one that could write a file a
        # running one, or one taken before it here, could write too.
        taken: list[Contract] = []
        for _, contract in board.ready():
            beside = (*running.values(), *taken)
            if not any(contract.scope.meets(other.scope) for other in beside):
                taken.append(contract)
        return taken

    def start(contract: Contract) -> Callable[[], int]:
        if not board.start(tree_id, contract.id):
            skipped.add(contract.id)
            return lambda: 0
        before[contract.id] = _results_of(journal, contract.id)
        running[contract.id] = contract
        run = argparse.Namespace(
            contract=str(path_of[contract.id]),
            config=args.config,
            repo=str(repo),
            sandbox=args.sandbox,
            commit=args.commit,
            branch=args.branch,
            record=args.record,
            result=None,
            session_id=args.session_id,
            session=session,
            in_batch=True,
        )
        if width > 1:
            run.beside_others = True
        job = _run if width == 1 else _held

        # In flight from now on: a job cancelled before it ran stays counted,
        # so the lease is kept for the process's life rather than dropped early.
        flying.add(contract.id)

        def tracked() -> int:
            try:
                return job(run)
            finally:
                flying.discard(contract.id)

        return tracked

    def came(contract: Contract, code: int) -> dict[str, Any]:
        del running[contract.id]
        codes[contract.id] = code
        source.refresh()
        return _settled(
            _results_of(journal, contract.id) - before.pop(contract.id), source
        )

    def settle(contract: Contract, code: int) -> None:
        if contract.id in skipped:
            skipped.discard(contract.id)
            return
        settled = came(contract, code)
        # A spent contract is re-planned before it is settled, so the tree
        # every batch reads never shows it failed while what replaces it is
        # still being asked for.
        if (
            replan is not None
            and settled["outcome"] == SPENT
            and settled.get("result")
            and _replanned(
                args,
                board,
                tree_id,
                contract,
                Path(settled["result"]),
                replan,
                config,
                folder,
                path_of,
            )
        ):
            # The work goes on under what replaced it, so this run's exit
            # is not the batch's.
            del codes[contract.id]
            return
        board.settle(tree_id, contract.id, **settled)

    def abandon(contract: Contract, code: int) -> None:
        # The batch is stopping: what ended beside the failure is put on the
        # tree as it came, and nothing is re-planned.
        if contract.id in skipped:
            skipped.discard(contract.id)
            return
        board.settle(tree_id, contract.id, **came(contract, code))

    try:
        tree_id = board.join(
            dec.contracts, source, hold=config.get("dependents", "hold") != "run"
        )
        for each in board.left:
            print(
                f"note: {each} is in flight in another batch on this repository; "
                f"this batch waits on it rather than run it twice.",
                file=sys.stderr,
            )
        with streams.routed() if width > 1 else nullcontext():
            while True:
                run_eager(
                    ready,
                    start,
                    settle,
                    workers=width,
                    abandon=abandon,
                    stopping=_say_stopping,
                )
                seen = board.generation()
                if board.ready():
                    continue
                if not board.waiting():
                    break
                board.wait(seen)
        held: list[str] = []
        for _, contract, hold in board.drain():
            codes[contract.id] = _write_held(args, contract, hold, session, journal)
            held.append(contract.id)
        if held and book is not None:
            book.held(held, board.state_file(tree_id))
        for each in board.left:
            # Left to another batch and waited for: what it came to there is
            # this batch's too.
            ended = board.state(tree_id, each)
            if ended is State.FAILED:
                codes[each] = int(Exit.ERROR)
            elif ended is State.DEAD:
                codes[each] = int(Exit.REFUSED)
    finally:
        # A run still going on a worker (a second interrupt left it) keeps the
        # lease, so nothing frees what it may yet deliver; the kernel drops
        # the lease when the process ends.
        if not flying:
            board.leave()
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    failed = [each for each in codes.values() if each != 0]
    return failed[-1] if failed else 0


def _say_stopping(in_flight: int) -> None:
    """Say that the batch stopped and waits for the runs it cannot stop."""
    if in_flight:
        print(
            f"note: the batch stopped; nothing more is started, and it waits for "
            f"the {in_flight} contract(s) in flight to end.",
            file=sys.stderr,
        )


def _held(run: argparse.Namespace) -> int:
    """`_run` on a worker, its output held and written whole when it ends."""
    from mcgyvr.cli import streams

    with streams.held():
        return _run(run)


def _batch_width(asked: int, config: Config) -> int:
    """How many contracts the batch runs at once: `--jobs`, capped at the fleet.

    1 is answered without reading the fleet, so `--jobs 1` is the loop it
    always was. Otherwise the fleet's total slots are read (`_fleet_width`),
    and a cap is said.
    """
    if asked == 1:
        return 1
    fleet = _fleet_width(config)
    width = _width(asked, fleet)
    if asked > width:
        print(
            f"note: --jobs {asked} is capped at the fleet's {fleet} slots."
            if fleet >= 1
            else f"note: the fleet declares no slots, so --jobs {asked} runs "
            f"one contract at a time.",
            file=sys.stderr,
        )
    return width


def _width(asked: int, fleet: int) -> int:
    """`asked` contracts at once (0 is all the fleet's slots), never more than
    the fleet's `fleet` slots and never fewer than one."""
    cap = max(fleet, 1)
    return cap if asked == 0 else min(asked, cap)


def _fleet_width(config: Config) -> int:
    """The fleet's total slots: the most dispatches its units take at once.

    `Capacity.total`, from the widths the config declares. A fleet whose
    width cannot be read is said, and counts as one slot.
    """
    from mcgyvr.capacity import Capacity, CapacityError

    try:
        return Capacity.of(config).total
    except CapacityError as exc:
        print(
            f"note: the fleet's width could not be read ({exc}); --jobs runs "
            f"one contract at a time.",
            file=sys.stderr,
        )
        return 1


def _jobs(text: str) -> int:
    """`--jobs`: a count of contracts, or `auto` (0), all the fleet's slots."""
    if text.strip().lower() == "auto":
        return 0
    try:
        jobs = int(text)
    except ValueError:
        jobs = -1
    if jobs < 0:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a count: give a whole number, 0 or `auto` for "
            f"the fleet's total slots"
        )
    return jobs


def _replanned(
    args: argparse.Namespace,
    board: Board,
    tree_id: str,
    spent: Contract,
    result: Path,
    replan: Replanner,
    config: Config,
    folder: Path,
    path_of: dict[str, Path],
) -> bool:
    """Re-plan a contract whose ladder is spent; whether anything took its place.

    Nothing is asked when `max_replans` is 0, and the result is left as it is.
    Past the bound, a re-plan that could not be had, and one that proposed
    nothing the batch does not already hold are each said on the spent result's
    `replanned`, and the tree keeps holding what waited on it. Otherwise the
    new contracts carry the lineage, are written into `folder`, take the spent
    one's place on the tree, and the result names them.
    """
    import json

    from mcgyvr.contract import dumps
    from mcgyvr.delegate import DelegationError
    from mcgyvr.local_pool import SourceUnavailableError
    from mcgyvr.orchestrator import IndexBuildError
    from mcgyvr.replan import Spent, failures_of, max_replans, next_round, stamped
    from mcgyvr.runner import RunnerError

    bound = max_replans(config)
    if bound <= 0:
        return False
    try:
        doc = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(
            f"error: {spent.id} is not re-planned: its result {result} could not "
            f"be read ({exc})",
            file=sys.stderr,
        )
        return False
    round_ = next_round(spent, bound)
    if round_ is None:
        _say_replanned(
            args,
            result,
            doc,
            spent.replan.round,
            bound,
            (),
            f"not re-planned: it is already re-plan round {spent.replan.round} "
            f"of max_replans {bound}.",
        )
        return False
    try:
        dec = replan(Spent(contract=spent, failures=failures_of(doc)))
    except (
        DelegationError,
        RunnerError,
        SourceUnavailableError,
        IndexBuildError,
    ) as exc:
        _say_replanned(
            args, result, doc, round_, bound, (), f"the re-plan failed: {exc}."
        )
        return False
    fresh = _runnable_replacements(
        dec.contracts, spent.id, {c.id for c in board.tree(tree_id).contracts()}
    )
    if not fresh:
        refused = "; ".join(str(r) for r in dec.refusals)
        _say_replanned(
            args,
            result,
            doc,
            round_,
            bound,
            (),
            "the re-plan proposed nothing new"
            + (f" (refused: {refused})" if refused else "")
            + ", so what waited on it stays held.",
        )
        return False
    replacing = stamped(fresh, spent, round_)
    try:
        for contract in replacing:
            path = folder / f"{contract.id}.json"
            path.write_text(dumps(contract) + "\n", encoding="utf-8")
            path_of[contract.id] = path
        board.replace(tree_id, spent.id, *replacing)
    except (OSError, ValueError) as exc:
        _say_replanned(
            args,
            result,
            doc,
            round_,
            bound,
            (),
            f"the re-plan could not be put in its place: {exc}.",
        )
        return False
    ids = tuple(c.id for c in replacing)
    _say_replanned(
        args,
        result,
        doc,
        round_,
        bound,
        ids,
        f"re-planned (round {round_} of max_replans {bound}) as "
        f"{', '.join(ids)}, which take its place in the batch.",
    )
    return True


def _runnable_replacements(
    proposed: Sequence[Contract], spent: str, tree: set[str]
) -> list[Contract]:
    """The proposed contracts that are new and could run, in their order.

    One the batch already holds (the spent contract proposed again unchanged,
    or a sibling already there) is not new. One that waits on an id neither
    the tree nor the other replacements will hold — the spent contract, or a
    replacement dropped here — could never start, so it is dropped too, until
    what is left waits only on what will be there.
    """
    kept = [c for c in proposed if c.id not in tree and c.id != spent]
    while True:
        there = (tree - {spent}) | {c.id for c in kept}
        runnable = [c for c in kept if all(w in there for w in c.depends_on)]
        if len(runnable) == len(kept):
            return kept
        kept = runnable


def _say_replanned(
    args: argparse.Namespace,
    result: Path,
    doc: dict[str, Any],
    round_: int,
    bound: int,
    contracts: Sequence[str],
    said: str,
) -> None:
    """Put what became of a spent contract on its result, and say it.

    The result under the journal is amended, and its `--record` copy when that
    is there; a copy that cannot be amended is said and does not stop the batch.
    """
    from mcgyvr.result import RESULTS_DIR, amend

    detail = str(doc.get("detail") or "")
    changes = {
        "detail": f"{detail} {said}".strip(),
        "replanned": {
            "round": round_,
            "max_replans": bound,
            "contracts": list(contracts),
            "detail": said,
        },
    }
    print(f"{doc.get('contract') or result.stem}: {said}", file=sys.stderr)
    try:
        amend(result, changes)
    except (OSError, ValueError) as exc:
        print(
            f"error: the result {result} could not be amended with that: {exc}",
            file=sys.stderr,
        )
        return
    if args.record is None:
        return
    copy = Path(args.record).expanduser() / RESULTS_DIR / result.name
    if copy.resolve() == result.resolve() or not copy.exists():
        return
    try:
        amend(copy, changes)
    except (OSError, ValueError) as exc:
        print(
            f"error: the copy of this result in {copy} could not be amended: "
            f"{exc}. It is amended at {result}.",
            file=sys.stderr,
        )


def _results_of(journal: Path, contract_id: str) -> set[Path]:
    """The result files the journal holds for `contract_id`.

    `<id>-<stamp>.json` with a run stamp after the id, so the result of a
    contract whose id merely starts with `<id>-`, run beside this one, is not
    taken for this one's.
    """
    from mcgyvr.result import RESULTS_DIR

    return {
        path
        for path in (journal / RESULTS_DIR).glob(f"{contract_id}-*.json")
        if _STAMPED.fullmatch(path.name[len(contract_id) + 1 :])
    }


#: What follows `<id>-` in a result file's name: a run stamp (`run_stamp`).
_STAMPED = re.compile(r"\d{8}T\d{6}\.\d{6}Z\.json")


def _came_to(
    journal: Path, contract_id: str, started: str, source: GitSource
) -> dict[str, Any] | None:
    """What a contract left in flight by a batch that is gone came to: read
    from a result its run wrote at or after `started`, as `_settled` reads
    one; None when it wrote none."""
    stamp = len(contract_id) + 1
    new = {
        path
        for path in _results_of(journal, contract_id)
        if path.name[stamp:] >= started
    }
    if not new:
        return None
    source.refresh()
    return _settled(new, source)


def _settled(new: set[Path], source: GitSource) -> dict[str, Any]:
    """What a run came to, for the tree, from the result file it wrote.

    The newest of `new` is the run's own, named by its stamp. A run that wrote
    none came to `error`. It landed when it was accepted with a commit the
    source — HEAD, the tree the next sandbox starts from — holds.
    """
    import json

    if not new:
        return {"outcome": "error", "landed": False, "detail": "no result written"}
    path = max(new, key=lambda p: p.name)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"outcome": "error", "landed": False, "detail": str(exc)}
    outcome = str(doc.get("outcome") or "error")
    commit = str(doc.get("commit") or "")
    landed = (
        outcome == "accepted" and bool(doc.get("committed")) and source.holds(commit)
    )
    detail = ""
    if outcome == "accepted" and not landed:
        detail = (
            "committed onto a branch the next sandbox does not start from"
            if commit
            else "left uncommitted, and a sandbox holds only the committed tree; "
            "pass --commit"
        )
    return {"outcome": outcome, "landed": landed, "detail": detail, "result": str(path)}


def _write_held(
    args: argparse.Namespace,
    contract: Contract,
    hold: Hold,
    session: Session,
    journal: Path,
) -> int:
    """Write the result of a contract the tree held, and say so; return its exit."""
    from mcgyvr.board import held_result
    from mcgyvr.result import result_path, run_stamp, write

    stamp = run_stamp()
    report = held_result(
        contract,
        hold,
        session=session.name,
        run=stamp,
        journal=str(journal),
        session_file=str(session.session_file) if session.session_file else None,
    )
    print(f"{contract.id}: {report.detail}", file=sys.stderr)
    written = write(result_path(journal, contract.id, stamp), report)
    if args.record is not None:
        mirror = Path(args.record).expanduser()
        if mirror.resolve() != journal.resolve():
            try:
                _copy(written, result_path(mirror, contract.id, stamp))
            except OSError as exc:
                print(
                    f"error: this held contract's result could not be copied into "
                    f"{mirror}: {exc}. It is at {written}.",
                    file=sys.stderr,
                )
    return int(report.exit_code or 0)


#: The `delegate --help` epilog: the exit codes and the `--log` kinds behind them.
DELEGATE_EPILOG = """\
exit codes (the --log record's `kind` in brackets):
  0  contracts emitted [emitted, emitted_with_refusals]; under --run, the
     batch's: the last non-zero exit of its runs, in the order they ended
  1  a failure: the config [config_invalid, config_missing], the orchestrator
     role or its reply [orchestrator_*, source_unavailable, reply_*,
     proposal_*], the repository [repo_*], or a crash [internal_error]
  2  usage: a --branch that cannot be honoured [usage_invalid], or --run with
     no session to file the runs under [session_unresolved]
  3  refused: no orchestrator role [config_no_orchestrator], no contract came
     of the request [none_emitted], or --run held a contract [batch_held]
New kinds may be added under mcgyvr.delegate_log/1; a reader tolerates one it
does not know."""


def add_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    """Register the `delegate` subcommand and its arguments.

    The prompt is required; the repository defaults to `.`. `--config` names
    the setup that binds the orchestrator role doing the proposing, `--into`
    keeps a clone, `--budget` caps the deterministic read, and `--output` writes
    the contracts to a directory instead of printing them; `--log` writes how
    the command ended as a `mcgyvr.delegate_log` record, and the epilog lists
    the exit codes with the record's kinds. `--jobs` is how many contracts
    `--run` runs at once. The flags `--run`, `--sandbox`,
    `--commit`, `--branch`, `--record` and `--session` are handed to each run;
    `--orchestrator` is `--session`'s deprecated alias. The
    subcommand's `func` is `_delegate`, and the subparser is returned so a
    session that cannot be named is refused through its own `error`.
    """

    delegate = sub.add_parser(
        "delegate",
        help="turn a prompt plus a repository into validated contracts",
        epilog=DELEGATE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    delegate.add_argument(
        "prompt",
        help="the natural-language request to decompose into contracts",
    )
    _add_repo(
        delegate,
        "the repository to work against: a local git checkout, or a URL to "
        "clone (https/git/file)",
    )
    delegate.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=(
            "config that binds the orchestrator role, which delegates the "
            f"prompt to (default: {CONFIG_DEFAULT_HELP})"
        ),
    )
    delegate.add_argument(
        "--into",
        default=None,
        metavar="DIR",
        help="clone a URL repo into DIR and keep it, instead of a temp dir",
    )
    delegate.add_argument(
        "--budget",
        type=int,
        default=None,
        metavar="TOKENS",
        help=(
            "cap the deterministic read at TOKENS estimated tokens before the "
            "orchestrator is asked (default: the decompose default)"
        ),
    )
    delegate.add_argument(
        "--output",
        default=None,
        metavar="DIR",
        help=(
            "write each emitted contract to DIR/<id>.json instead of printing "
            "them to stdout"
        ),
    )
    delegate.add_argument(
        "--run",
        action="store_true",
        help=(
            "execute each emitted contract through the existing run machinery, "
            "holding one whose provider did not land (see `dependents`)"
        ),
    )
    delegate.add_argument(
        "--jobs",
        default=1,
        type=_jobs,
        metavar="N",
        help=(
            "with --run, run up to N ready contracts at once, each settled as "
            "it ends and the next started as soon as it is ready (default: 1, "
            "one at a time). N is capped at the fleet's total slots, the most "
            "dispatches its units take at once; `auto` or 0 is that cap. Two "
            "contracts whose scopes can write one file never run at once, and "
            "a run's output is written whole when it ends. Runs beside each "
            "other share the fleet's slots, so one may wait for a rung, or "
            "pass a busy one by, as two runs typed in two terminals would"
        ),
    )
    delegate.add_argument(
        "--sandbox",
        default=None,
        choices=("docker", "tempdir"),
        help="sandbox mode for --run; default is `sandbox.mode`, then `docker`",
    )
    delegate.add_argument(
        "--commit",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "commit each accepted change, or not (--no-commit), whatever "
            "`delivery.commit` says (with --run)"
        ),
    )
    delegate.add_argument(
        "--branch",
        default=None,
        metavar="NAME",
        help="commit each accepted change onto branch NAME; implies --commit",
    )
    delegate.add_argument(
        "--record",
        default=None,
        type=_named_path,
        metavar="DIR",
        help="also journal each --run under DIR, as a complete second copy",
    )
    delegate.add_argument(
        "--log",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=(
            "write how this command ended to PATH as one JSON record "
            "(mcgyvr.delegate_log/1, schema in mcgyvr.delegate_log), on every "
            "exit once the arguments are read, a crash included: its `kind`, "
            "the exit code, the contracts and refusals, and the facts behind a "
            "failure. For a script that called delegate; stderr is unchanged"
        ),
    )
    add_session(
        delegate,
        "the session --run files its runs under, resolved before the "
        "orchestrator role is asked (default: the session that typed this "
        "command, and a refusal, exit 2, when there is none)",
    )
    delegate.set_defaults(func=_delegate)
    return delegate
