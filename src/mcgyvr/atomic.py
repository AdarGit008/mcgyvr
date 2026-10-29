"""Replace a kept file whole, by staging the bytes and renaming them into place.

Every file mcgyvr keeps for a later reader is written through ``write``, so a
failed or interrupted write leaves the previous file intact and no litter
beside it. The module also holds the two modes a kept file can have:
`_PRIVATE` for what only its owner may read, and `_ORDINARY` for the rest,
which the writer's umask narrows further.
"""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path

from mcgyvr import hostos

#: Mode for a file whose contents belong to its owner alone: read and write, and
#: nothing for group or other.
_PRIVATE = stat.S_IRUSR | stat.S_IWUSR
#: Baseline mode for a shared file: owner read and write plus group and other
#: read and write, narrowed by whatever umask the writing process runs under.
_ORDINARY = _PRIVATE | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH


def write(
    target: Path,
    data: str | bytes,
    *,
    private: bool = False,
    fsync: bool = False,
    staging: Path | None = None,
) -> None:
    """Replace `target` with `data`, whole or not at all.

    Text is encoded as UTF-8 and bytes are written as given. The bytes go to a
    staging file which is then renamed over `target`, so a reader sees the
    previous file or the new one and never a partial one. The staging path is
    ``.{target.name}.{pid}-{thread}.part`` beside the target unless `staging`
    names one, and anything already sitting at that path is removed first.

    `private` keeps the result readable and writable by its owner alone,
    whatever the umask says; otherwise group and other are given read and
    write, which the umask then narrows. `fsync` flushes the bytes to the
    device before the rename, so they survive a crash once the call returns.

    The staging file is created exclusively and without following a link, so a
    link planted at that path is refused rather than written through. If the
    write or the rename fails, the staging file is removed and the error is
    raised with `target` untouched.
    """
    if staging is None:
        staging = target.with_name(
            f".{target.name}.{os.getpid()}-{threading.get_ident()}.part"
        )
    body = data.encode("utf-8") if isinstance(data, str) else data
    staging.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = hostos.open_nofollow(staging, flags, _PRIVATE if private else _ORDINARY)
    try:
        try:
            if private:
                hostos.chmod_private(fd)
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
