"""The units this host shares with riders (hitchhike), as its agent tells the hub.

A host runs their own units for themselves. A unit whose ``rider_slots`` is 1
or more (:mod:`mcgyvr.config`) lends that many of its slots, at most, to
riders the hub matches: people whose requests for the unit's model the agent
passes to it, and whose prompts the host can read. The hub learns which units
from the agent's ``unit_advert`` (:func:`mcgyvr.rig.sessionwire.unit_advert`),
and the agent speaks the ``hitchhike_units`` feature to say it sends them.

**What is shared** (:func:`shared_units`) is read from the host's own setup,
the one :func:`mcgyvr.config.load` locates, and never from the hub. A unit of
the ladder, in the order work climbs it, with ``rider_slots`` of 1 or more;
not a relief rung (another person's unit, lent to this host as a rider: those
are in no ladder) and not a hosted one (a unit that needs a key cannot carry
``rider_slots`` at all). One unit per model, the first the ladder climbs, as
requests name it and answers carry it; at most
:data:`~mcgyvr.rig.sessionwire.MAX_UNITS`. Its slots are its ``width``, the
context of each its ``window``,
and the most rides at once its ``rider_slots``. A unit whose window is not
stated, or whose width or window the hub cannot carry, is left out and said.

**A unit's id** is its name where the name is already an id; otherwise the
name with every other character made a dash and cut to 64, and a short digest
of the name where that leaves no letter or digit, or is taken by a unit before
it. It is the same while the setup is.

**Free slots** (:func:`free_slots`) are what the host's own requests leave
free now: the unit's own server's count of requests in flight, read the way a
dispatch reads it (:func:`mcgyvr.pressure.server_counts`, through
:class:`mcgyvr.capacity.Capacity`), less the rides this agent serves on it now,
never below none or above the width. A server that does not say is read as
full: a slot is never offered on a guess.

**When** (:class:`Units`). An advert goes once the hello is acked, then when
the set or a free count changed, and at least every
:data:`~mcgyvr.rig.sessionwire.UNIT_ADVERT_INTERVAL_S` while anything is
shared. Whether anything changed is checked when asked (each heartbeat, and
each ride that ends) and when the next refresh is due, never twice in
:data:`CHECK_GAP_S`, on a thread of its own, one check at a time: reading a
server may take seconds, and the agent's loop never waits on it. A setup that
shares nothing sends nothing; one that stops sharing sends the empty set,
which withdraws it. Nothing goes while the channel is down, and the hub
forgets the adverts of a link that dropped, so the set goes again whole when
the channel is back. What cannot be shared is said once, not at every check.

**A ride** (``unit_relay_request``) is relayed by the head relay's own code
(:mod:`mcgyvr.rig.relay`) to the address of a unit this link advertised; the
hub names only its id. :meth:`Units.ride` admits it, the host first: a unit
takes at most its ``rider_slots`` rides at once, and none that would leave the
host fewer than ``slots - rider_slots`` free slots by the unit's own count at
that moment. An admitted ride holds one of the unit's slots, host-wide, for as
long as it runs (:meth:`mcgyvr.capacity.Capacity.hold`, without waiting), so
the host's own dispatches see it, and a unit with none free refuses it. A ride
that ends asks for a check, since the unit's free slots may have moved.
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
from typing import TYPE_CHECKING

from mcgyvr.capacity import SlotUnavailableError
from mcgyvr.rig import protocol, sessionwire
from mcgyvr.rig.relay import SEND_WAIT_S, RideRefusedError
from mcgyvr.rig.sessionwire import SessionCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config

#: The soonest a check of the shared units follows the one before, in seconds:
#: an advert goes at most once a second, as the hub's protocol asks.
CHECK_GAP_S = 1.0
#: How many hex digits of the name's digest an id made from it carries.
_DIGEST_DIGITS = 16

_NOT_ID = re.compile(r"[^A-Za-z0-9_-]")
_ALNUM = re.compile(r"[A-Za-z0-9]")
#: The longest id the hub's protocol carries.
_MAX_ID = 64


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="shared-units", daemon=True).start()


@dataclass(frozen=True, kw_only=True)
class Shared:
    """One unit this host shares, as its setup states it.

    ``name`` is the unit's name in the setup and ``address`` where it answers,
    both the host's own: neither is ever sent. ``slots`` is its width, ``ctx``
    the context of one slot, ``rider_cap`` the most rides at once.
    """

    unit_id: str
    name: str
    model: str
    address: str
    slots: int
    ctx: int
    rider_cap: int

    def url(self, endpoint: str) -> str:
        """Where a ride to ``endpoint`` goes: the unit's address joined to the
        endpoint's one path as a run joins it (``/v1`` is not doubled)."""
        from mcgyvr.runner import _url_for

        return _url_for(self.address, sessionwire.RELAY_PATHS[endpoint])


def _unit_id(name: str, taken: set[str]) -> str:
    """The id a unit named ``name`` is advertised under (see the module)."""
    if protocol.MESSAGE_ID.fullmatch(name) and name not in taken:
        return name
    made = _NOT_ID.sub("-", name)[:_MAX_ID]
    if _ALNUM.search(made) and made not in taken:
        return made
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:_DIGEST_DIGITS]
    return f"u-{digest}"


def shared_units(config: Config) -> tuple[tuple[Shared, ...], tuple[str, ...]]:
    """The units ``config`` shares, and a note for each it would but cannot."""
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
            continue  # the loader refuses it; a unit of one slot keeps it
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
    """The slots of a unit of ``slots`` the host's own requests leave free.

    ``in_flight`` is what the unit's server says it has in flight, ``None``
    where it did not say; ``riding`` the rides this agent serves on it now,
    which the server counts and which are not the host's own.
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
    """What the host's setup shares now, and how each shared unit is read.

    ``in_flight`` reads what a unit's server has in flight (``None`` unread);
    ``hold`` takes one of the unit's slots, host-wide, for as long as it is
    held, or raises :class:`mcgyvr.capacity.SlotUnavailableError` at once.
    """

    units: tuple[Shared, ...] = ()
    notes: tuple[str, ...] = ()
    in_flight: Callable[[Shared], int | None] = field(default=_unread)
    hold: Callable[[Shared], AbstractContextManager[None]] = field(default=_no_hold)


def setup_of(config: Config) -> Setup:
    """The :class:`Setup` of ``config``: its shared units, read and held through
    the capacity a run of the same setup holds its dispatches against
    (:meth:`mcgyvr.capacity.Capacity.of`, with the units' own servers read by
    :func:`mcgyvr.pressure.server_counts`), so a ride and the host's own
    dispatch count against the same slots."""
    from mcgyvr.capacity import Capacity
    from mcgyvr.pool import source_map
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


def load_setup() -> Setup:
    """The :class:`Setup` of the setup :func:`mcgyvr.config.load` locates: none
    shared where there is no setup, and a note where one does not load."""
    from mcgyvr.capacity import CapacityError
    from mcgyvr.config import ConfigError, ConfigMissingError, load

    try:
        return setup_of(load())
    except ConfigMissingError:
        return Setup()
    except (ConfigError, CapacityError) as exc:
        return Setup(notes=(f"no unit is shared with riders: {exc}",))


class Units:
    """The units this host shares, as the agent advertises them to the hub.

    :meth:`online` and :meth:`offline` follow the channel; :meth:`soon` asks
    for a check (the heartbeat, a ride that ended) and :meth:`tick` makes one
    when it is owed (call it about once a :data:`CHECK_GAP_S`); both return at
    once. A check reads the setup (``setup``), sends what changed through
    ``send`` (the agent's outbox) and says what cannot be shared once.
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
        self._serving = Setup()
        self._said: set[str] = set()
        self._closed = threading.Event()

    # -- the channel ---------------------------------------------------------

    def shares(self) -> bool:
        """Whether the setup shares a unit now: what the hello says."""
        return bool(self._setup().units)

    def online(self) -> None:
        """The hello is acked: the hub knows no advert of this link, so the
        whole set goes now."""
        with self._lock:
            self._online = True
            self._asked = True
            self._checked_at = None
            self._sent_at = None
            self._last = ()
        self.tick()

    def offline(self) -> None:
        """The channel is down: nothing is sent until it is back, and the hub
        has forgotten the adverts, so no ride is taken either."""
        with self._lock:
            self._online = False
            self._last = ()
            self._shared = {}

    def close(self) -> None:
        """The agent ends: the ticker started by :meth:`run_ticker` stops."""
        self.offline()
        self._closed.set()

    def run_ticker(self) -> None:
        """Tick each :data:`CHECK_GAP_S` on a thread of its own until
        :meth:`close`, so a refresh is never later than it is owed."""

        def ticking() -> None:
            while not self._closed.wait(CHECK_GAP_S):
                self.tick()

        threading.Thread(target=ticking, name="shared-units-tick", daemon=True).start()

    # -- the rides -----------------------------------------------------------

    def advertised(self, unit_id: str) -> Shared | None:
        """The unit the hub knows by ``unit_id`` from this link's adverts."""
        with self._lock:
            return self._shared.get(unit_id)

    @contextmanager
    def ride(self, unit_id: str) -> Iterator[None]:
        """Admit one ride to ``unit_id`` for the block, the host first.

        :class:`~mcgyvr.rig.relay.RideRefusedError` ``unknown_unit`` for a unit
        no longer advertised, ``busy`` when the unit has its riders or the
        ride would leave the host fewer than ``slots - rider_cap`` free slots
        by the unit's own count now (``rides + 1 > rider_cap - (slots -
        free)``), or when no slot of the unit is free host-wide. An admitted
        ride holds one of the unit's slots, which the host's own dispatches
        count, and counts as a ride (not the host's) in the free slots an
        advert says until it ends; its end asks for a check of the advert.
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
            if riding + 1 > unit.rider_cap - (unit.slots - free):
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

    # -- the checks ----------------------------------------------------------

    def soon(self) -> None:
        """Check at the next moment one may run: something may have changed."""
        with self._lock:
            self._asked = True
        self.tick()

    def tick(self) -> None:
        """Start a check if one is owed and may run now."""
        with self._lock:
            if not self._online or self._going:
                return
            now = self._clock()
            if self._checked_at is not None and now - self._checked_at < CHECK_GAP_S:
                return
            refresh = (
                bool(self._last)
                and self._sent_at is not None
                and now - self._sent_at >= sessionwire.UNIT_ADVERT_INTERVAL_S
            )
            if not (self._asked or refresh):
                return
            self._going = True
            self._asked = False
            self._checked_at = now
        self._start(self._check)

    def _serve(self, setup: Setup) -> None:
        """Take rides to the units the hub was told of, as ``setup`` states
        them now. Called under the lock."""
        self._shared = {unit.unit_id: unit for unit in setup.units}
        self._serving = setup

    def _note(self, line: str) -> None:
        with self._lock:
            if line in self._said:
                return
            self._said.add(line)
        self._say(f"note: {line}")

    def _check(self) -> None:
        try:
            setup = self._setup()
            for line in setup.notes:
                self._note(line)
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
            if self._send(sessionwire.unit_advert(wanted), timeout=SEND_WAIT_S):
                with self._lock:
                    if self._online:
                        self._last = wanted
                        self._sent_at = now
                        self._serve(setup)
        finally:
            with self._lock:
                self._going = False
