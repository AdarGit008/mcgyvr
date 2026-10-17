"""The ladder manager: sizing the local rungs to their queues, by asking Jev.

``mcgyvr manage`` builds a :class:`Manager` and calls :meth:`Manager.tick` every
``manager.interval_s`` seconds; ``mcgyvr run`` asks :func:`for_task` what a task
should climb under. Both mean nothing unless :func:`applicable` returns ``None``
— ``serving.enable_sleep_wake`` is on and the ladder holds a local rung that can
sleep and wake — and every function here then hands back what it was given.

A tick reads pressure on each resident local rung and works out the moves the
queue allows: a wake of a sleeping dearer rung once the dearest awake one is
full, and a sleep of an idle dearer rung once nothing anywhere is queued. Those
moves, the fan-out modes and the lead rungs the config lists become
:class:`mcgyvr.decision.Choice` questions for Jev, and a switch is made only
after the same answer ``manager.confirm`` times running, and never sooner than
``manager.dwell_s`` after the last switch. A wake first sleeps the units whose
memory the woken rung needs and wakes them again if the wake fails or the woken
rung is later slept; a queue that sleeping and waking cannot answer is printed
as a recommendation and left alone.

The fan-out and lead in force are published to the board in the rendezvous
directory, where :func:`effective` picks them up for a task that starts soon
after, on the same ladder.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr import decision
from mcgyvr.config import Ladder

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.cooldown import SharedHold
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.pressure import Gauge, Reading

#: The names of the three questions a tick may put to Jev. Each name keys the
#: question in ``questions``, its answer in ``answers``, and its streak of answers.
ASK_LADDER = "ladder"
ASK_FANOUT = "fanout"
ASK_LEAD = "lead"

#: The rendezvous lock name ``mcgyvr manage`` takes before it manages anything, so
#: two managers on one host cannot sleep and wake the same cards. It is held for
#: the whole run, because every sleep and wake is a side effect on shared hardware.
MANAGER_LOCK = "ladder-manager"

#: The key of the move that changes nothing, always offered so the ladder question
#: has a way to leave the ladder alone; and the answer that leaves the ladder's own
#: order as the lead.
HOLD = "hold"
KEEP_ORDER = "ladder"


class Switches(Protocol):
    """The power to sleep and wake rungs, and the card each rung sits on.

    ``sleep`` and ``wake`` answer whether the switch happened. ``room_for`` names
    the units that must sleep to give ``rung`` its card's memory, and ``card_of``
    names the units sharing ``rung``'s card, ``rung`` among them.
    """

    def wake(self, rung: str) -> bool: ...

    def sleep(self, rung: str) -> bool: ...

    def room_for(self, rung: str) -> tuple[str, ...]: ...

    def card_of(self, rung: str) -> tuple[str, ...]: ...


class PressureSource(Protocol):
    """Where one rung's queue is read from, by rung name."""

    def read(self, rung: str) -> Reading: ...


class Cooling(Protocol):
    """Which rungs are cooling down, and how the last switch on one turned out.

    ``cooled`` answers for a batch of rungs and names the ones to leave alone;
    ``worked`` and ``failed`` report a switch the manager just attempted.
    """

    def cooled(self, rungs: tuple[str, ...]) -> frozenset[str]: ...

    def failed(self, rung: str) -> None: ...

    def worked(self, rung: str) -> None: ...


#: The decision seam: state and questions in, a decision out. A test passes a plain
#: function; ``mcgyvr manage`` passes ``decide_on(...)``, which asks Jev.
Decide = Callable[
    [Mapping[str, Any], Mapping[str, decision.Question]], decision.Decision
]


@dataclass(frozen=True)
class Bounds:
    """The ``manager`` block of the config, as the manager uses it.

    ``interval_s`` is how long :func:`run` waits between ticks, ``confirm`` how
    many identical answers in a row it takes to act, ``dwell_s`` the least time
    between two switches — and also how long a rung must stay idle before it may
    be slept — and ``fanouts``/``leads`` the only values the manager may move the
    fan-out and the lead rung to. :meth:`of` reads them from a config.
    """

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
        """Whether the config lets the manager touch fan-out or the lead at all.

        True when at least two fan-out modes are listed or any lead is, which is
        also the one case in which a tick publishes what it chose.
        """
        return len(self.fanouts) >= 2 or bool(self.leads)


@dataclass(frozen=True)
class View:
    """The ladder as the manager sees it for the whole run.

    ``resident`` is the local rungs in ladder order, cheapest first; ``sleepable``
    the rungs it may put down; ``jev`` the rung Jev answers on, whose card is never
    slept; and ``fanout``/``ladder`` the config's fan-out mode and rung order as
    they were at startup. :meth:`of` builds it from a config.
    """

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
    """What one pass saw, asked and did.

    ``readings`` is one pressure reading per resident rung. ``asked`` maps each
    question name to the option keys it offered, ``answers`` each answered name to
    the choice picked. ``acted`` holds the lines printed for what the manager
    actually did, and ``recommended`` the printed recommendation, if the queue
    called for something the manager may not do itself.
    """

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
    """How much work is backed up behind a rung.

    That is what is waiting plus the part of what is in flight that runs past the
    rung's width; a count that was not read counts as nothing.
    """
    overflow = max(0, (reading.in_flight or 0) - reading.width)
    return (reading.waiting or 0) + overflow


def _load(reading: Reading) -> str:
    """A reading's queue as the prose a recommendation prints it in.

    A count that was not read is printed as ``unread`` rather than guessed at.
    """
    in_flight = "unread" if reading.in_flight is None else str(reading.in_flight)
    waiting = "unread" if reading.waiting is None else str(reading.waiting)
    return f"{in_flight} in flight of {reading.width}, {waiting} waiting"


def _idle(reading: Reading) -> bool:
    """Whether a reading shows a rung with nothing in flight, waiting or climbed.

    A count that was not read is not zero, so an unread reading is not idle.
    """
    return reading.in_flight == 0 and reading.waiting == 0 and reading.climbed == 0


class Manager:
    """One ladder's manager: reads pressure, asks Jev, sleeps and wakes rungs.

    Every seam is injected — pressure readings, the switches that sleep and wake,
    the decision function, cooling, the clock, where lines are printed, and where
    the fan-out and lead in force are published — so a tick can be driven by fakes
    in a test. The manager owns no thread: :meth:`tick` is one pass, and
    :func:`run` calls it.
    """

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
        #: What each resident rung was last seen to be doing. A rung that wakes or
        #: goes down without the manager — a task, or a person running ``mcgyvr
        #: serve`` — is found here, counts as a switch, and starts the dwell.
        self._expected: dict[str, bool] = {}
        #: When each resident rung was first seen awake and idle, so ``dwell_s`` of
        #: idleness has to pass before it is put to sleep.
        self._idle_since: dict[str, float] = {}
        #: The units each woken rung needed asleep for its room, to wake back when
        #: that rung sleeps.
        self._room: dict[str, tuple[str, ...]] = {}
        self._fanout = view.fanout
        self._lead = KEEP_ORDER
        self._recommended: str | None = None

    # Queries over one pass's readings: which rungs are cooling, which is dearest.

    def _cooled(self) -> frozenset[str]:
        if self._cooling is None:
            return frozenset()
        return self._cooling.cooled(self._view.resident)

    def _top(self, readings: Mapping[str, Reading]) -> str | None:
        awake = [r for r in self._view.resident if readings[r].awake]
        return awake[-1] if awake else None

    def _rank(self, rung: str) -> int:
        return self._view.resident.index(rung)

    # The moves the queue allows: wakes above a full rung, sleeps of idle rungs.

    def _wakes(
        self,
        readings: Mapping[str, Reading],
        cooled: frozenset[str],
        top: str | None,
    ) -> tuple[list[_Move], str | None]:
        """The wakes a full dearest rung licenses, or a recommendation instead.

        ``top`` is the dearest awake local rung. While it is full, every sleeping
        resident rung above it on the ladder is a candidate wake, unless it is
        cooling down or the units whose memory it needs may not be slept. With no
        candidate left, the second item is a recommendation saying that the queue
        is past what sleeping and waking can answer.
        """
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
            # A room unit that is down holds nothing, so only the ones that are up,
            # or that were not read at all, are still left to sleep.
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
        """Whether the manager may put ``rung`` to sleep.

        It must be a sleepable resident rung that is awake, its card must not hold
        Jev, and some awake rung below it on the ladder must sit on another card,
        so its work has somewhere cheaper to go. With ``room`` the rest of its card
        need not be idle: the caller is clearing the card for a wake, the one case
        where a card is emptied in order to be filled again.
        """
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
        """The sleeps the queue allows.

        Nothing is put to sleep while any awake rung has work backed up behind it;
        otherwise every rung that :meth:`_may_sleep` permits, that is not cooling
        down, and whose card has been idle for ``dwell_s`` is a candidate.
        """
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
        """Whether every rung on ``rung``'s card has been idle for ``dwell_s``.

        A rung missing from ``readings`` is skipped, and one whose idle time was
        never recorded fails the test.
        """
        for r in self._switches.card_of(rung):
            if r not in readings:
                continue
            since = self._idle_since.get(r)
            if since is None or now - since < self._bounds.dwell_s:
                return False
        return True

    def _observe(self, readings: Mapping[str, Reading], now: float) -> list[str]:
        """Record idle times, and notice rungs that changed state on their own.

        Returns one line per rung found awake when it was expected down, or the
        other way round. Such a change counts as a switch, so the dwell starts
        again and the streaks reset. The first pass only records, since nothing is
        expected of a rung yet.
        """
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
        """Expect ``awake`` of ``rung`` and of every rung sharing its card.

        Only rungs already expected are updated, so a switch the manager makes
        before its first pass is not mistaken for someone else's.
        """
        for r in self._switches.card_of(rung):
            if r in self._expected:
                self._expected[r] = awake

    # One pass, as :func:`run` drives it: read, ask, act, publish, report.

    def tick(self) -> Tick:
        """One pass: read the ladder, ask Jev, act on confirmed answers, publish.

        Pressure is read on every resident rung, the moves the queue allows are
        worked out, and the questions the config permits are put to Jev. If the
        last switch is at least ``dwell_s`` old, an answer confirmed ``confirm``
        times running is acted on — one switch per pass, because acting starts the
        dwell — while inside the dwell answers only lengthen their streaks. A
        decision that fails is printed as a warning and resets every streak. The
        fan-out and lead in force are published to the board when the config lets
        either change. Returns what this pass saw, asked and did.
        """
        now = self._clock()
        readings = {rung: self._pressure.read(rung) for rung in self._view.resident}
        cooled = self._cooled()
        top = self._top(readings)
        acted: list[str] = self._observe(readings, now)

        # A lead that is no longer serving — asleep, or cooling down — falls back
        # to the ladder's own order without asking, since it is no longer a choice.
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

    # The brakes: how many answers in a row it takes, and how long between switches.

    def _confirmed(self, name: str, answer: str) -> bool:
        """Hear ``answer`` once more and say whether its run reached ``confirm``."""
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

    # Carrying a move out, and the switch calls and give-backs behind it.

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
        """Take down how one switch call turned out.

        On success the rung's card is expected to match the new state, and cooling
        is told the switch worked; on failure the expectation is left alone and
        cooling is told it failed, which is what can hold a rung out of the next
        attempt.
        """
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

    # A recommendation is printed when it changes, and reported on every pass.

    def _recommend(self, line: str | None) -> tuple[str, ...]:
        """Keep and print a recommendation only while it stays the same.

        Returns the line as a one-item tuple for the pass to report, or an empty
        tuple when there is nothing to recommend.
        """
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
    """Call :meth:`Manager.tick` every ``interval_s`` until ``ticks`` passes are done.

    ``ticks=None`` runs until it is interrupted. Returns the number of passes made,
    and never sleeps after the last one. ``sleep`` is injected so a test can drive
    the loop without waiting.
    """
    count = 0
    while ticks is None or count < ticks:
        manager.tick()
        count += 1
        if ticks is None or count < ticks:
            sleep(interval_s)
    return count


# The ladder's local rungs, read from a config: who is resident, who can sleep.


def _local(config: Config) -> tuple[str, ...]:
    return tuple(
        name
        for name in config.ladder.names
        if name in config.units and not config.units[name].requires_credential
    )


def sleepable_rungs(config: Config) -> tuple[str, ...]:
    """The resident rungs the manager may put to sleep, in ladder order.

    A rung qualifies when it is local — its unit needs no credential — and mcgyvr
    can sleep and wake its card: exactly one launch spec sits under
    ``serving.compose_dir``, the card holds no unit of Jev's, and no shard of the
    unit runs on another host.
    """
    from mcgyvr.wake import left_alone, wakeable_rungs

    wakeable = set(wakeable_rungs(config)) - set(left_alone(config))
    return tuple(name for name in _local(config) if name in wakeable)


def applicable(config: Config) -> str | None:
    """Why the ladder manager has nothing to do here, or ``None`` when it has work.

    The reasons are prose for a person: ``serving.enable_sleep_wake`` is off, or no
    local rung on the ladder can sleep and wake, in which case every card that is
    left alone says why.
    """
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
    """The config a task should climb under, given what the manager published.

    A published board is used only when the manager applies, the board is a
    mapping for this same ladder, and its ``written_at`` is a number no more than
    ``interval_s * confirm`` seconds old and not in the future. A fan-out outside
    ``manager.fanouts`` and a lead outside ``manager.leads`` are ignored. When
    nothing changes this returns ``config`` itself, so an unchanged result can be
    told apart from one the manager had a say in.
    """
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
    """The ladder order with ``lead`` placed first among the local rungs.

    The other rungs keep their order: ``lead`` is inserted just before the first
    local rung, which is the front of the ladder when no other local rung is left.
    Hosted rungs ahead of that point stay ahead of it.
    """
    local = _local(config)
    rest = [name for name in config.ladder.names if name != lead]
    at = next((i for i, name in enumerate(rest) if name in local), 0)
    return (*rest[:at], lead, *rest[at:])


def gauge_for(config: Config) -> Gauge | None:
    """A :class:`~mcgyvr.pressure.Gauge` for counting climbs, or ``None``.

    One is made only when the manager applies, since only a manager asks whether a
    rung with work climbing through it is idle.
    """
    if applicable(config) is not None:
        return None
    from mcgyvr.pressure import Gauge

    return Gauge()


def presence_for(
    config: Config, gauge: Any
) -> Callable[[str], AbstractContextManager[object]] | None:
    """A hook marking a rung as climbed for as long as a task is on it.

    Returns ``None`` when the manager does not apply or no gauge was made.
    Otherwise the hook takes a rung name and returns a context manager to hold
    while a task climbs there, whose marker the gauge counts so the rung's
    pressure reads as climbed rather than idle.
    """
    if applicable(config) is not None or gauge is None:
        return None
    from mcgyvr.pressure import climbed_key

    def present(rung: str) -> AbstractContextManager[object]:
        marked: AbstractContextManager[object] = gauge.present(climbed_key(rung))
        return marked

    return present


@dataclass(frozen=True)
class ForTask:
    """What one task climbs under, and the hooks that need the manager's accounts.

    ``config`` is the config to climb with, changed only when the manager published
    a choice this task is fresh enough to apply. ``gauge`` and ``presence`` are
    ``None`` when nothing is managed. ``note`` is a line to print when the
    manager's choice shaped this task.
    """

    config: Config
    gauge: Gauge | None = None
    presence: Callable[[str], AbstractContextManager[object]] | None = None
    note: str | None = None
    #: Where the task's cooldown writes its holds, so the manager's cooling and
    #: every other process on the host read the same record of what is cooling.
    held: SharedHold | None = None


def for_task(
    config: Config,
    *,
    read_board: Callable[[], Mapping[str, Any] | None],
    now: Callable[[], float] = time.time,
) -> ForTask:
    """What this task should climb under, settled once before the climb starts.

    When the manager does not apply, the config is passed through untouched and no
    gauge, presence or hold is handed on. Otherwise the board is read once,
    :func:`effective` applies any fresh choice, and ``note`` is set when that
    choice differs from the config on disk.
    """
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
    """A :data:`Decide` that asks Jev, or the unit at ``rung``, for the manager.

    ``rung`` is checked against the pool at once, so a name that is not there
    fails where the manager is built rather than inside a pass. The returned
    function hands the state and questions to
    :func:`mcgyvr.decision.classify_for`, which asks the bound Jev role when the
    pool has one and the unit at ``rung`` when it does not.
    """
    if pool.get(rung) is None:
        raise ValueError(f"no rung named {rung!r} for the ladder manager to ask")

    def decide(
        state: Mapping[str, Any], questions: Mapping[str, decision.Question]
    ) -> decision.Decision:
        return decision.classify_for(
            pool, dict(state), questions, rung=rung, timeout_s=timeout_s
        )

    return decide
