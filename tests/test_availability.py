"""Availability probing (#22).

The three properties #22 asks for, each held by a test that would fail if the
implementation drifted back to the obvious version of itself:

1. **A dead source costs one short timeout per run, not one per attempt.** The
   probe is counted, not just observed — a cache that quietly stopped caching
   would still produce the right ladder and the wrong bill.
2. **Skipping is recorded with a reason.** A rung that vanished is not the same
   as a rung that was never there, and the reason has to survive into
   ``Skipped`` and out of ``bind()``.
3. **All sources down degrades to a named failure, never a hang.** An empty
   ladder that can say why, and a probe that classifies rather than raises.

The transport is stubbed throughout. A test that needed a live backend would be
a test that does not run in CI, and the interesting logic here is the
classification, which HTTP would only obscure.
"""

from __future__ import annotations

import time
import urllib.error

import pytest

from mcgyvr.availability import (
    Availability,
    Verdict,
    probe_endpoint,
)
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, Protocol, SourceUnavailableError, source_map

TWO_SOURCES = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
  spare:
    base_url: http://192.168.1.9:8000
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: local_small
      source: workstation
      model: qwen2.5-coder:1.5b
    - name: local_large
      source: workstation
      model: qwen2.5-coder:7b
    - name: remote_large
      source: spare
      model: qwen2.5-coder:32b
"""

# One source is keyless and one names a credential, so the structural pass and
# the probe each have something to do — which is what makes "a structurally
# skipped source is never probed" a real assertion rather than a vacuous one.
MIXED_CAUSES = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
  spare:
    base_url: https://api.example.com
    api: openai
    max_parallel: 1
    api_key_env: MCGYVR_AVAIL_TEST_KEY
ladder:
  tiers:
    - name: first
      source: workstation
      model: a
    - name: second
      source: spare
      model: b
    - name: third
      source: workstation
      model: c
"""

WITH_VERIFIER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
  spare:
    base_url: http://192.168.1.9:8000
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: local_small
      source: workstation
      model: a
verifier:
  source: spare
  model: judge
"""


def endpoint(source: str = "local", protocol: Protocol = Protocol.OPENAI) -> Endpoint:
    return Endpoint(
        source=source,
        base_url="http://localhost:8000",
        protocol=protocol,
        max_parallel=1,
        credential_env=None,
    )


def live(_endpoint: Endpoint, _timeout: float) -> Verdict:
    return Verdict(_endpoint.source, True, "", "stub: live", 0.0)


def dead(_endpoint: Endpoint, _timeout: float) -> Verdict:
    return Verdict(
        _endpoint.source,
        False,
        f"source {_endpoint.source!r} did not answer",
        "stub: dead",
        0.0,
    )


class Counting:
    """A probe that records how many times it was actually called."""

    def __init__(self, verdict=dead) -> None:
        self.calls: list[str] = []
        self._verdict = verdict

    def __call__(self, target: Endpoint, timeout: float) -> Verdict:
        self.calls.append(target.source)
        return self._verdict(target, timeout)


# --- 1. one timeout per run ------------------------------------------------


def test_a_source_is_probed_once_however_many_times_it_is_asked_for() -> None:
    """The cache is the whole feature: this is the bill, not the behaviour."""
    counting = Counting()
    availability = Availability(probe=counting)
    target = endpoint()

    for _ in range(5):
        availability.check(target)

    assert counting.calls == ["local"]


def test_one_source_serving_many_rungs_is_one_probe() -> None:
    """Three rungs on one dead host is one timeout, not three."""
    counting = Counting()
    availability = Availability(probe=counting)
    rungs = [endpoint("shared"), endpoint("shared"), endpoint("shared")]

    availability.unavailable(rungs)

    assert counting.calls == ["shared"]


def test_a_second_pass_over_the_same_sources_costs_nothing() -> None:
    counting = Counting()
    availability = Availability(probe=counting)
    targets = [endpoint("a"), endpoint("b")]

    availability.check_all(targets)
    availability.check_all(targets)

    assert sorted(counting.calls) == ["a", "b"]


def test_dead_sources_are_probed_concurrently() -> None:
    """Wall clock for n dead sources is one timeout, not n.

    The margin is deliberately loose — this is asserting a thread pool exists,
    not measuring one. Serial execution would take 1.2s against a bound of 0.6.
    """

    def slow(target: Endpoint, _timeout: float) -> Verdict:
        time.sleep(0.2)
        return dead(target, _timeout)

    availability = Availability(probe=slow)
    targets = [endpoint(f"s{i}") for i in range(6)]

    started = time.monotonic()
    availability.check_all(targets)
    elapsed = time.monotonic() - started

    assert elapsed < 0.6, f"probes look serial: {elapsed:.2f}s for 6 probes of 0.2s"


def test_the_probe_timeout_is_far_below_the_dispatch_timeout() -> None:
    """They measure different things; #22's must not inherit #21's two minutes."""
    from mcgyvr.availability import PROBE_TIMEOUT_S
    from mcgyvr.runner import GENERATE_TIMEOUT_S

    assert PROBE_TIMEOUT_S < GENERATE_TIMEOUT_S / 10


def test_a_non_positive_timeout_is_refused() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        Availability(timeout_s=0)


# --- 2. classification -----------------------------------------------------


def _stub_urlopen(monkeypatch, behaviour) -> None:
    monkeypatch.setattr(
        "mcgyvr.availability.urllib.request.urlopen",
        lambda request, timeout: behaviour(request, timeout),
    )


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.mark.parametrize(
    ("status", "expected_live"),
    [
        (200, True),
        (404, True),  # the model-list path is optional; a dispatch may still work
        (405, True),
        (401, False),
        (403, False),
        (500, False),
        (503, False),
    ],
)
def test_http_status_is_read_as_liveness(monkeypatch, status, expected_live) -> None:
    def behaviour(_request, _timeout):
        if status >= 400:
            raise urllib.error.HTTPError(
                "http://localhost:8000/v1/models", status, "", {}, None
            )
        return _Response(status)

    _stub_urlopen(monkeypatch, behaviour)
    verdict = probe_endpoint(endpoint())

    assert verdict.live is expected_live
    assert str(status) in verdict.how


def test_a_404_carries_the_argument_for_reading_it_as_live(monkeypatch) -> None:
    """The classification most likely to look like a bug states its own case.

    Reading a 404 at the model-list path as *down* would skip a source that
    serves generations perfectly well — a false negative that silently shortens
    the ladder, which is worse than the wasted attempt it saves.
    """

    def behaviour(_request, _timeout):
        raise urllib.error.HTTPError(
            "http://localhost:8000/v1/models", 404, "", {}, None
        )

    _stub_urlopen(monkeypatch, behaviour)
    verdict = probe_endpoint(endpoint())

    assert verdict.live is True
    assert verdict.reason == ""  # a live source has nothing to explain away
    assert "optional" in verdict.how


def test_a_credential_refusal_names_the_variable(monkeypatch) -> None:
    def behaviour(_request, _timeout):
        raise urllib.error.HTTPError(
            "https://api.example.com/v1/models", 401, "", {}, None
        )

    _stub_urlopen(monkeypatch, behaviour)
    monkeypatch.setenv("EXAMPLE_KEY", "sk-not-a-real-key")
    keyed = Endpoint(
        source="hosted",
        base_url="https://api.example.com",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env="EXAMPLE_KEY",
    )

    verdict = probe_endpoint(keyed)

    assert verdict.live is False
    assert "$EXAMPLE_KEY" in verdict.reason
    assert "sk-not-a-real-key" not in verdict.reason  # never quote the value


def test_transport_failure_is_down_and_never_raises(monkeypatch) -> None:
    def behaviour(_request, _timeout):
        raise TimeoutError("timed out")

    _stub_urlopen(monkeypatch, behaviour)
    verdict = probe_endpoint(endpoint(), timeout_s=0.5)

    assert verdict.live is False
    assert "0.5s" in verdict.reason
    assert "TimeoutError" in verdict.how


def test_each_protocol_is_asked_at_its_own_listing_path(monkeypatch) -> None:
    asked: list[str] = []

    def behaviour(request, _timeout):
        asked.append(request.full_url)
        return _Response(200)

    _stub_urlopen(monkeypatch, behaviour)
    probe_endpoint(endpoint(protocol=Protocol.OPENAI))
    probe_endpoint(endpoint(protocol=Protocol.OLLAMA))

    assert asked == [
        "http://localhost:8000/v1/models",
        "http://localhost:8000/api/tags",
    ]


def test_a_probe_is_a_listing_not_a_generation(monkeypatch) -> None:
    """A probe that cost tokens would be a probe nobody runs."""
    methods: list[str] = []

    def behaviour(request, _timeout):
        methods.append(request.get_method())
        assert request.data is None
        return _Response(200)

    _stub_urlopen(monkeypatch, behaviour)
    probe_endpoint(endpoint())

    assert methods == ["GET"]


# --- 3. the ladder degrades, with reasons ----------------------------------


class Stub:
    """A SourceProbe backed by a set of dead source names."""

    def __init__(self, *down: str) -> None:
        self.down = set(down)
        self.asked: list[str] = []

    def unavailable(self, endpoints):
        self.asked = [e.source for e in endpoints]
        return {
            e.source: f"source {e.source!r} did not answer"
            for e in endpoints
            if e.source in self.down
        }


def test_without_a_probe_nothing_touches_the_network() -> None:
    """Resolving a ladder must stay free; the probe is opt-in."""
    pool = source_map(parse(TWO_SOURCES))

    assert len(pool) == 3
    assert pool.skipped == ()


def test_an_unreachable_source_takes_its_rungs_with_it() -> None:
    pool = source_map(parse(TWO_SOURCES), probe=Stub("workstation"))

    assert [r.name for r in pool.rungs] == ["remote_large"]
    assert [s.name for s in pool.skipped] == ["local_small", "local_large"]
    assert all("did not answer" in s.reason for s in pool.skipped)


def test_the_ladder_keeps_declared_order_when_it_shortens() -> None:
    """Cheapest-first is the ladder's meaning; shortening must not reorder it."""
    pool = source_map(parse(TWO_SOURCES), probe=Stub("spare"))

    assert [r.name for r in pool.rungs] == ["local_small", "local_large"]


def test_binding_a_dropped_rung_names_the_reason() -> None:
    """The reason has to survive out of the seam, not just into a report."""
    pool = source_map(parse(TWO_SOURCES), probe=Stub("workstation"))

    with pytest.raises(SourceUnavailableError, match="did not answer"):
        pool.bind("local_small")


def test_all_sources_down_is_an_empty_ladder_that_says_why() -> None:
    """A named failure, not an exception and not a hang."""
    pool = source_map(parse(TWO_SOURCES), probe=Stub("workstation", "spare"))

    assert not pool
    assert len(pool.skipped) == 3
    assert all(s.reason for s in pool.skipped)


def test_a_structurally_skipped_source_is_never_probed(monkeypatch) -> None:
    """Nothing is learned by asking whether a host we have no key for is awake."""
    monkeypatch.delenv("MCGYVR_AVAIL_TEST_KEY", raising=False)
    stub = Stub()

    pool = source_map(parse(MIXED_CAUSES), probe=stub)

    assert stub.asked == ["workstation"]
    assert [s.name for s in pool.skipped] == ["second"]
    assert "MCGYVR_AVAIL_TEST_KEY" in pool.skipped[0].reason


def test_skipped_keeps_ladder_order_across_both_causes(monkeypatch) -> None:
    """Structural and unreachable skips interleave in declared order, not in
    two blocks — the order a reader is entitled to expect."""
    monkeypatch.delenv("MCGYVR_AVAIL_TEST_KEY", raising=False)

    pool = source_map(parse(MIXED_CAUSES), probe=Stub("workstation"))

    assert [s.name for s in pool.skipped] == ["first", "second", "third"]
    # And the two causes stay distinguishable in the words, not just the order.
    assert "did not answer" in pool.skipped[0].reason
    assert "MCGYVR_AVAIL_TEST_KEY" in pool.skipped[1].reason


def test_a_role_on_a_dead_source_is_reported_not_silently_dropped() -> None:
    pool = source_map(parse(WITH_VERIFIER), probe=Stub("spare"))

    with pytest.raises(SourceUnavailableError, match="did not answer"):
        pool.role("verifier")


def test_a_role_is_probed_alongside_the_ladder_in_one_batch() -> None:
    """The verifier's source is asked in the same batch, not in a second round."""
    counting = Counting(verdict=live)
    availability = Availability(probe=counting)

    source_map(parse(WITH_VERIFIER), probe=availability)

    assert sorted(counting.calls) == ["spare", "workstation"]


def test_the_probe_runs_once_for_the_whole_map() -> None:
    """One batch for the map, so the wall clock is one timeout for the run."""
    counting = Counting()
    availability = Availability(probe=counting)

    source_map(parse(TWO_SOURCES), probe=availability)

    assert sorted(counting.calls) == ["spare", "workstation"]
