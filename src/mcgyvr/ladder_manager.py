"""The ladder manager: Jev keeps the local ladder sized to the work queued on it.

Tasks start on the cheap, fast local rungs. Over a batch, the work that those
rungs could not finish climbs, and the dearest local rung that is awake fills
with it: dispatches wait for its slots, its own server reports more in flight
than it serves at once, and tasks that climbed to it pile up. That queue is
the signal. A sleeping dearer unit could take it; an idle dearer unit is
holding a card the fast rungs could use. This module watches the queue and
moves the ladder between those two shapes.

**Optional, per fleet.** It runs only under ``mcgyvr manage``, and only where
the ladder has units that can sleep and wake — a local rung whose card holds
exactly one launch spec (:func:`mcgyvr.wake.wakeable_rungs`) — and
``serving.enable_sleep_wake`` is on. :func:`applicable` says why not otherwise,
and every hook a task process takes from here (:func:`effective`,
:func:`gauge_for`, :func:`presence_for`) is then the identity or ``None``: a
ladder with nothing to sleep or wake behaves exactly as it did before this
module existed.

**Jev decides, in types and never in prose.** Every ``interval_s`` the manager
reads the queue on each local rung and asks Jev — a small local model,
through :func:`mcgyvr.decision.classify` — a :class:`~mcgyvr.decision.Choice`
for each decision that has more than one legal answer: the ladder move (hold,
wake a sleeping unit, put an idle one back to sleep), the fan-out mode and the
lead rung. A question with one legal answer is not asked, so a quiet ladder
costs no decision at all.

**What is legal is decided here, and is the hysteresis band.** A wake is
offered only while the dearest awake local rung is full — its server's own
count at its width, by the one check the climb's idle spill makes too
(:meth:`mcgyvr.capacity.Capacity.judge`); a sleep only for a unit whose whole
card has read idle — nothing in flight, nothing waiting and nothing climbed —
for at least ``dwell_s`` without a break, over a ladder with no queue
anywhere. Between the two bands only "hold" is legal. Then Jev must give the
same answer ``confirm`` times in a row before anything moves, and no two
switches are closer than ``dwell_s``, so a queue that flickers across one band
does not flap the ladder.

**A switch somebody else made counts as one.** A task that climbs to a sleeping
unit wakes it itself, through the dispatch-side door
(:meth:`mcgyvr.wake.Waker.dispatching`), and a person may run ``mcgyvr serve``.
The manager notices a unit whose state changed without it and starts the dwell
from there, so a unit a task just woke is not put back to sleep a few ticks
later only to be woken by the next climb.

**Its powers are sleep and wake, and nothing else.** The manager acts through
:class:`Switches`, whose only verbs are ``wake`` and ``sleep`` of a unit that
can do both — reversible acts, through the same gated door a person's
``mcgyvr serve`` uses (:class:`mcgyvr.wake.CardSwitches`). It never puts a
different model on a card, never changes a unit or a fleet: a flood that only a
model it cannot wake would answer, or a wake that needs room held by a unit it
may not sleep, is printed as a recommendation for a person to act on.

**What a sleep is.** A card whose units are all vLLM, run with sleep mode, is
slept at vLLM's level 2: the process and its container stay up, the weights and
the KV cache leave the card, and a wake reads the weights back from disk into
the same process through vLLM's wake route — no container start. Any other
card, and a vLLM card with no sleep route, is stopped instead, as ``mcgyvr
serve sleep`` stops it: its containers go down, and a wake starts them from the
launch spec and loads the model from disk. Either way a wake is a load from
disk, so ``dwell_s`` should be longer than the wake time ``mcgyvr serve wake``
prints.

* It never sleeps the card Jev itself runs on, and always leaves an awake rung
  below the unit it sleeps — the ladder keeps a floor.
* It never wakes or sleeps a unit that is cooling down, and a wake or sleep
  that fails is recorded as a failure against that unit (:class:`Cooling`).
  The record is the manager's own: a task's cooldown does not read it.
* A wake that needs another unit's room sleeps that unit first, and the sleep
  that ends the wake wakes it again: the card goes back to the fast rungs.

**Pipeline choices stay inside their bounds.** Fan-out and the lead rung — the
local unit new tasks start on — are chosen only among ``manager.fanouts`` and
``manager.leads``; empty bounds mean the question is never asked and nothing
is published. A task applies a published choice through :func:`effective`
only while it is fresh and only for the ladder it was made for, so a manager
that stopped, or that runs over another config, changes nothing.

**Above the seam.** It names rungs and never a machine: the pressure it reads
(:class:`mcgyvr.pressure.Pressure`), the switches it throws and the decision it
asks for are below-the-seam answers handed in through seams that speak in rung
names.
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
    from mcgyvr.pool import SourceMap
    from mcgyvr.pressure import Gauge, Reading

#: The question names Jev is asked under. One spelling each, because the
#: answer is read back by the same key.
ASK_LADDER = "ladder"
ASK_FANOUT = "fanout"
ASK_LEAD = "lead"

#: The name one host's ladder manager holds (:func:`mcgyvr.pressure.exclusive`)
#: while it runs: two managers of one ladder would each sleep what the other
#: had just woken.
MANAGER_LOCK = "ladder-manager"

#: The ladder move that changes nothing, and the lead that keeps the order the
#: config wrote.
HOLD = "hold"
KEEP_ORDER = "ladder"


class Switches(Protocol):
    """The only acts the manager has: wake and sleep a unit that can do both.

    ``room_for`` names the units that must sleep before ``rung`` can wake, and
    ``card_of`` the rungs a sleep of ``rung`` takes down with it — sleep and
    wake are whole-card acts.
    """

    def wake(self, rung: str) -> bool: ...

    def sleep(self, rung: str) -> bool: ...

    def room_for(self, rung: str) -> tuple[str, ...]: ...

    def card_of(self, rung: str) -> tuple[str, ...]: ...


class PressureSource(Protocol):
    """One reading of the queue on a rung, now."""

    def read(self, rung: str) -> Reading: ...


class Cooling(Protocol):
    """The units held out after failing, and the record of what failed."""

    def cooled(self, rungs: tuple[str, ...]) -> frozenset[str]: ...

    def failed(self, rung: str) -> None: ...

    def worked(self, rung: str) -> None: ...


#: Jev, as a seam: a state and typed questions in, a typed decision out.
Decide = Callable[
    [Mapping[str, Any], Mapping[str, decision.Question]], decision.Decision
]


@dataclass(frozen=True)
class Bounds:
    """The ``manager`` block: how often, how sure, how far apart, and within what."""

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
        """Whether any pipeline choice is Jev's to make at all."""
        return len(self.fanouts) >= 2 or bool(self.leads)


@dataclass(frozen=True)
class View:
    """The ladder as the manager sees it: rung names and nothing that runs.

    ``resident`` is the local rungs in ladder order, cheapest first;
    ``sleepable`` the ones that can sleep and wake; ``jev`` the rung the
    decisions run on; ``fanout`` and ``ladder`` the config's own, which a
    publication is checked against.
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
    """What one tick read, asked, heard and did."""

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
    """Work on this rung beyond what it serves at once: waiting plus overflow."""
    overflow = max(0, (reading.in_flight or 0) - reading.width)
    return (reading.waiting or 0) + overflow


def _load(reading: Reading) -> str:
    """A rung's load in words, for a recommendation a person reads."""
    in_flight = "unread" if reading.in_flight is None else str(reading.in_flight)
    waiting = "unread" if reading.waiting is None else str(reading.waiting)
    return f"{in_flight} in flight of {reading.width}, {waiting} waiting"


def _idle(reading: Reading) -> bool:
    """Provably idle: every count read, and every one of them zero."""
    return reading.in_flight == 0 and reading.waiting == 0 and reading.climbed == 0


class Manager:
    """One ladder's manager: reads the queue, asks Jev, throws switches."""

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
        #: Whether each rung was awake as of the last tick, with the manager's
        #: own switches applied: a reading that disagrees is a switch somebody
        #: else made.
        self._expected: dict[str, bool] = {}
        #: When each awake rung was first read idle in the run of idle readings
        #: it is in now; a rung that is busy or asleep has no entry.
        self._idle_since: dict[str, float] = {}
        #: The units each wake slept to make room, given back by its sleep.
        self._room: dict[str, tuple[str, ...]] = {}
        self._fanout = view.fanout
        self._lead = KEEP_ORDER
        self._recommended: str | None = None

    # --- reading ------------------------------------------------------------

    def _cooled(self) -> frozenset[str]:
        if self._cooling is None:
            return frozenset()
        return self._cooling.cooled(self._view.resident)

    def _top(self, readings: Mapping[str, Reading]) -> str | None:
        awake = [r for r in self._view.resident if readings[r].awake]
        return awake[-1] if awake else None

    def _rank(self, rung: str) -> int:
        return self._view.resident.index(rung)

    # --- what is legal ------------------------------------------------------

    def _wakes(
        self,
        readings: Mapping[str, Reading],
        cooled: frozenset[str],
        top: str | None,
    ) -> tuple[list[_Move], str | None]:
        """The legal wakes, and the recommendation a flood with none earns.

        A flood is the dearest awake local rung being **full** — the one
        definition, :meth:`mcgyvr.capacity.Capacity.judge`, that the climb's
        idle spill reads too: its server's own count at width, which sees every
        client, or this process's load, which here is nothing.
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
            room = self._switches.room_for(rung)
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
        """Whether ``rung`` is a unit the manager may put to sleep at all.

        Never the card Jev runs on, never a unit that cannot wake again, never
        one already asleep, and never the last awake rung below it. ``room``
        is a sleep that makes way for a wake, which drains rather than waiting
        for idle.
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
        """The legal sleeps: idle units whose whole card has idled for the dwell.

        The band is a duration, not a count of answers: a unit is offered only
        once every rung of its card has read idle for ``dwell_s`` without a
        break, so a batch that climbs to it now and then keeps it awake. A
        cooling unit is not offered either — a sleep that keeps failing would
        otherwise be asked about again every dwell.
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
        """Whether every rung of ``rung``'s card has idled for ``dwell_s`` by now."""
        for r in self._switches.card_of(rung):
            if r not in readings:
                continue
            since = self._idle_since.get(r)
            if since is None or now - since < self._bounds.dwell_s:
                return False
        return True

    def _observe(self, readings: Mapping[str, Reading], now: float) -> list[str]:
        """Keep the idle clocks, and count a switch somebody else made as one.

        A task that climbs to a sleeping unit wakes it through the dispatch-side
        door (:meth:`mcgyvr.wake.Waker.dispatching`), and a person may run
        ``mcgyvr serve``. Either is a unit that changed state without the
        manager, and it earns the dwell a switch of the manager's own would:
        otherwise a unit a task just woke could be put back to sleep a few ticks
        later, and the next climb would wake it again.
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
        """Record a switch of the manager's own, for the whole card it moved."""
        for r in self._switches.card_of(rung):
            if r in self._expected:
                self._expected[r] = awake

    # --- one tick -------------------------------------------------------------

    def tick(self) -> Tick:
        """Read, decide whether to ask, ask, and act on a confirmed answer."""
        now = self._clock()
        readings = {rung: self._pressure.read(rung) for rung in self._view.resident}
        cooled = self._cooled()
        top = self._top(readings)
        acted: list[str] = self._observe(readings, now)

        # A lead that is asleep or cooling is not a place to start tasks, and
        # dropping it is a safety reset, not a decision to be confirmed.
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

    # --- hysteresis -----------------------------------------------------------

    def _confirmed(self, name: str, answer: str) -> bool:
        """Hear ``answer``; true once it is the ``confirm``-th in a row."""
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

    # --- acting ---------------------------------------------------------------

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
        """Record a switch's outcome: the state it left, and what cooling learns."""
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

    # --- what Jev is told -----------------------------------------------------

    def _recommend(self, line: str | None) -> tuple[str, ...]:
        """Print a recommendation once, and again only when it changes."""
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
    """Tick ``manager`` every ``interval_s`` until ``ticks`` (forever by default).

    Stopped by the caller (``KeyboardInterrupt`` under ``mcgyvr manage``);
    returns how many ticks ran.
    """
    count = 0
    while ticks is None or count < ticks:
        manager.tick()
        count += 1
        if ticks is None or count < ticks:
            sleep(interval_s)
    return count


# --- what a config says about the manager ----------------------------------


def _local(config: Config) -> tuple[str, ...]:
    return tuple(
        name
        for name in config.ladder.names
        if name in config.units and not config.units[name].requires_credential
    )


def sleepable_rungs(config: Config) -> tuple[str, ...]:
    """The local ladder rungs that can sleep and wake, in ladder order.

    :func:`mcgyvr.wake.wakeable_rungs`' answer — a card that holds exactly one
    launch spec — reused rather than restated, and kept to the ladder's local
    rungs.
    """
    from mcgyvr.wake import wakeable_rungs

    wakeable = set(wakeable_rungs(config))
    return tuple(name for name in _local(config) if name in wakeable)


def applicable(config: Config) -> str | None:
    """``None`` when this ladder has a manager, else the sentence saying why not."""
    if not config.get("serving.enable_sleep_wake"):
        return (
            "serving.enable_sleep_wake is off, so mcgyvr may not sleep or wake "
            "any unit on its own and there is nothing for the manager to do"
        )
    if not sleepable_rungs(config):
        return (
            "no local unit on this ladder can sleep and wake: a unit can when "
            "its card holds exactly one launch spec under serving.compose_dir "
            "(`mcgyvr emit --out`)"
        )
    return None


def effective(
    config: Config, published: Mapping[str, Any] | None, *, now: float
) -> Config:
    """The config a task runs under, with the manager's fresh choice applied.

    ``config`` itself — the same object — unless all of these hold: the ladder
    is managed (:func:`applicable`); a choice was published for this exact
    ladder; it is fresh, written within ``confirm`` ticks of ``now`` (wall
    clock, since the manager is another process) — a manager that missed as
    many ticks as it takes to act is no longer watching; and each value it
    carries is inside this config's own bounds. A value outside them is
    ignored on its own, and the rest still apply.
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
    """The ladder with ``lead`` first among the local rungs; the rest in order."""
    local = _local(config)
    rest = [name for name in config.ladder.names if name != lead]
    at = next((i for i, name in enumerate(rest) if name in local), 0)
    return (*rest[:at], lead, *rest[at:])


def gauge_for(config: Config) -> Gauge | None:
    """The host-wide gauge a managed ladder's tasks report to, or ``None``."""
    if applicable(config) is not None:
        return None
    from mcgyvr.pressure import Gauge

    return Gauge()


def presence_for(
    config: Config, gauge: Any
) -> Callable[[str], AbstractContextManager[object]] | None:
    """The climb's ``presence`` hook: mark a task that climbed to a rung.

    ``None`` for a ladder with no manager, which is the climb as it was.
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
    """What a task process takes from the manager: its config and two hooks.

    ``note`` says what a published choice changed, for the operator, and is
    ``None`` when it changed nothing.
    """

    config: Config
    gauge: Gauge | None = None
    presence: Callable[[str], AbstractContextManager[object]] | None = None
    note: str | None = None


def for_task(
    config: Config,
    *,
    read_board: Callable[[], Mapping[str, Any] | None],
    now: Callable[[], float] = time.time,
) -> ForTask:
    """The config, gauge and presence hook one ``mcgyvr run`` climbs with.

    An unmanaged ladder gets ``ForTask(config)`` and nothing else, and the
    board is not so much as read: no file is opened, no gauge is built and the
    climb takes no hook, which is the run exactly as it was.
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
    return ForTask(
        config=chosen,
        gauge=gauge,
        presence=presence_for(chosen, gauge),
        note=note,
    )


def decide_on(pool: SourceMap, rung: str, *, timeout_s: float) -> Decide:
    """Jev on ``rung``: :func:`mcgyvr.decision.classify` through its endpoint."""
    resolved = pool.get(rung)
    if resolved is None:
        raise ValueError(f"no rung named {rung!r} for the ladder manager to ask")
    model = resolved.model

    def decide(
        state: Mapping[str, Any], questions: Mapping[str, decision.Question]
    ) -> decision.Decision:
        return decision.classify(
            pool.bind(rung), model, dict(state), questions, timeout_s=timeout_s
        )

    return decide
