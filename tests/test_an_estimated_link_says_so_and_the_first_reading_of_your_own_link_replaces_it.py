"""An estimated link says it is one, and the first reading of your own replaces it.

Until the user's link has been read, its bandwidth and latency are an estimate
shipped with mcgyvr, and the answer says so, and says where the user can set
their own. The first read of the user's own link keeps what it fitted in the
user's data folder, and from then on that reading answers for the class, in
place of the estimate, naming itself as a reading. A reading of one class
leaves the other class as it was, and nothing is read from a machine: the
timed transfers come from the reader the caller passes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import derived
from mcgyvr.fleet import links
from mcgyvr.serving import interconnect
from tests import link_fixture as lf


@pytest.fixture(autouse=True)
def _own_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lf.own_folders(tmp_path, monkeypatch)


@pytest.mark.parametrize("name", links.LINK_CLASSES)
def test_before_any_reading_a_link_is_the_estimate_and_says_so(name: str) -> None:
    answer = interconnect.link(name)
    assert answer.source == "estimate"
    assert (answer.gib_s, answer.latency_us) == lf.ESTIMATED[name]
    said = answer.says()
    assert "estimate" in said and "shipped with mcgyvr" in said
    assert name in said and "GiB/s" in said and "microseconds" in said
    assert "first reading" in said and "replaces" in said
    assert str(derived.overrides_path()) in said
    assert str(answer.where) in said


def test_the_first_reading_replaces_the_estimate_for_that_class_only() -> None:
    answer = interconnect.read_link(
        lf.HOST_A, lf.HOST_B, lf.reader, how="a fake reader", at="2000-01-01"
    )
    assert answer.link_class == links.NETWORK
    assert answer.source == "reading"
    assert answer.gib_s == pytest.approx(lf.TRUE_GIB_S)
    assert answer.latency_us == pytest.approx(lf.TRUE_LATENCY_US)
    assert answer.where == interconnect.readings_path()
    # From now on the reading answers, with no reader.
    again = interconnect.link(links.NETWORK)
    assert again == answer
    said = again.says()
    assert "your own reading" in said and "estimate" not in said
    assert str(interconnect.readings_path()) in said
    # The other class is untouched.
    assert interconnect.link(links.PCIE).source == "estimate"


def test_the_reading_is_kept_in_the_data_folder_with_how_when_and_between_what(
    tmp_path: Path,
) -> None:
    interconnect.read_link(
        lf.HOST_A, lf.HOST_B, lf.reader, how="a fake reader", at="2000-01-01"
    )
    path = interconnect.readings_path()
    assert path == tmp_path / "data" / "links.json"
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert kept["schema"] == 1
    reading = kept["links"][links.NETWORK]
    assert reading["how"] == "a fake reader" and reading["at"] == "2000-01-01"
    assert reading["between"] == [lf.HOST_A, lf.HOST_B]
    assert reading["gib_s"] == pytest.approx(lf.TRUE_GIB_S)
    assert reading["latency_us"] == pytest.approx(lf.TRUE_LATENCY_US)


def test_two_cards_on_one_host_are_read_as_a_bus_link_and_both_readings_are_kept() -> (
    None
):
    interconnect.read_link(lf.HOST_A, lf.HOST_A, lf.reader, how="x", at="t1")
    interconnect.read_link(lf.HOST_A, lf.HOST_B, lf.reader, how="x", at="t2")
    kept = json.loads(interconnect.readings_path().read_text(encoding="utf-8"))
    assert set(kept["links"]) == set(links.LINK_CLASSES)
    assert interconnect.link(links.PCIE).source == "reading"
    assert interconnect.link(links.NETWORK).source == "reading"


def test_a_later_reading_of_a_class_replaces_the_earlier_one() -> None:
    interconnect.read_link(lf.HOST_A, lf.HOST_B, lf.reader, how="x", at="t1")

    def faster(a: str, b: str) -> list[tuple[int, float]]:
        return lf.timed(gib_s=lf.TRUE_GIB_S * 2, latency_us=lf.TRUE_LATENCY_US / 2)

    answer = interconnect.read_link(lf.HOST_A, lf.HOST_B, faster, how="y", at="t2")
    assert answer.gib_s == pytest.approx(lf.TRUE_GIB_S * 2)
    assert answer.latency_us == pytest.approx(lf.TRUE_LATENCY_US / 2)


def test_the_readings_file_is_written_whole_and_leaves_no_temporary_file(
    tmp_path: Path,
) -> None:
    interconnect.record_reading(
        links.PCIE,
        gib_s=9.0,
        latency_us=7.0,
        how="by hand",
        at="t",
        between=(lf.HOST_A, lf.HOST_A),
    )
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == ["links.json"]


def test_a_reading_that_is_not_a_link_is_refused_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    with pytest.raises(interconnect.InterconnectError, match="gib_s"):
        interconnect.record_reading(
            links.PCIE,
            gib_s=0.0,
            latency_us=7.0,
            how="by hand",
            at="t",
            between=(lf.HOST_A, lf.HOST_A),
        )
    assert not (tmp_path / "data").exists()


def test_a_class_nobody_has_is_refused_by_name() -> None:
    with pytest.raises(interconnect.InterconnectError, match=lf.HOST_A):
        interconnect.link(lf.HOST_A)
