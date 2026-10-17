""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path

#
_PRIVATE = stat.S_IRUSR | stat.S_IWUSR
#
_ORDINARY = _PRIVATE | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH


def write(
    target: Path,
    data: str | bytes,
    *,
    private: bool = False,
    fsync: bool = False,
    staging: Path | None = None,
) -> None:
    ""
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
