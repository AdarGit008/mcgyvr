"""Pressure signals shared across processes through files in a temporary directory.

Nothing here owns a daemon or a socket. A holder says it is present by making a
file and keeping a ``flock`` on it, so any other process on the host can count
the live holders, read the one document a manager publishes, and see how long a
source is held out. Every one of those operations is best-effort: when the
directory is missing, not ours, or the data is unreadable, the answer is
``None`` (never a guess), and a failed write is left silent rather than raised
into the work it is attached to.
"""

from __future__ import annotations

import fcntl
import hashlib
import itertools
import json
import os
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr import atomic
from mcgyvr.availability import PROBE_TIMEOUT_S, AvailabilityVerdict, probe_endpoint
from mcgyvr.cooldown import COOLDOWN_S, Cooldown, SharedHold
from mcgyvr.runner import unit_in_flight
from mcgyvr.serving import host_of, port_of
from mcgyvr.userdir import private_dir, user_tempdir
from mcgyvr.wake import resting

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.local_pool import Endpoint, SourceMap

# Everything in a key that is not a letter, digit, dot or hyphen, collapsed to
# runs so a key can be used as part of a file name. Applied to a key before it
# is shortened: two keys that slug alike are still kept apart by the digest
# that `_stem` appends.
_SLUG = re.compile(r"[^A-Za-z0-9.-]+")

# The one file name a manager publishes its answer under, in the directory.
_BOARD = "pipeline.json"
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


def climbed_key(rung: str) -> str:
    """The gauge key a task holds while it is climbing onto `rung`.

    Prefixed so climbers are never counted as waiters, whose keys are the slot
    stems of a capacity.
    """
    return f"climbed.{rung}"


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
            fcntl.flock(fd, fcntl.LOCK_EX)
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
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _held(marker: Path) -> bool:
    """Whether a mark still has a live holder keeping its lock.

    The lock is taken without waiting, so a refusal means the holder is alive; a
    lock this process can take means the holder is gone, and the mark is removed
    here rather than left to be counted again.
    """
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        # Gone, or not a plain file this process may open (a symlink is refused
        # by O_NOFOLLOW): either way there is no live mark to count.
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return False
        _quietly_remove(marker)
        return False
    finally:
        os.close(fd)


class Board:
    """The manager's one published answer, kept in a single JSON file.

    Publishing replaces the document atomically, so a reader never sees half of
    it; reading treats an absent, unreadable or wrongly shaped file as no answer
    rather than raising, since the reader is a process that must keep working.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory if directory is not None else default_directory()

    def publish(self, doc: Mapping[str, Any]) -> bool:
        """Publish `doc` with the time it was written, replacing the last answer.

        The mapping given is copied, never modified: `written_at` is added to the
        copy. A document that cannot be serialized, or a write that cannot
        finish, is reported as `False` and leaves the previous document whole.
        """
        where = _usable(self._directory, make=True)
        if where is None:
            return False
        try:
            text = json.dumps({**doc, "written_at": time.time()})
        except (TypeError, ValueError):
            return False
        scratch = where / f"{_BOARD}.{os.getpid()}.{_next_number()}.tmp"
        try:
            atomic.write(where / _BOARD, text, private=True, staging=scratch)
        except OSError:
            return False
        return True

    def read(self) -> dict[str, Any] | None:
        """The last published document, or `None` if there is no usable one.

        A missing file, bytes that cannot be decoded, invalid JSON, or JSON that
        is not an object all read as `None`.
        """
        where = _usable(self._directory, make=False)
        if where is None:
            return None
        try:
            raw = (where / _BOARD).read_text(encoding="utf-8")
            said = json.loads(raw)
        except (OSError, ValueError, RecursionError):
            return None
        return said if isinstance(said, dict) else None


class HostCooling:
    """Per-source cooldown deadlines kept in files, and so shared host-wide.

    A hold recorded by one process is seen by every other process of the same
    user, so a source that just failed is not retried by the next task in line.
    Deadlines are wall-clock instants from `clock` (`time.time` by default), which
    is what lets a deadline written by one process mean the same to another.
    """

    def __init__(
        self, directory: Path | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self._directory = directory if directory is not None else default_directory()
        self._clock = clock

    def _file(self, where: Path, source: str) -> Path:
        return where / f"held.{_stem(source)}.json"

    def hold(self, source: str, seconds: float) -> None:
        """Hold `source` out for `seconds` from now, if that is longer than it is.

        An existing deadline that is the same or later is left alone, so a hold
        is only ever extended and never cut short by a later caller. Failing to
        write the file is not an error: the hold is then simply not shared.
        """
        where = _usable(self._directory, make=True)
        if where is None:
            return
        until = self._clock() + seconds
        if (self._until(where, source) or 0.0) >= until:
            return
        target = self._file(where, source)
        scratch = where / f"{target.name}.{os.getpid()}.{_next_number()}.tmp"
        try:
            body = json.dumps({"source": source, "until": until})
            atomic.write(target, body, private=True, staging=scratch)
        except OSError:
            return

    def held(self, source: str) -> float | None:
        """The seconds `source` is still held out for, or `None` if it is not held.

        A deadline that has already passed reads as `None`, as does a document
        that cannot be read or carries no numeric `until`.
        """
        where = _usable(self._directory, make=False)
        if where is None:
            return None
        until = self._until(where, source)
        if until is None:
            return None
        left = until - self._clock()
        return left if left > 0 else None

    def _until(self, where: Path, source: str) -> float | None:
        try:
            said = json.loads(self._file(where, source).read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        until = said.get("until") if isinstance(said, dict) else None
        if isinstance(until, bool) or not isinstance(until, (int, float)):
            return None
        return float(until)


@contextmanager
def exclusive(name: str, directory: Path | None = None) -> Iterator[bool | None]:
    """Hold an exclusive lock on `name` for the life of the block.

    Yields `True` when this process took the lock, `False` when the name is
    already held through another open file (another process, or another call
    here), and `None` when there is no lock to be had at all — the directory is
    not ours, or the file cannot be opened or locked for some reason other than
    another holder. `None` is not `False`: it says nothing about who else holds
    the name. The lock is the kernel's, so a process that dies holds nothing and
    the next one takes the name.
    """
    where = _usable(
        directory if directory is not None else default_directory(), make=True
    )
    if where is None:
        yield None
        return
    try:
        fd = os.open(
            where / f"{_stem(name)}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
    except OSError:
        yield None
        return
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held: bool | None = False
        except OSError:
            held = None
        else:
            held = True
        yield held
    finally:
        os.close(fd)


@dataclass(frozen=True)
class Reading:
    """One rung as pressure sees it at the moment of the reading.

    Frozen, so a reading can be compared, held and logged as the answer it was.
    A rung that is not awake carries `in_flight=None`, not zero, because nobody
    asked a server that was not there. `waiting` and `climbed` are `None` when
    there is no gauge to count them, and `full` is the capacity's judgement of
    its own load against the server count.
    """

    rung: str
    awake: bool
    in_flight: int | None
    waiting: int | None
    climbed: int | None
    width: int
    full: bool = False


def _probed(endpoint: Endpoint) -> bool:
    """Whether the endpoint answers, with a host put to rest counted as not awake.

    A resting host is not probed at all: it would refuse the connection, and
    that refusal says nothing about the source.
    """
    if resting(host_of(endpoint.base_url), port_of(endpoint.base_url)):
        return False
    return probe_endpoint(endpoint, PROBE_TIMEOUT_S).live


def _status(endpoint: Endpoint) -> int | None:
    """The server's count of work in flight for the endpoint, `None` if unread."""
    return unit_in_flight(
        endpoint.source,
        endpoint.base_url,
        endpoint.engine,
        endpoint.max_parallel,
        credential_env=endpoint.credential_env,
    )


class Pressure:
    """Reads the pressure signals for one rung out of a pool and a capacity.

    The probes are injectable so a reading can be taken without touching a
    network; the defaults ask the availability probe and the runner's status
    read.
    """

    def __init__(
        self,
        pool: SourceMap,
        capacity: Capacity,
        gauge: Gauge,
        *,
        live: Callable[[Endpoint], bool] | None = None,
        in_flight: Callable[[Endpoint], int | None] | None = None,
    ) -> None:
        self._pool = pool
        self._capacity = capacity
        self._gauge = gauge
        self._live = live if live is not None else _probed
        self._in_flight = in_flight if in_flight is not None else _status

    def read(self, rung: str) -> Reading:
        """Assemble everything known about `rung` into one `Reading`.

        The pool's own error is raised for a rung nobody declared. In-flight work
        is only asked of a rung that is awake, since a host that is asleep or
        down has no server to ask; waiting and width come from the capacity for
        the rung's source and rung, the climbers from the gauge, and `full` from
        the capacity's single judgement of the two counts.
        """
        endpoint = self._pool.bind(rung)
        awake = self._live(endpoint)
        in_flight = self._in_flight(endpoint) if awake else None
        return Reading(
            rung=rung,
            awake=awake,
            in_flight=in_flight,
            waiting=self._capacity.waiting(endpoint.source, rung),
            climbed=self._gauge.count(climbed_key(rung)),
            width=self._capacity.limit(endpoint.source, rung),
            full=self._capacity.judge(endpoint.source, rung, in_flight).full,
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


def _asleep_is_not_down(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
    """A probe that finds every endpoint live, for a cooldown that must not probe.

    Cooling here is decided by recorded failures alone. Probing a rung that is
    deliberately asleep would call it down and hold out a source that is fine, so
    the verdict is live with no network, no elapsed time and no reason.
    """
    return AvailabilityVerdict(
        source=endpoint.source,
        live=True,
        reason="",
        how="stub probe, no network",
        elapsed_s=0.0,
    )


class RungCooling:
    """Cooldown of rungs, for a caller that has a source map.

    Failures and successes are recorded against the rung's source, so rungs
    sharing a source cool together, and a hold may also come from another process
    on this host through a `SharedHold`. Unless one is supplied, the cooldown is
    built with the stub probe below (so it never calls a host down by probing it)
    and is held for `hold_s`, never shorter than the standard cooldown.
    """

    def __init__(
        self,
        pool: SourceMap,
        cooldown: Cooldown | None = None,
        *,
        hold_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        shared: SharedHold | None = None,
    ) -> None:
        self._pool = pool
        if cooldown is None:
            cooldown = Cooldown(
                probe=_asleep_is_not_down,
                clock=clock,
                cooldown_s=COOLDOWN_S if hold_s is None else max(COOLDOWN_S, hold_s),
                shared=shared,
            )
        self._cooldown = cooldown

    def cooled(self, rungs: tuple[str, ...]) -> frozenset[str]:
        """The sources among `rungs` that are out of service right now.

        A name the pool does not have is skipped rather than bound, since binding
        it would raise. The names returned are sources, so rungs sharing one cool
        together; what counts as out of service is the cooldown's own answer,
        which covers its liveness verdicts, recorded failures and any hold another
        process on this host left behind.
        """
        endpoints = [self._pool.bind(r) for r in rungs if self._pool.get(r) is not None]
        return frozenset(self._cooldown.unavailable(endpoints))

    def failed(self, rung: str) -> None:
        """Record one failure of `rung`'s source, which may hold it out for a while."""
        self._cooldown.record_failure(self._source(rung))

    def worked(self, rung: str) -> None:
        """Record one success of `rung`'s source, forgetting its failures.

        A source already cooling stays cooling until its deadline: a success
        resets the count of failures but does not lift the hold.
        """
        self._cooldown.record_success(self._source(rung))

    def _source(self, rung: str) -> str:
        return self._pool.bind(rung).source
