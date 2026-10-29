"""Pressure signals shared across processes through files in a temporary directory.

Nothing here owns a daemon or a socket. A holder says it is present by making a
file and keeping a ``flock`` on it, so any other process on the host can count
the live holders. That count is best-effort: when the directory is missing, not
ours, or unreadable, the answer is ``None`` (never a guess), and a failed mark
is left silent rather than raised into the work it is attached to.
:func:`server_counts` reads what a server reports in flight, for the capacity.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr import hostos
from mcgyvr.runner import unit_in_flight
from mcgyvr.userdir import private_dir, user_tempdir

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.local_pool import Endpoint, SourceMap

# Everything in a key that is not a letter, digit, dot or hyphen, collapsed to
# runs so a key can be used as part of a file name. Applied to a key before it
# is shortened: two keys that slug alike are still kept apart by the digest
# that `_stem` appends.
_SLUG = re.compile(r"[^A-Za-z0-9.-]+")

#: A staging file left behind by a write: `<name>.<pid>.<n>.tmp`. The pid is
#: captured so a sweep can tell whether the process that made it is still alive.
_SCRATCH = re.compile(r"^.+\.(\d+)\.\d+\.tmp$")

# Numbers handed out per process, under a lock, so that two marks made by
# different threads of one process never try to use the same file name, and
# a file name says nothing about any other process.
_numbers = itertools.count()
_numbers_lock = threading.Lock()


def _next_number() -> int:
    with _numbers_lock:
        return next(_numbers)


def default_directory() -> Path:
    """The per-user rendezvous directory under the temporary directory.

    Naming it after the uid keeps one user's processes together and out of
    another's; the directory is only used once `_usable` confirms it is ours.
    """
    return user_tempdir("pressure")


def _stem(key: str) -> str:
    """A file-name stem for a key: a shortened slug plus a digest of the key.

    The slug is for a person reading a directory listing; the 12 hex characters
    of the sha256 are what identify the key, so two keys that slug to the same
    text (`a/b` and `a-b`) still get different stems.
    """
    slug = _SLUG.sub("-", key).strip("-")[-40:] or "key"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"{slug}.{digest}"


def _usable(where: Path, *, make: bool) -> Path | None:
    """The directory if it is ours to use, otherwise `None`.

    With `make`, the directory is created first, privately (0o700). A directory
    owned by another user, or one anyone else may write into, would let
    somebody else choose the numbers read from it.
    """
    return private_dir(where, make=make)


def _quietly_remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return


class Gauge:
    """A cross-process count of who is present under a key.

    Each holder keeps a file locked for as long as it is present, so a count
    taken here sees holders in other interpreters. Nothing is remembered in
    memory: the directory is the whole state, and a directory that is missing or
    not ours means no reading (`None`) rather than a count of zero.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory if directory is not None else default_directory()

    @contextmanager
    def present(self, key: str) -> Iterator[None]:
        """Say this process is present under `key` for the life of the block.

        Failing to mark is not an error: the body runs either way, and only a
        mark that was actually made is removed on the way out. An exception
        raised in the body passes through.
        """
        held = self._mark(key)
        try:
            yield
        finally:
            if held is not None:
                fd, marker = held
                _quietly_remove(marker)
                with suppress(OSError):
                    os.close(fd)

    def _mark(self, key: str) -> tuple[int, Path] | None:
        where = _usable(self._directory, make=True)
        if where is None:
            return None
        name = f"{_stem(key)}.{os.getpid()}.{_next_number()}"
        scratch = where / f"{name}.tmp"
        marker = where / f"{name}.mark"
        try:
            fd = os.open(scratch, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            return None
        try:
            hostos.lock(fd)
            os.rename(scratch, marker)
        except OSError:
            _quietly_remove(scratch)
            os.close(fd)
            return None
        return fd, marker

    def count(self, key: str) -> int | None:
        """How many live holders there are under `key`, or `None` for no reading.

        A mark whose holder has died is not counted and is unlinked on the way
        past, since the kernel dropped its lock when the process went; staging
        files a dead process left behind are swept at the same time.
        """
        where = _usable(self._directory, make=True)
        if where is None:
            return None
        mine = re.compile(rf"^{re.escape(_stem(key))}\.\d+\.\d+\.mark$")
        try:
            names = os.listdir(where)
        except OSError:
            return None
        _sweep_scratch(where, names)
        return sum(1 for name in names if mine.match(name) and _held(where / name))


def _sweep_scratch(where: Path, names: list[str]) -> None:
    """Remove staging files whose making process is no longer running.

    A process killed between creating a staging file and renaming it into place
    would otherwise leave a file that nothing ever names again.
    """
    for name in names:
        found = _SCRATCH.match(name)
        if found is not None and not _running(int(found.group(1))):
            _quietly_remove(where / name)


def _running(pid: int) -> bool:
    """Whether a process with this pid exists, asked without touching it.

    A pid that cannot be signalled but is there (another user's) counts as
    running; only a pid the kernel reports as gone is dead.
    """
    return hostos.pid_alive(pid)


def _held(marker: Path) -> bool:
    """Whether a mark still has a live holder keeping its lock.

    The lock is taken without waiting, so a refusal means the holder is alive; a
    lock this process can take means the holder is gone, and the mark is removed
    here rather than left to be counted again.
    """
    try:
        fd = hostos.open_nofollow(marker, os.O_RDONLY)
    except OSError:
        # Gone, or not a plain file this process may open (a symlink is refused
        # by O_NOFOLLOW): either way there is no live mark to count.
        return False
    try:
        try:
            hostos.lock(fd, blocking=False)
        except BlockingIOError:
            return True
        except OSError:
            return False
        _quietly_remove(marker)
        return False
    finally:
        os.close(fd)


def _status(endpoint: Endpoint) -> int | None:
    """The server's count of work in flight for the endpoint, `None` if unread."""
    return unit_in_flight(
        endpoint.source,
        endpoint.base_url,
        endpoint.engine,
        endpoint.max_parallel,
        credential_env=endpoint.credential_env,
    )


def server_counts(pool: SourceMap) -> Callable[[str], int | None]:
    """Build the capacity's server-count reader: source name to work in flight.

    A name the pool has no rung for reads as `None` instead of raising, since the
    capacity may ask about a unit it was given no address for.
    """

    from mcgyvr.local_pool import UnknownRungError

    def count(source: str) -> int | None:
        try:
            endpoint = pool.bind(source)
        except UnknownRungError:
            return None
        return _status(endpoint)

    return count
