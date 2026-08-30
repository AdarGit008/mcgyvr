"""Concurrency is a property of the rung, because it is a property of the process.

The same weights on two rigs are two processes started with two different slot
counts, so one number on the source cannot describe both. A tier may state its
own width; the source's value remains the default for a tier that does not.

A width mcgyvr wrote into a launch line is a fact it knows, not a guess -- which
is the whole reason the default of 1 existed.
"""

from __future__ import annotations

import pytest

from mcgyvr.capacity import Capacity, CapacityError
from mcgyvr.config import parse

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
    with pytest.raises(Exception):
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


def test_slots_are_held_per_rung_not_pooled_across_the_source(tmp_path) -> None:
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
