"""Fan-out — the config knob, its default, and the two gaps under it.

Fan-out is spreading a batch across several sources instead of queueing every
contract on the cheapest rung. It is a **config knob**, ``ladder.fanout``, and
not a behaviour change, because the right answer is a property of the machines:
two interchangeable rigs should share a batch, and a Rig A → Rig B ladder — a
throughput rig feeding an intelligence rig — must not, since the second rig is
sized to drain the first's failure tail and fanning volume onto it eats exactly
the capacity that drain needs.

* ``none`` — the default, and today's behaviour: the cheapest rung at or above
  the contract's floor, queued behind whoever is already there.
* ``idle`` — the cheapest rung at or above the floor **that has a free slot**.
* ``full`` — spread across the eligible rungs regardless of load.

The floor is the only bound. ``idle`` may climb as far as the ascent goes, api
included, so a saturated local ladder spills into priced capacity rather than
waiting — a spend decision the knob makes deliberately, not an escalation.

Two seams carry this, and they are different modules on purpose:

**Within a family** — :func:`mcgyvr.route.plan` orders rungs by price and
nothing in it reads :meth:`~mcgyvr.capacity.Capacity.in_use`, so six contracts
of one task type all take the cheapest rung and queue two-wide while a peer that
serves the same model sits idle. That is ``full``'s seam, and it stays inside
#24's boundary: nothing in ``route`` looks past the family it was asked about.

**Across families** — ``idle``'s spill cannot live in ``route`` for that same
reason. :func:`mcgyvr.escalate.ascent` is already the view "every family this
contract may climb, from its floor upward", so it is where a load-aware choice
that may reach api belongs.

**Where the width comes from.** Under all three modes the bound itself is still
a guess: ``max_parallel`` is declared in config and enforced verbatim, and
nothing asks the machine whether the number is true. CON-02 is what makes that
cost something — a single-slot server handed four concurrent requests
*serializes them rather than refusing*, so an over-declared capacity is not an
error anyone sees, it is a queue nobody sees. :func:`mcgyvr.initialize.initialize`
writes ``1`` for that reason, which is honest and leaves CON-04's measured 8.5x
on the floor.

Concurrency is asserted the way ``test_capacity.py`` asserts it: an independent
:class:`Observer`, and a :class:`Rendezvous` rather than a stopwatch, so a loaded
machine makes a test slower and never wrong.

**Probed on the rigs, 2026-08-29.** srv1 and srv2 both serve ollama 0.32.15 on
:11434 and nothing else; the llama.cpp containers that answered ``GET /slots``
with four slots on 2026-08-25 are gone. ``/slots`` now answers 404 on both, and
both units declare ``OLLAMA_NUM_PARALLEL=0`` — ollama's *auto*, chosen per model
at load time against free VRAM. So the width of this project's own two rigs is
today neither declared nor reportable, which is why the second width test is not
a hypothetical branch: it is the branch both rigs are currently in.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity, run_batch
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import ascent
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import Result, Try, climb, plan

# How long a job waits for its group to assemble before giving up. Nothing
# asserts on it: if the routing under test fans out, the rendezvous latches as
# soon as the last member arrives, so this number costs a working implementation
# nothing and only decides how long a broken one takes to say so. Kept short
# because these tests are red until #24 lands, and a red test pays this on every
# run of the suite.
RENDEZVOUS_TIMEOUT_S = 5.0


@pytest.fixture(autouse=True)
def isolated_lock_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Slot files are host-wide by design (#185); tests must not share them."""
    monkeypatch.setattr(
        "mcgyvr.capacity._default_lock_dir", lambda: tmp_path / "capacity-locks"
    )


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credential for the api source, assembled rather than written literally."""
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)


# Two local sources carrying the *same model*, which is what makes the ordering
# question sharp: the rungs are genuinely equal in price, so preferring the free
# one costs nothing that could be called an escalation. Deliberately not srv1
# and srv2 as this project actually runs them — those are a throughput rig and
# an intelligence rig and are never interchangeable. This is the symmetric
# arrangement the knob exists for.
PEERS = """
version: 1
sources:
  srv1:
    base_url: http://srv1.example.net:11434
    api: ollama
    max_parallel: 2
  srv2:
    base_url: http://srv2.example.net:11434
    api: ollama
    max_parallel: 2
  vendor:
    base_url: https://api.example.com/v1
    api: openai
    max_parallel: 4
    api_key_env: EXAMPLE_API_KEY
ladder:
{fanout}  tiers:
    - name: local_srv1
      source: srv1
      model: qwen3-coder:30b
    - name: local_srv2
      source: srv2
      model: qwen3-coder:30b
    - name: api_big
      source: vendor
      model: vendor-large
"""

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
"""


def peers(mode: str = "") -> str:
    """The symmetric config, with ``ladder.fanout`` set or left at its default.

    Written as a substitution rather than three literals so that the *only*
    difference between the default case and a mode case is the one line under
    test, and no assertion can be quietly explained by a config that also
    drifted somewhere else.
    """
    return PEERS.format(fanout=f"  fanout: {mode}\n" if mode else "")


def mapped(text: str | None = None) -> tuple[Config, SourceMap]:
    config = parse(text if text is not None else peers())
    return config, source_map(config)


def contract(text: str = CONTRACT) -> Contract:
    return load_contract(text)


class Observer:
    """An independent record of how many jobs were inside a source at once.

    Independent on purpose, and for the reason ``test_capacity.py`` gives:
    asserting the bound with :meth:`Capacity.usage` asks the implementation
    whether it agrees with itself. This counts arrivals and departures from
    inside the held block, and keeps the cross-source total separately because a
    maximum of sums is not a sum of maxima.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.inside: dict[str, int] = {}
        self.peak: dict[str, int] = {}
        self.inside_total = 0
        self.peak_total = 0

    def enter(self, source: str) -> None:
        with self._lock:
            self.inside[source] = self.inside.get(source, 0) + 1
            self.peak[source] = max(self.peak.get(source, 0), self.inside[source])
            self.inside_total += 1
            self.peak_total = max(self.peak_total, self.inside_total)

    def leave(self, source: str) -> None:
        with self._lock:
            self.inside[source] -= 1
            self.inside_total -= 1


class Rendezvous:
    """Waits until ``parties`` jobs are inside together, then latches open.

    Deliberately *not* :class:`threading.Barrier`, which is cyclic: a batch of
    six jobs through four slots trips a four-party barrier once and leaves the
    last two waiting on a fresh generation for two parties that can never come,
    so the assertion would fail against a correct implementation as loudly as
    against a broken one. Latching is what a concurrency claim actually means —
    *this many were in flight at some moment* — and it says nothing about the
    stragglers, which is right, because a batch deeper than the pool must have
    stragglers.

    A batch that cannot put ``parties`` in flight together never latches, every
    waiter times out, and the failure arrives as failed outcomes rather than a
    hang.
    """

    def __init__(self, parties: int) -> None:
        self._cond = threading.Condition()
        self._parties = parties
        self._waiting = 0
        self.reached = False

    def wait(self, timeout: float = RENDEZVOUS_TIMEOUT_S) -> bool:
        with self._cond:
            if self.reached:
                return True
            self._waiting += 1
            if self._waiting >= self._parties:
                self.reached = True
                self._cond.notify_all()
            else:
                self._cond.wait_for(lambda: self.reached, timeout=timeout)
            self._waiting -= 1
            return self.reached


def climbing(
    pool: SourceMap,
    config: Config,
    observer: Observer,
    rendezvous: Rendezvous,
) -> Callable[[Capacity], str]:
    """One contract's whole climb, as a job :func:`run_batch` can run.

    The attempt function is where a real caller would dispatch, so it is where
    the slot is held — around the request and not around the task, which is the
    rule :mod:`mcgyvr.capacity` is built on. Resolving the rung to an endpoint
    goes through :meth:`~mcgyvr.pool.SourceMap.bind`, the one seam crossing,
    because the source a rung lands on is exactly the fact under test and a job
    that closed over an endpoint would have assumed the answer.
    """

    def job(capacity: Capacity) -> str:
        def attempt(step: Try) -> Result[str]:
            endpoint = pool.bind(step.rung.name)
            assert step.capacity is not None, "climb must hand the capacity down"
            with step.capacity.hold(endpoint):
                observer.enter(endpoint.source)
                try:
                    if not rendezvous.wait():
                        raise TimeoutError(
                            f"only {observer.peak_total} dispatches were ever in "
                            f"flight together; the group never assembled"
                        )
                finally:
                    observer.leave(endpoint.source)
            return Result.passed(endpoint.source)

        result = climb(plan(config, pool, contract()), attempt, capacity=capacity)
        return str(getattr(result, "value", "") or "")

    return job


@contextmanager
def saturated(capacity: Capacity, pool: SourceMap, *rungs: str) -> Iterator[None]:
    """Hold every slot of ``rungs`` for the body, from threads that can hold them.

    One thread per slot rather than a nested stack on this one, because
    :meth:`Capacity.hold` refuses a thread that already holds the source — a
    caller queueing against itself is a deadlock it names rather than performs.
    """
    endpoints = [pool.bind(rung) for rung in rungs]
    held = threading.Semaphore(0)
    release = threading.Event()
    slots = [(e, i) for e in endpoints for i in range(capacity.limits[e.source])]

    def occupy(endpoint: object) -> None:
        with capacity.hold(endpoint):  # type: ignore[arg-type]
            held.release()
            release.wait(RENDEZVOUS_TIMEOUT_S)

    threads = [threading.Thread(target=occupy, args=(e,)) for e, _ in slots]
    for thread in threads:
        thread.start()
    try:
        for _ in slots:
            assert held.acquire(timeout=RENDEZVOUS_TIMEOUT_S), "a slot never filled"
        yield
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=RENDEZVOUS_TIMEOUT_S)


# --------------------------------------------------------------------------
# Where the width comes from
# --------------------------------------------------------------------------


def test_a_source_that_reports_its_width_is_bounded_by_what_it_reported() -> None:
    """The declared number is a guess; a reported one is a fact, and it wins.

    `init` writes ``max_parallel: 1`` because it cannot know whether a backend
    was started with its parallel-slot setting on. A backend that will answer
    that question ends the guess, and ending it is the whole point: CON-04
    measured 8.5x at sixteen concurrent requests on a batching server, and a
    config pinned at 1 in front of it leaves all of that unused.
    """
    config, _ = mapped()
    reported = {"srv1": 4, "srv2": 4, "vendor": 4}

    capacity = Capacity.of(config, probe=_ReportingProbe(reported))

    assert capacity.limits["srv1"] == 4, "the config declared 2; the rig said 4"
    assert capacity.total == 12


def test_a_source_that_cannot_report_its_width_keeps_the_declared_one_and_says_so() -> (
    None
):
    """Not every backend will answer, and pretending otherwise is the trap.

    ollama serves its parallelism from ``OLLAMA_NUM_PARALLEL`` in the unit file
    and exposes no endpoint for it; at ``0`` it chooses per model at load time
    against free VRAM, so the width is not even a per-machine constant. The
    declared number is then the only number there is — and an operator reading
    a report must be able to tell that from a number a rig confirmed, because
    only one of the two is evidence.
    """
    config, _ = mapped()

    probe = _ReportingProbe({"srv1": None, "srv2": None})
    capacity = Capacity.of(config, probe=probe)

    assert capacity.limits["srv1"] == 2, "the declaration stands when nothing answers"
    assert capacity.confirmed("srv1") is False
    assert capacity.confirmed("vendor") is False


def test_a_declared_width_the_setup_contradicts_is_refused_rather_than_enforced() -> (
    None
):
    """The one failure the whole CON-02 note exists to warn about, made loud.

    A config declaring 2 in front of a single-slot server does not fail. It
    admits both dispatches, runs them one after another, and looks exactly like
    a source that is merely slow — so the operator's evidence for "my rig is
    slow" is indistinguishable from their evidence for "my config is wrong".
    When the rig will state its width, that ambiguity is a choice, not a limit.
    """
    config, _ = mapped()

    with pytest.raises(Exception, match=r"srv1.*declares 2.*reports 1"):
        Capacity.of(config, probe=_ReportingProbe({"srv1": 1}))


class _ReportingProbe:
    """A stand-in for the width half of #22's probe: source name -> width or None.

    ``None`` is an ordinary answer meaning "this backend does not say", which is
    the ollama case measured on both rigs on 2026-08-29 — not an error, and not
    the same as a source being down.
    """

    def __init__(self, widths: Mapping[str, int | None]) -> None:
        self._widths = widths

    def width(self, source: str) -> int | None:
        return self._widths.get(source)


# --------------------------------------------------------------------------
# Where the work goes
# --------------------------------------------------------------------------


def test_the_default_keeps_a_batch_on_one_rig_and_never_funds_the_api_family(
    key: None,
) -> None:
    """The default is no fan-out, and this is the test that keeps it that way.

    Green, and the only green test in this file. It guards two things the other
    three are all pressure on. The first is the default itself: fan-out is a
    knob because the Rig A → Rig B ladder must not fan out, and a default that
    drifted would silently spend Rig B's drain rate on Rig A's volume. The
    second is that queueing is not failing — six contracts through two slots
    means four of them wait, and :mod:`mcgyvr.escalate` climbs on ``FAILED``, so
    a wait that produced a failing verdict would fund the api family out of a
    queue that is free. Every contract lands on srv1, none on vendor, and
    nothing fails.
    """
    config, pool = mapped()
    capacity = Capacity.of(config)
    observer = Observer()
    rendezvous = Rendezvous(2)
    jobs = [climbing(pool, config, observer, rendezvous) for _ in range(6)]

    outcomes = run_batch(jobs, capacity)

    assert all(o.ok for o in outcomes), [str(o.error) for o in outcomes if not o.ok]
    landed = [o.value for o in outcomes]
    assert set(landed) == {"srv1"}, "the default takes the cheapest rung, always"
    assert observer.peak == {"srv1": 2}, "srv2 was never recruited"
    assert observer.peak_total == 2


def test_full_fanout_spreads_a_batch_across_every_source_that_can_serve_it(
    key: None,
) -> None:
    """The headline gap, and the reason raising ``max_parallel`` does not fix it.

    Six contracts, one task type, one floor family, two sources that both serve
    it at a width of two. The reachable concurrency is four. What happens today
    is two: every contract takes ``local_srv1`` because it is written first, and
    ``local_srv2`` is reached only by a contract that *failed* on srv1 — never
    because srv1 is busy. Widening ``max_parallel`` widens the rig that was
    already the only one being used.

    The assertions are per source *and* across sources, and both are needed.
    Two per-source peaks of 2 are equally true of a batch that drained srv1 and
    only then started srv2; that is the ambiguity #200 added
    :class:`~mcgyvr.capacity.Concurrency` to remove, and the rendezvous is what
    turns it into a fact rather than a stopwatch reading.
    """
    config, pool = mapped(peers("full"))
    capacity = Capacity.of(config)
    observer = Observer()
    rendezvous = Rendezvous(4)
    jobs = [climbing(pool, config, observer, rendezvous) for _ in range(6)]

    outcomes = run_batch(jobs, capacity)

    assert all(o.ok for o in outcomes), [str(o.error) for o in outcomes if not o.ok]
    assert observer.peak == {"srv1": 2, "srv2": 2}
    assert observer.peak_total == 4
    assert observer.peak_total > max(observer.peak.values()), "together, not in series"


def test_load_never_reorders_the_price_ladder_even_at_full_fanout() -> None:
    """The constraint that keeps the fix from becoming an escalation change.

    ``local_srv1`` and ``local_srv2`` carry the same model, so choosing the free
    one is a tie-break and costs nothing. Order is a different matter: a plan
    that put a busy rung last would be deciding, from inside one family, that
    load outranks price. Within the family this stays a tie-break, and #24's
    boundary — nothing in :mod:`mcgyvr.route` looks at a family other than the
    one it was asked about — is what keeps ``full`` from quietly becoming the
    cross-family spill that is ``idle``'s job and lives in another module.
    """
    config, pool = mapped(peers("full"))
    capacity = Capacity.of(config)

    ordered = plan(config, pool, contract(), capacity=capacity)

    assert ordered.rungs == ("local_srv1", "local_srv2"), "price order, always"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-30: decided - `idle` takes the cheapest rung AT OR ABOVE the "
        "contract's floor that has a free slot; the floor is the only bound, so "
        "a saturated local ladder spills into api rather than waiting. Red at "
        "parse until `ladder.fanout` exists, then red until `ascent` takes a "
        "capacity. `escalate.ascent` and not `route.plan` because the choice "
        "crosses families and #24 forbids `route` from seeing past one"
    ),
)
def test_idle_fanout_spills_to_a_free_api_rung_when_every_local_rung_is_full(
    key: None,
) -> None:
    """Where ``idle`` stops being a throughput knob and becomes a spend one.

    With both local rigs full, the cheapest rung at or above this contract's
    floor that still has a free slot is ``api_big`` — so ``idle`` buys capacity
    because the local rigs were busy, not because anything failed. That is the
    knob doing what it was asked to do, and it is worth writing down precisely
    because it looks identical, from the outside, to the escalation this file's
    other tests exist to prevent. The difference is the record: nothing failed,
    no verdict was reached, and the rung was chosen rather than climbed to.

    The floor is the one bound. A rung *below* the contract's floor is never
    eligible however idle it is — risk raises a floor and load may not lower it.
    """
    config, pool = mapped(peers("idle"))
    capacity = Capacity.of(config)

    with saturated(capacity, pool, "local_srv1", "local_srv2"):
        climbable = ascent(config, pool, contract(), capacity=capacity)  # type: ignore[call-arg]

        assert climbable.next_free_rung == "api_big"  # type: ignore[attr-defined]
