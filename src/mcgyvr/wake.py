"""Sleep, wake and stop the cards a ladder's units are served from.

A card is one host and every rung it serves. What can be done to it depends on
the config and on the launch spec `mcgyvr emit` wrote into
`serving.compose_dir`: `up` starts the units that are meant to be awake, `down`
stops them, `sleep` asks the card's vLLM units to sleep at level 2 (weights and
cache leave the card, its process stays) and `wake` brings slept units back. A
card that is down is gone, while one that is sleeping is resting with its
process still running: which of the two it is decides `up` from `wake`.

A sleeping card keeps no record of its own that can be asked, so two small
records are kept in a per-user directory under the temp dir: how long the last
`up` on a card took, which is what the next wake is measured against, and one
mark per port saying that unit is resting rather than stopped, which is what
decides `wake` from `up`. Both are read and written only in a directory this
user owns and nobody else may write, and a record that cannot be read is simply
no record.

Every action is one door run per card — `python -m mcgyvr.serving.run serve
<direction> ...` — and the exit code it answers with is the answer. `Waker`
turns a refused connection into one wake per card; `CardSwitches` is what a
fleet sample sleeps, wakes and makes room with.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import ROLE_SLEEPER, Config
from mcgyvr.runner import RefusedConnectionError
from mcgyvr.serving import DEFAULT_ENGINE, Card, cards, host_of, port_of

# The door: one process per card, run as `python -m mcgyvr.serving.run serve
# <up|down|sleep|wake> --host H --compose <spec> [--suffix S] [--unit C ...]`.
# DOOR_MODULE is the module spawned below and the one the "name the file
# yourself" message tells a person to run; NO_SLEEP_ROUTE is the exit code a
# `sleep` run answers with when a unit on the card has no sleep route, which
# means the card can only be stopped. Both names are taken from here so this
# file never spells the door's module again, and so the exit code the fallback
# in `put_down` depends on is the one the gate scripts themselves return.
from mcgyvr.serving.gatelib import DOOR_MODULE, NO_SLEEP_ROUTE
from mcgyvr.userdir import owned_outright, user_tempdir

#: The answer of whatever is being sent through `Waker.dispatching`: a draw or a
#: read, sent again after a wake, and always of the type it would have been
#: without the wake, since the caller is handed the send's own value back.
Answer = TypeVar("Answer")


class WakeError(Exception):
    """A card cannot be slept or woken, and the message says what is missing."""


def spawn_door(argv: Sequence[str], **kwargs: object) -> int:
    """Run the door with this argv and answer with the exit code it left.

    `check=False` keeps a non-zero code an answer rather than an exception: a
    door that could not sleep a card says so with its code. Any `kwargs` are
    handed to `subprocess.run` unchanged.
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
    """The command line of one door run.

    This interpreter and the door module, then `serve` and the direction, then
    the host, the launch spec, a suffix naming the run and one `--unit` pair per
    container the run is to act on. The suffix and the units are what this side
    chooses; the direction is the verb the caller asked for.
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
    """A suffix that tells this door run from another re-run of it.

    The pid and the millisecond clock, so two runs in a row do not share a
    RUN_ID and one run's record is not written over another's.
    """
    return f"wake-{os.getpid()}-{int(time.monotonic() * 1000) % 1_000_000}"


@dataclass(frozen=True)
class Wake:
    """What one door run did, as the caller is told it.

    `seconds` is how long the run took and `predicted_s` the number the clock
    directory held before it started, which is the last wake's timing and never
    this one's. `code` is the door's exit code, `direction` the verb it ran, and
    `ports` the ports of the rungs the run acted on.
    """

    host: str
    compose_file: Path
    direction: str
    seconds: float
    predicted_s: float | None
    code: int
    #: The ports of the rungs the run acted on: every rung of the card, or only
    #: the ones named with --unit, and what the resting marks are kept by.
    ports: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def deviation(self) -> str | None:
        """How far the run's `seconds` fell from its `predicted_s`, or None.

        Nothing here works that gap out yet, so this is always None and the
        warning `_run_door` would print is never printed.
        """
        return None


def _clock_dir() -> Path:
    """The per-user directory the wake records are kept in.

    One per uid under the temp dir, so two users running the same ladder do not
    read or write each other's record, and every process of one user agrees on
    where the record is.
    """
    return user_tempdir("wake")


#: The check every read and write of the clock directory goes through.
_ours = owned_outright


def _history(card: Card) -> Path:
    return _clock_dir() / f"{_safe(card.host)}.wake.json"


def _safe(host: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in host)


def predicted_wake_s(card: Card) -> float | None:
    """What the last `up` on this card took, in seconds, or None.

    The number comes from the record in the clock directory. It is None when
    this user has no clock directory, the file is missing or unreadable, it is
    not a JSON object, or its `seconds` is not a finite number — a bool is
    turned away too, though `isinstance` would have it as an int. Every failure
    degrades to no prediction, because a prediction may never shorten or abort a
    wake.
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
    # `isinstance(True, int)` holds, so a bool is turned away above, not read as 1.0
    number = float(seconds)
    return number if math.isfinite(number) else None


def _remember(made: Wake) -> None:
    """Write down how long a successful `up` took, as the next wake's yardstick.

    Only `up` is recorded: a `sleep`, a `wake` or a `down` says nothing about
    how long coming up takes. The directory is made 0o700 and written into only
    when it is ours. Every failure is dropped — a record is not worth a wake,
    and a wake with no record simply has no prediction.
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
    """Whether this card, or one port of it, is resting: slept, process kept.

    A resting card needs `wake`, not `up`. With a port the answer is that port's
    mark; without one, any mark for the host, which is the question asked before
    the port is known. A clock directory that is not ours answers False, so a
    card this user has no record of is treated as stopped rather than slept.
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
    """Keep the resting marks in step with a door run that answered.

    A `sleep` leaves a mark for each port the run acted on; any other direction
    clears them, a `down` included, since a card that was stopped is not
    resting. Failure is dropped: the cost of a missing mark is the next wake
    sent as `up` where `wake` was wanted.
    """
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
    """`wake` for a card that is resting, `up` for one that is not.

    `ports` asks the question for the units being acted on rather than for the
    whole card, which is what a card whose units switch one at a time asks; with
    none, any resting mark for the host answers for the card.
    """
    if ports:
        return "wake" if any(resting(card.host, port) for port in ports) else "up"
    return "wake" if resting(card.host) else "up"


def _ports(config: Config, rungs: Sequence[str]) -> tuple[int, ...]:
    """The port each named rung is served on, in the order given.

    A rung this config holds no unit for is skipped rather than raising, so a
    caller gets no port for it instead of a KeyError.
    """
    return tuple(
        port_of(config.units[rung].address) for rung in rungs if rung in config.units
    )


def _all_vllm(config: Config, card: Card) -> bool:
    """True when every source of this card is a vLLM unit the config holds.

    Only then can the card be slept at level 2: one unit of another engine on
    the card means stopping the card is the only way to give its memory back.
    """
    units = [config.units.get(name) for name in card.sources]
    return bool(units) and all(
        unit is not None and unit.engine == "vllm" for unit in units
    )


#: The engines whose units can be acted on one at a time: vLLM keeps its
#: process through a level-2 sleep, and a llama.cpp unit is a container of its
#: own that `serve down --unit` stops without touching its neighbours. Any other
#: engine is acted on only with the whole card.
_ALONE_ENGINES = ("vllm", DEFAULT_ENGINE)


def _engine(config: Config, rung: str) -> str | None:
    """The engine a rung runs: what its unit states, else llama.cpp.

    None for a rung this config holds no unit for, which is how a caller tells a
    missing unit from one that states no engine of its own.
    """
    unit = config.units.get(rung)
    return None if unit is None else unit.engine or DEFAULT_ENGINE


def _stopped_alone(config: Config, rungs: Sequence[str]) -> bool:
    """True when every named rung is a llama.cpp unit.

    Such a unit is one container, so the door can stop that container with
    `--unit` and leave the card's other units as they are; a vLLM unit is slept
    instead, which is why it is not covered here.
    """
    return bool(rungs) and all(_engine(config, r) == DEFAULT_ENGINE for r in rungs)


def _sleeper(config: Config, rung: str) -> bool:
    """True when the rung's unit is the config's sleeper, `sleeps-until-needed`.

    Such a unit starts asleep by design, so its refusal is the state its role
    asks for rather than an outage to be woken out of.
    """
    unit = config.units.get(rung)
    return unit is not None and unit.role == ROLE_SLEEPER


def _unit_containers(
    config: Config, card: Card, compose: Path, rungs: Sequence[str]
) -> tuple[str, ...] | None:
    """The compose container name of each named rung, found by its port.

    The launch spec is read for the port each service serves. None when the spec
    cannot be read, a rung's port is not in it, or fewer containers were found
    than rungs asked for: with no container named, no run can be aimed at single
    units, so the caller acts on the whole card instead.
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
    """True when this card's units can be slept, woken or stopped one at a time.

    All of: the card serves two rungs or more, every source runs an engine that
    acts alone, the card has exactly one launch spec, and every rung's container
    can be found in that spec. Where any of it fails, a door run on the card
    acts on every unit it serves.
    """
    if len(card.rungs) < 2 or not all(
        _engine(config, name) in _ALONE_ENGINES for name in card.sources
    ):
        return False
    compose = compose_for(card)
    return compose is not None and (
        _unit_containers(config, card, compose, card.rungs) is not None
    )


def compose_for(card: Card) -> Path | None:
    """The one launch spec this card is served from, or None.

    None when the config holds no spec for the card and when it holds two: with
    more than one, which of them is current is not something mcgyvr can tell, so
    no door is aimed at a guess.
    """
    if len(card.specs) == 1:
        return card.specs[0]
    return None


def resident_units(config: Config) -> frozenset[str]:
    """The unit bound to `jev.unit`: resident, and so never slept or woken.

    Empty when nothing is bound, which is the ordinary case — then no card is
    resident and every card of the ladder is a switch.
    """
    bound = config.get("jev.unit")
    return frozenset({str(bound)}) if bound else frozenset()


def holds_resident(config: Config, card: Card) -> str | None:
    """The resident unit's name when it sits on this card's host, else None.

    A card that holds the resident unit is not slept or woken at all: sleeping
    it would take down the one unit that is meant to stay up.
    """
    for name in resident_units(config):
        unit = config.units.get(name)
        if unit is not None and host_of(unit.address) == card.host:
            return name
    return None


def wakeable_rungs(config: Config) -> tuple[str, ...]:
    """The rungs that can be slept and woken: one launch spec, no resident unit.

    This is the ladder's set of switches.
    """
    return tuple(
        name
        for name, card in cards(config).items()
        if compose_for(card) is not None and holds_resident(config, card) is None
    )


def _split_elsewhere(config: Config, card: Card) -> str | None:
    """A sentence naming a source of this card that is split onto other rigs.

    Each source's `launch` shards are read and every shard's rig compared with
    the host the unit's own address is on; the first source with a shard
    elsewhere is named, with the rigs it is spread over. None when every source
    runs where it is addressed, and a source whose address will not parse is
    passed over rather than raised on.
    """
    from mcgyvr.serving import SHARDS_KEY, UnitError, host_of

    for source in card.sources:
        unit = config.units[source]
        shards = unit.launch.get(SHARDS_KEY)
        try:
            home = host_of(unit.address).lower()
        except UnitError:
            continue
        elsewhere = sorted(
            {
                str(shard.get("rig"))
                for shard in (shards if isinstance(shards, list) else ())
                if isinstance(shard, Mapping)
                and str(shard.get("rig", "")).lower() != home
            }
        )
        if elsewhere:
            return f"{source} is split onto {', '.join(elsewhere)}"
    return None


def _why_not_one(card: Card) -> str:
    """Why this card has no single launch spec to run a door with.

    Two cases, told apart: no spec was emitted for the card, so the person is
    pointed at `serving.compose_dir` and `mcgyvr emit`; or several were, and then
    they are listed, since which one is current is not something the config
    answers and mcgyvr will not guess.
    """
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
    """Run one door for a card and answer with what it did.

    The prediction is read before the door is spawned, so it is the last wake's
    number and not this run's. `only` narrows the run to those rungs' containers
    when the spec names every one of them; the ports recorded in the `Wake` are
    the ones the run really acted on, which on a narrowed run is `only` and
    otherwise every rung of the card. A `deviation` is printed as a warning when
    there is one to print.
    """
    predicted = predicted_wake_s(card)
    containers = _unit_containers(config, card, compose, only) if only else None
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
    """Wakes a card when a draw on it is refused, once per card per outage.

    `for_config` makes one for a ladder and everything drawing on that ladder
    shares it, so a card already being woken is not woken a second time by a
    second draw refused in the meantime.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._cards = cards(config)
        #: The answer of each card's last wake, with the clock reading the run
        #: ended at: whether it worked, and when. The key is the card's host, or
        #: `host:rung` on a card whose units switch one at a time, so one unit's
        #: wake does not answer for its neighbour. Written under that card's own
        #: lock, taken below.
        self._woken: dict[str, tuple[bool, float]] = {}
        #: `_lock` guards `_card_locks` and nothing else, and is held only long
        #: enough to take out one card's lock; the door run itself happens under
        #: that card's lock. A second draw refused by the same card therefore
        #: waits for the run already happening instead of starting another, and
        #: finds the card awake when it is let in. Two different cards never wait
        #: on each other.
        self._lock = threading.Lock()
        self._card_locks: dict[str, threading.Lock] = {}

    def dispatching(self, rung: str, send: Callable[[], Answer]) -> Answer:
        """Send one draw to a rung, waking its card when the send is refused.

        A card the record says is resting is woken before the draw is sent; any
        other card is sent to first, and only an instant refusal wakes it, since
        a read timeout on a card that is up is not an outage. A draw is sent once
        more after a wake that worked, and re-raised when the wake did not.
        """
        card = self._cards.get(rung)
        if rung in resident_units(self._config) or (
            card is not None and holds_resident(self._config, card) is not None
        ):
            # The card holding the jev unit is resident: it is never slept, so
            # a refusal here is not something a wake would fix.
            return send()
        if _sleeper(self._config, rung):
            # A unit that starts asleep is not woken on a refusal: it is in the
            # state its role asks for, so the draw goes as it is and its own
            # refusal is the answer.
            return send()
        if card is not None and any(
            resting(card.host, port) for port in _ports(self._config, (rung,))
        ):
            # The record says this card was slept with its process kept, so
            # every port on it answers with a refusal until something wakes it.
            # Wake first, and let the draw be refused only if the wake fails.
            if not self.wake_for(rung, refused_at=time.monotonic()):
                raise RefusedConnectionError(
                    f"{rung}: its card {card.host} was put to sleep with its "
                    "process kept, and could not be woken"
                )
            return send()
        try:
            return send()
        except RefusedConnectionError as refused:
            # An instant refusal, not a timeout: nothing is listening, which is
            # what a card that was stopped looks like. Wake it and send again.
            if not self.wake_for(rung, refused_at=time.monotonic()):
                raise refused
            return send()

    def wake_for(self, rung: str, *, refused_at: float | None = None) -> bool:
        """Wake the card serving this rung, one wake per card at a time.

        True when the card is up by the end, and False for a rung no card serves.
        `refused_at` is when the draw was refused: it is what tells a second
        refusal from the same outage apart from one that came after the wake.
        """
        card = self._cards.get(rung)
        if card is None:
            return False
        with self._lock:
            card_lock = self._card_locks.setdefault(card.host, threading.Lock())
        with card_lock:
            return self._wake_for(card, refused_at, rung)

    def _wake_for(self, card: Card, refused_at: float | None, rung: str) -> bool:
        # A card whose units switch one at a time is woken for this one rung and
        # remembered per rung; any other card is woken and remembered whole,
        # because a door run on it acts on every unit it serves.
        alone = _per_unit(self._config, card)
        key = f"{card.host}:{rung}" if alone else card.host
        if key in self._woken:
            ok, ended = self._woken[key]
            return ok and refused_at is not None and refused_at < ended
        # A live fleet's lock says which hosts mcgyvr may act on: when this
        # config is run against a fleet, only a host the fleet holds locked is
        # woken, since an unlocked one is another's to run or is being admitted.
        # No fleet directory, or a host that is not locked, means no wake; a
        # fleet directory that cannot be read is said out loud and also means no
        # wake. Neither is a reason to wake a card without the lock, so both
        # answer False and the draw keeps its refusal.
        from mcgyvr.fleet.roots import LiveFleetError, live_fleet_dir, runs_live

        if runs_live(self._config.path):
            from mcgyvr.fleet.admit import host_is_locked

            try:
                root = live_fleet_dir()
            except LiveFleetError as exc:
                print(f"warning: {exc}", file=sys.stderr)
                return False
            if root is None or not host_is_locked(root, card.host):
                return False
        compose = compose_for(card)
        if compose is None:
            # No single launch spec is this card's, so there is nothing to aim a
            # door at: waking would be a guess at which spec is current. The
            # failure is remembered like any other answer, so the same draw is
            # not retried against the same gap, but only a card the config holds
            # specs for is worth a warning — a card with none was never emitted
            # for, and `_why_not_one` says what to set and run to fix that.
            if card.specs:
                self._woken[key] = (False, time.monotonic())
                print(f"warning: {_why_not_one(card)}", file=sys.stderr)
            return False
        if alone:
            direction = _wake_direction(card, _ports(self._config, (rung,)))
            # Name the unit when it is asleep, so the card's other units are
            # left as they are, or when it is a llama.cpp unit being stopped.
            only: tuple[str, ...] = (
                (rung,)
                if direction == "wake" or _stopped_alone(self._config, (rung,))
                else ()
            )
        else:
            direction, only = _wake_direction(card), ()
        ok = _run_door(self._config, card, direction, compose, only=only).ok
        self._woken[key] = (ok, time.monotonic())
        return ok


def for_config(config: Config) -> Waker | None:
    """The waker for this config, or None when mcgyvr may not switch cards.

    None unless `serving.enable_sleep_wake` is on and `serving.compose_dir` is
    set: with the setting off, a person has said mcgyvr may not sleep or wake a
    unit itself, and with no emitted spec there is nothing to aim a door at.
    """
    if not config.get("serving.enable_sleep_wake"):
        return None
    if not config.get("serving.compose_dir"):
        return None
    return Waker(config)


def card_named(config: Config, host: str) -> Card:
    """The card served by `host`, or `WakeError` naming the rigs this ladder has.

    A host is a card, so a host no rung is served from is a typo or another
    ladder's rig, and the message lists the rigs this config does serve.
    """
    for card in cards(config).values():
        if card.host == host:
            return card
    known = sorted({card.host for card in cards(config).values()})
    raise WakeError(
        f"no rung of this ladder is served by {host!r}"
        + (f" — this config's rigs are {', '.join(known)}" if known else "")
    )


def sleep(config: Config, host: str) -> Wake:
    """Sleep or stop the card served by `host`, and answer with the door's run.

    Raises `WakeError` when no rung is served by that host, when the card holds
    the resident jev unit, or when the card has no single launch spec.
    """
    card = card_named(config, host)
    _refuse_resident(config, card, "slept")
    return put_down(config, card)


def put_down(config: Config, card: Card, only: tuple[str, ...] = ()) -> Wake:
    """Give a card back: sleep its vLLM units, or stop the card.

    Sleep where every source is vLLM and no unit of it is split over machines,
    and stop where the door answers with no sleep route. `only` narrows a card
    whose units switch one at a time to the unit being put down. Raises
    `WakeError` when the card holds the resident unit or has no single spec.
    """
    _refuse_resident(config, card, "slept")
    compose = compose_for(card)
    if compose is None:
        raise WakeError(_why_not_one(card))
    split = _split_elsewhere(config, card)
    if split is not None:
        # A unit split over machines is stopped rather than slept: level 2 is
        # not measured for one, and the note says which rigs it is spread over.
        print(
            f"note: {split}; vLLM's sleep at level 2 is not measured for a unit "
            f"split across machines, so {card.host} is stopped instead",
            file=sys.stderr,
        )
    elif only and _per_unit(config, card) and _stopped_alone(config, only):
        return _run_door(config, card, "down", compose, only=only)
    elif _all_vllm(config, card):
        asked = _run_door(config, card, "sleep", compose, only=only)
        if asked.code != NO_SLEEP_ROUTE:
            return asked
    # Either the card has a unit that is not vLLM, which only stopping gives
    # back, or the sleep run found no sleep route on it: stopping the card is
    # what is left to do.
    return _run_door(config, card, "down", compose)


def _refuse_resident(config: Config, card: Card, verb: str) -> None:
    held = holds_resident(config, card)
    if held is not None:
        raise WakeError(
            f"{card.host} holds {held!r}, the jev unit, which is resident: it is "
            f"never slept or woken, so its card is not {verb}. Unbind `jev.unit` "
            "to make the card a switch again."
        )


def wake(config: Config, host: str) -> Wake:
    """Wake the card served by `host`, and answer with the door's run.

    `wake` for a card the record says is resting, `up` for one that is not.
    Raises `WakeError` when no rung is served by that host, when the card holds
    the resident jev unit, or when it has no single launch spec.
    """
    card = card_named(config, host)
    _refuse_resident(config, card, "woken")
    compose = compose_for(card)
    if compose is None:
        # No single launch spec is this card's, so there is nothing to aim a
        # door at and a wake would be a guess at which spec is current. Say why
        # instead: a card whose config holds no spec at all, and one that holds
        # two, are told apart by `_why_not_one`.
        raise WakeError(_why_not_one(card))
    return _run_door(config, card, _wake_direction(card), compose)


def drain_timeout(config: Config, card: Card) -> float | None:
    """How long to wait for in-flight requests before a drain gives up.

    The longest `request_timeout_s` any source of the card states, since a
    request on any one of them may still be running when the drain starts. None
    when no source states one, which is a drain that waits as long as the
    capacity locks take.
    """
    timeouts: list[float] = []
    for name in card.sources:
        unit = config.units.get(name)
        if unit is not None and unit.request_timeout_s is not None:
            timeouts.append(unit.request_timeout_s)
    return max(timeouts) if timeouts else None


class CardSwitches:
    """The sleep and wake switches of a card, as a fleet sample asks them.

    Every answer is a yes or a sentence rather than an exception, so the caller
    can leave a card alone and say why: `wake` and `sleep` answer whether the door
    worked, `room_for` says which units must be slept to make room for a wake,
    `why_no_room` says what stops room being reckoned, and `card_of` says which
    rungs one sleep or wake acts on.
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

    def _resident(self, rung: str) -> bool:
        """Whether this rung, or the card serving it, holds the resident jev unit."""
        if rung in resident_units(self._config):
            return True
        card = self._cards.get(rung)
        return card is not None and holds_resident(self._config, card) is not None

    def wake(self, rung: str) -> bool:
        """Wake this rung's card, answering False where it is not mcgyvr's to wake.

        False for a resident card and for a ladder where sleep and wake is off;
        otherwise whatever the door answered.
        """
        if self._resident(rung):
            return False
        waker = for_config(self._config)
        return waker is not None and waker.wake_for(rung)

    def sleep(self, rung: str) -> bool:
        """Sleep or stop this rung's card, answering False where it was not done.

        False unless sleep and wake is on, the card is not resident, and the card
        has a single launch spec. The card is drained first, and if anything is
        still queued once the capacity locks are held, nothing is put down. A
        lock that cannot be taken and a `WakeError` both answer False.
        """
        if not self._allowed() or self._resident(rung):
            return False
        card = self._cards.get(rung)
        if card is None or compose_for(card) is None:
            return False
        alone = _per_unit(self._config, card)
        # One unit drains alone on a card whose units switch one at a time.
        sources = (rung,) if alone else card.sources
        try:
            with self._capacity.drain(
                sources, timeout=drain_timeout(self._config, card)
            ):
                # The card is drained: anything still queued on these sources
                # arrived after the capacity locks and would be killed by the
                # sleep, so the card stays up and the answer is no.
                if self._capacity.queued(sources) != 0:
                    return False
                return self._put_down(card, (rung,) if alone else ())
        except (SlotUnavailableError, WakeError):
            return False

    def _put_down(self, card: Card, only: tuple[str, ...]) -> bool:
        """Put the card down and answer the door's verdict, not the `Wake`."""
        return put_down(self._config, card, only).ok

    def room_for(self, rung: str) -> tuple[str, ...]:
        """The units to sleep first to make room for this rung, smallest first.

        Empty where nothing has to sleep, and where no room can be reckoned at
        all — `why_no_room` says which of the two it is.
        """
        return self._room(rung)[0]

    def why_no_room(self, rung: str) -> str | None:
        """Why room cannot be reckoned for this rung, or None where it need not be."""
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
        """Which card each rung of the card is on, by the scan's card index.

        Read from the device reservations of the containers that serve the rungs:
        a single index is taken as it stands, and a rung whose reservation names
        no device is put on the only card when the host has one. A sentence
        instead of a mapping where the spec cannot be read, says nothing and the
        host has several cards, reserves a unit more than one card, or names a
        card by something that is not a card index.
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
        """The rungs a sleep or wake on this rung acts on.

        The rung alone on a card whose units switch one at a time, every rung of
        the card otherwise, and the rung itself when no card serves it.
        """
        card = self._cards.get(rung)
        if card is None:
            return (rung,)
        return (rung,) if _per_unit(self._config, card) else tuple(card.rungs)
