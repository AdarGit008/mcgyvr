"""A link's bandwidth and latency are fitted from timed transfers, or refused.

Seconds are a fixed cost plus the payload over the bandwidth, so transfers of
several sizes name both. The fit recovers them from exact timings, and refuses
timings that cannot come from a link: a single payload size, which cannot tell
bandwidth from latency; a payload that took no longer when it was bigger; a
latency that is not above 0; and a time that is not a time. Nothing is
clamped into shape.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from mcgyvr.serving import interconnect
from tests import link_fixture as lf


@pytest.mark.parametrize(
    ("gib_s", "latency_us"), [(12.0, 10.0), (0.11, 200.0), (3.5, 1.0), (60.0, 7.0)]
)
def test_exact_timings_give_back_the_bandwidth_and_latency_they_came_from(
    gib_s: float, latency_us: float
) -> None:
    got_gib_s, got_latency_us = interconnect.fit_transfers(lf.timed(gib_s, latency_us))
    assert math.isclose(got_gib_s, gib_s, rel_tol=1e-6)
    assert math.isclose(got_latency_us, latency_us, rel_tol=1e-6)


def test_two_sizes_are_enough_and_the_order_of_the_timings_does_not_matter() -> None:
    samples = lf.timed()
    forward = interconnect.fit_transfers(samples[:2])
    backward = interconnect.fit_transfers(list(reversed(samples[:2])))
    assert forward == pytest.approx(backward)
    assert forward == pytest.approx((lf.TRUE_GIB_S, lf.TRUE_LATENCY_US))


def test_noisy_timings_are_fitted_by_least_squares() -> None:
    samples = [
        (size, seconds * factor)
        for (size, seconds), factor in zip(
            lf.timed(), (1.01, 0.99, 1.02, 0.98), strict=True
        )
    ]
    gib_s, latency_us = interconnect.fit_transfers(samples)
    assert gib_s == pytest.approx(lf.TRUE_GIB_S, rel=0.1)
    assert latency_us > 0


def test_one_payload_size_is_refused_however_often_it_was_timed() -> None:
    with pytest.raises(interconnect.InterconnectError, match="two distinct payload"):
        interconnect.fit_transfers(
            [(1 << 20, 0.01), (1 << 20, 0.011), (1 << 20, 0.012)]
        )


def test_no_timings_are_refused() -> None:
    with pytest.raises(interconnect.InterconnectError, match="two distinct payload"):
        interconnect.fit_transfers([])


def test_a_bigger_payload_that_took_no_longer_is_refused() -> None:
    with pytest.raises(interconnect.InterconnectError, match="bandwidth"):
        interconnect.fit_transfers([(1 << 10, 0.02), (1 << 20, 0.02)])
    with pytest.raises(interconnect.InterconnectError, match="bandwidth"):
        interconnect.fit_transfers([(1 << 10, 0.03), (1 << 20, 0.02)])


def test_timings_that_say_a_transfer_is_free_are_refused_not_clamped() -> None:
    # Exactly proportional to the payload: a line through the origin, no latency.
    samples = [(1 << 20, 1.0), (2 << 20, 2.0), (4 << 20, 4.0)]
    with pytest.raises(interconnect.InterconnectError, match="latency"):
        interconnect.fit_transfers(samples)
    # A line that crosses below the origin.
    with pytest.raises(interconnect.InterconnectError, match="latency"):
        interconnect.fit_transfers([(1 << 20, 0.5), (2 << 20, 2.0)])


@pytest.mark.parametrize(
    "bad",
    [
        (1 << 20, 0.0),
        (1 << 20, -1.0),
        (1 << 20, math.nan),
        (1 << 20, math.inf),
        (-5, 0.01),
    ],
)
def test_a_timing_that_is_not_a_time_or_a_payload_that_is_not_bytes_is_refused(
    bad: tuple[int, float],
) -> None:
    with pytest.raises(interconnect.InterconnectError):
        interconnect.fit_transfers([*lf.timed(), bad])


def test_a_reader_whose_timings_cannot_be_fitted_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lf.own_folders(tmp_path, monkeypatch)
    with pytest.raises(interconnect.InterconnectError):
        interconnect.read_link(
            lf.HOST_A,
            lf.HOST_B,
            lambda a, b: [(1 << 20, 0.01)],
            how="x",
            at="t",
        )
    assert not interconnect.readings_path().exists()
