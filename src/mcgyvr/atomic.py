"""A file is replaced whole or not at all: stage beside it, then ``os.replace``.

Every file mcgyvr keeps for a later reader (a result, a cache, the rig's state,
a credentials file) is written the same way: the bytes go to a staging name in
the target's own folder, and ``os.replace`` moves them over the target in one
step. A reader then sees the old file or the new one, never half of one, and a
write that failed part-way leaves no staging file for the next reader to wonder
about. That routine used to be written out at each of a dozen call sites, each
with its own staging name and its own idea of what to tidy up; :func:`write` is
the one copy.

The staging file sits in the target's folder because ``os.replace`` is atomic
only within one filesystem. It is created exclusively, so a writer never
appends to a stranger's half-file, and its name carries the pid and thread so
two writers of the same target stage their own copies.
"""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path

#: Mode of a staging file the caller marked ``private``: the owner alone.
_PRIVATE = stat.S_IRUSR | stat.S_IWUSR
#: Mode of any other staging file, before the umask: what ``open(..., "w")`` makes.
_ORDINARY = _PRIVATE | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH


def write(
    target: Path,
    data: str | bytes,
    *,
    private: bool = False,
    fsync: bool = False,
    staging: Path | None = None,
) -> None:
    """Replace ``target`` with ``data``, whole or not at all.

    ``str`` is written as UTF-8 and ``bytes`` as given; neither has its
    newlines translated. The target's folder must exist.

    ``private`` makes the file readable by its owner alone (mode ``rw-------``), set on
    the descriptor before any byte is written and never following a link, so
    the secret is not world-readable for an instant. ``fsync`` makes the bytes
    durable before the replace, for a file whose loss a crash must not cause.
    ``staging`` names the staging file when something else sweeps for it by
    name; a stale file at that name is removed first.

    On any failure the staging file is removed and the error raised.
    """
    if staging is None:
        staging = target.with_name(
            f".{target.name}.{os.getpid()}-{threading.get_ident()}.part"
        )
    body = data.encode("utf-8") if isinstance(data, str) else data
    staging.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(staging, flags, _PRIVATE if private else _ORDINARY)
    try:
        try:
            if private:
                os.fchmod(fd, _PRIVATE)
            view = memoryview(body)
            while view:
                view = view[os.write(fd, view) :]
            if fsync:
                os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(staging, target)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
