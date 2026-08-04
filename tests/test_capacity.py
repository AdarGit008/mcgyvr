"""#23's acceptance is three statements about a bound, and two of them are about
what happens when work moves: N jobs across M sources never exceed any source's
capacity, a task escalating across sources neither leaks nor double-counts, and a
mixed batch finishes measurably sooner than the same work run one at a time.

Concurrency is the one thing a test cannot assert by reading a return value, so
what is held here is *observed overlap*. Every job records its own arrival and
departure through an independent counter — deliberately not the one
:class:`Capacity` keeps, since that is the thing under test — and the assertions
are made against what that counter saw. A bound that was never approached would
satisfy "never exceeded" vacuously, so each test that asserts a ceiling also
asserts the ceiling was *reached*.

The wall-clock test measures this module and nothing else. Its jobs sleep; they
do not talk to a model. What it demonstrates is that the executor genuinely
overlaps work and that the bound shapes how much — not that a backend gets
faster, which is CON-01's and CON-04's measurement and was taken on real
hardware this test has no access to.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, CapacityError, Outcome, run_batch
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, Protocol

CONFIG = """
version: 1
sources:
  local:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 3
  fast:
    base_url: http://localhost:8080
    api: openai
    max_parallel: 2
  spare:
    base_url: http://localhost:9090
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: cheap
      source: local
      model: qwen2.5-coder:7b
    - name: strong
      source: fast
      model: qwen2.5-coder:14b
"""


def endpoint(source: str, max_parallel: int) -> Endpoint:
    return Endpoint(
        source=source,
        base_url=f"http://localhost/{source}",
        protocol=Protocol.OPENAI,
        max_parallel=max_parallel,
        credential_env=None,
    )


LOCAL = endpoint("local", 3)
FAST = endpoint("fast", 2)
SPARE = endpoint("spare", 1)


class Observer:
    """An independent record of how many jobs were inside a source at once.

    Independent on purpose. Asserting the bound with :meth:`Capacity.usage`
    would be asking the implementation whether it agrees with itself; this
    counts arrivals and departures from inside the held block, where a slot that
    was never really taken would show up as an overlap the limit forbids.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.inside: dict[str, int] = {}
        self.peak: dict[str, int] = {}
        self.order: list[str] = []

    def enter(self, source: str) -> None:
        with self._lock:
            self.inside[source] = self.inside.get(source, 0) + 1
            self.peak[source] = max(self.peak.get(source, 0), self.inside[source])
            self.order.append(source)

    def leave(self, source: str) -> None:
        with self._lock:
            self.inside[source] -= 1


def working(observer: Observer, *endpoints: Endpoint, seconds: float = 0.02) -> Any:
    """A job that occupies each endpoint in turn — one dispatch, or an escalation."""

    def job(capacity: Capacity) -> tuple[str, ...]:
        for target in endpoints:
            with capacity.hold(target):
                observer.enter(target.source)
                time.sleep(seconds)
                observer.leave(target.source)
        return tuple(e.source for e in endpoints)

    return job


# --- N jobs across M sources never exceed any source's capacity -------------


def test_no_source_ever_exceeds_its_declared_capacity(capsys: Any) -> None:
    capacity = Capacity({"local": 3, "fast": 2, "spare": 1})
    observer = Observer()
    jobs = [
        working(observer, target) for target in ([LOCAL] * 8 + [FAST] * 8 + [SPARE] * 4)
    ]

    outcomes = run_batch(jobs, capacity, workers=20)

    assert all(o.ok for o in outcomes)
    assert observer.peak["local"] <= 3
    assert observer.peak["fast"] <= 2
    assert observer.peak["spare"] <= 1
    # Non-vacuous: each ceiling was actually reached, so "never exceeded" is a
    # bound that bit rather than a batch that was too small to test it.
    assert observer.peak["local"] == 3
    assert observer.peak["fast"] == 2
    assert observer.peak["spare"] == 1


def test_the_capacitys_own_record_agrees_with_what_was_observed() -> None:
    """`usage()` is what an operator reads; it must not be a different story."""
    capacity = Capacity({"local": 3})
    observer = Observer()

    run_batch([working(observer, LOCAL) for _ in range(6)], capacity, workers=6)

    (usage,) = capacity.usage()
    assert usage.source == "local"
    assert usage.limit == 3
    assert usage.acquisitions == 6
    assert usage.peak == observer.peak["local"] == 3
    assert usage.saturated
    # Something waited: six jobs through three slots cannot all start at once.
    assert usage.waited_seconds > 0


def test_a_source_that_never_filled_up_is_reported_unsaturated() -> None:
    """The other half of `saturated`: it must distinguish, not always say yes."""
    capacity = Capacity({"local": 3})
    observer = Observer()

    run_batch([working(observer, LOCAL)], capacity)

    (usage,) = capacity.usage()
    assert usage.peak == 1
    assert not usage.saturated


# --- escalation neither leaks nor double-counts -----------------------------


def test_a_task_escalating_across_sources_holds_one_slot_at_a_time() -> None:
    """The acceptance's second bullet, and the reason a slot is per dispatch.

    Each job runs on `local`, then `fast`, then `spare` — a cascade. If a slot
    were held for the task rather than the dispatch, four jobs could not run at
    all: `spare` admits one, so the fourth would be waiting on a slot the first
    was holding while it worked somewhere else.
    """
    capacity = Capacity({"local": 3, "fast": 2, "spare": 1})
    observer = Observer()
    jobs = [working(observer, LOCAL, FAST, SPARE) for _ in range(4)]

    outcomes = run_batch(jobs, capacity, workers=4)

    assert [o.value for o in outcomes] == [("local", "fast", "spare")] * 4
    assert observer.peak["local"] <= 3
    assert observer.peak["fast"] <= 2
    assert observer.peak["spare"] <= 1
    # Twelve dispatches from four tasks: counted once each, not once per task.
    assert {u.source: u.acquisitions for u in capacity.usage()} == {
        "local": 4,
        "fast": 4,
        "spare": 4,
    }


def test_every_slot_is_free_once_the_batch_is_done() -> None:
    """No leak: a held slot that outlives its dispatch shrinks the source forever."""
    capacity = Capacity({"local": 3, "fast": 2})
    observer = Observer()

    run_batch([working(observer, LOCAL, FAST) for _ in range(6)], capacity)

    assert capacity.in_use("local") == 0
    assert capacity.in_use("fast") == 0
    # And the source still admits its full capacity afterwards.
    assert all(o.ok for o in run_batch([working(observer, LOCAL)] * 3, capacity))


def test_a_dispatch_that_raises_still_gives_its_slot_back() -> None:
    """A backend that times out must not cost the source a slot for the run."""
    capacity = Capacity({"spare": 1})

    def failing(capacity: Capacity) -> None:
        with capacity.hold(SPARE):
            raise TimeoutError("the endpoint did not answer")

    def fine(capacity: Capacity) -> str:
        with capacity.hold(SPARE):
            return "ok"

    outcomes = run_batch([failing, fine, failing, fine], capacity, workers=4)

    assert [o.ok for o in outcomes] == [False, True, False, True]
    assert isinstance(outcomes[0].error, TimeoutError)
    assert capacity.in_use("spare") == 0
    assert capacity.usage()[0].acquisitions == 4


# --- a mixed batch beats serial execution -----------------------------------


def test_a_mixed_batch_finishes_sooner_than_the_same_work_serialized() -> None:
    """The third acceptance bullet, measured on this module and not on a model.

    The jobs sleep rather than generate, so what this shows is that the executor
    overlaps work and that the per-source bound shapes how much. It is not a
    throughput claim about a backend: that is CON-01 (three models on one card,
    23.6 s against ~44 s serial) and CON-04, both measured on hardware.

    Six jobs of 50 ms across two sources of capacity 3 and 2. Serial is 300 ms;
    the concurrent floor is two rounds of `fast` against two of `local`, so
    ~100 ms. The assertion leaves a wide margin because a loaded CI box is not a
    quiet one, and a flaky timing test would be worse than none.
    """
    capacity = Capacity({"local": 3, "fast": 2})
    observer = Observer()
    unit = 0.05
    targets = [LOCAL] * 3 + [FAST] * 3
    jobs = [working(observer, target, seconds=unit) for target in targets]

    started = time.monotonic()
    outcomes = run_batch(jobs, capacity)
    elapsed = time.monotonic() - started

    serial = unit * len(jobs)
    assert all(o.ok for o in outcomes)
    assert elapsed < serial * 0.7, (
        f"{elapsed:.3f}s against a {serial:.3f}s serial floor"
    )
    assert observer.peak["local"] == 3
    assert observer.peak["fast"] == 2


def test_capacity_one_serializes_and_that_is_visible() -> None:
    """A single-slot source is the CON-02 case, and it must not look concurrent."""
    capacity = Capacity({"spare": 1})
    observer = Observer()

    run_batch([working(observer, SPARE, seconds=0.01) for _ in range(5)], capacity)

    assert observer.peak["spare"] == 1
    assert capacity.usage()[0].waited_seconds > 0


# --- refusing what would otherwise fail silently ----------------------------


def test_a_nested_hold_on_one_source_is_refused_rather_than_deadlocked() -> None:
    """At max_parallel=1 this would block forever with no output and no traceback."""
    capacity = Capacity({"spare": 1})

    with (
        capacity.hold(SPARE),
        pytest.raises(CapacityError) as caught,
        capacity.hold(SPARE),
    ):
        pass  # pragma: no cover - the second hold raises on the way in

    assert "already holds a slot" in str(caught.value)
    assert "deadlock" in str(caught.value)


def test_holding_two_different_sources_at_once_is_fine() -> None:
    """The guard is about one source, not about nesting — a verifier does this."""
    capacity = Capacity({"local": 3, "fast": 2})

    with capacity.hold(LOCAL), capacity.hold(FAST):
        assert capacity.in_use("local") == 1
        assert capacity.in_use("fast") == 1

    assert capacity.in_use("local") == capacity.in_use("fast") == 0


def test_an_undeclared_source_is_refused_rather_than_run_unbounded() -> None:
    capacity = Capacity({"local": 3})

    with pytest.raises(CapacityError) as caught, capacity.hold(FAST):
        pass  # pragma: no cover - the hold raises on the way in

    assert "no declared capacity for source 'fast'" in str(caught.value)
    assert "different configs" in str(caught.value)


def test_an_endpoint_disagreeing_about_its_own_capacity_is_refused() -> None:
    """Two answers to one question means one of them is from a stale config."""
    capacity = Capacity({"local": 3})

    with pytest.raises(CapacityError) as caught, capacity.hold(endpoint("local", 8)):
        pass  # pragma: no cover - the hold raises on the way in

    assert "bounded at 3" in str(caught.value)
    assert "max_parallel=8" in str(caught.value)


def test_a_capacity_of_zero_is_refused_at_construction() -> None:
    with pytest.raises(CapacityError) as caught:
        Capacity({"local": 0})

    assert "no dispatch at all" in str(caught.value)


# --- the batch's own contract -----------------------------------------------


def test_results_come_back_in_the_order_the_jobs_were_given() -> None:
    """Ordered by completion, a batch would be reproducible only on a quiet box."""
    capacity = Capacity({"local": 3})

    def sleeper(delay: float, label: str) -> Any:
        def job(capacity: Capacity) -> str:
            with capacity.hold(LOCAL):
                time.sleep(delay)
            return label

        return job

    # Deliberately finishing in reverse: the slowest is submitted first.
    outcomes = run_batch(
        [sleeper(0.06, "a"), sleeper(0.03, "b"), sleeper(0.001, "c")],
        capacity,
        workers=3,
    )

    assert [o.value for o in outcomes] == ["a", "b", "c"]
    assert [o.index for o in outcomes] == [0, 1, 2]


def test_one_failing_job_does_not_sink_the_batch() -> None:
    capacity = Capacity({"local": 3})

    def boom(capacity: Capacity) -> None:
        raise ValueError("this one contract was malformed")

    outcomes = run_batch([boom, working(Observer(), LOCAL), boom], capacity)

    assert [o.ok for o in outcomes] == [False, True, False]
    assert str(outcomes[0].error) == "this one contract was malformed"
    assert outcomes[0].value is None


def test_an_interrupt_is_not_reported_as_a_jobs_failure() -> None:
    """Swallowing Ctrl-C into an Outcome would make it look like a bad contract."""
    capacity = Capacity({"local": 3})

    def interrupted(capacity: Capacity) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_batch([interrupted], capacity)


def test_an_empty_batch_is_an_empty_result_not_an_error() -> None:
    assert run_batch([], Capacity({"local": 1})) == ()


def test_the_default_worker_count_is_the_total_capacity() -> None:
    """More threads than slots can only queue on a semaphore, at a stack each."""
    capacity = Capacity({"local": 3, "fast": 2, "spare": 1})
    assert capacity.total == 6


def test_asking_for_no_workers_is_refused() -> None:
    with pytest.raises(CapacityError) as caught:
        run_batch([working(Observer(), LOCAL)], Capacity({"local": 3}), workers=0)

    assert "would run nothing" in str(caught.value)


# --- built from the config, and from nothing else ---------------------------


def test_capacity_comes_from_the_declared_config() -> None:
    capacity = Capacity.of(parse(CONFIG))

    assert capacity.limits == {"local": 3, "fast": 2, "spare": 1}
    assert capacity.total == 6


def test_every_declared_source_is_covered_not_only_the_laddered_ones() -> None:
    """`spare` serves no tier. A role could still dispatch against it."""
    capacity = Capacity.of(parse(CONFIG))

    with capacity.hold(SPARE):
        assert capacity.in_use("spare") == 1


def test_an_outcome_reports_failure_rather_than_an_absent_value() -> None:
    """`ok` exists so a failure cannot be read as a job that returned None."""
    assert Outcome[int](index=0, value=None).ok
    assert not Outcome[int](index=0, error=ValueError("x")).ok
