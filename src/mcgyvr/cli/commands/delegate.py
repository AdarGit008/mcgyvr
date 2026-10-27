"""The `delegate` subcommand: turn a prompt and a repository into contracts.

`_delegate` loads the config the orchestrator role is bound in — a bare install,
with no setup named or found, is refused rather than failed — resolves it into a
`SourceMap`, and picks a proposer from `orchestrator.authoring`. It attaches the
repository, says once what a sandbox built from it leaves out, builds the index,
and hands the evidence to `decompose`. The contracts that come back are reported,
written as `DIR/<id>.json` or printed, and, with `--run`, run one at a time
through the machinery `run` already has, in the order their dependency tree
allows — a contract whose provider did not land is held, not run, and one
whose ladder is spent is handed back to the orchestrator to be re-planned
(`mcgyvr.replan`, up to `max_replans`), what comes back taking its place.
`add_parser` registers the subcommand and its arguments.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.config import (
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)
from mcgyvr.config import load as load_config
from mcgyvr.exits import Exit

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.board import Board, GitSource
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer
    from mcgyvr.replan import Replanner, Spent
    from mcgyvr.session import Session
    from mcgyvr.tree import Hold, Tree

from mcgyvr.cli.commands.run import _copy, _run
from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _add_repo, _named_path, add_session
from mcgyvr.cli.sandbox import _say_what_the_sandbox_leaves_out


def _delegate(args: argparse.Namespace) -> int:
    """Turn one prompt into contracts, and run them when asked to.

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
    the same checkout. The exit code is 0 when that all worked; 3
    (`Exit.REFUSED`) when there is no orchestrator role to ask; 1 when the
    config, attaching, indexing or proposing failed; and otherwise under
    `--run` the batch's, the last non-zero exit of its runs (3 for a contract
    held `blocked`). A `--run` with no session to file it under never gets
    here: the dispatcher refuses it first, exit 2. A reply that cannot be read
    as proposals is printed whole, delimited, on stderr after its error.
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
        return 1

    # `chosen` is the path `--config` names and `named` is that, or the setup
    # the environment names, so a None `named` means nothing was named here.
    # A missing setup is a bare install only when nothing named one: that is
    # refused as no orchestrator role, while any other load failure is an error.
    bare_install = isinstance(config_error, ConfigMissingError) and named is None
    if config is None and not bare_install:
        print(f"error: {config_error}", file=sys.stderr)
        return 1
    if config is None:
        print(NO_ORCHESTRATOR_ROLE, file=sys.stderr)
        return Exit.REFUSED

    pool = source_map(config)
    try:
        propose = _proposer_for_delegate(config, pool)
    except SourceUnavailableError as exc:
        print(
            f"error: the orchestrator role is declared but cannot run: {exc}. "
            f"Bind `orchestrator.unit` to a usable unit, or author contracts "
            f"yourself and run them with `mcgyvr run`.",
            file=sys.stderr,
        )
        return 1
    if propose is None:
        print(NO_ORCHESTRATOR_ROLE, file=sys.stderr)
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
            if args.run:
                return _run_delegated(
                    args,
                    repo.root,
                    decomposition,
                    written,
                    config,
                    replan=_replanner(args, repo.root, config, pool, propose),
                )
            return 0
    except AttachError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (DelegationError, RunnerError, SourceUnavailableError) as exc:
        # A delegation, runner or pool failure leaves nothing to run: report it
        # on stderr and exit 1, the same answer an attach or index failure gets.
        print(f"error: {exc}", file=sys.stderr)
        if isinstance(exc, UnreadableProposalError) and exc.reply is not None:
            _print_raw_reply(exc.reply)
        return 1


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
    classifier is built only when the strategy is "classifier", and
    `proposer_by_authoring` then puts it in front of the prose one, which stands
    in when the classifier declines. A strategy that is not a string is passed
    as None, which selects prose. None comes back when nothing can propose.
    """
    from mcgyvr.delegate import (
        classifier_proposer_for,
        proposer_by_authoring,
        proposer_for,
    )

    strategy = config.get("orchestrator.authoring")
    typed = classifier_proposer_for(pool) if strategy == "classifier" else None
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
    tree now, and the spent contract's own work is decomposed with its failure
    notes on the evidence. The prose proposer is asked, since it is the one
    that is shown the notes; `propose` stands in when no prose one is bound.
    """
    from mcgyvr.delegate import proposer_for
    from mcgyvr.orchestrator import build_index, decompose
    from mcgyvr.replan import request_for

    asked = proposer_for(pool) or propose

    def replan(spent: Spent) -> Decomposition:
        dec = decompose(
            build_index(root),
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
) -> int:
    """Run the emitted contracts through `_run`, one at a time, as the tree allows.

    Nothing runs when no contract was emitted. Documents already written to
    `--output` are run in place; when they were printed instead, they are staged
    into a temporary directory first, so either way every run reads a contract
    file. The session the runs are filed under is `args.session`, resolved from
    `--session` before the orchestrator role was asked (`_name_the_writer`).

    The contracts go on a dependency tree (`mcgyvr.tree`) read against the
    repository's committed tree, and the next one run is the first the tree
    says is ready. Each run's result settles it there: it landed when it was
    accepted with a commit HEAD now holds, the tree the next sandbox starts
    from. Under `dependents: hold`, the default, a contract whose provider did
    not land is held, and once nothing more is ready each held one gets a
    result with outcome `blocked` and no attempt spent, and exit 3. Under
    `dependents: run` every contract runs once what it waits on has come to
    anything.

    A contract whose run came to `ladder_spent` is handed to `replan` with the
    failure notes its result carries, while its `replan` round is below
    `max_replans` (`mcgyvr.replan`). The contracts that come back, each
    carrying the spent one's id and the round, are written beside the others
    and take its place on the tree, which frees what it held; the spent result
    says so under `replanned`. The last non-zero exit code is returned, not
    counting a run whose contract was re-planned, since its work goes on.
    """
    if not dec.contracts:
        return 0

    import shutil
    import tempfile

    from mcgyvr.board import Board, GitSource, tree_id_for
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.replan import SPENT
    from mcgyvr.tree import Tree

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
    tree = Tree.of(
        dec.contracts,
        source,
        tree_id=tree_id_for(str(repo), source.commit, path_of),
        hold=config.get("dependents", "hold") != "run",
    )
    board = Board(journal)
    board.attach(tree)

    codes: dict[str, int] = {}
    try:
        while ready := board.ready():
            _, contract = ready[0]
            board.start(tree.tree_id, contract.id)
            before = _results_of(journal, contract.id)
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
            codes[contract.id] = _run(run)
            source.refresh()
            settled = _settled(_results_of(journal, contract.id) - before, source)
            board.settle(tree.tree_id, contract.id, **settled)
            if (
                replan is not None
                and settled["outcome"] == SPENT
                and settled.get("result")
                and _replanned(
                    args,
                    board,
                    tree,
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
        for _, contract, hold in board.drain():
            codes[contract.id] = _write_held(args, contract, hold, session, journal)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    failed = [each for each in codes.values() if each != 0]
    return failed[-1] if failed else 0


def _replanned(
    args: argparse.Namespace,
    board: Board,
    tree: Tree,
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
        dec.contracts, spent.id, {c.id for c in tree.contracts()}
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
        board.replace(tree.tree_id, spent.id, *replacing)
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
    """The result files the journal holds for `contract_id`."""
    from mcgyvr.result import RESULTS_DIR

    return set((journal / RESULTS_DIR).glob(f"{contract_id}-*.json"))


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


def add_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    """Register the `delegate` subcommand and its arguments.

    The prompt is required; the repository defaults to `.`. `--config` names
    the setup that binds the orchestrator role doing the proposing, `--into`
    keeps a clone, `--budget` caps the deterministic read, and `--output` writes
    the contracts to a directory instead of printing them. The flags `--run`,
    `--sandbox`, `--commit`, `--branch`, `--record` and `--session` are handed
    to each run; `--orchestrator` is `--session`'s deprecated alias. The
    subcommand's `func` is `_delegate`, and the subparser is returned so a
    session that cannot be named is refused through its own `error`.
    """

    delegate = sub.add_parser(
        "delegate",
        help="turn a prompt plus a repository into validated contracts",
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
    add_session(
        delegate,
        "the session --run files its runs under, resolved before the "
        "orchestrator role is asked (default: the session that typed this "
        "command, and a refusal, exit 2, when there is none)",
    )
    delegate.set_defaults(func=_delegate)
    return delegate
