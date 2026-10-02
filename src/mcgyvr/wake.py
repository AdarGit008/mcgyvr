"""A card that is down and has a launch spec is asleep, and asleep is not a decline.

Three neighbours already answer liveness questions and none of them answers
this one.

* :mod:`mcgyvr.cooldown` is failure-driven and its outcome is a **decline**:
  after consecutive dispatch failures ``drive`` declines a rung on that source
  (``Verdict.DECLINED``) until the cooldown ends. A sleeping card must wake, not
  step aside.
* :mod:`mcgyvr.availability` is liveness-driven and reads a sleeping rig as
  **down**, correctly on its own terms — nothing is listening — and with the
  wrong consequence.
* :mod:`mcgyvr.capacity` bounds a wait for a *slot* on a server that exists.

So ``asleep`` is not a fourth state to store. It is ``down`` plus one more fact
mcgyvr already holds: **a launch spec it wrote for that card**::

    up      the unit answers                          -> dispatch, unchanged
    asleep  it does not answer, and this config's
            serving.compose_dir holds a file for it   -> wake, then dispatch
    down    it does not answer, and there is no
            such file                                 -> availability's DOWN

There is no state machine, no field to keep in sync with a rig and no third
liveness module. The distinction that matters to a caller — *can mcgyvr bring
this back?* — is answered by *does mcgyvr have the file?*, which is answerable
without touching the network. It degrades honestly by construction: an api
source has no compose file and is never asleep, a rig somebody else runs has no
compose file and is never asleep, and a config with no ``serving.compose_dir``
has no sleeping cards at all.

**Fail-first, never probe-first.** A card that is up must cost nothing extra, so
this module does not ask whether a rig is awake before sending work. It sends
the work. A sleeping rig has nothing listening, so the connection is refused in
under a millisecond and **that instant refusal is the wake signal**. A
probe-first design would pay a round trip on every dispatch to learn something
the dispatch itself reports for free, which is the cost
:mod:`mcgyvr.availability` exists to avoid, re-added per request.

**One door and nothing else.** A wake is
``python -m mcgyvr.serving.run serve up --host H --compose FILE --suffix S``,
spawned as a subprocess, and a sleep is the same with ``down``. The ladder
manager also uses ``sleep`` and ``wake``, vLLM's level 2 and its way back,
where the process stays up (see :class:`CardSwitches` and :func:`resting`).
Nothing here
runs ``docker`` or ``ssh``: under the door those two names resolve to shims that
"admit exactly the host the door was opened for and refuse any process the door
did not start" (:mod:`mcgyvr.serving.run`), and ``tests/test_one_door.py`` bans
the way round it. :func:`spawn_door` is therefore the whole of this module's
contact with a machine, which is what lets a test own all of it.

The design is ``mcgyvr-lab/records/plans/sleep-wake.md``, approved; the budget argument
is ``mcgyvr-lab/records/plans/wake-timeout.md``.
"""

from __future__ import annotations

import json
import math
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import Config
from mcgyvr.runner import RefusedConnectionError
from mcgyvr.serving import Card, cards, port_of

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.scan import Scan

# The module the door is spelled as -- an ``-m`` and never a path, because the
# door mints its own ``RUN_*`` vocabulary, refuses to start under an inherited
# one and files write-once evidence under ``records/evidence/``, so a wake that
# reached a rig any other way would be the second way in that
# ``src/mcgyvr/serving/run.py`` says the seal is against.
#
# Imported rather than restated: two spellings of one door is a door that can
# be half-renamed. `gatelib` is the definition and this is the reader.
from mcgyvr.serving.gatelib import DOOR_MODULE, NO_SLEEP_ROUTE

#: What one dispatch answers with. Named so that :meth:`Waker.dispatching`
#: hands back exactly what the call it wrapped would have, which is what lets it
#: sit inside `drive` without `drive` learning anything about wakes.
Answer = TypeVar("Answer")


class WakeError(Exception):
    """A card could not be woken or slept, and the reason is worth reading."""


def spawn_door(argv: Sequence[str], **kwargs: object) -> int:
    """Run the door to completion and return its exit code.

    The one seam. It is a module-level function rather than a method so that a
    test can substitute it with one ``monkeypatch.setattr`` and thereby own
    every path from this module to a machine — which is the property D3 buys by
    refusing to let anything here run ``docker`` or ``ssh`` directly.

    Output is inherited rather than captured: the door writes its own evidence
    envelope and its refusals are worth reading verbatim, and a wake that
    swallowed "no run root, refusing before gate 1" would silently decline a
    rung on an install that simply cannot wake a card.
    """
    done = subprocess.run(list(argv), check=False, **kwargs)  # type: ignore[call-overload]
    code: int = done.returncode
    return code


def door_argv(
    *,
    direction: str,
    host: str,
    compose: Path,
    suffix: str,
    units: Sequence[str] = (),
) -> tuple[str, ...]:
    """The one command a wake or a sleep is.

    ``--suffix`` is not optional and is not cosmetic. Gate 5 claims the
    ``RUN_ID`` with ``O_CREAT | O_EXCL`` and refuses a second run that mints the
    same one, so without a suffix two wakes on one day collide with each other
    and with an operator's hand-run ``serve up``. It is derived from the waker's
    pid and clock, so every wake gets an envelope of its own.

    ``units`` names the containers a ``sleep`` or ``wake`` acts on alone
    (``--unit``), the rest of the card left as it is; empty is the whole card.
    """
    return (
        sys.executable,
        "-m",
        DOOR_MODULE,
        "serve",
        direction,
        "--host",
        host,
        "--compose",
        str(compose),
        "--suffix",
        suffix,
        *(part for unit in units for part in ("--unit", unit)),
    )


def _suffix() -> str:
    """A RUN_ID suffix no other wake on this host will mint.

    Only ``[A-Za-z0-9_.-]`` — gate 5 requires it because the id prefixes
    container names.
    """
    return f"wake-{os.getpid()}-{int(time.monotonic() * 1000) % 1_000_000}"


@dataclass(frozen=True)
class Wake:
    """What one door run cost, beside what the last wake of this card cost.

    ``predicted_s`` is carried as data and nothing here compares the two — see
    :func:`predicted_wake_s` and :attr:`deviation`.
    """

    host: str
    compose_file: Path
    direction: str
    seconds: float
    predicted_s: float | None
    code: int
    #: The ports of the units this run acted on: the whole card's, or the one
    #: unit a ``--unit`` sleep or wake named.
    ports: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def deviation(self) -> str | None:
        """Always ``None``: this module holds no rule that judges a wake."""
        return None


def _clock_dir() -> Path:
    """Where this host keeps what it has learned about its own wakes.

    Beside the capacity rendezvous directory and keyed by uid for the same
    reason D7 gives: twenty ``mcgyvr run`` processes have twenty memories and
    one filesystem, and a record that lived in memory would be a record the
    next run could not read. Nothing here is a lock and nothing here is
    authoritative — it is one number per card, and a missing or unreadable file
    means the card has no history, which is the ordinary state on the first
    wake after an install.
    """
    return Path(tempfile.gettempdir()) / f"mcgyvr-wake-{os.getuid()}"


def _ours(where: Path) -> bool:
    """Whether this directory is one only this user can have put anything in.

    ``/tmp/mcgyvr-wake-<uid>/`` is a predictable path in a world-writable
    directory, so the first process to create it wins the name — and
    ``mkdir(exist_ok=True)`` adopts whatever is there, including a directory
    another local user made, and including a symlink pointing somewhere else
    entirely.

    Nothing in this cache is secret. What is at stake is that the number in it
    is read back and printed to an operator as what the card did last time, and
    that a wake writes into the directory afterwards. So it is used only when it
    is a real directory, owned by this user, and writable by nobody else — the
    conditions ``mkdir(mode=0o700)`` establishes when we are the one who made
    it. Anything else degrades to no history, which is free: it is the ordinary
    state of the first wake after an install.

    ``lstat`` and not ``stat``, because a symlink is precisely the case a
    ``stat`` would follow into and approve.
    """
    try:
        found = os.lstat(where)
    except OSError:
        return False
    if not stat.S_ISDIR(found.st_mode):
        return False
    if found.st_uid != os.getuid():
        return False
    return not found.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def _history(card: Card) -> Path:
    return _clock_dir() / f"{_safe(card.host)}.wake.json"


def _safe(host: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in host)


def predicted_wake_s(card: Card) -> float | None:
    """How long this card took to wake last time, or ``None`` the first time.

    **The last actual is the prediction; no curve is fitted** (why:
    ``mcgyvr-lab/records/plans/wake-timeout.md`` §4).

    **It never shortens or aborts a wake.** It is recorded on the :class:`Wake`
    and nothing acts on it: the door's own health poll
    (``mcgyvr.config.HEALTH_POLLS`` x ``HEALTH_INTERVAL_S``) is what gives up.

    **Every way of not being a number is no prediction, and none of them is an
    exception.** This function must be unable to stop a wake, and a raise stops
    one — :func:`_run_door` calls this *before* it spawns the door, so an
    ``AttributeError`` here is a card that never comes back for a rung that is
    queued on it. What is on the other end is a file in a temporary directory
    written by a process that may have been killed halfway through it, so JSON
    ``null``, a list, a number, a string, half a document and a file of bytes
    that are not text are all things that have to arrive as ``None``. The read
    catches ``ValueError`` as well as ``OSError`` because a file that is not
    UTF-8 raises ``UnicodeDecodeError`` out of ``read_text``, which is neither
    an ``OSError`` nor something ``json`` ever sees.

    A boolean is not a number of seconds either, however much
    ``isinstance(True, int)`` says otherwise.
    """
    where = _clock_dir()
    if not _ours(where):
        return None
    try:
        raw = _history(card).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        said = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(said, dict):
        return None
    seconds = said.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    # `NaN` and `inf` are JSON that `json` accepts and not a number of seconds.
    number = float(seconds)
    return number if math.isfinite(number) else None


def _remember(made: Wake) -> None:
    """Write down what this wake actually cost, for the next one to carry.

    Best-effort and silent on failure: a wake that landed must not be reported
    as failed because a temporary directory was not writable, and the only thing
    lost is the next wake's ``predicted_s``.

    ``mode=0o700`` on the directory, and :func:`_ours` before writing into one
    that already exists. ``mkdir(exist_ok=True)`` on a predictable path under
    ``/tmp`` adopts whatever another local user put there first, symlink
    included, and this is the write that would then land in it.
    """
    if not made.ok or made.direction != "up":
        return
    try:
        where = _clock_dir()
        where.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not _ours(where):
            return
        (where / f"{_safe(made.host)}.wake.json").write_text(
            json.dumps({"host": made.host, "seconds": round(made.seconds, 3)}),
            encoding="utf-8",
        )
    except OSError:
        return


def _rest_mark(host: str, port: int) -> Path:
    return _clock_dir() / f"{_safe(host)}-{port}.resting"


def resting(host: str, port: int | None = None) -> bool:
    """Whether mcgyvr put a unit on ``host`` to sleep with its process kept.

    Per unit, by the port it serves on: a card's co-resident vLLM units each
    sleep on their own, one to make room for another. ``port`` omitted asks
    whether any unit of the card is resting.

    A card slept at vLLM's level 2 keeps its containers and answers
    ``/v1/models``, and then hangs on a real request. So it never gives the
    instant refusal fail-first waits for, and liveness reads it as up. This
    mark is what mcgyvr knows instead: written when a ``serve sleep`` of the
    card worked, and removed by any wake or stop of it that worked. Reading it
    is a file lookup and no network, so a dispatch that finds no mark costs
    what it cost before.

    Host-wide, beside the wake history and for the same reason: the manager
    that slept the card and the task that next climbs to it are different
    processes. A directory that is not ours is no mark.
    """
    where = _clock_dir()
    if not _ours(where):
        return False
    if port is not None:
        return _rest_mark(host, port).exists()
    prefix, suffix = f"{_safe(host)}-", ".resting"
    try:
        names = os.listdir(where)
    except OSError:
        return False
    return any(
        name.startswith(prefix)
        and name.endswith(suffix)
        and name[len(prefix) : -len(suffix)].isdigit()
        for name in names
    )


def _note_rest(made: Wake) -> None:
    """Keep the resting mark in step with a door run that worked; best-effort."""
    if not made.ok:
        return
    try:
        where = _clock_dir()
        where.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not _ours(where):
            return
        for port in made.ports:
            if made.direction == "sleep":
                _rest_mark(made.host, port).touch()
            else:
                _rest_mark(made.host, port).unlink(missing_ok=True)
    except OSError:
        return


def _wake_direction(card: Card, ports: Sequence[int] = ()) -> str:
    """``wake`` for units resting with their process kept, ``up`` for a card stopped.

    ``serve up`` opens only on an idle rig, and a resting unit's container is
    running, so the door would refuse it; ``serve wake`` is the route back.
    ``ports`` are the units asked about; none is the whole card.
    """
    if ports:
        return "wake" if any(resting(card.host, port) for port in ports) else "up"
    return "wake" if resting(card.host) else "up"


def _ports(config: Config, rungs: Sequence[str]) -> tuple[int, ...]:
    """The ports the named rungs' units serve on, from the config."""
    return tuple(
        port_of(config.units[rung].address) for rung in rungs if rung in config.units
    )


def _all_vllm(config: Config, card: Card) -> bool:
    """Whether every unit of the card is vLLM, so each can sleep at level 2."""
    units = [config.units.get(name) for name in card.sources]
    return bool(units) and all(
        unit is not None and unit.engine == "vllm" for unit in units
    )


def _unit_containers(
    config: Config, card: Card, compose: Path, rungs: Sequence[str]
) -> tuple[str, ...] | None:
    """The containers that serve ``rungs`` in the card's launch spec, or ``None``.

    Matched by port: a unit's address names the port, and the spec's command
    names it too (the door reads both the same way, :func:`servelib.services`).
    ``None`` when the spec cannot be read that way or does not hold a rung's
    port — then nothing can act on one unit alone, and the card acts whole.
    """
    from mcgyvr.serving import servelib

    try:
        by_port = {
            service.port: service.container for service in servelib.services(compose)
        }
    except (servelib.ComposeError, OSError):
        return None
    found: list[str] = []
    for port in _ports(config, rungs):
        if port not in by_port:
            return None
        found.append(by_port[port])
    return tuple(found) if len(found) == len(rungs) else None


def _per_unit(config: Config, card: Card) -> bool:
    """Whether this card's units sleep and wake one at a time.

    A card of co-resident vLLM units, each its own container in the card's one
    launch spec: each can sleep at level 2 alone, so one can make room for
    another. Every other card acts whole.
    """
    if len(card.rungs) < 2 or not _all_vllm(config, card):
        return False
    compose = compose_for(card)
    return compose is not None and (
        _unit_containers(config, card, compose, card.rungs) is not None
    )


def card_rooms(scans: Mapping[str, Scan]) -> dict[str, dict[int, int]]:
    """Each scanned host's card memory in MiB, by card index.

    The figure ``emit`` sizes a card against, from the scan ``mcgyvr scan``
    recorded, keyed by the index the scan read the card at — the index ``emit``
    reserves for a unit in its launch spec. Which card a unit is on is the
    spec's to say, not the config's (:meth:`CardSwitches.room_for`).
    """
    return {
        host: {gpu.index: gpu.vram.total_mib for gpu in scan.gpus}
        for host, scan in scans.items()
        if scan.gpus
    }


def compose_for(card: Card) -> Path | None:
    """The launch spec that would bring this card back, if there is exactly one.

    **One, or none, and never a choice.** A card whose directory holds several
    of mcgyvr's launch specs is a card mcgyvr cannot bring back, because
    ``serve up`` starts one file and nothing in a config says which of them is
    the current one (D2, ``mcgyvr-lab/records/plans/sleep-wake.md``). Picking is not a
    tie-break to be got right later; it is the fleet-shape controller's question
    (``mcgyvr-lab/records/plans/fleet-shape/``) and no line of it is implemented.

    Declining is not conservatism for its own sake. ``emit`` deletes nothing,
    so a leftover ``compose.<host>.yml`` can hold units that do not sum onto
    the card, and a name-based pick would start it — the overcommit
    ``hold_together`` refuses — with ``emit --check`` clean, because a check
    reads only the paths a config plans.

    :func:`mcgyvr.emit.unplanned` is the other half: it names the leftover so
    the operator can delete it, and one spec is left, and this answers again.
    """
    if len(card.specs) == 1:
        return card.specs[0]
    return None


def wakeable_rungs(config: Config) -> tuple[str, ...]:
    """The rung names whose card this config can wake, in ladder order.

    The read-only half of :meth:`Waker.wake_for`: which rungs *could* be woken
    — their card is asleep, meaning down but holding exactly one launch spec
    mcgyvr wrote — without the door run that does it. The one-or-none rule is
    :func:`compose_for`'s, reused rather than restated. A caller that wants to
    *route* to an asleep rung reads this; a caller that wants to wake one asks
    :meth:`Waker.wake_for`.
    """
    return tuple(
        name for name, card in cards(config).items() if compose_for(card) is not None
    )


def _why_not_one(card: Card) -> str:
    """The sentence a caller is owed when there is no single spec to start."""
    if not card.specs:
        return (
            f"{card.host}: this config holds no launch spec for that card. "
            f"`asleep` is `down` plus a file mcgyvr wrote, and there is no "
            f"file: set `serving.compose_dir` to where `mcgyvr emit --out` "
            f"wrote, and emit if it has not been emitted"
        )
    listed = ", ".join(path.name for path in card.specs)
    return (
        f"{card.host}: this config holds {len(card.specs)} launch specs for "
        f"that card — {listed} — and only one of them is ever up. Which one is "
        f"current is not a question the config answers, so mcgyvr will not "
        f"guess: name the file to `python -m {DOOR_MODULE} serve` yourself. If "
        f"one of these is an older cut of the rig, `mcgyvr emit --check` says "
        f"which, and deleting it leaves one"
    )


def _run_door(
    config: Config,
    card: Card,
    direction: str,
    compose: Path,
    *,
    only: Sequence[str] = (),
) -> Wake:
    """One door run for ``card``; ``only`` names the rungs a sleep or wake acts on.

    ``only`` empty, or rungs whose containers the spec does not name, is the
    whole card.
    """
    predicted = predicted_wake_s(card)
    containers = (
        _unit_containers(config, card, compose, only)
        if only and direction in ("sleep", "wake")
        else None
    )
    acting = tuple(only) if containers is not None else card.rungs
    started = time.monotonic()
    code = spawn_door(
        door_argv(
            direction=direction,
            host=card.host,
            compose=compose,
            suffix=_suffix(),
            units=containers or (),
        )
    )
    made = Wake(
        host=card.host,
        compose_file=compose,
        direction=direction,
        seconds=time.monotonic() - started,
        predicted_s=predicted,
        code=code,
        ports=_ports(config, acting),
    )
    _remember(made)
    _note_rest(made)
    said = made.deviation
    if said is not None:
        print(f"warning: {said}", file=sys.stderr)
    return made


class Waker:
    """The dispatch-time half: a refused port becomes a wake and one retry.

    Built by :func:`for_config` and ``None`` for a config that did not ask, so
    that "the switch is off" and "the feature does not exist" are the same code
    path rather than a branch that could be got wrong. That equality is the
    design's safety property: mcgyvr must not be able to take a card down for an
    operator who did not ask, and a switch that gated only *some* of the
    behaviour would leave "asked" meaning nothing.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._cards = cards(config)
        #: Cards this run has already woken, with whether the wake worked and
        #: when it ended. One wake per card per run: a refusal after a
        #: successful wake is a real fault of the rung — the card is up and
        #: something else is wrong — and re-running the door for it would
        #: spend minutes of rig time proving that twice.
        self._woken: dict[str, tuple[bool, float]] = {}
        #: The draws of one attempt are dispatched together, so two of them
        #: can be refused by the same sleeping card at once. One wake per card
        #: per run has to hold across them, so each card's check-then-wake is
        #: taken under that card's own lock: a draw refused while the door
        #: runs waits for it and is sent again if it worked, and a wake of one
        #: card never waits on another's. `_lock` guards only the map.
        self._lock = threading.Lock()
        self._card_locks: dict[str, threading.Lock] = {}

    def dispatching(self, rung: str, send: Callable[[], Answer]) -> Answer:
        """Send, and on a refused port wake the card once and send again.

        The retry spends **no attempt**: nothing was asked and nothing answered,
        which is the rule ``drive`` already applies to a declined rung and the
        reason it has to hold here too — a refusal charged as a failure would
        exhaust a one-attempt rung on a card that was merely off.

        A wake that *fails* is a different thing and is a real verdict against
        the rung: the original refusal is re-raised with the door's exit code
        left where the operator can read it, and the run reports the transport
        fault it actually had.
        """
        card = self._cards.get(rung)
        if card is not None and any(
            resting(card.host, port) for port in _ports(self._config, (rung,))
        ):
            # Slept with its process kept: it would answer and then hang, so
            # the refusal fail-first waits for never comes. The mark is that
            # refusal, and the wake is the same one a refusal earns.
            if not self.wake_for(rung, refused_at=time.monotonic()):
                raise RefusedConnectionError(
                    f"{rung}: its card {card.host} was put to sleep with its "
                    "process kept, and could not be woken"
                )
            return send()
        try:
            return send()
        except RefusedConnectionError as refused:
            # Only a refusal. A timeout is a card that is up and busy, and
            # waking it would start a door run and send the generation twice.
            if not self.wake_for(rung, refused_at=time.monotonic()):
                raise refused
            return send()

    def wake_for(self, rung: str, *, refused_at: float | None = None) -> bool:
        """Bring this rung's card back, or say why nothing was tried.

        ``False`` is not a failure. It is every one of the honest degradations
        D2 asks for — an api rung, a rig somebody else runs, a config that
        states no ``compose_dir``, a card mcgyvr never wrote a spec for, and a
        card this run has already woken once — and in each of them the caller's
        refusal stands exactly as it stands today.

        ``refused_at`` is when the caller was refused. A refusal from before a
        wake of this card ended was given by the sleeping card, so the caller
        gets that wake's result and sends again; one from after it is the real
        fault above, and gets ``False``.
        """
        card = self._cards.get(rung)
        if card is None:
            return False
        with self._lock:
            card_lock = self._card_locks.setdefault(card.host, threading.Lock())
        with card_lock:
            return self._wake_for(card, refused_at, rung)

    def _wake_for(self, card: Card, refused_at: float | None, rung: str) -> bool:
        # A card of co-resident vLLM units wakes one unit at a time, so a run
        # remembers each unit's wake; any other card wakes whole, once.
        alone = _per_unit(self._config, card)
        key = f"{card.host}:{rung}" if alone else card.host
        if key in self._woken:
            ok, ended = self._woken[key]
            return ok and refused_at is not None and refused_at < ended
        # Live wakes only along a listed switch, and a switch exists only on a
        # locked fleet. With no live lock naming this rig — the lock of the
        # fleet the config folder's live.json names, never whatever directory
        # the run was started in — there is no switch to be along, so the wake
        # is refused
        # before any door run. No live.json is no live lock.
        if self._config.get("profile") == "live":
            from mcgyvr.fleet.admit import host_is_locked
            from mcgyvr.fleet.roots import LiveFleetError, lock_root

            try:
                root = lock_root("live")
            except LiveFleetError as exc:
                print(f"warning: {exc}", file=sys.stderr)
                return False
            if root is None or not host_is_locked(root, card.host):
                return False
        compose = compose_for(card)
        if compose is None:
            # `down`, not `asleep`. Waking a card mcgyvr never sized would be
            # sizing and starting in one act, which is exactly what
            # `mcgyvr.emit`'s boundary forbids: sizing is a judgement a person
            # reviews.
            #
            # A card with *several* specs is the same refusal for the opposite
            # reason, and it is the one worth a sentence: nothing is missing,
            # something is ambiguous, and the difference is a directory listing
            # an operator has not looked at. Said once per card per run — the
            # `_woken` map is what bounds it — because a rung that declines for
            # a reason only the filesystem holds is the silence this whole
            # module exists to stop.
            if card.specs:
                self._woken[key] = (False, time.monotonic())
                print(f"warning: {_why_not_one(card)}", file=sys.stderr)
            return False
        if alone:
            direction = _wake_direction(card, _ports(self._config, (rung,)))
            only: tuple[str, ...] = (rung,) if direction == "wake" else ()
        else:
            direction, only = _wake_direction(card), ()
        ok = _run_door(self._config, card, direction, compose, only=only).ok
        self._woken[key] = (ok, time.monotonic())
        return ok


def for_config(config: Config) -> Waker | None:
    """A waker for this run, or ``None`` where the config did not ask for one.

    Two keys and both of them have to be there. ``enable_sleep_wake`` is the
    permission and ``compose_dir`` is the means: a config that says yes and
    names no directory holds no launch spec for anything, so there is nothing
    to wake and nothing to be wrong about.
    """
    if not config.get("serving.enable_sleep_wake"):
        return None
    if not config.get("serving.compose_dir"):
        return None
    return Waker(config)


def card_named(config: Config, host: str) -> Card:
    """The card an operator named by host, refused by name where there is none."""
    for card in cards(config).values():
        if card.host == host:
            return card
    known = sorted({card.host for card in cards(config).values()})
    raise WakeError(
        f"no rung of this ladder is served by {host!r}"
        + (f" — this config's rigs are {', '.join(known)}" if known else "")
    )


def sleep(config: Config, host: str) -> Wake:
    """Take the whole card down, after draining every slot it serves.

    **Whole-card eviction is not a behaviour to build; it is the behaviour
    ``serve down`` already has**, because the down step tears down every service
    in the file it is given. On a host of co-residents that file is the host's
    and the sentence is exact — every unit in it goes down together, in one door
    run, and the operator never spells a container name.

    **The drain is the caller's and is not optional in practice.** An eviction
    takes all of the card's slots before it takes the card down, never
    interrupts a dispatch already in flight, and is best-effort against
    processes the flock cannot see (D8) — and the thing that owns those slots is
    a :class:`~mcgyvr.capacity.Capacity`, which is built from a config by the
    caller and is not this module's to construct. So the drain is spelled where
    the capacity is, as ``capacity.drain(card.sources)`` around this call, and
    :func:`mcgyvr.cli._serve` is the worked example. Calling this without one is
    correct only where there is no capacity at all; with one and unused, it is
    killing containers out from under requests that were already admitted.
    """
    card = card_named(config, host)
    compose = compose_for(card)
    if compose is None:
        raise WakeError(_why_not_one(card))
    return _run_door(config, card, "down", compose)


def wake(config: Config, host: str) -> Wake:
    """Bring the whole card back, through the door and through nothing else."""
    card = card_named(config, host)
    compose = compose_for(card)
    if compose is None:
        # Two refusals in one sentence, and `_why_not_one` tells them apart. No
        # spec at all is emit's boundary — waking a card mcgyvr never sized
        # would be sizing and starting in one act. Several specs is D2's gap:
        # mcgyvr holds the files and not the answer to which.
        raise WakeError(_why_not_one(card))
    return _run_door(config, card, _wake_direction(card), compose)


def drain_timeout(config: Config, card: Card) -> float | None:
    """How long a sleep of ``card`` waits for each of its slots, or ``None``.

    A dispatch in flight either finishes inside its own unit's transport bound
    or the transport has already given up on it, so waiting longer than that is
    waiting for something that is no longer running. The card may hold units
    with different bounds; the longest is what covers them all. ``None`` where
    no unit of the card states one: the drain then waits as long as it takes,
    which is :meth:`~mcgyvr.capacity.Capacity.drain`'s own default.

    One place for it, because a person's ``mcgyvr serve sleep`` and the ladder
    manager's :class:`CardSwitches` drain the same card and must not wait
    differently for it.
    """
    timeouts: list[float] = []
    for name in card.sources:
        unit = config.units.get(name)
        if unit is not None and unit.request_timeout_s is not None:
            timeouts.append(unit.request_timeout_s)
    return max(timeouts) if timeouts else None


class CardSwitches:
    """The ladder manager's two verbs, thrown through the door ``serve`` uses.

    :class:`mcgyvr.ladder_manager.Switches` is a protocol over rung names; this
    is its answer, and it adds nothing to what a person typing ``mcgyvr serve``
    can do. A sleep comes after a drain. For a card whose units are all vLLM
    it is the door's ``sleep``: vLLM's level 2, which keeps the process and
    drops the weights and KV cache. For any other card, and for a vLLM card
    with no sleep route, it is the door's ``down``: the containers stop. A wake
    is the door's ``wake`` for a card resting at level 2, which reads the
    weights back into the same process, and ``up`` for one that was stopped.
    Both verbs are gated by ``serving.enable_sleep_wake``
    — the switch exists so that mcgyvr takes no card down or up on its own
    unless asked, and this is the "on its own" (``mcgyvr serve`` is the person
    asking, and is not gated).

    **A fresh waker per wake.** :class:`Waker` remembers that it woke a card so
    that one run wakes it once. The manager lives for hours and may wake a card
    it slept in between, so each wake builds its own and the memory dies with
    it. The live-lock gate inside :meth:`Waker._wake_for` therefore applies to
    every wake the manager makes.

    **A sleep is a drain and then the door.** The card's slots are taken before
    its containers are stopped (:meth:`~mcgyvr.capacity.Capacity.drain`), and a
    dispatch that is still running is a sleep that does not happen now: ``False``,
    and the manager asks again on a later tick. So is a dispatch that queued for
    the card while the drain held it (:meth:`~mcgyvr.capacity.Capacity.queued`),
    and a capacity with no gauge to say: either would take a slot as the card
    went down and wake it straight back up. A door that fails, or refuses, is
    ``False`` as well.

    **A card goes whole, except a card of co-resident vLLM units.** Sleep
    evicts the entire card and wake brings the entire launch spec back, which
    was sized whole by ``emit``. A card whose co-resident units are all vLLM is
    the exception: each unit is its own process and sleeps at level 2 alone
    (``serve sleep --unit``), so :meth:`card_of` is the unit and one unit can
    make room for another.

    **Room is arithmetic on facts already held.** :meth:`room_for` adds each
    unit's ``room_mib`` and compares the sum with the memory of the card the
    waking unit is on, from the host's recorded scan (``card_mib``, by card
    index, :func:`card_rooms`). The card a unit is on is the one its launch
    spec reserves for it — what ``emit`` wrote and the door starts — so on a
    host with several cards only the units on that card are neighbours. Where
    the unit waking does not fit beside them, the smallest of them sleep first
    until it does. A missing figure, or a card that cannot be told, is no
    answer: no room is made, and :meth:`why_no_room` says why.
    """

    def __init__(
        self,
        config: Config,
        capacity: Capacity,
        *,
        card_mib: Mapping[str, Mapping[int, int]] | None = None,
    ) -> None:
        self._config = config
        self._capacity = capacity
        self._cards = cards(config)
        self._card_mib = {host: dict(sizes) for host, sizes in (card_mib or {}).items()}

    def _allowed(self) -> bool:
        return bool(
            self._config.get("serving.enable_sleep_wake")
            and self._config.get("serving.compose_dir")
        )

    def wake(self, rung: str) -> bool:
        """Bring the rung's card back through the door; ``False`` if it was not."""
        waker = for_config(self._config)
        return waker is not None and waker.wake_for(rung)

    def sleep(self, rung: str) -> bool:
        """Drain the rung's card and take it down; ``False`` if it was not."""
        if not self._allowed():
            return False
        card = self._cards.get(rung)
        if card is None or compose_for(card) is None:
            return False
        alone = _per_unit(self._config, card)
        # One unit of a shared vLLM card drains alone; any other card whole.
        sources = (rung,) if alone else card.sources
        try:
            with self._capacity.drain(
                sources, timeout=drain_timeout(self._config, card)
            ):
                # The drain holds every slot, so anyone queued now is a dispatch
                # that would take one the moment the card went down, be refused,
                # and wake it again. Not now, then; and no reading is not zero.
                if self._capacity.queued(sources) != 0:
                    return False
                return self._put_down(card, (rung,) if alone else ())
        except (SlotUnavailableError, WakeError):
            return False

    def _put_down(self, card: Card, only: tuple[str, ...]) -> bool:
        """Sleep a vLLM card at level 2, and stop any other; inside the drain.

        A card all of whose units are vLLM is asked to sleep first (``serve
        sleep``): the process stays, the weights and KV cache leave the card,
        and the wake reads them back without a container start. One that turns
        out to have no sleep route — vLLM run without its development routes
        — is left exactly as it was by that run, which says so with
        :data:`~mcgyvr.serving.gatelib.NO_SLEEP_ROUTE`, and is stopped
        instead. Any other engine has no sleep to ask for and is stopped.
        ``only`` is the one unit of a shared vLLM card to sleep; the fallback
        stops the whole card, which is the only stop there is.
        """
        if _all_vllm(self._config, card):
            compose = compose_for(card)
            if compose is None:
                return False
            asked = _run_door(self._config, card, "sleep", compose, only=only)
            if asked.code != NO_SLEEP_ROUTE:
                return asked.ok
        return sleep(self._config, card.host).ok

    def room_for(self, rung: str) -> tuple[str, ...]:
        """The co-resident units that must sleep before ``rung`` can wake.

        Only on a card of co-resident vLLM units, and only from figures held:
        every unit's ``room_mib``, the card each is on and that card's memory.
        Where the waking unit and its neighbours on its card do not fit, the
        smallest neighbours are named first until the rest would. ``()`` where
        they fit, or where there is no answer (:meth:`why_no_room`).
        """
        return self._room(rung)[0]

    def why_no_room(self, rung: str) -> str | None:
        """Why no room can be reckoned for ``rung`` on its card, or ``None``.

        ``None`` too where room is not a question: a card that acts whole.
        """
        return self._room(rung)[1]

    def _room(self, rung: str) -> tuple[tuple[str, ...], str | None]:
        card = self._cards.get(rung)
        if card is None or not _per_unit(self._config, card):
            return (), None
        sizes = self._card_mib.get(card.host, {})
        if not sizes:
            return (), (
                f"no recorded scan gives {card.host}'s card memory "
                f"(`mcgyvr scan` records one)"
            )
        rooms: dict[str, int] = {}
        for name in card.rungs:
            unit = self._config.units.get(name)
            if unit is None or unit.room_mib is None:
                return (), f"{name} states no room_mib"
            rooms[name] = unit.room_mib
        on = self._placement(card, sizes)
        if isinstance(on, str):
            return (), on
        index = on[rung]
        if index not in sizes:
            return (), (
                f"no recorded scan of {card.host} has card {index}, which {rung} is on"
            )
        others = sorted(
            (r for r in card.rungs if r != rung and on[r] == index),
            key=lambda r: (rooms[r], r),
        )
        total = rooms[rung] + sum(rooms[r] for r in others)
        making: list[str] = []
        for other in others:
            if total <= sizes[index]:
                break
            making.append(other)
            total -= rooms[other]
        return tuple(making), None

    def _placement(self, card: Card, sizes: Mapping[int, int]) -> dict[str, int] | str:
        """The card index each rung of ``card`` is on, or why it cannot be told.

        Read from the reservation in the launch spec, matched by port as the
        door matches it. A service that reserves no card is on the host's only
        card, and on a host of several it is on a card nobody can name. A
        service reserving several cards is a unit split across them, whose
        share of each this does not reckon, and an id that is not an index is
        not one a scan can be read at.
        """
        from mcgyvr.serving import servelib

        compose = compose_for(card)
        if compose is None:
            return _why_not_one(card)
        try:
            by_port = {service.port: service for service in servelib.services(compose)}
        except (servelib.ComposeError, OSError) as exc:
            return f"its launch spec cannot be read: {exc}"
        on: dict[str, int] = {}
        for name in card.rungs:
            service = by_port.get(port_of(self._config.units[name].address))
            ids = service.devices if service is not None else ()
            if not ids:
                if len(sizes) == 1:
                    on[name] = next(iter(sizes))
                    continue
                return (
                    f"{compose.name} does not say which card {name} is on, and "
                    f"{card.host} has {len(sizes)} cards"
                )
            if len(ids) > 1:
                return (
                    f"{name} is reserved more than one card ({', '.join(ids)}) "
                    f"in {compose.name}, and room is reckoned one card at a time"
                )
            if not ids[0].isdigit():
                return (
                    f"{compose.name} names {name}'s card {ids[0]!r}, not by the "
                    f"index a scan reads it at, so which card it is cannot be told"
                )
            on[name] = int(ids[0])
        return on

    def card_of(self, rung: str) -> tuple[str, ...]:
        """The rungs a sleep of ``rung`` takes down: the unit alone on a card of
        co-resident vLLM units, every rung the card serves otherwise, and the
        rung alone where it has no card."""
        card = self._cards.get(rung)
        if card is None:
            return (rung,)
        return (rung,) if _per_unit(self._config, card) else tuple(card.rungs)
