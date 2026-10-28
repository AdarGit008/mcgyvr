"""The `direct` subcommand: run a contract set someone wrote, as a prompt's would run.

`mcgyvr PROMPT` has its proposer write the contracts; `mcgyvr direct FILE... |
DIR` takes them from a person or a session model. From there it is one
process with one flag set (`delegate.add_flags`): the contracts are vetted as
a proposal is (`mcgyvr.vet`), a refusal is printed with what to change and
logged, and what passed goes on one dependency tree and is run through
`_run_delegated`, the bare verb's own dispatch. No proposer is asked, so a
contract whose ladder is spent is not re-planned: its result says so, and the
author writes the next contract. `--output DIR` writes what passed vetting
and runs none of it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mcgyvr.cli.commands.delegate import (
    EPILOG,
    _Logbook,
    _meaningless,
    _report_decomposition,
    _run_delegated,
    _str_or_none,
    _write_delegated,
    add_flags,
)
from mcgyvr.cli.sandbox import _say_what_the_sandbox_leaves_out
from mcgyvr.config import (
    Config,
    ConfigError,
    ConfigMissingError,
    Ladder,
    named_config_path,
)
from mcgyvr.config import load as load_config
from mcgyvr.delegate_log import DelegateKind
from mcgyvr.exits import Exit

#: The files a contracts directory is read for, as `contract.load` reads them.
CONTRACT_SUFFIXES = (".json", ".yaml", ".yml")


def contract_paths(named: list[str]) -> list[Path] | str:
    """The contract files `named` gives, in order, or why it gives none.

    A file is taken as it is named; a directory for its `*.json`, `*.yaml`
    and `*.yml` files, sorted by name, less those whose name starts with `.`
    or `_` (a provenance note beside the contracts, say). A path that is not
    there, a directory with no contract file in it, and one file named twice
    are each a reason.
    """
    found: list[Path] = []
    for name in named:
        path = Path(name).expanduser()
        if path.is_dir():
            inside = sorted(
                p
                for p in path.iterdir()
                if p.is_file()
                and p.suffix in CONTRACT_SUFFIXES
                and not p.name.startswith((".", "_"))
            )
            if not inside:
                return (
                    f"{path} holds no contract file ({', '.join(CONTRACT_SUFFIXES)}). "
                    f"Name the files, or the directory that holds them."
                )
            found.extend(inside)
        elif path.is_file():
            found.append(path)
        else:
            return f"{path} is not there. Name a contract file, or a directory of them."
    resolved = [p.resolve() for p in found]
    twice = next((p for i, p in enumerate(resolved) if p in resolved[:i]), None)
    if twice is not None:
        return f"{twice} is named twice. Name each contract file once."
    return found


def _refuse_before_direct(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    """Refuse, through `parser` (exit 2), what `direct`'s arguments cannot do.

    The files are read into `args.paths`. A path that gives no contract file,
    a `--branch` that cannot be honoured, `--budget` (there is no prompt), and
    `--result` with more than one file are `usage_invalid`; unless `--output`
    asks for the vetted contracts alone, a session that cannot be named is
    `session_unresolved`, and on success it is resolved into `args.session`.
    Either refusal is logged to `--log` before the parser exits.
    """
    from mcgyvr.cli.commands.run import _delivery_problem, _unusable_writer

    args.run = args.output is None
    kind = DelegateKind.USAGE_INVALID
    paths = contract_paths(args.contracts)
    problem = paths if isinstance(paths, str) else None
    if problem is None:
        args.paths = paths
        problem = _delivery_problem(args) or _meaningless(
            args, "`direct`", "--budget", why="it reads no prompt"
        )
    if problem is None and args.output is not None:
        problem = _meaningless(
            args,
            "`direct --output`",
            "--result",
            "--notes-from",
            why="it runs nothing",
        )
    if problem is None and args.result is not None and len(args.paths) != 1:
        problem = (
            f"--result names one file and this set is {len(args.paths)} contracts. "
            f"Leave it off and read each result under the journal, or under "
            f"--record DIR."
        )
    if problem is None and args.run:
        kind = DelegateKind.SESSION_UNRESOLVED
        problem = _unusable_writer(args)
    if problem is None:
        return
    book = _Logbook(args.log)
    book.ended(kind, problem)
    book.write(Exit.USAGE)
    parser.error(problem)


def _direct(args: argparse.Namespace) -> int:
    """Vet and run the contracts at `args.paths`, and log how it ended.

    The work is `_direct_logged`'s; an exception nothing there names is logged
    as `internal_error` and raised on, as the bare verb does.
    """
    book = _Logbook(args.log)
    try:
        code = _direct_logged(args, book)
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


def _direct_logged(args: argparse.Namespace, book: _Logbook) -> int:
    """Vet the set, then write it (`--output`) or run it; name the end in `book`.

    The config is loaded as the bare verb loads it, but a bare install is not
    refused: no proposer is asked here, and a contract on the deterministic
    floor runs with no setup, as it always could. A setup that is named and
    does not load is an error, exit 1. The repository is attached (a local
    checkout in place, or a clone kept in `--into`), the index is built, and
    every contract is vetted (`mcgyvr.vet`). Each refusal is printed with what
    to change; when none passed it is `none_emitted`, exit 3, and nothing
    runs. With `--output` what passed is written there and nothing runs, exit
    0. Otherwise each `--notes-from` is matched to the contract its result
    names, and what passed runs where it was written, through
    `_run_delegated`, with no re-planner; the exit is the batch's.
    """
    from mcgyvr.orchestrator import AttachError, IndexBuildError, attach, build_index
    from mcgyvr.vet import vet

    chosen = Path(args.config) if args.config else None
    named = chosen if chosen is not None else named_config_path()
    config: Config | None = None
    try:
        config = load_config(chosen)
    except ConfigMissingError as exc:
        if named is not None:
            print(f"error: {exc}", file=sys.stderr)
            book.ended(DelegateKind.CONFIG_MISSING, str(exc), path=str(named))
            return 1
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        book.ended(DelegateKind.CONFIG_INVALID, str(exc), path=_str_or_none(named))
        return 1

    into = Path(args.into) if args.into else None
    try:
        with attach(args.repo, into=into) as repo:
            _say_what_the_sandbox_leaves_out(repo.root)
            index = build_index(repo.root)
            vetted = vet(args.paths, index, config=config)
            dec = vetted.decomposition
            _report_decomposition(dec, said="vetted")
            written = (
                _write_delegated(dec, Path(args.output))
                if args.output is not None and not dec.empty
                else list(vetted.paths)
            )
            book.decomposed(dec, written, said="vetted")
            if dec.empty:
                return Exit.REFUSED
            if args.output is not None:
                return 0
            seeds = _seeds(args.notes_from or [], {c.id for c in dec.contracts})
            if isinstance(seeds, str):
                print(f"error: {seeds}", file=sys.stderr)
                book.ended(DelegateKind.USAGE_INVALID, seeds)
                return Exit.USAGE
            args.seeds = seeds
            if args.result is not None:
                args.result_of = {dec.contracts[0].id: args.result}
            return _run_delegated(
                args,
                repo.root,
                dec,
                vetted.paths,
                config if config is not None else _no_setup(),
                book=book,
            )
    except AttachError as exc:
        print(f"error: {exc}", file=sys.stderr)
        book.ended(DelegateKind.REPO_ATTACH_FAILED, str(exc), repo=str(args.repo))
        return 1
    except IndexBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        book.ended(DelegateKind.REPO_INDEX_FAILED, str(exc), repo=str(args.repo))
        return 1


def _seeds(given: list[str], ids: set[str]) -> dict[str, str] | str:
    """Each `--notes-from` RESULT keyed by the contract its result names.

    The result's own `contract` names it; `_run` checks the rest. A result
    that cannot be read, one naming no contract in the set, and two naming
    one contract are each a reason, returned instead.
    """
    seeds: dict[str, str] = {}
    for result in given:
        try:
            named = json.loads(Path(result).read_text(encoding="utf-8")).get("contract")
        except (OSError, ValueError, AttributeError) as exc:
            return f"--notes-from {result}: the result cannot be read ({exc})."
        if named not in ids:
            return (
                f"--notes-from {result} is a result of {named!r}, and no contract "
                f"in this set that passed vetting has that id."
            )
        if named in seeds:
            return f"--notes-from names two results of {named!r}: give one."
        seeds[str(named)] = result
    return seeds


def _no_setup() -> Config:
    """What a batch reads when no setup is installed: nothing, so every default.

    A run on the deterministic floor needs no setup; each run settles its own
    config, so this stands in only for the batch's own reads (the journal
    directory, `dependents`, the fleet's width).
    """
    return Config(path=None, data={}, units={}, ladder=Ladder(names=()))


def add_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    """Register `direct` with the bare verb's flags, and return its parser.

    The parser is returned so the arguments it cannot honour are refused
    through its own `error` (`_refuse_before_direct`).
    """
    direct = sub.add_parser(
        "direct",
        help="vet and run contracts you wrote: files, or a directory of them",
        description=(
            "Vet each contract as a proposal is vetted, print every refusal with "
            "what to change, and run the rest in the order their dependency tree "
            "allows. The flags are `mcgyvr PROMPT`'s; no proposer is asked, so a "
            "spent contract is not re-planned."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    direct.add_argument(
        "contracts",
        nargs="+",
        metavar="FILE|DIR",
        help="contract files (YAML or JSON), or a directory of them",
    )
    add_flags(direct)
    direct.set_defaults(func=_direct)
    return direct
