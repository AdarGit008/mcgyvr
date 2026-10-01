"""Queue pressure — what a manager reads, host-wide, without being in the way.

A long-running process that decides how the ladder should run — which rung to
keep awake, how widely to fan out — has to read the same thing the work is
doing, and the work is not in its process. ``mcgyvr run`` is one process per
task, so a count in memory is a count of one task. Every signal here is
therefore *host-wide*, and kept in the same place the capacity bound already is:
files on this host's filesystem that the kernel keeps honest.

* **Presence is a locked file.** :meth:`Gauge.present` makes a marker, takes an
  exclusive ``flock`` on it, and keeps both for the length of a block.
  :meth:`Gauge.count` counts the markers whose lock is still held. There is no
  daemon to start, no socket to find and no heartbeat to lose: the lock is the
  heartbeat, and the kernel releases it when its holder dies however it dies.
  That is :mod:`mcgyvr.capacity`'s reason for ``flock``, restated for a count
  rather than a bound — a ``finally`` cannot cover a ``SIGKILL``, and a count
  that did would climb with every crash and never come back down.
* **A marker whose holder is gone is not counted, and is removed.** Whoever
  counts finds out by trying to take the lock: getting it means nobody held it.
  Removal is the counter's, and it is safe to do there because a marker is
  renamed into place only *after* it is locked — a file that exists under its
  final name and is unlocked can only be one whose holder died, never one whose
  holder has not got to it yet.
* **A gauge must never fail the work it is attached to.** It is bookkeeping for
  somebody else's decision. Every way the filesystem can refuse — no space, no
  permission, a path that is a file — leaves the body running unmarked, and the
  reader sees a smaller count than the truth or none at all. A gauge that raised
  would turn "the temporary directory is full" into "the task failed", which is
  the wrong way round.
* **A gauge without its directory degrades to no reading, never to an error.**
  :meth:`Gauge.count` is ``None`` — which is not zero — whenever the directory
  cannot be made or is not one only this user can have written into. The
  rendezvous is a predictable path in a shared temporary directory, so the first
  process to create it wins the name; :func:`mcgyvr.wake._ours` is the test of
  whether it is ours, and it is the same one the wake clock applies to its own,
  for the same reason: a count read back from a directory somebody else made is
  a number somebody else chose.

:class:`Board` is the other half of the same rendezvous: the one document the
manager *publishes*, which the work reads. It is a file, moved into place whole,
so a reader sees the previous document or the new one and never a part of
either, and it is read with the same suspicion — a document that is absent,
unreadable, not JSON or not a mapping is no document.

:class:`Pressure` assembles one rung's reading from the places each fact is
already kept: whether the rung answers (:mod:`mcgyvr.availability`), what the
unit itself says it has in flight (:func:`mcgyvr.runner.unit_in_flight`), how
many dispatches are queued for its slots (:meth:`~mcgyvr.capacity.Capacity.waiting`),
and how many tasks are working on it after climbing to it from a cheaper rung
(:func:`climbed_key`). It invents none of them, and it decides nothing: what
the numbers mean is the manager's, and this is below the seam, where a rung has
already resolved to an endpoint.
"""

from __future__ import annotations

import fcntl
import hashlib
import itertools
import json
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.availability import PROBE_TIMEOUT_S, AvailabilityVerdict, probe_endpoint
from mcgyvr.cooldown import Cooldown
from mcgyvr.runner import unit_in_flight
from mcgyvr.wake import _ours

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.pool import Endpoint, SourceMap

# Marker names keep a readable prefix of the key for an operator listing the
# directory, and a digest for identity — two keys that sanitize alike must not
# be one count by accident. The same idiom, and the same reason, as
# `mcgyvr.capacity._slot_stem`.
_SLUG = re.compile(r"[^A-Za-z0-9.-]+")

# The file the manager's published choice lives in, beside the markers.
_BOARD = "pipeline.json"

# Marker and scratch names must not collide between threads of one process, and
# the process id separates the processes; a counter and the lock that makes
# taking the next one a single step is what separates the threads.
_numbers = itertools.count()
_numbers_lock = threading.Lock()


def _next_number() -> int:
    with _numbers_lock:
        return next(_numbers)


def default_directory() -> Path:
    """The per-user rendezvous directory for this host's pressure signals.

    Keyed by uid, beside the capacity and wake directories and for the same
    reason: two users on one host have two sets of work and one temporary
    directory. Processes that resolve different temporary directories — a
    session-scoped ``TMPDIR``, say — are reading different files, honestly and
    separately; point :class:`Gauge` and :class:`Board` at a stable directory
    when the environment does that.
    """
    return Path(tempfile.gettempdir()) / f"mcgyvr-pressure-{os.getuid()}"


def _stem(key: str) -> str:
    """A filesystem-safe identity for one key: a readable slug and a digest.

    The digest is of the key as given, so a key that differs only in what the
    slug throws away is still a different key.
    """
    slug = _SLUG.sub("-", key).strip("-")[-40:] or "key"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"{slug}.{digest}"


def climbed_key(rung: str) -> str:
    """The gauge key for "a task that climbed to this rung is working on it".

    A *climb* is what :func:`mcgyvr.escalate.escalate` marks: an attempt on a
    rung reached after attempts were spent on a cheaper one. It is a key of its
    own, apart from the waiting keys :mod:`mcgyvr.capacity` writes, because the
    two answer different questions — a dispatch queued for a slot is demand for a
    rig, and a task that outgrew the rungs beneath this one is evidence about
    them.
    """
    return f"climbed.{rung}"


def _usable(where: Path, *, make: bool) -> Path | None:
    """``where`` if it is a directory only this user can have written into.

    ``make`` creates it first, private. :func:`mcgyvr.wake._ours` is the one
    judgement of whether a directory in the shared temporary directory is ours;
    anything else is no directory at all, which every caller turns into "no
    reading" or "not written" and never into an error.
    """
    if make:
        try:
            where.mkdir(parents=True, mode=0o700, exist_ok=True)
        except OSError:
            return None
    return where if _ours(where) else None


def _quietly_remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return


class Gauge:
    """Host-wide presence counts, kept as locked marker files.

    ``directory`` defaults to :func:`default_directory`; tests and callers with
    an unusual temporary directory pass one. Safe to share across threads, and
    shared with every other gauge on this host that names the same directory by
    construction — a marker is a file both can see.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory if directory is not None else default_directory()

    @contextmanager
    def present(self, key: str) -> Iterator[None]:
        """Be counted under ``key`` for the length of the block.

        Best-effort and silent on failure, which is the contract rather than a
        leniency: any ``OSError``, or a directory that is not ours, runs the
        body unmarked. Nothing raised *by the body* is touched — it propagates
        after the marker is given back.

        The marker is made under a scratch name, locked, and only then renamed
        to the name :meth:`count` looks for, so a counter never sees a marker
        that exists and is not yet held. On the way out it is removed *and then*
        closed: the removal is what lets a counter that arrives next find
        nothing, and the close is what releases the lock.
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
        """How many holders are present under ``key`` on this host right now.

        ``None`` when there is no reading to give: the directory cannot be made
        or is not ours. Zero is a reading — it is what a host nobody has marked
        anything on says — and the directory is made here as well as in
        :meth:`present`, so a manager started before any task reads zero rather
        than nothing.

        A marker is counted when its lock is held. It is probed by trying to
        take the lock without waiting: failing means somebody holds it, and
        succeeding means nobody does, so the marker is removed and not counted.
        Scratch files, which are markers not yet locked, are not markers.

        Two counters probing a dead marker at once can each see the other's
        probe as a holder and count it for one reading; the next reading is
        right, and nothing here is worth a lock of its own to prevent that.
        """
        where = _usable(self._directory, make=True)
        if where is None:
            return None
        mine = re.compile(rf"^{re.escape(_stem(key))}\.\d+\.\d+\.mark$")
        try:
            names = os.listdir(where)
        except OSError:
            return None
        return sum(1 for name in names if mine.match(name) and _held(where / name))


def _held(marker: Path) -> bool:
    """Whether somebody holds this marker's lock; a dead holder's is removed."""
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        # Gone since it was listed — its holder just left — or not ours to
        # open. Neither is a holder this can vouch for.
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
    """The manager's published choice: one JSON document, replaced whole.

    A file named for it beside the gauge's markers. :meth:`publish` writes the
    document next to it and moves it over, so a reader that arrives in the
    middle sees the previous one; :meth:`read` takes only what is shaped like a
    document, and is ``None`` for everything else — which every reader treats as
    "the manager has said nothing", the ordinary state of an install that did
    not ask for one.

    Nothing about a published choice is authoritative beyond its age. The
    ``written_at`` it carries is the publisher's clock, added here so a reader
    can decide for itself how long a choice stays in force without the publisher
    having to say.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory if directory is not None else default_directory()

    def publish(self, doc: Mapping[str, Any]) -> bool:
        """Replace the published document with ``doc`` plus ``written_at``.

        ``False`` — and the previous document left as it was — when it could not
        be done: a directory that is not ours, a filesystem that refused, or a
        document that is not JSON. A caller that publishes on a timer simply
        tries again on the next tick; none of these is worth an exception in a
        loop whose job is to keep running.
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
            fd = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(scratch, where / _BOARD)
        except OSError:
            _quietly_remove(scratch)
            return False
        return True

    def read(self) -> dict[str, Any] | None:
        """The published document, or ``None`` if there is not a usable one.

        Absent, unreadable, not UTF-8, not JSON, nested past what the parser
        will follow, or JSON that is not an object are all the same answer. The
        directory is not made for a read: nobody has published into one that
        does not exist.
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


@dataclass(frozen=True)
class Reading:
    """What is known about one rung's load right now, each fact as far as it goes.

    ``None`` is *not read*, never zero: a rung that does not answer has no status
    page to count, a capacity without a gauge cannot count its waiters, and a
    gauge whose directory is not ours cannot count anything, and a manager that
    read those as zero would see an idle rig where it had seen nothing.

    ``awake`` is whether the rung answers. ``in_flight`` is what the unit itself
    reports serving. ``waiting`` is the host-wide count of dispatches queued for
    its slots, and ``climbed`` the host-wide count of tasks working on it after
    climbing from a cheaper rung. ``width`` is the number of slots it enforces,
    which is what the other three are to be read against.
    """

    rung: str
    awake: bool
    in_flight: int | None
    waiting: int | None
    climbed: int | None
    width: int


def _probed(endpoint: Endpoint) -> bool:
    """Whether the endpoint answers — :mod:`mcgyvr.availability`'s own probe."""
    return probe_endpoint(endpoint, PROBE_TIMEOUT_S).live


def _status(endpoint: Endpoint) -> int | None:
    """What the unit says it has in flight, read the way a dispatch reads it."""
    return unit_in_flight(
        endpoint.source, endpoint.base_url, endpoint.engine, endpoint.max_parallel
    )


class Pressure:
    """Reads one rung's :class:`Reading` from where each fact is kept.

    ``live`` and ``in_flight`` take the rung's endpoint and are injectable so
    that nothing here needs a network to be asserted; the defaults are the real
    probe and the real status read. The pool is a :class:`~mcgyvr.pool.SourceMap`
    built *without* an availability filter, because the question is whether a
    rung that is declared answers, and a map that had already dropped it would
    have no endpoint to ask about.

    An unknown rung raises the pool's own error: a manager asking about a rung
    nobody declared is holding a config that is not this one, which is the
    mistake :meth:`~mcgyvr.pool.SourceMap.bind` names, and answering it with an
    empty reading would hide it.
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
        """One rung's reading.

        A rung that does not answer is not asked what it has in flight: there is
        no status page to read, and asking would spend a connection timeout per
        reading on a rig that is asleep — which a manager reading every rung on
        a timer would pay on every tick.
        """
        endpoint = self._pool.bind(rung)
        awake = self._live(endpoint)
        return Reading(
            rung=rung,
            awake=awake,
            in_flight=self._in_flight(endpoint) if awake else None,
            waiting=self._capacity.waiting(endpoint.source, rung),
            climbed=self._gauge.count(climbed_key(rung)),
            width=self._capacity.limit(endpoint.source, rung),
        )


def _asleep_is_not_down(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
    """A probe that always answers live, for a cooldown that must not read sleep.

    A unit the manager has put to sleep answers nothing, and asleep is the state
    it wakes; a cooldown that read that as down would hold out the very unit the
    manager is about to wake. What a cooldown learns here is failures only.
    """
    return AvailabilityVerdict(
        source=endpoint.source,
        live=True,
        reason="",
        how="stub probe, no network",
        elapsed_s=0.0,
    )


class RungCooling:
    """The units held out after failing switches, in rung names.

    :class:`mcgyvr.ladder_manager.Cooling` over :class:`mcgyvr.cooldown.Cooldown`:
    a wake or a sleep that failed is recorded against the unit as a failed
    dispatch is, and the same consecutive-failures rule and expiry take the unit
    out of the manager's reach for a while. The cooldown is built with a probe
    that always reads live (:func:`_asleep_is_not_down`), so the only thing that
    can cool a unit is what the manager itself did to it.

    A rung the pool does not hold is not cooled and not recorded: the manager
    names rungs of its own config, and one with no endpoint has nothing to hold
    out.
    """

    def __init__(self, pool: SourceMap, cooldown: Cooldown | None = None) -> None:
        self._pool = pool
        self._cooldown = (
            cooldown if cooldown is not None else Cooldown(probe=_asleep_is_not_down)
        )

    def cooled(self, rungs: tuple[str, ...]) -> frozenset[str]:
        """The rungs among ``rungs`` that are cooling down now."""
        endpoints = [self._pool.bind(r) for r in rungs if self._pool.get(r) is not None]
        return frozenset(self._cooldown.unavailable(endpoints))

    def failed(self, rung: str) -> None:
        """A wake or sleep of ``rung`` failed."""
        self._cooldown.record_failure(self._source(rung))

    def worked(self, rung: str) -> None:
        """A wake or sleep of ``rung`` worked, so its streak of failures is over."""
        self._cooldown.record_success(self._source(rung))

    def _source(self, rung: str) -> str:
        return self._pool.bind(rung).source
