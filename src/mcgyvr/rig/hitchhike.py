"""What this rig shares with riders, and what it tells the hub of it.

The host's agent advertises the units of its ladder that may take riders the
hub matches to it (a ``unit_advert``), and admits or refuses the rides the hub
then sends. This module is that policy and the state behind it:

* :func:`shared_units` walks the ladder and returns the units that may be
  shared, with a note on each it left out for a reason a host can fix.
* :class:`Shared` is one such unit: its wire id, model and address, its
  ``width`` as ``slots``, its ``window`` as ``ctx``, and its ``rider_slots`` as
  ``rider_cap``. :meth:`Shared.url` is where a ride's request goes.
* :func:`free_slots` is what the host's own requests leave open to riders.
* :class:`Units` sends the advert while the channel is up, and admits a ride
  only while the unit has a slot free and fewer than ``rider_cap`` rides run.

Nothing here opens a connection or sends anything itself: the send, the setup
read, the clock and the thread a check runs on are all handed in.
"""

from __future__ import annotations

import hashlib
import re
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.capacity import SlotUnavailableError
from mcgyvr.rig import protocol, sessionwire
from mcgyvr.rig.relay import SEND_WAIT_S, RideRefusedError
from mcgyvr.rig.sessionwire import SessionCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config

#: The least time between two adverts: a change found sooner after
#: the last one is left to the check after it rather than sent now.
ADVERT_GAP_S = 1.0
#: How often the ticker ticks, and so the least time between two
#: checks: a tick less than this after the last check does nothing.
POLL_S = 0.25
#: How many hex digits of the name's digest a made-up id keeps.
_DIGEST_DIGITS = 16

_NOT_ID = re.compile(r"[^A-Za-z0-9_-]")
_ALNUM = re.compile(r"[A-Za-z0-9]")
#: The longest an id made from a name may be: the width of a message id.
_MAX_ID = 64


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="shared-units", daemon=True).start()


@dataclass(frozen=True, kw_only=True)
class Shared:
    """One unit of the ladder that is offered to riders.

    ``slots`` is the unit's width and ``ctx`` its window, the context of
    one slot; ``rider_cap`` is the policy's ``rider_slots``, the most
    rides that run on it at once; ``address`` is where the unit answers.
    """

    unit_id: str
    name: str
    model: str
    address: str
    slots: int
    ctx: int
    rider_cap: int

    def url(self, endpoint: str) -> str:
        """The URL of ``endpoint``'s relay path on this unit's address."""
        from mcgyvr.runner import _url_for

        return _url_for(self.address, sessionwire.RELAY_PATHS[endpoint])


def _unit_id(name: str, taken: set[str]) -> str:
    """The wire id for ``name``, the same each time for the same setup.

    The name itself where it is already a message id, the name with every
    other character made a dash and cut to ``_MAX_ID`` where that leaves a
    letter or a digit, and a short digest of the name where neither holds
    or the name is taken.
    """
    if protocol.MESSAGE_ID.fullmatch(name) and name not in taken:
        return name
    made = _NOT_ID.sub("-", name)[:_MAX_ID]
    if _ALNUM.search(made) and made not in taken:
        return made
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:_DIGEST_DIGITS]
    return f"u-{digest}"


def shared_units(config: Config) -> tuple[tuple[Shared, ...], tuple[str, ...]]:
    """The units of the ladder that may take riders, and why others may not.

    A unit is passed over without a word where it never takes riders: no
    ``rider_slots``, a relief rung, one that needs a credential, or a width
    under two, which leaves no slot to lend. A width over ``MAX_SLOTS``, a
    ``window`` missing or outside ``MIN_CTX`` to ``MAX_CTX``, a model name
    the hub cannot carry, a model an accepted unit already shares, and a
    rig that already found ``MAX_UNITS`` units each leave the unit out with
    one note saying so. Units come back in ladder order, each with an id no
    unit before it took.
    """
    found: list[Shared] = []
    notes: list[str] = []
    taken: set[str] = set()
    models: dict[str, str] = {}
    for name in config.ladder.names:
        unit = config.units[name]
        if unit.rider_slots < 1 or unit.relief or unit.requires_credential:
            continue
        width = unit.width or 1
        if width < 2:
            continue  # a unit of one slot lends no slot to a rider
        if width > sessionwire.MAX_SLOTS:
            notes.append(
                f"unit {name!r} is not shared with riders: its width, {width}, is "
                f"more than the {sessionwire.MAX_SLOTS} slots the hub takes"
            )
            continue
        window = unit.window
        if window is None or not sessionwire.MIN_CTX <= window <= sessionwire.MAX_CTX:
            stated = "states no `window`" if window is None else f"has window {window}"
            notes.append(
                f"unit {name!r} is not shared with riders: it {stated}, and a "
                f"ride's context is one slot's window, {sessionwire.MIN_CTX} to "
                f"{sessionwire.MAX_CTX} tokens"
            )
            continue
        if not protocol.MODEL_NAME.fullmatch(unit.model):
            notes.append(
                f"unit {name!r} is not shared with riders: its model's name is "
                f"not one the hub carries"
            )
            continue
        first = models.get(unit.model)
        if first is not None:
            notes.append(
                f"unit {name!r} is not shared with riders: {first!r} shares "
                f"{unit.model!r} already, and riders are matched one unit per model"
            )
            continue
        if len(found) >= sessionwire.MAX_UNITS:
            notes.append(
                f"unit {name!r} is not shared with riders: the hub takes "
                f"{sessionwire.MAX_UNITS} units from one rig"
            )
            continue
        unit_id = _unit_id(name, taken)
        taken.add(unit_id)
        models[unit.model] = name
        found.append(
            Shared(
                unit_id=unit_id,
                name=name,
                model=unit.model,
                address=unit.address,
                slots=width,
                ctx=window,
                rider_cap=unit.rider_slots,
            )
        )
    return tuple(found), tuple(notes)


def free_slots(slots: int, in_flight: int | None, riding: int) -> int:
    """How many of a unit's ``slots`` are open to riders right now.

    ``in_flight`` is the unit's server count of the requests it is serving,
    and ``riding`` the rides this agent is serving on it, which are not the
    host's own. A server that does not say (``None``) is read as full, so
    nothing is free on a guess. The answer runs from none to ``slots``.
    """
    if in_flight is None:
        return 0
    own = min(slots, max(0, in_flight - riding))
    return slots - own


def _unread(unit: Shared) -> int | None:
    return None


def _no_hold(unit: Shared) -> AbstractContextManager[None]:
    return nullcontext()


@dataclass(frozen=True, kw_only=True)
class Setup:
    """What may be shared now, and how a unit's state is read and held.

    ``in_flight`` answers with the unit's server count, or ``None`` where
    the server does not say; the default never says, so nothing is ever
    free. ``hold`` takes a slot on the unit for the length of its block
    and raises ``SlotUnavailableError`` where it cannot; the default
    takes no slot.
    """

    units: tuple[Shared, ...] = ()
    notes: tuple[str, ...] = ()
    in_flight: Callable[[Shared], int | None] = field(default=_unread)
    hold: Callable[[Shared], AbstractContextManager[None]] = field(default=_no_hold)


def setup_of(config: Config) -> Setup:
    """The setup of ``config``, with its units' state read from this rig now.

    Where the setup shares nothing, the notes carry why and the stubs stay.
    Where it shares something, a ``Capacity`` built over the local pool's
    server counts answers for a unit with what its server has in flight, and
    holding a unit takes a slot from that capacity with no wait.
    """
    from mcgyvr.capacity import Capacity
    from mcgyvr.local_pool import source_map
    from mcgyvr.pressure import server_counts

    units, notes = shared_units(config)
    if not units:
        return Setup(notes=notes)
    capacity = Capacity.of(config, busy=server_counts(source_map(config)))
    return Setup(
        units=units,
        notes=notes,
        in_flight=lambda unit: capacity.server_busy(unit.name),
        hold=lambda unit: capacity.hold(unit.name, timeout=0),
    )


def load_setup(path: Path | None = None) -> Setup:
    """The setup of the config at ``path``, or of the default config.

    A config that is not there is a setup that shares nothing and has
    nothing to say; a config or a capacity that does not hold gives a setup
    that shares nothing and says why in one note.
    """
    from mcgyvr.capacity import CapacityError
    from mcgyvr.config import ConfigError, ConfigMissingError, load

    try:
        return setup_of(load(path))
    except ConfigMissingError:
        return Setup()
    except (ConfigError, CapacityError) as exc:
        return Setup(notes=(f"no unit is shared with riders: {exc}",))


class Units:
    """The units this agent shares, and the rides it may admit on them.

    Under the lock it keeps whether the channel is up, whether a check is
    running, when the last check and the last advert were, the advert last
    sent, the units a ride may name now with the setup they were read from,
    and how many rides each unit is serving.
    """

    def __init__(
        self,
        *,
        send: Callable[..., bool],
        setup: Callable[[], Setup] = load_setup,
        clock: Callable[[], float] = time.monotonic,
        say: Callable[[str], None] = _say,
        start: Callable[[Callable[[], None]], None] = _thread,
    ) -> None:
        self._send = send
        self._setup = setup
        self._clock = clock
        self._say = say
        self._start = start
        self._lock = threading.Lock()
        self._online = False
        self._going = False
        self._asked = False
        self._checked_at: float | None = None
        self._sent_at: float | None = None
        self._last: tuple[sessionwire.AdvertisedUnit, ...] = ()
        self._riding: dict[str, int] = {}
        self._shared: dict[str, Shared] = {}
        self._served: tuple[Shared, ...] = ()
        self._serving = Setup()
        self._said: set[str] = set()
        self._closed = threading.Event()

    # The serve path's handle on this: what the setup shares, and the
    # channel's going up, coming down and coming to an end.

    def shares(self) -> bool:
        """Whether the setup read now shares any unit with riders."""
        return bool(self._setup().units)

    def online(self) -> None:
        """The channel came up: send a full advert of what is shared."""
        with self._lock:
            self._online = True
            self._asked = True
            self._checked_at = None
            self._sent_at = None
            self._last = ()
        self.tick()

    def offline(self) -> None:
        """The channel went down: send nothing, and name no unit for a ride.

        The advert last sent and the units a ride may name are dropped, so a
        ride that arrives meanwhile names no unit and is refused as unknown.
        """
        with self._lock:
            self._online = False
            self._last = ()
            self._shared = {}
            self._served = ()

    def close(self) -> None:
        """Go offline for good, and end the ticker thread."""
        self.offline()
        self._closed.set()

    def run_ticker(self) -> None:
        """Start a daemon thread that ticks every ``POLL_S`` until ``close``."""

        def ticking() -> None:
            while not self._closed.wait(POLL_S):
                self.tick()

        threading.Thread(target=ticking, name="shared-units-tick", daemon=True).start()

    # The hub's side: the unit a ride names, admitting that ride, and the
    # checks that keep the advert true.

    def advertised(self, unit_id: str) -> Shared | None:
        """The unit advertised under ``unit_id`` now, or ``None``."""
        with self._lock:
            return self._shared.get(unit_id)

    @contextmanager
    def ride(self, unit_id: str) -> Iterator[None]:
        """Hold one of a unit's free slots for the length of the block.

        Refused with ``SessionCode.UNKNOWN_UNIT`` where no unit is advertised
        under that id, and with ``SessionCode.BUSY`` where the unit already
        serves ``rider_cap`` rides, where the host's own requests leave no
        slot for another, or where the capacity book has no slot to hold.
        The ride is counted out and a check asked for when the block ends,
        however it ends.
        """
        with self._lock:
            unit = self._shared.get(unit_id)
            setup = self._serving
        if unit is None:
            raise RideRefusedError(SessionCode.UNKNOWN_UNIT)
        in_flight = setup.in_flight(unit)
        with self._lock:
            riding = self._riding.get(unit_id, 0)
            free = free_slots(unit.slots, in_flight, riding)
            if riding >= unit.rider_cap or riding >= free:
                raise RideRefusedError(SessionCode.BUSY)
            self._riding[unit_id] = riding + 1
        try:
            with ExitStack() as held:
                try:
                    held.enter_context(setup.hold(unit))
                except SlotUnavailableError as exc:
                    raise RideRefusedError(SessionCode.BUSY) from exc
                yield
        finally:
            with self._lock:
                self._riding[unit_id] -= 1
            self.soon()

    # Sending: a full check on request, and the tick that decides what is
    # due to be sent.

    def soon(self) -> None:
        """Ask for a full check now: a unit's free slots have changed."""
        with self._lock:
            self._asked = True
        self.tick()

    def tick(self) -> None:
        """Start a check on a background thread, unless it can wait.

        It returns while the channel is down, while a check is already
        running, and while the last check was less than ``POLL_S`` ago.
        The check is full when one was asked for, or when
        ``UNIT_ADVERT_INTERVAL_S`` has gone by since the last advert;
        light otherwise, which sends nothing while the setup's units are
        what they were.
        """
        with self._lock:
            if not self._online or self._going:
                return
            now = self._clock()
            if self._checked_at is not None and now - self._checked_at < POLL_S:
                return
            refresh = (
                bool(self._last)
                and self._sent_at is not None
                and now - self._sent_at >= sessionwire.UNIT_ADVERT_INTERVAL_S
            )
            full = self._asked or refresh
            self._going = True
            self._asked = False
            self._checked_at = now
        self._start(lambda: self._check(full))

    def _serve(self, setup: Setup) -> None:
        """Make ``setup`` the one adverts and rides are read from."""
        self._shared = {unit.unit_id: unit for unit in setup.units}
        self._served = setup.units
        self._serving = setup

    def _note(self, line: str) -> None:
        with self._lock:
            if line in self._said:
                return
            self._said.add(line)
        self._say(f"note: {line}")

    def _check(self, full: bool) -> None:
        try:
            setup = self._setup()
            for line in setup.notes:
                self._note(line)
            with self._lock:
                if not full and setup.units == self._served:
                    return  # a light check of the same units
            advert = []
            for unit in setup.units:
                in_flight = setup.in_flight(unit)
                if in_flight is None:
                    self._note(
                        f"unit {unit.name!r} is shared with no free slot: its "
                        f"server does not say what it has in flight"
                    )
                with self._lock:
                    riding = self._riding.get(unit.unit_id, 0)
                advert.append(
                    sessionwire.AdvertisedUnit(
                        unit_id=unit.unit_id,
                        model=unit.model,
                        slots=unit.slots,
                        ctx=unit.ctx,
                        free_slots=free_slots(unit.slots, in_flight, riding),
                        rider_cap=unit.rider_cap,
                    )
                )
            wanted = tuple(advert)
            now = self._clock()
            with self._lock:
                if not self._online:
                    return
                due = (
                    bool(wanted)
                    and self._sent_at is not None
                    and now - self._sent_at >= sessionwire.UNIT_ADVERT_INTERVAL_S
                )
                if wanted == self._last and not due:
                    self._serve(setup)
                    return
                if self._sent_at is not None and now - self._sent_at < ADVERT_GAP_S:
                    self._asked = True  # the next check must send
                    return
            if self._send(sessionwire.unit_advert(wanted), timeout=SEND_WAIT_S):
                with self._lock:
                    if self._online:
                        self._last = wanted
                        self._sent_at = now
                        self._serve(setup)
        finally:
            with self._lock:
                self._going = False
