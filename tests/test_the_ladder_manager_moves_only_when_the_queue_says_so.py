"""The ladder manager: Jev sizes the ladder to its queue, and moves only when sure.

The promises, none of which names a machine or a number read on one:

* **Nothing to manage is nothing done.** A ladder with no unit that can sleep
  and wake — or one whose ``serving.enable_sleep_wake`` is off — has no
  manager: :func:`~mcgyvr.ladder_manager.applicable` says why, the effective
  config a task runs under is the config itself, and no gauge or presence hook
  is handed to a climb. The ladder behaves exactly as it did before the manager
  existed.
* **Jev answers typed questions, and only when there is a choice.** A quiet
  ladder asks nothing; a question with a single legal option is not asked.
  Every question is a :class:`~mcgyvr.decision.Choice`.
* **A flood wakes a bigger sleeping unit; a drained ladder puts it back.**
  Pressure on the dearest awake local rung — work waiting beyond its width —
  makes a wake of a sleeping dearer rung legal. A dearer rung with nothing in
  flight, nothing waiting and nothing climbed, over a ladder with no queue
  anywhere, may be put back to sleep.
* **Hysteresis and dwell.** Jev must give the same answer ``confirm`` times in
  a row before anything moves, and no two switches are closer than ``dwell_s``.
* **Room first, and given back.** A wake that needs another unit's card memory
  sleeps that unit first, and the sleep that ends the wake wakes it again. A
  unit the manager may not sleep blocks the wake and is printed as a
  recommendation, never acted on.
* **Its powers are sleep and wake.** It never sleeps the card Jev runs on,
  never wakes a cooled-down unit, and a flood it cannot answer by waking is a
  printed recommendation, never a load.
* **Pipeline choices stay inside their bounds.** Fan-out and the lead rung are
  chosen only among what ``manager.fanouts`` and ``manager.leads`` allow, and a
  task applies a published choice only while it is fresh and only for the
  ladder it was made for.

Everything here is a fake: pressure, switches, the decision seam and the clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import decision, ladder_manager
from mcgyvr.config import parse
from mcgyvr.ladder_manager import Bounds, Manager, View
from mcgyvr.pressure import Reading

FAST = "local_fast"
MID = "local_mid"
BIG = "local_big"
API = "api_big"

FAST_HOST = "fast-box.example"
BIG_HOST = "big-box.example"


# --- configs ---------------------------------------------------------------


def ladder_text(
    compose_dir: Path | None, *, sleep_wake: bool = True, manager: str = ""
) -> str:
    serving = ""
    if compose_dir is not None:
        serving = (
            "serving:\n"
            f"  compose_dir: {compose_dir}\n"
            f"  enable_sleep_wake: {'true' if sleep_wake else 'false'}\n"
        )
    return (
        "units:\n"
        f"  {FAST}:\n"
        f"    address: http://{FAST_HOST}:8000\n"
        "    model: small-coder\n"
        "    rig: fast-rig\n"
        "    width: 2\n"
        f"  {BIG}:\n"
        f"    address: http://{BIG_HOST}:8001\n"
        "    model: large-coder\n"
        "    rig: big-rig\n"
        "    width: 2\n"
        f"  {API}:\n"
        "    address: https://api.example.com/v1\n"
        "    model: vendor-large\n"
        "    rig: vendor\n"
        "    width: 4\n"
        "    api_key_env: EXAMPLE_API_KEY\n"
        "ladder:\n"
        f"- {FAST}\n"
        f"- {BIG}\n"
        f"- {API}\n"
        "max_escalations: 2\n"
        "profile: dev\n" + serving + manager
    )


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)


def write_spec(tmp_path: Path, host: str) -> Path:
    """One launch spec for ``host``, as ``emit`` would write it."""
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    (where / f"{COMPOSE_PREFIX}{host}{COMPOSE_SUFFIX}").write_text(
        "services:\n  big:\n    image: example/server:1\n", encoding="utf-8"
    )
    return where


# --- fakes -----------------------------------------------------------------


def reading(
    rung: str,
    *,
    awake: bool = True,
    in_flight: int | None = 0,
    waiting: int | None = 0,
    climbed: int | None = 0,
    width: int = 2,
) -> Reading:
    return Reading(
        rung=rung,
        awake=awake,
        in_flight=in_flight,
        waiting=waiting,
        climbed=climbed,
        width=width,
    )


class FakePressure:
    def __init__(self, *readings: Reading) -> None:
        self.now: dict[str, Reading] = {r.rung: r for r in readings}

    def set(self, value: Reading) -> None:
        self.now[value.rung] = value

    def read(self, rung: str) -> Reading:
        return self.now[rung]


class FakeSwitches:
    """Records every switch, and moves the fake pressure with it."""

    def __init__(
        self,
        pressure: FakePressure,
        *,
        room: Mapping[str, tuple[str, ...]] | None = None,
        cards: Mapping[str, tuple[str, ...]] | None = None,
        fail: set[str] | None = None,
    ) -> None:
        self.pressure = pressure
        self.room = dict(room or {})
        self.cards = dict(cards or {})
        self.fail = set(fail or ())
        self.calls: list[tuple[str, str]] = []

    def _move(self, rung: str, awake: bool) -> bool:
        if rung in self.fail:
            return False
        old = self.pressure.now[rung]
        self.pressure.set(
            Reading(
                rung=rung,
                awake=awake,
                in_flight=0,
                waiting=old.waiting,
                climbed=old.climbed,
                width=old.width,
            )
        )
        return True

    def wake(self, rung: str) -> bool:
        self.calls.append(("wake", rung))
        return self._move(rung, True)

    def sleep(self, rung: str) -> bool:
        self.calls.append(("sleep", rung))
        return self._move(rung, False)

    def room_for(self, rung: str) -> tuple[str, ...]:
        return self.room.get(rung, ())

    def card_of(self, rung: str) -> tuple[str, ...]:
        return self.cards.get(rung, (rung,))


class FakeCooling:
    def __init__(self, cooled: set[str] | None = None) -> None:
        self.out = set(cooled or ())
        self.failures: list[str] = []
        self.successes: list[str] = []

    def cooled(self, rungs: tuple[str, ...]) -> frozenset[str]:
        return frozenset(r for r in rungs if r in self.out)

    def failed(self, rung: str) -> None:
        self.failures.append(rung)

    def worked(self, rung: str) -> None:
        self.successes.append(rung)


class FakeDecide:
    """Answers each question with the scripted option key, and records the ask."""

    def __init__(self, **script: str) -> None:
        self.script = dict(script)
        self.asked: list[dict[str, decision.Question]] = []
        self.states: list[Mapping[str, Any]] = []
        self.raises: Exception | None = None

    def __call__(
        self, state: Mapping[str, Any], questions: Mapping[str, decision.Question]
    ) -> decision.Decision:
        self.asked.append(dict(questions))
        self.states.append(state)
        if self.raises is not None:
            raise self.raises
        answers: dict[str, decision.Answer] = {}
        for name, question in questions.items():
            assert isinstance(question, decision.Choice), "Jev is asked typed choices"
            pick = self.script.get(name, next(iter(question.options)))
            assert pick in question.options, (
                f"{pick!r} is not an option of {name!r}: {list(question.options)}"
            )
            answers[name] = decision.ChoiceAnswer(
                choice=pick,
                probabilities={k: 1.0 if k == pick else 0.0 for k in question.options},
                confidence=1.0,
            )
        return decision.Decision(answers=answers)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def bounds(**over: Any) -> Bounds:
    base: dict[str, Any] = {
        "interval_s": 10.0,
        "confirm": 3,
        "dwell_s": 100.0,
        "fanouts": (),
        "leads": (),
    }
    base.update(over)
    return Bounds(**base)


def view(*resident: str, sleepable: tuple[str, ...] = (BIG,)) -> View:
    rungs = resident or (FAST, BIG)
    return View(
        resident=rungs,
        sleepable=frozenset(sleepable),
        jev=rungs[0],
        fanout="none",
        ladder=(*rungs, API),
    )


def manager(
    pressure: FakePressure,
    switches: FakeSwitches,
    decide: FakeDecide,
    *,
    the_view: View | None = None,
    the_bounds: Bounds | None = None,
    cooling: FakeCooling | None = None,
    clock: Clock | None = None,
    said: list[str] | None = None,
    published: list[Mapping[str, Any]] | None = None,
) -> Manager:
    lines = said if said is not None else []
    board = published if published is not None else []
    return Manager(
        the_view or view(),
        the_bounds or bounds(),
        pressure=pressure,
        switches=switches,
        decide=decide,
        cooling=cooling,
        clock=clock or Clock(),
        say=lines.append,
        publish=board.append,
    )


def flooded() -> FakePressure:
    """The fast rung is saturated with work waiting; the big rung sleeps."""
    return FakePressure(
        reading(FAST, in_flight=2, waiting=3, climbed=2),
        reading(BIG, awake=False, in_flight=None),
    )


def drained() -> FakePressure:
    """The big rung is awake and idle, and nothing waits anywhere."""
    return FakePressure(reading(FAST), reading(BIG))


# --- nothing to manage -----------------------------------------------------


def test_a_ladder_with_a_sleepable_unit_and_the_switch_on_is_managed(
    tmp_path: Path, key: None
) -> None:
    config = parse(ladder_text(write_spec(tmp_path, BIG_HOST)))
    assert ladder_manager.applicable(config) is None
    assert ladder_manager.sleepable_rungs(config) == (BIG,)


def test_a_ladder_with_no_sleepable_unit_is_not_managed_and_runs_as_today(
    tmp_path: Path, key: None
) -> None:
    empty = tmp_path / "specs"
    empty.mkdir()
    config = parse(ladder_text(empty))
    why = ladder_manager.applicable(config)
    assert why is not None and "sleep" in why
    published = {
        "ladder": [FAST, BIG, API],
        "fanout": "idle",
        "lead": BIG,
        "written_at": 0.0,
    }
    assert ladder_manager.effective(config, published, now=0.0) is config
    assert ladder_manager.presence_for(config, gauge=object()) is None
    assert ladder_manager.gauge_for(config) is None

    def no_board() -> dict[str, Any]:
        raise AssertionError("an unmanaged ladder must not read the board")

    task = ladder_manager.for_task(config, read_board=no_board)
    assert task == ladder_manager.ForTask(config)
    assert task.config is config


def test_a_ladder_whose_switch_is_off_is_not_managed(tmp_path: Path, key: None) -> None:
    config = parse(ladder_text(write_spec(tmp_path, BIG_HOST), sleep_wake=False))
    why = ladder_manager.applicable(config)
    assert why is not None and "enable_sleep_wake" in why
    assert ladder_manager.gauge_for(config) is None


# --- asking ----------------------------------------------------------------


def test_a_quiet_ladder_asks_jev_nothing_and_moves_nothing() -> None:
    pressure = FakePressure(reading(FAST), reading(BIG, awake=False, in_flight=None))
    switches = FakeSwitches(pressure)
    decide = FakeDecide()
    run = manager(pressure, switches, decide)
    for _ in range(5):
        run.tick()
    assert decide.asked == []
    assert switches.calls == []


def test_a_flood_offers_jev_a_wake_as_a_typed_choice() -> None:
    pressure = flooded()
    decide = FakeDecide(ladder="hold")
    manager(pressure, FakeSwitches(pressure), decide).tick()
    assert len(decide.asked) == 1
    question = decide.asked[0]["ladder"]
    assert isinstance(question, decision.Choice)
    assert set(question.options) == {"hold", f"wake:{BIG}"}
    rungs = {row["rung"]: row for row in decide.states[0]["rungs"]}
    assert rungs[FAST]["waiting"] == 3 and rungs[BIG]["awake"] is False


# --- hysteresis and dwell ----------------------------------------------------


def test_a_wake_needs_the_same_answer_confirm_times_in_a_row() -> None:
    pressure = flooded()
    switches = FakeSwitches(pressure)
    run = manager(pressure, switches, FakeDecide(ladder=f"wake:{BIG}"))
    run.tick()
    run.tick()
    assert switches.calls == [], "two answers are not three"
    run.tick()
    assert switches.calls == [("wake", BIG)]


def test_answers_that_change_their_mind_never_move_the_ladder() -> None:
    pressure = flooded()
    switches = FakeSwitches(pressure)
    decide = FakeDecide(ladder=f"wake:{BIG}")
    run = manager(pressure, switches, decide)
    for pick in ("wake", "hold", "wake", "wake", "hold", "wake", "wake"):
        decide.script["ladder"] = f"wake:{BIG}" if pick == "wake" else "hold"
        run.tick()
    assert switches.calls == []


def test_no_switch_follows_another_inside_the_dwell() -> None:
    pressure = flooded()
    switches = FakeSwitches(pressure)
    clock = Clock()
    decide = FakeDecide(ladder=f"wake:{BIG}")
    run = manager(pressure, switches, decide, clock=clock)
    for _ in range(3):
        run.tick()
        clock.t += 10
    assert switches.calls == [("wake", BIG)]

    # The flood is gone at once, and Jev says sleep at once — too soon.
    pressure.set(reading(FAST))
    decide.script["ladder"] = f"sleep:{BIG}"
    for _ in range(5):
        run.tick()
        clock.t += 10
    assert switches.calls == [("wake", BIG)], "a sleep inside the dwell is held"

    clock.t += 100
    for _ in range(3):
        run.tick()
        clock.t += 10
    assert switches.calls == [("wake", BIG), ("sleep", BIG)]


def test_a_unit_a_task_woke_is_not_slept_again_inside_the_dwell() -> None:
    """A wake the manager did not make is a switch all the same.

    A task that climbs to a sleeping unit wakes it through the dispatch-side
    door, outside the manager. Were that not a switch, the manager would put
    the unit back to sleep a few ticks later and the next climb would wake it
    again — a container stop and a full model load on every turn, at the pace
    of the batch rather than of ``dwell_s``.
    """
    pressure = FakePressure(reading(FAST), reading(BIG, awake=False, in_flight=None))
    switches = FakeSwitches(pressure)
    clock = Clock()
    run = manager(pressure, switches, FakeDecide(ladder=f"sleep:{BIG}"), clock=clock)
    run.tick()

    for _ in range(2):
        # A task climbs, is refused, and wakes the unit; then it idles.
        clock.t += 10
        pressure.set(reading(BIG))
        woke_at = clock.t
        before = len(switches.calls)
        while clock.t < woke_at + 100:
            run.tick()
            clock.t += 10
        assert switches.calls[before:] == [], (
            "a unit a task woke was slept again inside the dwell"
        )
        for _ in range(3):
            run.tick()
            clock.t += 10
        assert switches.calls[-1] == ("sleep", BIG), (
            "past the dwell, an idle unit is still put back to sleep"
        )
    assert switches.calls == [("sleep", BIG), ("sleep", BIG)]


def test_an_idle_unit_is_offered_for_sleep_only_once_it_has_idled_for_the_dwell() -> (
    None
):
    """The sleep band is a duration, not a count of answers."""
    pressure = drained()
    clock = Clock()
    decide = FakeDecide(ladder="hold")
    run = manager(pressure, FakeSwitches(pressure), decide, clock=clock)
    while clock.t < 1100:
        run.tick()
        clock.t += 10
    assert decide.asked == [], "idle for less than dwell_s is not idle enough"

    run.tick()
    assert set(decide.asked[0]["ladder"].options) == {"hold", f"sleep:{BIG}"}  # type: ignore[union-attr]

    # A moment of work starts the idle time again.
    pressure.set(reading(BIG, in_flight=1))
    clock.t += 10
    run.tick()
    pressure.set(reading(BIG))
    asked = len(decide.asked)
    for _ in range(5):
        clock.t += 10
        run.tick()
    assert len(decide.asked) == asked


# --- both directions -------------------------------------------------------


def test_a_drained_ladder_offers_to_put_the_big_unit_back_to_sleep() -> None:
    pressure = drained()
    switches = FakeSwitches(pressure)
    decide = FakeDecide(ladder=f"sleep:{BIG}")
    run = manager(pressure, switches, decide, the_bounds=bounds(dwell_s=0.0))
    for _ in range(3):
        run.tick()
    assert set(decide.asked[0]["ladder"].options) == {"hold", f"sleep:{BIG}"}  # type: ignore[union-attr]
    assert switches.calls == [("sleep", BIG)]


@pytest.mark.parametrize(
    "busy",
    [
        {"in_flight": 1},
        {"waiting": 1},
        {"climbed": 1},
        {"in_flight": None},
        {"waiting": None},
    ],
    ids=["in-flight", "waiting", "climbed", "in-flight-unread", "waiting-unread"],
)
def test_a_unit_that_is_not_provably_idle_is_never_offered_for_sleep(
    busy: dict[str, Any],
) -> None:
    pressure = FakePressure(reading(FAST), reading(BIG, **busy))
    decide = FakeDecide()
    manager(pressure, FakeSwitches(pressure), decide).tick()
    assert decide.asked == [], "only hold is legal, so nothing is asked"


def test_a_queue_below_keeps_the_big_unit_awake() -> None:
    pressure = FakePressure(reading(FAST, in_flight=2, waiting=1), reading(BIG))
    decide = FakeDecide()
    manager(pressure, FakeSwitches(pressure), decide).tick()
    assert decide.asked == [], "neither a wake nor a sleep is legal, so only hold"


# --- room, cards and cooldown ------------------------------------------------


def test_a_wake_that_needs_room_sleeps_the_smaller_unit_first_and_gives_it_back() -> (
    None
):
    pressure = FakePressure(
        reading(FAST, in_flight=2, waiting=4),
        reading(MID, in_flight=2, waiting=2),
        reading(BIG, awake=False, in_flight=None),
    )
    switches = FakeSwitches(pressure, room={BIG: (MID,)})
    clock = Clock()
    decide = FakeDecide(ladder=f"wake:{BIG}")
    run = manager(
        pressure,
        switches,
        decide,
        the_view=view(FAST, MID, BIG, sleepable=(MID, BIG)),
        clock=clock,
    )
    for _ in range(3):
        run.tick()
        clock.t += 10
    assert switches.calls == [("sleep", MID), ("wake", BIG)]

    pressure.set(reading(FAST))
    run.tick()  # the big unit's idle time starts here
    clock.t += 1000
    decide.script["ladder"] = f"sleep:{BIG}"
    for _ in range(3):
        run.tick()
        clock.t += 10
    assert switches.calls[2:] == [("sleep", BIG), ("wake", MID)]


def test_room_held_by_a_unit_that_cannot_sleep_is_a_recommendation() -> None:
    pressure = FakePressure(
        reading(FAST, in_flight=2, waiting=4),
        reading(MID, in_flight=2, waiting=2),
        reading(BIG, awake=False, in_flight=None),
    )
    switches = FakeSwitches(pressure, room={BIG: (MID,)})
    decide = FakeDecide()
    said: list[str] = []
    run = manager(
        pressure,
        switches,
        decide,
        the_view=view(FAST, MID, BIG, sleepable=(BIG,)),
        said=said,
    )
    for _ in range(4):
        run.tick()
    assert switches.calls == []
    recommendations = [line for line in said if line.startswith("recommend")]
    assert len(recommendations) == 1, "printed once, not every tick"
    assert BIG in recommendations[0] and MID in recommendations[0]


def test_a_flood_with_nothing_to_wake_is_a_recommendation_and_never_a_load() -> None:
    pressure = FakePressure(reading(FAST, in_flight=2, waiting=5), reading(BIG))
    pressure.set(reading(BIG, in_flight=2, waiting=3))
    switches = FakeSwitches(pressure)
    decide = FakeDecide()
    said: list[str] = []
    run = manager(pressure, switches, decide, said=said)
    run.tick()
    run.tick()
    assert switches.calls == []
    assert decide.asked == []
    assert sum(line.startswith("recommend") for line in said) == 1


def test_a_cooled_down_unit_is_never_offered_for_a_wake() -> None:
    pressure = flooded()
    decide = FakeDecide()
    manager(pressure, FakeSwitches(pressure), decide, cooling=FakeCooling({BIG})).tick()
    assert decide.asked == []


def test_a_cooled_down_unit_is_never_offered_for_sleep() -> None:
    """A unit whose sleeps keep failing is not asked about again every dwell."""
    pressure = drained()
    clock = Clock()
    decide = FakeDecide()
    run = manager(
        pressure,
        FakeSwitches(pressure),
        decide,
        cooling=FakeCooling({BIG}),
        clock=clock,
        the_bounds=bounds(dwell_s=0.0),
    )
    for _ in range(3):
        run.tick()
        clock.t += 10
    assert decide.asked == []


def test_the_card_jev_runs_on_is_never_offered_for_sleep() -> None:
    pressure = drained()
    switches = FakeSwitches(pressure, cards={BIG: (FAST, BIG), FAST: (FAST, BIG)})
    decide = FakeDecide()
    manager(pressure, switches, decide).tick()
    assert decide.asked == []


def test_a_failed_wake_cools_the_unit_and_gives_the_room_back() -> None:
    pressure = FakePressure(
        reading(FAST, in_flight=2, waiting=4),
        reading(MID, in_flight=2, waiting=2),
        reading(BIG, awake=False, in_flight=None),
    )
    switches = FakeSwitches(pressure, room={BIG: (MID,)}, fail={BIG})
    cooling = FakeCooling()
    run = manager(
        pressure,
        switches,
        FakeDecide(ladder=f"wake:{BIG}"),
        the_view=view(FAST, MID, BIG, sleepable=(MID, BIG)),
        cooling=cooling,
    )
    for _ in range(3):
        run.tick()
    assert switches.calls == [("sleep", MID), ("wake", BIG), ("wake", MID)]
    assert cooling.failures == [BIG]


def test_a_decision_that_cannot_be_read_holds_and_starts_the_count_again() -> None:
    pressure = flooded()
    switches = FakeSwitches(pressure)
    decide = FakeDecide(ladder=f"wake:{BIG}")
    said: list[str] = []
    run = manager(pressure, switches, decide, said=said)
    run.tick()
    run.tick()
    decide.raises = decision.DecisionError("no labels")
    run.tick()
    decide.raises = None
    run.tick()
    run.tick()
    assert switches.calls == [], "the unreadable answer broke the streak"
    run.tick()
    assert switches.calls == [("wake", BIG)]
    assert any("no labels" in line for line in said)


# --- pipeline choices ---------------------------------------------------------


def test_fanout_is_chosen_only_among_its_bounds_and_published() -> None:
    pressure = FakePressure(reading(FAST), reading(BIG, awake=False, in_flight=None))
    decide = FakeDecide(fanout="idle")
    published: list[Mapping[str, Any]] = []
    run = manager(
        pressure,
        FakeSwitches(pressure),
        decide,
        the_bounds=bounds(fanouts=("none", "idle")),
        published=published,
    )
    for _ in range(3):
        run.tick()
    assert set(decide.asked[0]["fanout"].options) == {"none", "idle"}  # type: ignore[union-attr]
    assert published[-1]["fanout"] == "idle"
    assert published[-1]["ladder"] == [FAST, BIG, API]


def test_without_pipeline_bounds_nothing_is_published() -> None:
    pressure = flooded()
    published: list[Mapping[str, Any]] = []
    run = manager(pressure, FakeSwitches(pressure), FakeDecide(), published=published)
    run.tick()
    assert published == []


def test_a_lead_that_goes_to_sleep_is_dropped_without_asking() -> None:
    pressure = FakePressure(reading(FAST), reading(BIG))
    decide = FakeDecide(lead=BIG)
    published: list[Mapping[str, Any]] = []
    clock = Clock()
    run = manager(
        pressure,
        FakeSwitches(pressure),
        decide,
        the_bounds=bounds(leads=(BIG,)),
        published=published,
        clock=clock,
    )
    for _ in range(3):
        run.tick()
        clock.t += 10
    assert published[-1]["lead"] == BIG
    pressure.set(reading(BIG, awake=False, in_flight=None))
    run.tick()
    assert published[-1]["lead"] == "ladder"


# --- what a task applies -----------------------------------------------------


def managed(tmp_path: Path, manager_block: str) -> Any:
    return parse(ladder_text(write_spec(tmp_path, BIG_HOST), manager=manager_block))


BOUNDED = (
    "manager:\n"
    "  interval_s: 10\n"
    "  confirm: 3\n"
    "  fanouts: [none, idle]\n"
    f"  leads: [{BIG}]\n"
)


def test_a_fresh_published_choice_inside_the_bounds_is_applied(
    tmp_path: Path, key: None
) -> None:
    config = managed(tmp_path, BOUNDED)
    doc = {
        "ladder": [FAST, BIG, API],
        "fanout": "idle",
        "lead": BIG,
        "written_at": 100.0,
    }
    got = ladder_manager.effective(config, doc, now=110.0)
    assert got.ladder.fanout == "idle"
    assert got.ladder.names == (BIG, FAST, API), (
        "the lead moves within the local family"
    )
    assert config.ladder.names == (FAST, BIG, API), "the loaded config is untouched"


@pytest.mark.parametrize(
    "doc",
    [
        {"ladder": [FAST, BIG, API], "fanout": "idle", "written_at": 0.0},
        {"ladder": [BIG, FAST, API], "fanout": "idle", "written_at": 100.0},
        {"ladder": [FAST, BIG, API], "fanout": "full", "written_at": 100.0},
        {"ladder": [FAST, BIG, API], "lead": API, "written_at": 100.0},
        {"ladder": [FAST, BIG, API], "fanout": "idle"},
        None,
    ],
    ids=[
        "stale",
        "another-ladder",
        "fanout-out-of-bounds",
        "lead-out-of-bounds",
        "undated",
        "absent",
    ],
)
def test_a_published_choice_that_is_stale_foreign_or_unbounded_is_ignored(
    tmp_path: Path, key: None, doc: dict[str, Any] | None
) -> None:
    config = managed(tmp_path, BOUNDED)
    assert ladder_manager.effective(config, doc, now=110.0) is config


def test_a_managed_task_takes_the_choice_and_reports_its_climbs(
    tmp_path: Path, key: None
) -> None:
    config = managed(tmp_path, BOUNDED)
    doc = {"ladder": [FAST, BIG, API], "fanout": "idle", "written_at": 100.0}
    task = ladder_manager.for_task(config, read_board=lambda: doc, now=lambda: 105.0)
    assert task.config.ladder.fanout == "idle"
    assert task.note is not None and "idle" in task.note
    assert task.gauge is not None and task.presence is not None


# --- the loop ------------------------------------------------------------------


def test_the_loop_ticks_at_its_interval() -> None:
    pressure = FakePressure(reading(FAST), reading(BIG, awake=False, in_flight=None))
    run = manager(pressure, FakeSwitches(pressure), FakeDecide())
    slept: list[float] = []
    ticks = ladder_manager.run(run, interval_s=10.0, sleep=slept.append, ticks=3)
    assert ticks == 3
    assert slept == [10.0, 10.0]
