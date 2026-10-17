""

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

if TYPE_CHECKING:  #
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
    ""
    if not value.strip():
        raise argparse.ArgumentTypeError(
            "a blank value is not a path. It is what an unset variable leaves "
            "behind. Pass a path, or leave the argument off to take the default "
            "on purpose."
        )
    return value


class _RepoByPosition(argparse.Action):
    ""

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
    ""
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
    ""
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
    ""

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
