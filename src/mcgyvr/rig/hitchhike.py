""

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

if TYPE_CHECKING:  #
    from mcgyvr.config import Config

#
#
ADVERT_GAP_S = 1.0
#
#
POLL_S = 0.25
#
_DIGEST_DIGITS = 16

_NOT_ID = re.compile(r"[^A-Za-z0-9_-]")
_ALNUM = re.compile(r"[A-Za-z0-9]")
#
_MAX_ID = 64


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="shared-units", daemon=True).start()


@dataclass(frozen=True, kw_only=True)
class Shared:
    ""

    unit_id: str
    name: str
    model: str
    address: str
    slots: int
    ctx: int
    rider_cap: int

    def url(self, endpoint: str) -> str:
        ""
        from mcgyvr.runner import _url_for

        return _url_for(self.address, sessionwire.RELAY_PATHS[endpoint])


def _unit_id(name: str, taken: set[str]) -> str:
    ""
    if protocol.MESSAGE_ID.fullmatch(name) and name not in taken:
        return name
    made = _NOT_ID.sub("-", name)[:_MAX_ID]
    if _ALNUM.search(made) and made not in taken:
        return made
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:_DIGEST_DIGITS]
    return f"u-{digest}"


def shared_units(config: Config) -> tuple[tuple[Shared, ...], tuple[str, ...]]:
    ""
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
            continue  #
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
    ""
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
    ""

    units: tuple[Shared, ...] = ()
    notes: tuple[str, ...] = ()
    in_flight: Callable[[Shared], int | None] = field(default=_unread)
    hold: Callable[[Shared], AbstractContextManager[None]] = field(default=_no_hold)


def setup_of(config: Config) -> Setup:
    ""
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
    ""
    from mcgyvr.capacity import CapacityError
    from mcgyvr.config import ConfigError, ConfigMissingError, load

    try:
        return setup_of(load(path))
    except ConfigMissingError:
        return Setup()
    except (ConfigError, CapacityError) as exc:
        return Setup(notes=(f"no unit is shared with riders: {exc}",))


class Units:
    ""

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

    #

    def shares(self) -> bool:
        ""
        return bool(self._setup().units)

    def online(self) -> None:
        ""
        with self._lock:
            self._online = True
            self._asked = True
            self._checked_at = None
            self._sent_at = None
            self._last = ()
        self.tick()

    def offline(self) -> None:
        ""
        with self._lock:
            self._online = False
            self._last = ()
            self._shared = {}
            self._served = ()

    def close(self) -> None:
        ""
        self.offline()
        self._closed.set()

    def run_ticker(self) -> None:
        ""

        def ticking() -> None:
            while not self._closed.wait(POLL_S):
                self.tick()

        threading.Thread(target=ticking, name="shared-units-tick", daemon=True).start()

    #

    def advertised(self, unit_id: str) -> Shared | None:
        ""
        with self._lock:
            return self._shared.get(unit_id)

    @contextmanager
    def ride(self, unit_id: str) -> Iterator[None]:
        ""
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

    #

    def soon(self) -> None:
        ""
        with self._lock:
            self._asked = True
        self.tick()

    def tick(self) -> None:
        ""
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
        ""
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
                    return  #
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
                    self._asked = True  #
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
