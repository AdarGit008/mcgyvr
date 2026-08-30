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
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, CapacityError, Outcome, run_batch
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, Protocol, source_map


@pytest.fixture(autouse=True)
def isolated_lock_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Slot files are host-wide by design (#185); tests must not share them.

    Two suites running at once on one machine — or a suite beside a real run —
    would otherwise contend for the same bound and flake each other.
    """
    monkeypatch.setattr(
        "mcgyvr.capacity._default_lock_dir", lambda: tmp_path / "capacity-locks"
    )


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

# A deadlock guard for `rendezvous`, deliberately far longer than any batch here
# needs. Nothing asserts on it: if the executor overlaps dispatches the barrier
# trips as soon as the last party arrives, so a generous bound costs a slow test
# nothing and only decides how long a genuinely broken one takes to say so.
BARRIER_TIMEOUT_S = 30.0


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
        # The same two figures across every source, kept independently of the
        # per-source dict for the reason `Concurrency` exists: a maximum of sums
        # is not the sum of maxima, so `max(peak.values())` and `sum(...)` both
        # answer a different question than "were two sources ever busy at once".
        self.inside_total = 0
        self.peak_total = 0

    def enter(self, source: str) -> None:
        with self._lock:
            self.inside[source] = self.inside.get(source, 0) + 1
            self.peak[source] = max(self.peak.get(source, 0), self.inside[source])
            self.inside_total += 1
            self.peak_total = max(self.peak_total, self.inside_total)
            self.order.append(source)

    def leave(self, source: str) -> None:
        with self._lock:
            self.inside[source] -= 1
            self.inside_total -= 1


def rendezvous(
    observer: Observer, endpoint: Endpoint, barrier: threading.Barrier
) -> Any:
    """A job that holds its slot until ``barrier`` parties are holding theirs.

    The load-immune way to assert concurrency. A job that sleeps and a test that
    then reads a peak is asking several threads to coincide inside a fixed
    window, which is a race the machine's load decides — #200 is what that costs.
    Waiting on a barrier inverts it: the job blocks until the required number of
    dispatches really are in flight together, however long that takes, so a busy
    box makes the test slower and never wrong.

    If the executor cannot put that many in flight — the property under test
    failing — no party arrives, every waiter raises ``BrokenBarrierError`` at the
    timeout, and the batch reports failures rather than hanging. The timeout is
    a deadlock guard, not a measurement: nothing asserts on how long it took.
    """

    def job(_capacity: Capacity) -> str:
        with _capacity.hold(endpoint):
            observer.enter(endpoint.source)
            try:
                barrier.wait(timeout=BARRIER_TIMEOUT_S)
            finally:
                observer.leave(endpoint.source)
        return endpoint.source

    return job


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
    # The safety property, and the only one that has to hold on every run: a
    # sleeping job is enough to test it, because exceeding a bound is something
    # the code would have to actively do and no amount of load can cause.
    assert observer.peak["local"] <= 3
    assert observer.peak["fast"] <= 2
    assert observer.peak["spare"] <= 1
    # Non-vacuity — that each ceiling was actually reached — is a *liveness*
    # claim, which sampled peaks cannot carry on a loaded box (#200). It is
    # asserted deterministically in the barrier tests below instead of hoped for
    # here, so this test is about the bound and nothing else.


def test_the_capacitys_own_record_agrees_with_what_was_observed() -> None:
    """`usage()` is what an operator reads; it must not be a different story.

    Six jobs through three slots, each holding until three are held at once. The
    barrier is reusable, so the batch runs as two deterministic rounds of three:
    `peak` is 3 because three genuinely coincided, and the second round could not
    start until the first released, which is what makes `waited_seconds`
    non-zero. Both were sampled from a sleep until #200 and flaked.
    """
    capacity = Capacity({"local": 3})
    observer = Observer()
    barrier = threading.Barrier(3)

    outcomes = run_batch(
        [rendezvous(observer, LOCAL, barrier) for _ in range(6)], capacity, workers=6
    )
    assert all(o.ok for o in outcomes)

    (usage,) = capacity.usage()
    assert usage.source == "local"
    assert usage.limit == 3
    assert usage.acquisitions == 6
    assert usage.peak == observer.peak["local"] == 3
    assert usage.saturated
    # Something waited: six jobs through three slots cannot all start at once.
    assert usage.waited_seconds > 0


def test_the_cross_source_peak_agrees_with_what_was_observed() -> None:
    """The same cross-check the per-source peak gets, for the figure #200 added.

    ``concurrency()`` is the product's own report, and a test that asserted on
    it alone would be asking the code under test to grade its own homework: a
    bug in the accounting would be invisible, because the behaviour and the
    report come from the same object. ``Observer`` counts the same thing from
    outside, so the two are independent measurements of one fact.
    """
    capacity = Capacity({"local": 3, "fast": 2})
    observer = Observer()
    targets = [LOCAL] * 3 + [FAST] * 2
    barrier = threading.Barrier(len(targets))

    outcomes = run_batch([rendezvous(observer, t, barrier) for t in targets], capacity)

    assert all(o.ok for o in outcomes)
    reported = capacity.concurrency()
    assert reported.peak == observer.peak_total == 5
    assert reported.total == 5
    assert reported.saturated


def test_the_cross_source_peak_is_not_the_sum_of_the_per_source_peaks() -> None:
    """Why it is tracked rather than derived: a maximum of sums is not a sum of maxima.

    One source at a time, run to completion before the next begins. Each source
    reaches its own limit, so summing the per-source peaks would report 5 — a
    fully saturated batch — when at no instant was more than one dispatch in
    flight. This is the reading `Usage` structurally cannot correct, and the
    series-draining bug the mixed-batch test is guarding against.
    """
    capacity = Capacity({"local": 3, "fast": 2})
    observer = Observer()

    run_batch([working(observer, LOCAL, seconds=0.01)], capacity)
    run_batch([working(observer, FAST, seconds=0.01)], capacity)

    assert sum(u.peak for u in capacity.usage()) == 2
    assert capacity.concurrency().peak == 1
    assert not capacity.concurrency().saturated


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


def test_a_mixed_batch_runs_two_sources_at_once_rather_than_in_series() -> None:
    """The third acceptance bullet, measured on this module and not on a model.

    The jobs sleep rather than generate, so what this shows is that the executor
    overlaps work and that the per-source bound shapes how much. It is not a
    throughput claim about a backend: that is CON-01 (three models on one card,
    23.6 s against ~44 s serial) and CON-04, both measured on hardware.

    **This asserted a stopwatch until #200 and flaked.** It ran six 50 ms jobs
    and required them to beat the 300 ms serial floor by 30%; on a loaded box it
    came in at 232 ms — faster than serial, with the per-source peaks intact, so
    the concurrency plainly happened — and failed for delivering 23% instead.
    A ``sleep`` guarantees *at least* its duration, and a thread whose sleep has
    elapsed still waits for a free core before it can release its slot, so the
    wall clock stretches under load while the behaviour does not change.

    The clock was there because the property this test is named for had no
    instrument. ``peak`` is per source in both witnesses: a batch that drained
    ``local`` three wide and only then started ``fast`` two wide satisfies both
    per-source assertions and takes twice as long, and elapsed time was the only
    thing that would have caught it. #200 gave that property a number in the
    product and an independent one here, so the assertion is now on overlap
    itself — which is immune to how busy the machine is, where timing it was not.
    """
    capacity = Capacity({"local": 3, "fast": 2})
    observer = Observer()
    targets = [LOCAL] * 3 + [FAST] * 2
    barrier = threading.Barrier(len(targets))
    jobs = [rendezvous(observer, target, barrier) for target in targets]

    outcomes = run_batch(jobs, capacity)

    # Every job returning means every one of them was inside its slot when the
    # last party arrived. A batch that drained one source before starting the
    # other could never trip the barrier, and these would be timeouts instead.
    assert all(o.ok for o in outcomes)
    assert observer.peak["local"] == 3
    assert observer.peak["fast"] == 2

    # The property the name claims, and the one the per-source peaks structurally
    # cannot express: strictly more in flight than either source can supply on
    # its own, so the two were busy together rather than in series.
    assert observer.peak_total == 5
    assert observer.peak_total > max(observer.peak.values())


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


# --- and from the machine, when the machine will say -------------------------


class Widths:
    """A stand-in for the width half of #22's probe: source name -> width or None.

    A dict rather than anything that opens a socket, because the seam under test
    is "what does this module do with an answer" and not "how is the answer
    fetched". ``None`` — including for a source the table never mentions — is the
    ollama case: a backend that does not report its parallelism at all, which is
    an ordinary answer and not a failure.
    """

    def __init__(self, widths: dict[str, int | None]) -> None:
        self._widths = widths

    def width(self, source: str) -> int | None:
        return self._widths.get(source)


def test_a_width_the_rig_reports_beats_the_one_the_config_guessed() -> None:
    """`init` writes 1 because it cannot know; a rig that says otherwise ends it."""
    capacity = Capacity.of(parse(CONFIG), probe=Widths({"local": 8}))

    assert capacity.limits["local"] == 8, "the config declared 3; the rig said 8"
    assert capacity.total == 11
    assert capacity.confirmed("local") is True


def test_a_width_reported_the_same_as_declared_is_still_a_confirmed_one() -> None:
    """The guess being right is not the same fact as the guess being unchecked."""
    capacity = Capacity.of(parse(CONFIG), probe=Widths({"fast": 2}))

    assert capacity.limits["fast"] == 2
    assert capacity.confirmed("fast") is True


def test_a_source_that_does_not_report_keeps_its_declaration_and_says_so() -> None:
    """ollama serves its parallelism from a unit file and exposes no endpoint."""
    capacity = Capacity.of(parse(CONFIG), probe=Widths({"local": None}))

    assert capacity.limits["local"] == 3, "the declaration stands"
    assert capacity.confirmed("local") is False


def test_a_source_the_probe_never_mentions_is_unconfirmed_not_absent() -> None:
    """Nobody asked, and the backend does not say: one state of knowledge."""
    capacity = Capacity.of(parse(CONFIG), probe=Widths({"local": 8}))

    assert capacity.limits["spare"] == 1
    assert capacity.confirmed("spare") is False


def test_without_a_probe_no_width_is_confirmed() -> None:
    """The ordinary case, and the one every other test in this file is in."""
    capacity = Capacity.of(parse(CONFIG))

    assert not any(capacity.confirmed(source) for source in capacity.limits)


def test_a_declared_width_the_machine_contradicts_is_refused_by_name() -> None:
    """CON-02's invisible queue, made visible the moment the rig can be asked.

    Lowering the bound silently would leave the config still wrong and the
    operator's evidence for "my rig is slow" still indistinguishable from their
    evidence for "my config is wrong".
    """
    with pytest.raises(CapacityError) as caught:
        Capacity.of(parse(CONFIG), probe=Widths({"local": 1}))

    assert "'local' declares 3 but reports 1" in str(caught.value)
    assert "Two answers to one question" in str(caught.value)


def test_asking_whether_an_unbounded_source_was_confirmed_is_refused() -> None:
    """False would claim the source is known and merely unconfirmed."""
    capacity = Capacity.of(parse(CONFIG))

    with pytest.raises(CapacityError) as caught:
        capacity.confirmed("nowhere")

    assert "no declared capacity for source 'nowhere'" in str(caught.value)
    assert "Known sources: fast, local, spare" in str(caught.value)


def test_a_confirmation_for_a_source_with_no_limit_is_refused() -> None:
    """A confirmation is a fact about a limit, so there must be a limit."""
    with pytest.raises(CapacityError) as caught:
        Capacity({"local": 3}, confirmed=["fast"])

    assert "confirmed width(s) for source(s) fast" in str(caught.value)


def test_an_outcome_reports_failure_rather_than_an_absent_value() -> None:
    """`ok` exists so a failure cannot be read as a job that returned None."""
    assert Outcome[int](index=0, value=None).ok
    assert not Outcome[int](index=0, error=ValueError("x")).ok


# --- and dispatching through what the machine reported ----------------------


def test_a_probed_capacity_dispatches_at_the_width_the_rig_reported() -> None:
    """The test whose absence let a probe that worked ship unusable.

    Every earlier test in this section reads the bound and stops there, so all
    of them passed while the first `hold` through a widened source raised: the
    endpoints a `SourceMap` builds carry `max_parallel` from the config, and a
    hold that compared them against the *enforced* width refused every one of
    them — blaming a stale config for a disagreement `Capacity.of` had itself
    created one line earlier. So this dispatches, through real endpoints, and
    asserts the enforced width is what actually admitted them: four at once
    through a source the config declared three wide.
    """
    config = parse(CONFIG)
    capacity = Capacity.of(config, probe=Widths({"local": 8}))
    dispatched = source_map(config).bind("cheap")
    observer = Observer()
    barrier = threading.Barrier(4)

    outcomes = run_batch(
        [rendezvous(observer, dispatched, barrier) for _ in range(4)], capacity
    )

    assert all(o.ok for o in outcomes), [str(o.error) for o in outcomes if not o.ok]
    assert dispatched.max_parallel == 3, "an endpoint carries what the config said"
    assert capacity.limits["local"] == 8, "and the rig's 8 is what is enforced"
    assert observer.peak["local"] == 4, "four at once, which the declared 3 forbids"


def test_the_declared_width_stays_readable_beside_the_enforced_one() -> None:
    """Two numbers, both kept, because they answer two different questions."""
    capacity = Capacity.of(parse(CONFIG), probe=Widths({"local": 8}))

    assert capacity.declared("local") == 3
    assert capacity.limits["local"] == 8
    assert capacity.declared("fast") == capacity.limits["fast"] == 2


def test_an_endpoint_from_another_config_is_refused_by_a_probed_capacity() -> None:
    """The guard is narrowed to the declaration, not deleted.

    A second config declaring 5 for the same source is exactly what the check
    exists to catch, and a probe having widened this capacity to 8 must not
    make 5 look like a number that fits inside the bound.
    """
    capacity = Capacity.of(parse(CONFIG), probe=Widths({"local": 8}))
    stale = source_map(parse(CONFIG.replace("max_parallel: 3", "max_parallel: 5")))

    with pytest.raises(CapacityError) as caught, capacity.hold(stale.bind("cheap")):
        pass  # pragma: no cover - the hold raises on the way in

    assert "bounded at 3" in str(caught.value)
    assert "max_parallel=5" in str(caught.value)
    assert "probe widened this source to 8" in str(caught.value)


def test_a_bound_that_differs_from_its_declaration_with_nothing_confirming_it() -> None:
    """Only a machine's report may widen a declaration, so the pair needs one."""
    with pytest.raises(CapacityError) as caught:
        Capacity({"local": 8}, declared={"local": 3})

    assert "without a confirmation" in str(caught.value)


def test_a_declaration_above_the_bound_is_refused() -> None:
    """`of` refuses a narrower report rather than lowering, so this cannot arise."""
    with pytest.raises(CapacityError) as caught:
        Capacity({"local": 3}, confirmed=["local"], declared={"local": 8})

    assert "declares 8 but is bounded at 3" in str(caught.value)


# --- reservations: the count that exists before a slot does -----------------


def test_reservations_are_this_capacitys_and_not_the_process_s() -> None:
    """The defect a module-global ledger has by construction.

    Two configs that merely share the name `local` are two bounds, two sets of
    slot files and two batches. A count keyed by source name across the process
    pools them, so a climb under one config reads a machine as busy because of
    work under the other — and there is no config edit that separates them.
    """
    mine = Capacity({"local": 3})
    theirs = Capacity({"local": 3})

    mine.reserve("local")

    assert mine.load("local") == 1
    assert theirs.load("local") == 0, "a different capacity is a different ledger"

    mine.release("local")
    assert mine.load("local") == 0


def test_one_dispatch_counts_once_whether_it_is_reserved_granted_or_both() -> None:
    """Reserved and granted overlap, so the load is the greater and not the sum.

    An attempt is reserved when its rung is chosen and keeps that reservation
    while it holds the slot it was granted. Summing would report a source as
    full at half its width, which is the same funnel the count exists to end,
    arrived at from the other direction.
    """
    capacity = Capacity({"local": 3})

    with capacity.reserving("local"):
        assert capacity.load("local") == 1, "chosen, not yet admitted"
        with capacity.hold(LOCAL):
            assert capacity.in_use("local") == 1
            assert capacity.load("local") == 1, "one dispatch, counted once"
        assert capacity.load("local") == 1

    assert capacity.load("local") == 0


def test_a_reservation_is_given_back_however_the_block_leaves() -> None:
    """A leaked reservation is permanent: the machine looks busy for the run."""
    capacity = Capacity({"local": 3})

    with pytest.raises(ValueError), capacity.reserving("local"):
        raise ValueError("the attempt raised")

    assert capacity.load("local") == 0


def test_releasing_what_was_never_reserved_is_floored_rather_than_negative() -> None:
    """`release` runs in a `finally`, where raising would hide the real error."""
    capacity = Capacity({"local": 3})

    capacity.release("local")
    capacity.release("nowhere")  # a source this capacity does not bound

    assert capacity.load("local") == 0, "a negative count would read as free forever"


def test_reserving_a_source_this_capacity_does_not_bound_is_refused() -> None:
    """A reservation is a claim against a bound, so there must be a bound."""
    capacity = Capacity({"local": 3})

    with pytest.raises(CapacityError) as caught:
        capacity.reserve("nowhere")

    assert "no declared capacity for source 'nowhere'" in str(caught.value)
    assert "different configs" in str(caught.value)


def test_reading_the_load_of_a_source_this_capacity_does_not_bound_is_refused() -> None:
    """Zero would say the machine is idle when what is unknown is the machine."""
    capacity = Capacity({"local": 3})

    with pytest.raises(CapacityError):
        capacity.load("nowhere")


def test_choosing_under_deciding_spreads_a_batch_instead_of_stacking_it() -> None:
    """Read-then-reserve is one decision, and `deciding` is what makes it one.

    Six threads pick the least loaded of two equal sources at the same moment.
    Outside the lock they all read the same zeroes and all pick `fast`, which is
    the funnel this count exists to end. Inside it each one's choice is visible
    to the next, so the six split evenly — and the split is exact rather than
    approximate, which is what makes this assertable rather than a heuristic.
    """
    capacity = Capacity({"local": 4, "fast": 4})
    start = threading.Barrier(6)
    chosen: list[str] = []
    recording = threading.Lock()

    def choose() -> None:
        start.wait(timeout=BARRIER_TIMEOUT_S)
        with capacity.deciding():
            source = min(("fast", "local"), key=capacity.load)
            capacity.reserve(source)
        with recording:
            chosen.append(source)

    threads = [threading.Thread(target=choose) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=BARRIER_TIMEOUT_S)

    assert chosen.count("fast") == 3
    assert chosen.count("local") == 3
    assert capacity.load("fast") == capacity.load("local") == 3
