""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr import decision
from mcgyvr.config import Ladder

if TYPE_CHECKING:  #
    from mcgyvr.config import Config
    from mcgyvr.cooldown import SharedHold
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.pressure import Gauge, Reading

#
#
ASK_LADDER = "ladder"
ASK_FANOUT = "fanout"
ASK_LEAD = "lead"

#
#
#
MANAGER_LOCK = "ladder-manager"

#
#
HOLD = "hold"
KEEP_ORDER = "ladder"


class Switches(Protocol):
    ""

    def wake(self, rung: str) -> bool: ...

    def sleep(self, rung: str) -> bool: ...

    def room_for(self, rung: str) -> tuple[str, ...]: ...

    def card_of(self, rung: str) -> tuple[str, ...]: ...


class PressureSource(Protocol):
    ""

    def read(self, rung: str) -> Reading: ...


class Cooling(Protocol):
    ""

    def cooled(self, rungs: tuple[str, ...]) -> frozenset[str]: ...

    def failed(self, rung: str) -> None: ...

    def worked(self, rung: str) -> None: ...


#
Decide = Callable[
    [Mapping[str, Any], Mapping[str, decision.Question]], decision.Decision
]


@dataclass(frozen=True)
class Bounds:
    ""

    interval_s: float
    confirm: int
    dwell_s: float
    fanouts: tuple[str, ...]
    leads: tuple[str, ...]

    @classmethod
    def of(cls, config: Config) -> Bounds:
        return cls(
            interval_s=float(config.require("manager.interval_s")),
            confirm=int(config.require("manager.confirm")),
            dwell_s=float(config.require("manager.dwell_s")),
            fanouts=tuple(config.get("manager.fanouts") or ()),
            leads=tuple(config.get("manager.leads") or ()),
        )

    @property
    def pipeline(self) -> bool:
        ""
        return len(self.fanouts) >= 2 or bool(self.leads)


@dataclass(frozen=True)
class View:
    ""

    resident: tuple[str, ...]
    sleepable: frozenset[str]
    jev: str
    fanout: str
    ladder: tuple[str, ...]

    @classmethod
    def of(cls, config: Config, *, jev: str) -> View:
        return cls(
            resident=_local(config),
            sleepable=frozenset(sleepable_rungs(config)),
            jev=jev,
            fanout=config.ladder.fanout,
            ladder=config.ladder.names,
        )


@dataclass(frozen=True)
class Tick:
    ""

    readings: Mapping[str, Reading]
    asked: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    answers: Mapping[str, str] = field(default_factory=dict)
    acted: tuple[str, ...] = ()
    recommended: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Move:
    verb: str
    rung: str | None = None
    first: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return HOLD if self.rung is None else f"{self.verb}:{self.rung}"


@dataclass
class _Streak:
    answer: str | None = None
    count: int = 0

    def hear(self, answer: str) -> int:
        if answer == self.answer:
            self.count += 1
        else:
            self.answer, self.count = answer, 1
        return self.count

    def reset(self) -> None:
        self.answer, self.count = None, 0


def _queued(reading: Reading) -> int:
    ""
    overflow = max(0, (reading.in_flight or 0) - reading.width)
    return (reading.waiting or 0) + overflow


def _load(reading: Reading) -> str:
    ""
    in_flight = "unread" if reading.in_flight is None else str(reading.in_flight)
    waiting = "unread" if reading.waiting is None else str(reading.waiting)
    return f"{in_flight} in flight of {reading.width}, {waiting} waiting"


def _idle(reading: Reading) -> bool:
    ""
    return reading.in_flight == 0 and reading.waiting == 0 and reading.climbed == 0


class Manager:
    ""

    def __init__(
        self,
        view: View,
        bounds: Bounds,
        *,
        pressure: PressureSource,
        switches: Switches,
        decide: Decide,
        cooling: Cooling | None = None,
        clock: Callable[[], float] = time.monotonic,
        say: Callable[[str], object] = print,
        publish: Callable[[Mapping[str, Any]], object] | None = None,
    ) -> None:
        self._view = view
        self._bounds = bounds
        self._pressure = pressure
        self._switches = switches
        self._decide = decide
        self._cooling = cooling
        self._clock = clock
        self._say = say
        self._publish = publish
        self._streaks = {
            ASK_LADDER: _Streak(),
            ASK_FANOUT: _Streak(),
            ASK_LEAD: _Streak(),
        }
        self._last_switch: float | None = None
        #
        #
        #
        self._expected: dict[str, bool] = {}
        #
        #
        self._idle_since: dict[str, float] = {}
        #
        self._room: dict[str, tuple[str, ...]] = {}
        self._fanout = view.fanout
        self._lead = KEEP_ORDER
        self._recommended: str | None = None

    #

    def _cooled(self) -> frozenset[str]:
        if self._cooling is None:
            return frozenset()
        return self._cooling.cooled(self._view.resident)

    def _top(self, readings: Mapping[str, Reading]) -> str | None:
        awake = [r for r in self._view.resident if readings[r].awake]
        return awake[-1] if awake else None

    def _rank(self, rung: str) -> int:
        return self._view.resident.index(rung)

    #

    def _wakes(
        self,
        readings: Mapping[str, Reading],
        cooled: frozenset[str],
        top: str | None,
    ) -> tuple[list[_Move], str | None]:
        ""
        if top is None or not readings[top].full:
            return [], None
        moves: list[_Move] = []
        blocked: list[str] = []
        for rung in self._view.resident[self._rank(top) + 1 :]:
            if rung not in self._view.sleepable or readings[rung].awake:
                continue
            if rung in cooled:
                blocked.append(f"{rung} is cooling down")
                continue
            #
            room = tuple(
                unit
                for unit in self._switches.room_for(rung)
                if unit not in readings or readings[unit].awake
            )
            refused = [
                unit for unit in room if not self._may_sleep(unit, readings, room=True)
            ]
            if refused:
                blocked.append(
                    f"waking {rung} needs the room {', '.join(refused)} holds, "
                    f"which mcgyvr may not put to sleep"
                )
                continue
            moves.append(_Move("wake", rung, first=room))
        if moves:
            return moves, None
        why = "; ".join(blocked) or "no sleeping unit above it can be woken"
        return [], (
            f"recommend: {top} is full ({_load(readings[top])}) and {why}. "
            f"Answering it takes loading or swapping a model, which the ladder "
            f"manager leaves to you."
        )

    def _may_sleep(
        self, rung: str, readings: Mapping[str, Reading], *, room: bool = False
    ) -> bool:
        ""
        if rung not in self._view.sleepable or not readings[rung].awake:
            return False
        card = self._switches.card_of(rung)
        if self._view.jev in card:
            return False
        below = [
            r
            for r in self._view.resident[: self._rank(rung)]
            if readings[r].awake and r not in card
        ]
        if not below:
            return False
        return room or all(_idle(readings[r]) for r in card if r in readings)

    def _sleeps(
        self, readings: Mapping[str, Reading], cooled: frozenset[str], now: float
    ) -> list[_Move]:
        ""
        awake = [r for r in self._view.resident if readings[r].awake]
        if any(_queued(readings[r]) > 0 for r in awake):
            return []
        return [
            _Move("sleep", rung)
            for rung in self._view.resident
            if rung not in cooled
            and self._may_sleep(rung, readings)
            and self._idled(rung, readings, now)
        ]

    def _idled(self, rung: str, readings: Mapping[str, Reading], now: float) -> bool:
        ""
        for r in self._switches.card_of(rung):
            if r not in readings:
                continue
            since = self._idle_since.get(r)
            if since is None or now - since < self._bounds.dwell_s:
                return False
        return True

    def _observe(self, readings: Mapping[str, Reading], now: float) -> list[str]:
        ""
        for rung in self._view.resident:
            if readings[rung].awake and _idle(readings[rung]):
                self._idle_since.setdefault(rung, now)
            else:
                self._idle_since.pop(rung, None)
        moved = [
            rung
            for rung in self._view.resident
            if rung in self._expected and self._expected[rung] != readings[rung].awake
        ]
        self._expected = {r: readings[r].awake for r in self._view.resident}
        if not moved:
            return []
        self._switched(now)
        return [
            f"{rung} {'woke' if readings[rung].awake else 'went down'} outside the "
            f"ladder manager; no switch for {self._bounds.dwell_s:g}s"
            for rung in moved
        ]

    def _now_awake(self, rung: str, awake: bool) -> None:
        ""
        for r in self._switches.card_of(rung):
            if r in self._expected:
                self._expected[r] = awake

    #

    def tick(self) -> Tick:
        ""
        now = self._clock()
        readings = {rung: self._pressure.read(rung) for rung in self._view.resident}
        cooled = self._cooled()
        top = self._top(readings)
        acted: list[str] = self._observe(readings, now)

        #
        #
        if self._lead != KEEP_ORDER and (
            not readings[self._lead].awake or self._lead in cooled
        ):
            acted.append(self._set_lead(KEEP_ORDER, why="it is not serving"))

        wakes, recommendation = self._wakes(readings, cooled, top)
        moves = [_Move(HOLD), *wakes, *self._sleeps(readings, cooled, now)]
        recommended = self._recommend(recommendation)

        questions: dict[str, decision.Choice] = {}
        by_key = {move.key: move for move in moves}
        if len(moves) > 1:
            questions[ASK_LADDER] = decision.Choice(
                "The local rungs are listed cheapest first with their queues. "
                "Pick the move to make now: keep the ladder as it is, wake a "
                "sleeping bigger unit for a queue that is building, or put an "
                "idle bigger unit back to sleep so its card goes back to the "
                "fast rungs.",
                {move.key: self._describe(move) for move in moves},
            )
        if len(self._bounds.fanouts) >= 2:
            questions[ASK_FANOUT] = decision.Choice(
                "How should new tasks spread across the ladder now?",
                {
                    mode: _FANOUT_MEANING.get(mode, mode)
                    for mode in self._bounds.fanouts
                },
            )
        leads = [
            rung
            for rung in self._bounds.leads
            if rung in readings and readings[rung].awake and rung not in cooled
        ]
        if leads:
            questions[ASK_LEAD] = decision.Choice(
                "Which local rung should new tasks start on now?",
                {
                    KEEP_ORDER: "the ladder's own order, cheapest first",
                    **{rung: f"start new tasks on {rung}" for rung in leads},
                },
            )

        answers: dict[str, str] = {}
        if questions:
            try:
                made = self._decide(self._state(readings, cooled, top, now), questions)
                for name in questions:
                    answer = made.answers[name]
                    assert isinstance(answer, decision.ChoiceAnswer)
                    answers[name] = answer.choice
            except Exception as exc:
                self._say(f"warning: the ladder manager could not read Jev: {exc}")
                for streak in self._streaks.values():
                    streak.reset()
                answers = {}
        for name in self._streaks:
            if name not in answers:
                self._streaks[name].reset()

        if self._may_switch(now):
            ladder = answers.get(ASK_LADDER)
            if ladder is not None and self._confirmed(ASK_LADDER, ladder):
                move = by_key[ladder]
                if move.rung is not None:
                    acted.extend(self._act(move))
                    self._switched(now)
            fanout = answers.get(ASK_FANOUT)
            if (
                not self._recently(now)
                and fanout is not None
                and self._confirmed(ASK_FANOUT, fanout)
                and fanout != self._fanout
            ):
                self._fanout = fanout
                acted.append(f"fanout: {fanout}")
                self._switched(now)
            lead = answers.get(ASK_LEAD)
            if (
                not self._recently(now)
                and lead is not None
                and self._confirmed(ASK_LEAD, lead)
                and lead != self._lead
            ):
                acted.append(self._set_lead(lead, why="Jev chose it"))
                self._switched(now)
        else:
            for name, heard in answers.items():
                self._streaks[name].hear(heard)

        for line in acted:
            self._say(line)
        if self._publish is not None and self._bounds.pipeline:
            self._publish(
                {
                    "ladder": list(self._view.ladder),
                    "fanout": self._fanout,
                    "lead": self._lead,
                }
            )
        return Tick(
            readings=readings,
            asked={name: tuple(q.options) for name, q in questions.items()},
            answers=answers,
            acted=tuple(acted),
            recommended=recommended,
        )

    #

    def _confirmed(self, name: str, answer: str) -> bool:
        ""
        return self._streaks[name].hear(answer) >= self._bounds.confirm

    def _may_switch(self, now: float) -> bool:
        return not self._recently(now)

    def _recently(self, now: float) -> bool:
        return (
            self._last_switch is not None
            and now - self._last_switch < self._bounds.dwell_s
        )

    def _switched(self, now: float) -> None:
        self._last_switch = now
        for streak in self._streaks.values():
            streak.reset()

    #

    def _act(self, move: _Move) -> list[str]:
        assert move.rung is not None
        if move.verb == "wake":
            return self._wake(move.rung, move.first)
        return self._sleep(move.rung)

    def _wake(self, rung: str, room: tuple[str, ...]) -> list[str]:
        lines: list[str] = []
        slept: list[str] = []
        for unit in room:
            ok = self._switches.sleep(unit)
            lines.append(f"sleep {unit} to make room for {rung}: {_ok(ok)}")
            self._record(unit, ok, awake=False)
            if not ok:
                lines.extend(self._give_back(slept))
                return lines
            slept.append(unit)
        ok = self._switches.wake(rung)
        lines.append(f"wake {rung}: {_ok(ok)}")
        self._record(rung, ok, awake=True)
        if ok:
            self._room[rung] = tuple(slept)
        else:
            lines.extend(self._give_back(slept))
        return lines

    def _sleep(self, rung: str) -> list[str]:
        ok = self._switches.sleep(rung)
        lines = [f"sleep {rung}: {_ok(ok)}"]
        self._record(rung, ok, awake=False)
        if not ok:
            return lines
        if self._lead == rung:
            lines.append(self._set_lead(KEEP_ORDER, why=f"{rung} went to sleep"))
        lines.extend(self._give_back(list(self._room.pop(rung, ()))))
        return lines

    def _give_back(self, units: list[str]) -> list[str]:
        lines: list[str] = []
        for unit in units:
            ok = self._switches.wake(unit)
            lines.append(f"wake {unit} back: {_ok(ok)}")
            self._record(unit, ok, awake=True)
        return lines

    def _record(self, rung: str, ok: bool, *, awake: bool) -> None:
        ""
        if ok:
            self._now_awake(rung, awake)
        if self._cooling is None:
            return
        if ok:
            self._cooling.worked(rung)
        else:
            self._cooling.failed(rung)

    def _set_lead(self, lead: str, *, why: str) -> str:
        self._lead = lead
        return f"lead: {lead} ({why})"

    #

    def _recommend(self, line: str | None) -> tuple[str, ...]:
        ""
        if line is None:
            self._recommended = None
            return ()
        if line != self._recommended:
            self._recommended = line
            self._say(line)
        return (line,)

    def _describe(self, move: _Move) -> str:
        if move.rung is None:
            return "keep the ladder as it is"
        if move.verb == "wake":
            first = f", sleeping {', '.join(move.first)} first" if move.first else ""
            return f"wake {move.rung}{first}"
        return f"put {move.rung} to sleep and send its work back down the ladder"

    def _state(
        self,
        readings: Mapping[str, Reading],
        cooled: frozenset[str],
        top: str | None,
        now: float,
    ) -> dict[str, Any]:
        return {
            "rungs": [
                {
                    "rung": rung,
                    "awake": readings[rung].awake,
                    "in_flight": readings[rung].in_flight,
                    "waiting": readings[rung].waiting,
                    "climbed": readings[rung].climbed,
                    "width": readings[rung].width,
                    "queued": _queued(readings[rung]),
                    "full": readings[rung].full,
                    "cooling": rung in cooled,
                    "idle_s": (
                        None
                        if rung not in self._idle_since
                        else now - self._idle_since[rung]
                    ),
                    "can_sleep": rung in self._view.sleepable,
                }
                for rung in self._view.resident
            ],
            "top_awake": top,
            "seconds_since_last_switch": (
                None if self._last_switch is None else now - self._last_switch
            ),
            "fanout": self._fanout,
            "lead": self._lead,
        }


_FANOUT_MEANING = {
    "none": "every task starts on the cheapest rung of its family and queues there",
    "idle": "a task starts on the cheapest rung with a free slot, even a dearer one",
    "full": "tasks spread across the rungs of their family",
}


def _ok(ok: bool) -> str:
    return "done" if ok else "failed"


def run(
    manager: Manager,
    *,
    interval_s: float,
    sleep: Callable[[float], object] = time.sleep,
    ticks: int | None = None,
) -> int:
    ""
    count = 0
    while ticks is None or count < ticks:
        manager.tick()
        count += 1
        if ticks is None or count < ticks:
            sleep(interval_s)
    return count


#


def _local(config: Config) -> tuple[str, ...]:
    return tuple(
        name
        for name in config.ladder.names
        if name in config.units and not config.units[name].requires_credential
    )


def sleepable_rungs(config: Config) -> tuple[str, ...]:
    ""
    from mcgyvr.wake import left_alone, wakeable_rungs

    wakeable = set(wakeable_rungs(config)) - set(left_alone(config))
    return tuple(name for name in _local(config) if name in wakeable)


def applicable(config: Config) -> str | None:
    ""
    if not config.get("serving.enable_sleep_wake"):
        return (
            "serving.enable_sleep_wake is off, so mcgyvr may not sleep or wake "
            "any unit on its own and there is nothing for the manager to do"
        )
    if not sleepable_rungs(config):
        from mcgyvr.wake import left_alone

        alone = left_alone(config)
        return (
            "no local unit on this ladder can sleep and wake: a unit can when "
            "its card holds exactly one launch spec under serving.compose_dir "
            "(`mcgyvr emit --out`)"
            + "".join(f"; {rung} is left alone: {why}" for rung, why in alone.items())
        )
    return None


def effective(
    config: Config, published: Mapping[str, Any] | None, *, now: float
) -> Config:
    ""
    if applicable(config) is not None or not isinstance(published, Mapping):
        return config
    if published.get("ladder") != list(config.ladder.names):
        return config
    written = published.get("written_at")
    if isinstance(written, bool) or not isinstance(written, (int, float)):
        return config
    bounds = Bounds.of(config)
    if not 0 <= now - written <= bounds.interval_s * bounds.confirm:
        return config

    fanout = config.ladder.fanout
    chosen = published.get("fanout")
    if len(bounds.fanouts) >= 2 and chosen in bounds.fanouts:
        fanout = str(chosen)
    names = config.ladder.names
    lead = published.get("lead")
    if lead in bounds.leads:
        names = _led_by(config, str(lead))
    if fanout == config.ladder.fanout and names == config.ladder.names:
        return config
    data = dict(config.data)
    data["ladder"] = list(names)
    data["fanout"] = fanout
    return dataclasses.replace(
        config, data=data, ladder=Ladder(names=names, fanout=fanout)
    )


def _led_by(config: Config, lead: str) -> tuple[str, ...]:
    ""
    local = _local(config)
    rest = [name for name in config.ladder.names if name != lead]
    at = next((i for i, name in enumerate(rest) if name in local), 0)
    return (*rest[:at], lead, *rest[at:])


def gauge_for(config: Config) -> Gauge | None:
    ""
    if applicable(config) is not None:
        return None
    from mcgyvr.pressure import Gauge

    return Gauge()


def presence_for(
    config: Config, gauge: Any
) -> Callable[[str], AbstractContextManager[object]] | None:
    ""
    if applicable(config) is not None or gauge is None:
        return None
    from mcgyvr.pressure import climbed_key

    def present(rung: str) -> AbstractContextManager[object]:
        marked: AbstractContextManager[object] = gauge.present(climbed_key(rung))
        return marked

    return present


@dataclass(frozen=True)
class ForTask:
    ""

    config: Config
    gauge: Gauge | None = None
    presence: Callable[[str], AbstractContextManager[object]] | None = None
    note: str | None = None
    #
    #
    held: SharedHold | None = None


def for_task(
    config: Config,
    *,
    read_board: Callable[[], Mapping[str, Any] | None],
    now: Callable[[], float] = time.time,
) -> ForTask:
    ""
    if applicable(config) is not None:
        return ForTask(config)
    chosen = effective(config, read_board(), now=now())
    gauge = gauge_for(chosen)
    note = None
    if chosen is not config:
        note = (
            f"the ladder manager's choice applies to this task: fanout "
            f"{chosen.ladder.fanout}, ladder {', '.join(chosen.ladder.names)}"
        )
    from mcgyvr.pressure import HostCooling

    return ForTask(
        config=chosen,
        gauge=gauge,
        presence=presence_for(chosen, gauge),
        note=note,
        held=HostCooling(),
    )


def decide_on(pool: SourceMap, rung: str, *, timeout_s: float) -> Decide:
    ""
    if pool.get(rung) is None:
        raise ValueError(f"no rung named {rung!r} for the ladder manager to ask")

    def decide(
        state: Mapping[str, Any], questions: Mapping[str, decision.Question]
    ) -> decision.Decision:
        return decision.classify_for(
            pool, dict(state), questions, rung=rung, timeout_s=timeout_s
        )

    return decide
