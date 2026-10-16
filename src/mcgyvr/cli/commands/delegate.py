"""The `mcgyvr delegate` command.

Only what is built is exposed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.config import (
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)
from mcgyvr.config import load as load_config
from mcgyvr.exits import Exit

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer

from mcgyvr.cli.commands.run import _run
from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _add_repo, _named_path
from mcgyvr.cli.sandbox import _say_what_the_sandbox_leaves_out


def _delegate(args: argparse.Namespace) -> int:
    """Turn a prompt plus a repository into validated contracts.

    The delegated-mode half of the product, and the first real caller of
    :func:`~mcgyvr.orchestrator.decompose.decompose`'s ``propose`` seam. This
    command attaches and indexes the repository, and ``decompose`` runs the
    rest of the deterministic pass (resolve → read) internally; this command
    also adds the one ingredient ``decompose`` does not bind itself: the
    orchestrator role, resolved through :func:`~mcgyvr.delegate.proposer_for`
    and dispatched below the pool seam by :func:`~mcgyvr.runner.dispatch_role`.

    A keyless install has no orchestrator role, and that is an ordinary,
    documented answer (:data:`~mcgyvr.delegate.NO_ORCHESTRATOR_ROLE`, exit
    ``REFUSED``) rather than a traceback. With a role bound, the emitted
    contracts are printed or written to ``--output``, and ``--run`` drives
    each of them through the existing ``run`` machinery.
    """

    from mcgyvr.config import ConfigError
    from mcgyvr.delegate import NO_ORCHESTRATOR_ROLE, DelegationError
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

    # A default location with nothing in it is the supported bare install; a
    # path somebody typed is not (the same distinction ``_run`` draws). Both
    # leave ``config`` unset, and the bare one is answered as "no orchestrator
    # role" because there is nowhere to bind one.
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
            # Before the read: the baseline below is observed in the working
            # tree, and each drafted contract runs in a sandbox of HEAD, so on
            # a dirty tree the two can disagree.
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
                return _run_delegated(args, repo.root, decomposition, written)
            return 0
    except AttachError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (DelegationError, RunnerError, SourceUnavailableError) as exc:
        # The role was bound and could not be asked, or answered unreadably —
        # a reviewer-side fault, reported, never a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _proposer_for_delegate(config: Config, pool: SourceMap) -> Proposer | None:
    """The proposer ``mcgyvr delegate`` drafts with, by ``orchestrator.authoring``.

    ``classifier`` puts the typed proposer (the jev unit, or the orchestrator
    role when none is bound) first and the prose proposer behind it; anything
    else is the prose proposer alone, as before the field existed.
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
    """One line per outcome, to stderr so stdout stays machine-readable."""
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
    """Write each emitted contract to ``output``, or print them to stdout.

    Returns the files written, so ``--run`` can drive the same documents it
    showed the caller.
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
) -> int:
    """Execute each emitted contract through the existing ``run`` machinery.

    Contracts that were only printed to stdout are staged into a temporary
    directory first; ``_run`` reads a contract from a path, and the same
    document must reach both the caller and the runner.
    """
    if not dec.contracts:
        return 0

    import shutil
    import tempfile

    from mcgyvr.session import SessionError, resolve

    paths = list(written)
    staging: Path | None = None
    if not paths:
        staging = Path(tempfile.mkdtemp(prefix="mcgyvr-delegate-"))
        for contract, document in zip(dec.contracts, dec.documents, strict=True):
            path = staging / f"{contract.id}.json"
            path.write_text(document + "\n", encoding="utf-8")
            paths.append(path)

    try:
        session = resolve(args.orchestrator)
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        return 1

    code = 0
    try:
        for path in paths:
            run = argparse.Namespace(
                contract=str(path),
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
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    return code


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `delegate` command."""

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
        help="execute each emitted contract through the existing run machinery",
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
