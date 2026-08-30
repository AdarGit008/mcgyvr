"""Concurrency is a property of the rung, because it is a property of the process.

The same weights on two rigs are two processes started with two different slot
counts, so one number on the source cannot describe both. A tier may state its
own width; the source's value remains the default for a tier that does not.

A width mcgyvr wrote into a launch line is a fact it knows, not a guess -- which
is the whole reason the default of 1 existed.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import runner
from mcgyvr.capacity import Capacity, CapacityError
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import ascent
from mcgyvr.pool import source_map
from mcgyvr.route import Result, Try, climb, plan
from mcgyvr.runner import Request

TIER_WIDTH = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai}
ladder:
  tiers:
    - {name: local_moe, source: d1, model: qwen3-coder-30b, max_parallel: 8}
"""

TIER_OVERRIDES_SOURCE = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai, max_parallel: 2}
ladder:
  tiers:
    - {name: local_moe, source: d1, model: qwen3-coder-30b, max_parallel: 8}
"""

TWO_WIDTHS = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai}
ladder:
  tiers:
    - {name: fast, source: d1, model: qwen2.5-coder-3b, max_parallel: 16}
    - {name: smart, source: d1, model: qwen3-coder-30b, max_parallel: 4}
"""

NO_TIER_WIDTH = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai, max_parallel: 3}
ladder:
  tiers:
    - {name: local_moe, source: d1, model: qwen3-coder-30b}
"""


class Probe:
    def __init__(self, **widths: int | None) -> None:
        self.widths = widths

    def width(self, source: str, rung: str | None = None) -> int | None:
        return self.widths.get(rung or source)


def test_a_tier_accepts_its_own_width() -> None:
    assert parse(TIER_WIDTH).ladder.tiers[0].max_parallel == 8


def test_a_tier_without_a_width_says_so() -> None:
    assert parse(NO_TIER_WIDTH).ladder.tiers[0].max_parallel is None


def test_a_width_below_one_is_refused() -> None:
    with pytest.raises(ConfigSchemaError):
        parse(TIER_WIDTH.replace("max_parallel: 8", "max_parallel: 0"))


def test_tier_width_overrides_the_source_default() -> None:
    capacity = Capacity.of(parse(TIER_OVERRIDES_SOURCE))
    assert capacity.limit("d1", rung="local_moe") == 8


def test_an_unset_tier_width_falls_back_to_the_source() -> None:
    capacity = Capacity.of(parse(NO_TIER_WIDTH))
    assert capacity.limit("d1", rung="local_moe") == 3


def test_two_rungs_on_one_source_may_hold_different_widths() -> None:
    capacity = Capacity.of(parse(TWO_WIDTHS))
    assert capacity.limit("d1", rung="fast") == 16
    assert capacity.limit("d1", rung="smart") == 4


def test_slots_are_held_per_rung_not_pooled_across_the_source(
    tmp_path: Path,
) -> None:
    capacity = Capacity.of(parse(TWO_WIDTHS), root=tmp_path)
    with capacity.hold("d1", rung="smart"):
        assert capacity.in_flight("d1", rung="fast") == 0


def test_a_written_width_is_confirmed_rather_than_assumed() -> None:
    capacity = Capacity.of(parse(TWO_WIDTHS), probe=Probe(fast=16, smart=4))
    assert capacity.confirmed("d1", rung="fast") is True


def test_an_unprobed_width_is_not_confirmed() -> None:
    capacity = Capacity.of(parse(TWO_WIDTHS))
    assert capacity.confirmed("d1", rung="fast") is False


def test_a_backend_reporting_less_than_written_is_an_error() -> None:
    with pytest.raises(CapacityError):
        Capacity.of(parse(TWO_WIDTHS), probe=Probe(fast=4, smart=4))


def test_a_backend_reporting_more_than_written_wins() -> None:
    capacity = Capacity.of(parse(NO_TIER_WIDTH), probe=Probe(local_moe=12))
    assert capacity.limit("d1", rung="local_moe") == 12


def test_the_source_level_width_still_parses() -> None:
    assert parse(NO_TIER_WIDTH).sources["d1"].max_parallel == 3


# ---------------------------------------------------------------------------
# The width is enforced, and not merely reported (#23)
#
# Every test above this line passed while a dispatch to a sixteen-wide rung ran
# one request at a time, because every one of them asked ``limit()`` — the
# number — and none of them asked the rig. What follows asks the rig: observed
# concurrency, a load a fan-out can actually read, and a config that has to
# start. A width nobody reaches is a number in a report, which is precisely the
# thing this module exists to stop being.
# ---------------------------------------------------------------------------

# How long a dispatch waits for its group to assemble before giving up. Nothing
# asserts on it: where the rung's width is enforced the group latches as soon as
# the last member arrives, so this costs a working implementation nothing and
# only decides how long a pinned one takes to say so.
TOGETHER_TIMEOUT_S = 2.0

RUNG_WIDER_THAN_ITS_SOURCE = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai, max_parallel: 1}
ladder:
  tiers:
    - {name: fast, source: d1, model: qwen2.5-coder-3b, max_parallel: 4}
"""

PEER_RIGS = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai, max_parallel: 2}
  d2: {base_url: "http://desktop-2:8080", api: openai, max_parallel: 2}
ladder:
  fanout: full
  tiers:
    - {name: local_d1, source: d1, model: qwen3-coder-30b, max_parallel: 1}
    - {name: local_d2, source: d2, model: qwen3-coder-30b, max_parallel: 1}
"""

ONE_RIG_TWO_PROCESSES = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai, max_parallel: 4}
  vendor:
    base_url: "https://api.example.com/v1"
    api: openai
    max_parallel: 4
    api_key_env: EXAMPLE_API_KEY
ladder:
  fanout: idle
  tiers:
    - {name: fast, source: d1, model: qwen2.5-coder-3b, max_parallel: 1}
    - {name: slow, source: d1, model: qwen3-coder-30b, max_parallel: 1}
    - {name: api_big, source: vendor, model: vendor-large}
"""

WIDENED_SOURCE_NARROW_RUNG = """
version: 1
sources:
  d1: {base_url: "http://desktop-1:8080", api: openai, max_parallel: 2}
ladder:
  tiers:
    - {name: fast, source: d1, model: qwen2.5-coder-3b}
    - {name: slow, source: d1, model: qwen3-coder-30b}
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

ANSWER: dict[str, Any] = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "def f():\n    return 1\n"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 4},
}

ASK = Request(prompt="write a function", max_output_tokens=64)


class Together:
    """An independent count of how many dispatches were inside the backend at once.

    Independent because :meth:`Capacity.usage` and :meth:`Capacity.limit` are the
    implementation grading its own homework: both reported the rung's declared
    sixteen while the rig served one at a time. This counts arrivals from inside
    the transport — the far side of every seam under test — and holds each one
    there until the whole group has arrived, so the number it reports is
    concurrency actually reached and not a width restated.

    A dispatch that cannot join its group leaves at the timeout rather than
    hanging, so a pinned width arrives as a failed assertion and not as a suite
    that never finishes.
    """

    def __init__(self, parties: int) -> None:
        self._lock = threading.Lock()
        self._barrier = threading.Barrier(parties)
        self.inside = 0
        self.peak = 0

    def arrive(self) -> None:
        with self._lock:
            self.inside += 1
            self.peak = max(self.peak, self.inside)
        # A group that never assembles leaves at the timeout: ``peak`` is what
        # says so, and a hang would say it far less clearly.
        with contextlib.suppress(threading.BrokenBarrierError):
            self._barrier.wait(timeout=TOGETHER_TIMEOUT_S)
        with self._lock:
            self.inside -= 1


def transport(monkeypatch: pytest.MonkeyPatch, together: Together) -> None:
    """Replace the wire with one that reports what was in flight while it ran."""

    def fake_post(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        together.arrive()
        return ANSWER

    monkeypatch.setattr(runner, "_post_json", fake_post, raising=True)


def test_a_rungs_declared_width_is_reached_by_dispatches_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rung says four, the source says one, and four must actually run.

    Asserted on observed concurrency rather than on ``limit()``, because
    ``limit()`` answered four throughout the whole life of the defect: the rung
    was named to the pool and not to the capacity, so every dispatch was held
    against the source's single slot and the ladder's declared width was a
    number that existed only in reports. Four threads that must be inside the
    backend together are the only assertion the bug could not pass.
    """
    config = parse(RUNG_WIDER_THAN_ITS_SOURCE)
    pool = source_map(config)
    capacity = Capacity.of(config, root=tmp_path)
    together = Together(4)
    transport(monkeypatch, together)

    def dispatching() -> None:
        runner.dispatch(pool, "fast", ASK, capacity=capacity)

    threads = [threading.Thread(target=dispatching) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TOGETHER_TIMEOUT_S * 4)

    assert together.peak == 4, (
        "the rung declares four slots; a dispatch naming it must be held "
        "against those and not against its source's one"
    )
    assert capacity.limit("d1") == 1, "and the source's own bound is untouched"


def test_a_dispatch_to_a_rung_without_a_width_still_holds_its_sources_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compatibility half: a rung that declares nothing is bounded as before.

    ``sources.*.max_parallel`` keeps the meaning it has always had, so naming the
    rung must change nothing for a ladder that never declared a rung width.
    """
    config = parse(NO_TIER_WIDTH)
    pool = source_map(config)
    capacity = Capacity.of(config, root=tmp_path)
    seen: list[int] = []

    def fake_post(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        seen.append(capacity.in_use("d1"))
        return ANSWER

    monkeypatch.setattr(runner, "_post_json", fake_post, raising=True)

    runner.dispatch(pool, "local_moe", ASK, capacity=capacity)

    assert seen == [1], "the source's own slot, held for the length of the request"
    assert capacity.in_use("d1") == 0


def test_full_fanout_can_see_a_rung_that_is_full_of_its_own_holds(
    tmp_path: Path,
) -> None:
    """A rung's holds are load, and a fan-out that cannot see them is price order.

    Once a dispatch is held against its rung, ``in_use(source)`` counts none of
    it — that is the point of a second queue — so a load read from the source
    alone reports zero for every rung with a width of its own. Every member of a
    batch would then compare zeroes, ``full`` would return the cheapest rung
    every time, and the funnel the knob exists to end would be back with the
    knob still saying ``full``.
    """
    config = parse(PEER_RIGS)
    pool = source_map(config)
    capacity = Capacity.of(config, root=tmp_path)
    tried: list[str] = []

    def attempt(each: Try) -> Result[str]:
        tried.append(each.rung.name)
        return Result.passed(each.rung.name)

    made = plan(config, pool, load_contract(CONTRACT))
    busy = made.steps[0].machine
    assert busy is not None

    with capacity.hold(pool.bind("local_d1"), rung="local_d1"):
        assert busy.load(capacity, "local_d1") == 1, "the rung's own slot is held"
        climb(made, attempt, capacity=capacity)

    assert tried == ["local_d2"], "the peer whose own server is idle"


def test_a_load_read_for_no_rung_is_still_the_sources_own_queue(
    tmp_path: Path,
) -> None:
    """The compatibility half of the load: an unnamed rung reads what it always did."""
    config = parse(PEER_RIGS)
    pool = source_map(config)
    capacity = Capacity.of(config, root=tmp_path)
    made = plan(config, pool, load_contract(CONTRACT))
    machine = made.steps[0].machine
    assert machine is not None

    assert machine.load(capacity) == 0
    with capacity.hold(pool.bind("local_d1")):
        assert machine.load(capacity) == 1


def test_idle_takes_a_free_narrow_rung_rather_than_buying_a_priced_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``idle``'s two halves must be the same half: this rung's load, this rung's width.

    One rig, two server processes, one of them full. The free slot is on the
    other local rung, and naming the api rung instead is a spend decision made
    out of a mis-read number. Both halves were wrong together: the load came
    from the source, which counts no rung's holds, and the width came from the
    source, which is not what bounds a rung that declared its own.
    """
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    config = parse(ONE_RIG_TWO_PROCESSES)
    pool = source_map(config)
    capacity = Capacity.of(config, root=tmp_path)

    route = ascent(config, pool, load_contract(CONTRACT), capacity=capacity)
    assert route.widths["slow"] == 1, "the rung's own width, not its rig's four"

    with capacity.hold(pool.bind("fast"), rung="fast"):
        assert route.next_free_rung == "slow"


def test_a_narrow_rung_on_a_widened_source_is_not_a_contradiction(
    tmp_path: Path,
) -> None:
    """Nobody wrote the number the rung was refused for contradicting.

    The source declares 2 and neither rung declares anything. A probe reporting
    source 8, fast 8 and slow 4 was read as "slow is written for 8 and reports
    4" — the 8 being the probe's own answer about the *other* process, promoted
    to a declaration on the way past. One rig running a wide process and a
    narrow one is exactly what per-rung widths are for, and it has to start.
    """
    capacity = Capacity.of(
        parse(WIDENED_SOURCE_NARROW_RUNG),
        probe=Probe(d1=8, fast=8, slow=4),
        root=tmp_path,
    )

    assert capacity.limit("d1") == 8, "the rig's own report still wins"
    assert capacity.limit("d1", rung="fast") == 8
    assert capacity.limit("d1", rung="slow") == 4


def test_a_rung_narrower_than_the_config_wrote_is_still_refused() -> None:
    """The rule that is not being loosened: a machine contradicting the *config*.

    The source declares 2 and the rung's server reports 1, with no probe having
    widened anything. That is two answers to one question with a config on one
    side of it, and quietly lowering the bound would leave the config wrong and
    the operator guessing.
    """
    with pytest.raises(CapacityError, match="reports 1"):
        Capacity.of(parse(WIDENED_SOURCE_NARROW_RUNG), probe=Probe(slow=1))


def test_a_rigs_superseded_source_width_is_not_a_second_queue() -> None:
    """``total`` sizes :func:`run_batch`'s pool, so a phantom slot is a thread.

    A rung's width overrides its source's, so the rig here admits four and not
    the five that summing every bound reported. The rung bounds of one rig do
    add up between themselves — each is a server process of its own — which is
    the difference this counts.
    """
    assert Capacity.of(parse(RUNG_WIDER_THAN_ITS_SOURCE)).total == 4
    assert Capacity.of(parse(TWO_WIDTHS)).total == 20, "16 and 4 are two servers"
    assert Capacity.of(parse(NO_TIER_WIDTH)).total == 3, "no rung width, no change"
