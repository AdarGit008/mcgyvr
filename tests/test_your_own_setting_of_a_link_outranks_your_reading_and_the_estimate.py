"""Your own setting of a link outranks your own reading and the shipped estimate.

The user's word in ``numbers.yaml`` always answers first, over a reading of
their link and over the estimate. The two numbers of a link are layered one at
a time: a user who sets only one of them has that one, and the other comes from
the next layer down, and the answer names each layer rather than calling the
whole a setting. A reading taken while a setting stands is still kept, for the
day the setting goes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import derived
from mcgyvr.fleet import links
from mcgyvr.serving import interconnect
from tests import link_fixture as lf


@pytest.fixture(autouse=True)
def _own_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lf.own_folders(tmp_path, monkeypatch)


def _both(gib_s: float, latency_us: float) -> dict[str, dict[str, float]]:
    return {
        derived.LINK_GIB_S: {links.NETWORK: gib_s},
        derived.LINK_LATENCY_US: {links.NETWORK: latency_us},
    }


def test_a_setting_of_both_numbers_outranks_the_estimate(tmp_path: Path) -> None:
    where = lf.set_by_user(tmp_path, _both(7.5, 33.0))
    answer = interconnect.link(links.NETWORK)
    assert (answer.gib_s, answer.latency_us) == (7.5, 33.0)
    assert answer.source == "override" and answer.where == where
    assert "your own setting" in answer.says() and "estimate" not in answer.says()


def test_a_setting_of_both_numbers_outranks_a_reading_taken_before_and_after(
    tmp_path: Path,
) -> None:
    interconnect.read_link(lf.HOST_A, lf.HOST_B, lf.reader, how="x", at="t1")
    lf.set_by_user(tmp_path, _both(7.5, 33.0))
    assert interconnect.link(links.NETWORK).source == "override"
    # A new read while the setting stands answers with the setting...
    answer = interconnect.read_link(
        lf.HOST_A,
        lf.HOST_B,
        lambda a, b: lf.timed(gib_s=1.5, latency_us=90.0),
        how="y",
        at="t2",
    )
    assert (answer.gib_s, answer.latency_us, answer.source) == (7.5, 33.0, "override")
    # ...and is kept: with the setting gone the reading answers.
    (tmp_path / "config" / derived.OVERRIDES_FILENAME).unlink()
    gone = interconnect.link(links.NETWORK)
    assert gone.source == "reading"
    assert gone.gib_s == pytest.approx(1.5)
    assert gone.latency_us == pytest.approx(90.0)


def test_a_setting_of_one_number_takes_the_other_from_the_reading(
    tmp_path: Path,
) -> None:
    interconnect.read_link(lf.HOST_A, lf.HOST_B, lf.reader, how="x", at="t1")
    lf.set_by_user(tmp_path, {derived.LINK_GIB_S: {links.NETWORK: 7.5}})
    answer = interconnect.link(links.NETWORK)
    assert answer.gib_s == 7.5
    assert answer.latency_us == pytest.approx(lf.TRUE_LATENCY_US)
    assert answer.source == "reading"
    said = answer.says()
    assert "your own setting" in said and "your own reading" in said
    assert "estimate" not in said


def test_a_setting_of_one_number_takes_the_other_from_the_estimate_and_says_so(
    tmp_path: Path,
) -> None:
    lf.set_by_user(tmp_path, {derived.LINK_LATENCY_US: {links.PCIE: 12.0}})
    answer = interconnect.link(links.PCIE)
    assert answer.latency_us == 12.0
    assert answer.gib_s == lf.ESTIMATED[links.PCIE][0]
    assert answer.source == "estimate"
    said = answer.says()
    assert "your own setting" in said
    assert "an estimate shipped with mcgyvr" in said
    assert "first reading" in said


def test_a_setting_for_one_class_leaves_the_other_class_alone(tmp_path: Path) -> None:
    lf.set_by_user(tmp_path, _both(7.5, 33.0))
    other = interconnect.link(links.PCIE)
    assert other.source == "estimate"
    assert (other.gib_s, other.latency_us) == lf.ESTIMATED[links.PCIE]


def test_a_setting_keyed_by_a_host_name_is_refused(tmp_path: Path) -> None:
    lf.set_by_user(tmp_path, {derived.LINK_GIB_S: {lf.HOST_A: 7.5}})
    with pytest.raises(derived.DerivedNumbersError, match=lf.HOST_A):
        interconnect.link(links.NETWORK)
