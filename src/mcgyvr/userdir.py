"""Per-user directories under the temporary directory, used only when ours outright.

The temporary directory is shared by every local user, so a path named for this
user could have been made first by somebody else: as a directory they own, one
anyone may write into, or a symlink to somewhere else. A directory here is
used only once :func:`owned_outright` accepts it.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from mcgyvr import hostos


def user_tempdir(purpose: str) -> Path:
    """``<tmp>/mcgyvr-<purpose>-<uid>``: one directory per purpose and per user.

    ``<uid>`` is :func:`mcgyvr.hostos.current_user_id`: the uid on POSIX, the
    login name on Windows.

    The temporary directory is looked up on every call, so a test that points
    ``tempfile.tempdir`` somewhere else moves every such directory with it.
    """
    return Path(tempfile.gettempdir()) / f"mcgyvr-{purpose}-{hostos.current_user_id()}"


def owned_outright(where: Path) -> bool:
    """True when `where` is a directory this user owns outright.

    `lstat`, so a symlink does not pass for the directory it points at. It has
    to be a directory, owned by this uid, and not writable by group or other: a
    path another local user could have got to first is not read from, and
    nothing is written into it.
    """
    try:
        found = os.lstat(where)
    except OSError:
        return False
    if not stat.S_ISDIR(found.st_mode):
        return False
    if not hostos.owned_by_current_user(found):
        return False
    return not hostos.others_mode_bits(found, stat.S_IWGRP | stat.S_IWOTH)


def private_dir(where: Path, *, make: bool) -> Path | None:
    """The directory if it is ours to use, otherwise `None`.

    With `make`, the directory is created first, privately (0o700) and with
    parents. Either way the answer is `None` unless :func:`owned_outright`
    accepts it: a directory owned by another user, or one anyone else may
    write into, would let somebody else choose what is read from it.
    """
    if make:
        try:
            where.mkdir(parents=True, mode=0o700, exist_ok=True)
        except OSError:
            return None
    return where if owned_outright(where) else None
