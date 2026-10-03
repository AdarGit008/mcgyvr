"""An attempt that climbed says so to whoever is watching, and nobody else is told.

The promise: given a ``presence`` — a context manager made per rung, which the
caller wires to a host-wide gauge — :func:`~mcgyvr.escalate.escalate` runs an
attempt inside it exactly when the attempt is on a rung it *reached after
spending attempts on a cheaper one*; and given none, the climb is the climb it
always was.

* **A first rung is not a climb.** Work that starts where it was always going
  to start is not demand for the rung above it.
* **A rung reached because something failed below is.** That is the pressure a
  manager wants to see: tasks that outgrew the cheap rung and are now working
  on this one. It is marked for the length of the attempt, with the rung's name.
* **A raised entry is not.** Under ``fanout: idle`` a busy ladder enters high
  without anything having failed — the same rule that makes it free of an
  escalation (see ``_idle_entry``) makes it no evidence the cheap rung was too
  small.
* **A decline spends nothing, so it is not a rung one climbed from.**
* **``None`` is today's behaviour exactly.** The kwarg adds no state, no call
  and no outcome of its own.

Nothing here touches a network or a rig: the attempt is a script, the capacity
is built over ``tmp_path``, and every host is invented.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import Assurance, Delivered, Halted, Judgement, escalate
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import Try, Verdict

FAST = "local_fast"
SMART = "local_smart"
API = "api_big"
API_TOP = "api_bigger"

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

LADDER = """
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    rig: fast-rig
    width: 1
  local_smart:
    address: http://smart-box.example:8001
    model: qwen2.5-coder-7b
    rig: smart-rig
    width: 1
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    rig: vendor
    width: 1
    api_key_env: EXAMPLE_API_KEY
  api_bigger:
    address: https://big.example.com/v1
    model: vendor-largest
    rig: vendor-big
    width: 4
    api_key_env: EXAMPLE_API_KEY
ladder:
- local_fast
- local_smart
- api_big
- api_bigger
max_escalations: 3
{fanout}"""


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)


def mapped(fanout: str = "") -> tuple[Config, SourceMap]:
    config = parse(LADDER.format(fanout=f"fanout: {fanout}\n" if fanout else ""))
    return config, source_map(config)


def contract() -> Contract:
    return load_contract(CONTRACT)


class Script:
    """An attempt function that answers from a script and logs what it was inside.

    ``events`` is shared with :class:`Presence`, so the order of "entered",
    "attempted" and "left" is one list a test reads, and an attempt that ran
    outside a presence is visibly different from one that ran inside.
    """

    def __init__(self, events: list[str], *verdicts: Verdict) -> None:
        self._events = events
        self._verdicts = list(verdicts)
        self.seen: list[Try] = []

    def __call__(self, this: Try) -> Judgement:
        self.seen.append(this)
        self._events.append(f"attempt {this.rung.name}")
        if not self._verdicts:
            raise AssertionError(f"an unscripted attempt on {this.rung.name!r}")
        verdict = self._verdicts.pop(0)
        if verdict is Verdict.PASSED:
            return Judgement(verdict=Verdict.PASSED, assurance=Assurance.UNVERIFIED)
        if verdict is Verdict.DECLINED:
            return Judgement(verdict=Verdict.DECLINED, detail="not work this rung does")
        return Judgement(verdict=Verdict.FAILED, detail="the gate rejected it")


class Presence:
    """A recording presence: ``presence(rung)`` is a context manager that logs."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    @contextmanager
    def __call__(self, rung: str) -> Iterator[None]:
        self._events.append(f"in {rung}")
        try:
            yield
        finally:
            self._events.append(f"out {rung}")


def delivered(result: Delivered | Halted) -> Delivered:
    assert isinstance(result, Delivered), f"expected an accepted task, got {result}"
    return result


def test_an_attempt_on_the_first_rung_is_not_marked() -> None:
    config, pool = mapped()
    events: list[str] = []

    result = delivered(
        escalate(
            config,
            pool,
            contract(),
            Script(events, Verdict.PASSED),
            presence=Presence(events),
        )
    )

    assert result.rung == FAST
    assert events == [f"attempt {FAST}"]


def test_an_attempt_on_a_rung_reached_after_a_failure_is_marked_for_its_length() -> (
    None
):
    config, pool = mapped()
    events: list[str] = []

    result = delivered(
        escalate(
            config,
            pool,
            contract(),
            Script(events, Verdict.FAILED, Verdict.FAILED, Verdict.PASSED),
            presence=Presence(events),
        )
    )

    assert result.rung == API
    assert events == [
        f"attempt {FAST}",
        f"in {SMART}",
        f"attempt {SMART}",
        f"out {SMART}",
        f"in {API}",
        f"attempt {API}",
        f"out {API}",
    ], "each climbed attempt is inside its own rung's presence and no other"


def test_a_climbed_attempt_that_raises_is_unmarked_and_still_reported() -> None:
    config, pool = mapped()
    events: list[str] = []
    presence = Presence(events)
    verdicts = iter([Verdict.FAILED])

    def attempt(this: Try) -> Judgement:
        events.append(f"attempt {this.rung.name}")
        if next(verdicts, None) is None:
            raise RuntimeError("the dispatch died mid-flight")
        return Judgement(verdict=Verdict.FAILED, detail="the gate rejected it")

    result = escalate(
        config,
        pool,
        contract(),
        attempt,
        presence=presence,
    )

    assert isinstance(result, Halted)
    assert "RuntimeError" in result.detail
    assert events == [
        f"attempt {FAST}",
        f"in {SMART}",
        f"attempt {SMART}",
        f"out {SMART}",
    ], "an exception leaves the presence the way a verdict does"


def test_a_rung_reached_past_a_decline_is_not_a_climb() -> None:
    """A decline spends nothing, so nothing has been tried below this rung."""
    config, pool = mapped()
    events: list[str] = []

    result = delivered(
        escalate(
            config,
            pool,
            contract(),
            Script(events, Verdict.DECLINED, Verdict.PASSED),
            presence=Presence(events),
        )
    )

    assert result.rung == SMART
    assert events == [f"attempt {FAST}", f"attempt {SMART}"]


@contextmanager
def holding(capacity: Capacity, pool: SourceMap, *rungs: str) -> Iterator[None]:
    with ExitStack() as stack:
        for rung in rungs:
            stack.enter_context(capacity.hold(pool.bind(rung), rung=rung))
        yield


def test_a_raised_entry_under_idle_fanout_is_not_marked(tmp_path: Path) -> None:
    """Both local rigs are full, so ``idle`` enters on the priced rung at once.
    Nothing failed below it, so it is not a rung anything climbed to."""
    config, pool = mapped("idle")
    capacity = Capacity.of(config, root=tmp_path / "slots")
    events: list[str] = []

    with holding(capacity, pool, FAST, SMART):
        result = delivered(
            escalate(
                config,
                pool,
                contract(),
                Script(events, Verdict.PASSED),
                capacity=capacity,
                presence=Presence(events),
            )
        )

    assert result.rung == API
    assert events == [f"attempt {API}"]


def test_a_failure_after_a_raised_entry_marks_the_rung_it_climbs_to(
    tmp_path: Path,
) -> None:
    """The raised entry is free; what a failure on it buys is a climb."""
    config, pool = mapped("idle")
    capacity = Capacity.of(config, root=tmp_path / "slots")
    events: list[str] = []

    with holding(capacity, pool, FAST, SMART):
        result = delivered(
            escalate(
                config,
                pool,
                contract(),
                Script(events, Verdict.FAILED, Verdict.PASSED),
                capacity=capacity,
                presence=Presence(events),
            )
        )

    assert result.rung == API_TOP
    assert events == [
        f"attempt {API}",
        f"in {API_TOP}",
        f"attempt {API_TOP}",
        f"out {API_TOP}",
    ]


@pytest.mark.parametrize(
    "verdicts",
    [
        (Verdict.PASSED,),
        (Verdict.FAILED, Verdict.PASSED),
        (Verdict.FAILED, Verdict.FAILED, Verdict.FAILED, Verdict.FAILED),
        (Verdict.DECLINED, Verdict.FAILED, Verdict.PASSED),
    ],
)
def test_without_a_presence_the_climb_is_exactly_what_it_was(
    verdicts: tuple[Verdict, ...],
) -> None:
    config, pool = mapped()
    plain_events: list[str] = []
    none_events: list[str] = []

    plain = escalate(
        config,
        pool,
        contract(),
        Script(plain_events, *verdicts),
    )
    nothing = escalate(
        config,
        pool,
        contract(),
        Script(none_events, *verdicts),
        presence=None,
    )

    assert type(plain) is type(nothing)
    assert plain_events == none_events
    assert plain.history == nothing.history
    assert plain.attempts_spent == nothing.attempts_spent
    assert plain.escalations == nothing.escalations
    assert plain.entered == nothing.entered
    if isinstance(plain, Halted) and isinstance(nothing, Halted):
        assert plain.outcome is nothing.outcome
        assert plain.detail == nothing.detail
    if isinstance(plain, Delivered) and isinstance(nothing, Delivered):
        assert plain.rung == nothing.rung
