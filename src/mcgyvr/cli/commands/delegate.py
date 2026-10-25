"""The `delegate` subcommand: turn a prompt and a repository into contracts.

`_delegate` loads the config the orchestrator role is bound in — a bare install,
with no setup named or found, is refused rather than failed — resolves it into a
`SourceMap`, and picks a proposer from `orchestrator.authoring`. It attaches the
repository, says once what a sandbox built from it leaves out, builds the index,
and hands the evidence to `decompose`. The contracts that come back are reported,
written as `DIR/<id>.json` or printed, and, with `--run`, run one at a time
through the machinery `run` already has, in the order their dependency tree
allows — a contract whose provider did not land is held, not run. `add_parser`
registers the subcommand and its arguments.
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
    from mcgyvr.board import GitSource
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer
    from mcgyvr.session import Session
    from mcgyvr.tree import Hold

from mcgyvr.cli.commands.run import _copy, _run
from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _add_repo, _named_path
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
    printed when `--output` is not given, and `--run` runs each of them. The
    exit code is 0 when that all worked and 1 when attaching, indexing,
    proposing or running did not. A reply that cannot be read as proposals is
    printed whole, delimited, on stderr after its error.
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
                return _run_delegated(args, repo.root, decomposition, written, config)
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
) -> int:
    """Run the emitted contracts through `_run`, one at a time, as the tree allows.

    Nothing runs when no contract was emitted. Documents already written to
    `--output` are run in place; when they were printed instead, they are staged
    into a temporary directory first, so either way every run reads a contract
    file. The session is resolved from `--orchestrator`, and a failure to resolve
    it removes the staging and returns 1.

    The contracts go on a dependency tree (`mcgyvr.tree`) read against the
    repository's committed tree, and the next one run is the first the tree
    says is ready. Each run's result settles it there: it landed when it was
    accepted with a commit HEAD now holds, the tree the next sandbox starts
    from. Under `dependents: hold`, the default, a contract whose provider did
    not land is held, and once nothing more is ready each held one gets a
    result with outcome `blocked` and no attempt spent, and exit 3. Under
    `dependents: run` every contract runs once what it waits on has come to
    anything. The last non-zero exit code is returned.
    """
    if not dec.contracts:
        return 0

    import shutil
    import tempfile

    from mcgyvr.board import Board, GitSource, tree_id_for
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.session import SessionError, resolve
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

    try:
        session = resolve(args.orchestrator)
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        return 1

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

    code = 0
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
                orchestrator=args.orchestrator,
                session=session,
            )
            result = _run(run)
            if result != 0:
                code = result
            source.refresh()
            board.settle(
                tree.tree_id,
                contract.id,
                **_settled(_results_of(journal, contract.id) - before, source),
            )
        for _, contract, hold in board.drain():
            code = _write_held(args, contract, hold, session, journal)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    return code


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
        orchestrator=session.orchestrator,
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
    print(f"result: {written}")
    return int(report.exit_code or 0)


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `delegate` subcommand and its arguments.

    The prompt and the repository are required. `--config` names the setup that
    binds the orchestrator role doing the proposing, `--into` keeps a clone,
    `--budget` caps the deterministic read, and `--output` writes the contracts
    to a directory instead of printing them. The flags `--run`, `--sandbox`,
    `--commit`, `--branch`, `--record` and `--orchestrator` are handed to each
    run. The subcommand's `func` is `_delegate`.
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
    delegate.add_argument(
        "--orchestrator",
        default=None,
        metavar="ID",
        help="who writes the journal for --run (default: the session)",
    )
    delegate.set_defaults(func=_delegate)
