"""Two gaps between the bound mcgyvr enforces and the machines it enforces it on.

Every test here is red on purpose, and the two groups fail for different
reasons.

**Where the width comes from.** ``max_parallel`` is declared in the config and
enforced verbatim (:mod:`mcgyvr.capacity`), and nothing ever asks the machine
whether the number is true. CON-02 is precisely the case that makes this cost
something: a single-slot server handed four concurrent requests *serializes them
rather than refusing them*, so an over-declared capacity is not an error anyone
sees — it is a queue nobody sees. :func:`mcgyvr.initialize.initialize` writes
``1`` for exactly this reason, which is honest and leaves measured throughput on
the floor. The width is knowable on some backends and not others, so these tests
hold both halves: a setup that can say must be believed, and a setup that cannot
say must be *distinguishable* from one that was confirmed.

**Where the work goes.** :func:`mcgyvr.route.plan` orders rungs by price, and
nothing in the module reads :meth:`~mcgyvr.capacity.Capacity.in_use`. So a batch
of contracts that share a task type share a floor family, take the same cheapest
rung, and queue on one source while every other source that could serve the same
family sits idle. The capacity layer is not at fault and is already green:
``test_a_mixed_batch_runs_two_sources_at_once_rather_than_in_series`` proves two
sources *can* run together — but its jobs are handed their endpoints outright,
so it never exercises a routing decision. That is the untested seam.

Concurrency is asserted the way ``test_capacity.py`` asserts it: an independent
:class:`Observer`, and a :class:`threading.Barrier` rather than a stopwatch, so
a loaded machine makes a test slower and never wrong. A batch that cannot put
the required number in flight together never trips the barrier, every waiter
raises ``BrokenBarrierError`` at the deadline, and the failure is reported as
failed outcomes rather than a hang.

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
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity, run_batch
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import Result, Try, climb, plan

# Deliberately far longer than any batch here needs. Nothing asserts on it: if
# the routing under test fans out, the barrier trips as soon as the last party
# arrives, so a generous bound costs a working implementation nothing and only
# decides how long a broken one takes to say so.
BARRIER_TIMEOUT_S = 20.0


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
# one costs nothing that could be called an escalation.
FANOUT = """
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
  tiers:
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


def mapped(text: str = FANOUT) -> tuple[Config, SourceMap]:
    config = parse(text)
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


def climbing(
    pool: SourceMap,
    config: Config,
    observer: Observer,
    barrier: threading.Barrier,
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
                    barrier.wait(timeout=BARRIER_TIMEOUT_S)
                finally:
                    observer.leave(endpoint.source)
            return Result.passed(endpoint.source)

        result = climb(plan(config, pool, contract()), attempt, capacity=capacity)
        return str(getattr(result, "value", "") or "")

    return job


# --------------------------------------------------------------------------
# Where the width comes from
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-29: decided - the width is whatever the setup says, not what "
        "the config guesses. Red until a source that can report its own "
        "parallel width is bounded by the reported number: there is no probe "
        "for it today, so `Capacity.of` takes no probe and this raises rather "
        "than asserts. llama.cpp answers it on `GET /slots` and `/props."
        "total_slots`; that is the backend this covers"
    ),
)
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

    capacity = Capacity.of(config, probe=_ReportingProbe(reported))  # type: ignore[call-arg]  # red: Capacity.of takes no probe yet

    assert capacity.limits["srv1"] == 4, "the config declared 2; the rig said 4"
    assert capacity.total == 12


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-29: decided - a width that was confirmed and a width that was "
        "assumed must not look alike. Red until an unreportable source keeps "
        "its declared number and is marked unconfirmed. Probed 2026-08-29: "
        "srv1 and srv2 both serve ollama 0.32.15, `/slots` answers 404, and "
        "both units set OLLAMA_NUM_PARALLEL=0 (auto, decided per model at load "
        "time), so this is the branch both of this project's rigs are in"
    ),
)
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
    capacity = Capacity.of(config, probe=probe)  # type: ignore[call-arg]  # red: no probe yet

    assert capacity.limits["srv1"] == 2, "the declaration stands when nothing answers"
    assert capacity.confirmed("srv1") is False  # type: ignore[attr-defined]
    assert capacity.confirmed("vendor") is False  # type: ignore[attr-defined]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-29: decided - CON-02's invisible queue becomes visible the "
        "moment the rig can be asked. Red until a declared width the setup "
        "contradicts is refused by name instead of enforced. `Capacity.hold` "
        "already refuses an endpoint that disagrees with the enforced limit "
        "('two answers to one question'); this is the same rule pointed at the "
        "machine rather than at a stale config"
    ),
)
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
        Capacity.of(config, probe=_ReportingProbe({"srv1": 1}))  # type: ignore[call-arg]


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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-29: decided - a batch must use every rig that can serve it. "
        "Red because `route.plan` orders rungs by price alone and nothing reads "
        "`Capacity.in_use`, so six contracts of one task type all take the "
        "cheapest rung, queue two-wide on srv1, and never reach srv2. Four "
        "parties never assemble, so the barrier times out and the outcomes "
        "carry BrokenBarrierError"
    ),
)
def test_a_batch_of_one_task_type_saturates_every_source_that_can_serve_it(
    key: None,
) -> None:
    """The headline gap, and the reason raising ``max_parallel`` does not fix it.

    Six contracts, one task type, one floor family, two sources that both serve
    it at a width of two. The reachable concurrency is four. What happens today
    is two: every contract takes ``local_srv1`` because it is written first, and
    ``local_srv2`` is reached only by a contract that *failed* on srv1 — never
    because srv1 is busy.

    The assertions are per source *and* across sources, and both are needed.
    Two per-source peaks of 2 are equally true of a batch that drained srv1 and
    only then started srv2; that is the ambiguity #200 added
    :class:`~mcgyvr.capacity.Concurrency` to remove, and the barrier is what
    turns it into a fact rather than a stopwatch reading.
    """
    config, pool = mapped()
    capacity = Capacity.of(config)
    observer = Observer()
    barrier = threading.Barrier(4)
    jobs = [climbing(pool, config, observer, barrier) for _ in range(6)]

    outcomes = run_batch(jobs, capacity)

    assert all(o.ok for o in outcomes), "four dispatches never assembled together"
    assert observer.peak == {"srv1": 2, "srv2": 2}
    assert observer.peak_total == 4
    assert observer.peak_total > max(observer.peak.values()), "together, not in series"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-29: decided - load may break a tie and may never reorder the "
        "price ladder. Red until there is a load-aware choice at all; written "
        "now because it is the regression the fix invites, and a guard added "
        "after the fact guards nothing"
    ),
)
def test_load_only_breaks_a_tie_and_never_reorders_the_price_ladder() -> None:
    """The constraint that keeps the fix from becoming an escalation change.

    ``local_srv1`` and ``local_srv2`` carry the same model, so choosing the free
    one is a tie-break and costs nothing. A dearer rung is a different matter:
    preferring it because a cheaper one is busy is a spend decision, it is #43's
    and not #24's, and `route.py` states as its own boundary that nothing in it
    may look at a family other than the one it was asked about. So a saturated
    ladder must still plan in price order.
    """
    config, pool = mapped()
    capacity = Capacity.of(config)

    ordered = plan(config, pool, contract(), capacity=capacity)  # type: ignore[call-arg]

    assert ordered.rungs == ("local_srv1", "local_srv2"), "price order, always"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-29: decided - a full rig is a queue, not a failure. Red until "
        "the load-aware path exists to be constrained; the rule it encodes is "
        "that waiting for a slot must never be reported as a verdict, because "
        "`escalate` funds the next family off exactly those verdicts"
    ),
)
def test_a_saturated_source_waits_rather_than_being_reported_as_a_failure(
    key: None,
) -> None:
    """Waiting is not failing, and confusing the two spends real money.

    :mod:`mcgyvr.escalate` climbs on ``FAILED``. If a saturated local source
    ever produced a failing verdict, a deep batch would escalate itself into the
    api family purely because the local rigs were busy — turning a queue, which
    is free, into spend. :meth:`Capacity.hold` already blocks rather than
    raising for this reason; the rule has to survive contact with a router that
    can see load.
    """
    config, pool = mapped()
    capacity = Capacity.of(config)
    observer = Observer()
    barrier = threading.Barrier(4)
    jobs = [climbing(pool, config, observer, barrier) for _ in range(6)]

    outcomes = run_batch(jobs, capacity)

    landed = [o.value for o in outcomes if o.ok]
    assert len(landed) == 6, "every contract was served"
    assert "vendor" not in landed, "a busy local rig must not fund the api family"
    assert set(landed) == {"srv1", "srv2"}
