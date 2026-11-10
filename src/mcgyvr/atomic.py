"""Replace a kept file whole, by staging the bytes and renaming them into place.

Every file mcgyvr keeps for a later reader is written through ``write``, so a
failed or interrupted write leaves the previous file intact and no litter
beside it; ``replace`` is the rename that ends it, for a caller whose staged
file or folder is built some other way (a resumed download, an unpacked
release). The module also holds the two modes a kept file can have:
`_PRIVATE` for what only its owner may read, and `_ORDINARY` for the rest,
which the writer's umask narrows further, and the pair that keeps a secret in a
file of its own (`write_private`, `read_private`): written at 0600, read back
only from a plain file of this user that nobody else may read or write.

Standard library and ``mcgyvr.hostos`` only, and Python 3.9: the programs the
door ships to a rig (:mod:`mcgyvr.serving.shipped`) carry this module.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

from mcgyvr import hostos

#: Mode for a file whose contents belong to its owner alone: read and write, and
#: nothing for group or other.
_PRIVATE = stat.S_IRUSR | stat.S_IWUSR
#: Baseline mode for a shared file: owner read and write plus group and other
#: read and write, narrowed by whatever umask the writing process runs under.
_ORDINARY = _PRIVATE | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH
#: How often, and how far apart, a staged file is renamed over its target
#: while the rename is refused: Windows refuses it while a reader holds the
#: target open, which a record read at that moment does.
REPLACE_TRIES = 20
REPLACE_PAUSE_S = 0.05


def write(
    target: Path,
    data: str | bytes,
    *,
    private: bool = False,
    fsync: bool = False,
    staging: Path | None = None,
    mode: int | None = None,
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
    `mode` names the mode an ordinary file is made with instead, which the
    umask then narrows; it cannot be given with `private`.

    The staging file is created exclusively and without following a link, so a
    link planted at that path is refused rather than written through. The
    rename is :func:`replace`, tried again while it is refused. If the write
    or the rename fails, the staging file is removed and the error is raised
    with `target` untouched.
    """
    if private and mode is not None:
        raise ValueError("a private file has its own mode; give `private` or `mode`")
    if staging is None:
        staging = target.with_name(
            f".{target.name}.{os.getpid()}-{threading.get_ident()}.part"
        )
    body = data.encode("utf-8") if isinstance(data, str) else data
    staging.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    made = _PRIVATE if private else _ORDINARY if mode is None else mode
    fd = hostos.open_nofollow(staging, flags, made)
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
        replace(staging, target)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise


def replace(source: Path, target: Path) -> None:
    """Rename `source` over `target` in one step, as ``os.replace`` does.

    A rename refused with PermissionError is tried again, :data:`REPLACE_TRIES`
    times in all, :data:`REPLACE_PAUSE_S` apart, and the last refusal is
    raised: Windows refuses it while another process holds `target` open, as a
    reader of a record does for a moment. Anywhere else a refusal stands, and
    is raised the same way once the tries are spent.
    """
    for _ in range(REPLACE_TRIES - 1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            time.sleep(REPLACE_PAUSE_S)
    os.replace(source, target)


class PrivateFileError(Exception):
    "A private file that cannot be trusted, named with what to do about it."


def write_private(target: Path, text: str) -> Path:
    """Write `text` to `target`, a file readable by its owner alone, and say
    where it went.

    The folder is created at 0700 only when it is missing; one that exists
    keeps its own mode. A link in the file's place raises PrivateFileError
    rather than being written through. `write` puts the text in place in one
    step, at 0600, fsynced. This is the one copy of that write: the rig token
    (`mcgyvr.rig.credentials`) and a unit's API key (`mcgyvr.unitkey`) are kept
    the same way.
    """
    folder = target.parent
    if not folder.exists():
        folder.mkdir(mode=0o700, parents=True)
        hostos.chmod_private(folder, directory=True)
    if target.is_symlink():
        raise PrivateFileError(
            f"{target} is a link; remove it, and keep no link in its place"
        )
    write(target, text, private=True, fsync=True)
    return target


def read_private(target: Path, most: int, *, again: str, leaked: str) -> bytes | None:
    """The bytes of `target` as :func:`write_private` wrote it, at most `most`
    of them and one more (so a caller can tell a file that is too long), or
    None when there is no such file.

    The file is opened without following a link and then judged by what is
    actually open, not by the path: it must be a plain file of this user with no
    group or other bits. Anything else raises PrivateFileError saying what to
    do: `again` how to make the file anew, `leaked` what to do if another could
    have read it.
    """
    try:
        fd = hostos.open_nofollow(target, os.O_RDONLY)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PrivateFileError(
            f"{target} cannot be opened ({exc.strerror}); it must be a plain file, "
            "not a link"
        ) from exc
    with os.fdopen(fd, "rb") as handle:
        facts = os.fstat(handle.fileno())
        if not stat.S_ISREG(facts.st_mode):
            raise PrivateFileError(f"{target} is not a plain file; remove it")
        if not hostos.owned_by_current_user(facts):
            raise PrivateFileError(
                f"{target} belongs to another user; remove it and {again}"
            )
        if hostos.others_mode_bits(facts):
            raise PrivateFileError(
                f"{target} can be read or written by others; run `chmod 600 "
                f"{target}`, and if anyone else could have read it, {leaked}"
            )
        return handle.read(most + 1)
