"""The option and argument pieces the `mcgyvr` verbs spell the same way.

Two things are named on most command lines: the setup to read, with `--config`,
and the repository to work on, with `--repo`. The helpers here attach those
options to a subparser and carry the types and actions behind them, including
the refusals the shapes leave room for: a blank path, a repository written as a
positional, and two different setups named on one command line. The constants
carry the default each option's help text states.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.config import (
    CONFIG_PATH_ENV,
)
from mcgyvr.fleet.roots import (
    FLEETS_SHOWN,
    LIVE_FILE_SHOWN,
    STAGING_SHOWN,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


CONFIG_DEFAULT_HELP = (
    f"${CONFIG_PATH_ENV}, else the live fleet folder under {FLEETS_SHOWN} that "
    f"{LIVE_FILE_SHOWN} names — a directory holding fleet.yaml and policy.yaml"
)


INIT_DEFAULT_HELP = (
    f"${CONFIG_PATH_ENV}, else a folder of the run's own, {STAGING_SHOWN} — "
    f"never the working directory, and never a live fleet folder, which is "
    f"written only when setup promotes a fleet it locked"
)


SETUP_DOC = "skills/mcgyvr/SETUP.md"


def _mib(size_bytes: int) -> str:
    return f"{size_bytes / 1024 / 1024:.1f} MiB"


def _named_path(value: str) -> str:
    """The type of a path argument, refusing a blank one and passing the rest.

    A blank value is what an unset environment variable leaves behind, so it is
    told apart from a path the user meant: the help tells them to pass a path,
    or to leave the argument off and take the default on purpose. The value is
    returned as typed; whoever loads it expands and resolves it.
    """
    if not value.strip():
        raise argparse.ArgumentTypeError(
            "a blank value is not a path. It is what an unset variable leaves "
            "behind. Pass a path, or leave the argument off to take the default "
            "on purpose."
        )
    return value


class _RepoByPosition(argparse.Action):
    """Refuse a repository named by position, and say to name it with `--repo`.

    `_add_repo` registers this as a hidden optional positional, so a bare path
    lands here instead of on argparse's unrecognised-argument error and the
    message can show how the repository is spelled.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        raise argparse.ArgumentError(
            None,
            f"the repository is named with --repo, not by position: --repo {values}",
        )


def _add_repo(parser: argparse.ArgumentParser, what: str) -> None:
    """Attach `--repo` to `parser`, with `what` completing the help sentence.

    The repository defaults to the working directory and must be a named path.
    The hidden positional carrying `_RepoByPosition` is added alongside it so
    the same repository written without the option is refused by name.
    """
    parser.add_argument(
        "--repo",
        default=".",
        type=_named_path,
        metavar="PATH",
        help=f"{what} (default: .)",
    )
    parser.add_argument(
        "_repo_by_position",
        nargs="?",
        default=argparse.SUPPRESS,
        action=_RepoByPosition,
        help=argparse.SUPPRESS,
    )


def add_config(
    parser: argparse.ArgumentParser,
    *,
    dest: str = "config",
    what: str = "config to read",
) -> None:
    """Attach `--config` to `parser`, storing the named setup under `dest`.

    The help's parenthetical default is `CONFIG_DEFAULT_HELP`, the environment
    variable and then the live fleet folder. The default is `SUPPRESS`, so a
    verb reading `getattr(args, dest, None)` can tell a setup it was given from
    one it must look up. `what` completes the help sentence, and `_OneSetup`
    makes a setup named more than once on the command line have to be the same
    one.
    """
    parser.add_argument(
        "--config",
        dest=dest,
        default=argparse.SUPPRESS,
        type=_named_path,
        metavar="PATH",
        action=_OneSetup,
        help=f"{what} (default: {CONFIG_DEFAULT_HELP})",
    )


class _OneSetup(argparse.Action):
    """Accept one setup, however many places on the command line name it.

    A global `--config` and a verb's own `--config` (or `setup`'s positional
    PATH) all land in one destination: naming the same path twice is allowed,
    and two paths that differ after `~` is expanded are an error saying to name
    one. A value that is not a string — a `None` positional default, say — is
    stored only when nothing earlier named a setup.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        earlier = getattr(namespace, self.dest, None)
        if not isinstance(values, str):
            if not isinstance(earlier, str):
                setattr(namespace, self.dest, values)
            return
        if (
            isinstance(earlier, str)
            and Path(earlier).expanduser() != Path(values).expanduser()
        ):
            parser.error(
                f"the command line names two setups, {earlier} and {values}; "
                "name one, with --config"
            )
        setattr(namespace, self.dest, values)
