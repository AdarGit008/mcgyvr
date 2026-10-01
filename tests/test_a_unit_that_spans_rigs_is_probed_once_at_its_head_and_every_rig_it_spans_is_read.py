"""A unit that spans rigs is probed once at its head, and every rig it spans is read.

A spanning unit holds a room slot on every rig it spans, but one process answers
at one address: its head's. So a probe measures it once, at its head, files and
judges it once against the head rig's lock record, and never once per rig. Every
rig it spans is still read through the door when a reader is given, workers
included, because a worker's card and restarts are as much the unit's as the
head's. Given a link reader, each distinct (head, worker) pair of an awake
spanning unit has its link read once and what that recorded is in the report; a
link that cannot be read fails the probe by name.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.fleet import lock, probe
from mcgyvr.serving import interconnect as links_module
from tests import span_fleet as sf

NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)
#: The head answers on 8080, ``small`` on 8082; the figures the lock was given.
RATES = {
    f"http://{sf.A}:8080": (30.0, 400.0),
    f"http://{sf.A}:8082": (60.0, 800.0),
}


class FakeUnits:
    """The two llama.cpp faces on A. Any request to another host fails the test."""

    def __init__(self) -> None:
        self.posts: list[str] = []

    def clock(self) -> float:
        return 1000.0

    def get(self, url: str, timeout: float) -> dict[str, Any]:
        raise AssertionError(f"nothing asks for {url}")

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        base = url.removesuffix("/completion")
        assert base in RATES, f"a probe asked {url}, which is not a head's address"
        self.posts.append(base)
        decode, prefill = RATES[base]
        if payload["n_predict"] == 256:
            return {"timings": {"predicted_per_second": decode}}
        if payload["n_predict"] == 16:
            return {"timings": {"prompt_per_second": prefill}}
        return {"timings": {"predicted_per_second": 1.0}}


def idle(*_: Any) -> int:
    return 0


@pytest.fixture
def journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME holding the ``whole`` fleet, locked and named live."""
    home = tmp_path / "home"
    folder = home / ".mcgyvr" / "fleets" / "whole"
    folder.mkdir(parents=True)
    fleet = sf.fleet()
    fleet["profile"] = "live"
    journal = tmp_path / "journal"
    (folder / "fleet.yaml").write_text(yaml.safe_dump(fleet), encoding="utf-8")
    policy = {"ladder": [sf.BIG, sf.SMALL], "journal": {"dir": str(journal)}}
    (folder / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    lock.write(folder, fleet, sf.evidence(fleet), tolerances=sf.TOLERANCES)
    (home / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": "whole", "since": "2026-09-25T00:00:00Z"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MCGYVR_HOME", raising=False)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    return journal


def run(fake: FakeUnits, **more: Any) -> probe.Report:
    return probe.run(transport=fake, in_flight=idle, clock=fake.clock, now=NOW, **more)


def test_a_spanning_unit_is_measured_once_at_its_head(journal: Path) -> None:
    fake = FakeUnits()
    report = run(fake)
    assert set(report.probed) == {sf.BIG, sf.SMALL}, report
    assert report.failed == {} and report.alerts == [], report
    head = fake.posts.count(f"http://{sf.A}:8080")
    plain = fake.posts.count(f"http://{sf.A}:8082")
    assert head == plain > 0, "the head is measured as often as one plain unit"
    assert report.probed[sf.BIG]["warm_decode_tok_s"] == 30.0


def test_a_spanning_unit_is_filed_once_not_once_per_rig(journal: Path) -> None:
    """Made busy after its probe, the head's figures are filed as contended: once,
    under the head's rig and the head rig's combination, and none under B's."""
    asked: dict[str, int] = {}

    def busy_after(name: str, unit: Mapping[str, Any]) -> int:
        asked[name] = asked.get(name, 0) + 1
        return 1 if name == sf.BIG and asked[name] > 1 else 0

    fake = FakeUnits()
    report = probe.run(transport=fake, in_flight=busy_after, clock=fake.clock, now=NOW)
    assert report.contended == [sf.BIG]
    rows = [
        json.loads(line)
        for path in sorted(journal.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    mine = [row for row in rows if row.get("unit_id") == sf.BIG_ID]
    assert sorted(row["field"] for row in mine) == [
        "prefill_tok_s",
        "warm_decode_tok_s",
    ], mine
    assert {row["rig"] for row in mine} == {sf.A}
    assert {row["rig_id"] for row in mine} == {sf.RIG_A}


def test_every_rig_a_unit_spans_is_read_through_the_door(journal: Path) -> None:
    read: list[tuple[str, tuple[str, ...]]] = []

    def reader(rig: str, run_id: str, units: Sequence[str]) -> int:
        read.append((rig, tuple(units)))
        return 1

    report = run(FakeUnits(), reader=reader)
    assert [rig for rig, _ in read] == [sf.A, sf.B], "the worker's rig is read too"
    assert sf.BIG in report.not_read, "a rig whose read filed nothing says so"


def test_a_probe_of_one_unit_still_reads_the_worker_rigs_it_spans(
    journal: Path,
) -> None:
    read: list[str] = []

    def reader(rig: str, run_id: str, units: Sequence[str]) -> int:
        read.append(rig)
        return 1

    fake = FakeUnits()
    report = run(fake, reader=reader, units=[sf.BIG])
    assert read == [sf.A, sf.B]
    assert set(report.probed) == {sf.BIG} and set(fake.posts) == {f"http://{sf.A}:8080"}


# --- the link of a (head, worker) pair ---------------------------------------


class FakeLink:
    def __init__(self, said: str) -> None:
        self.said = said

    def says(self) -> str:
        return self.said


@pytest.fixture
def interconnect(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str, str]]:
    """A stand-in for :mod:`mcgyvr.serving.interconnect`, so no test here reads a
    link: it records each ``read_link`` call and answers with a fixed sentence."""
    calls: list[tuple[str, str, str, str]] = []

    def read_link(
        host_a: str, host_b: str, reader: Any, *, how: str, at: str
    ) -> FakeLink:
        calls.append((host_a, host_b, how, at))
        return FakeLink(f"{host_a} to {host_b}: a link of the stand-in")

    monkeypatch.setattr(links_module, "read_link", read_link)
    return calls


def never(host_a: str, host_b: str) -> Sequence[tuple[int, float]]:
    raise AssertionError("the stand-in never calls its reader")


def test_each_head_and_worker_pair_has_its_link_read_once(
    journal: Path, interconnect: list[tuple[str, str, str, str]]
) -> None:
    report = run(FakeUnits(), link_reader=never)
    assert [call[:2] for call in interconnect] == [(sf.A, sf.B)]
    assert interconnect[0][3] == "2026-09-25T12:00:00", "read at the probe's moment"
    assert report.links == {
        f"{sf.A} -> {sf.B}": f"{sf.A} to {sf.B}: a link of the stand-in"
    }
    assert report.exit_code == 0


def test_no_link_is_read_without_a_link_reader(
    journal: Path, interconnect: list[tuple[str, str, str, str]]
) -> None:
    report = run(FakeUnits())
    assert interconnect == [] and report.links == {}


def test_a_link_that_cannot_be_read_fails_the_probe_by_name(
    journal: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def read_link(*_: Any, **__: Any) -> Mapping[str, str]:
        raise ValueError("the transfers were too few to fit")

    monkeypatch.setattr(links_module, "read_link", read_link)
    report = run(FakeUnits(), link_reader=never)
    assert report.links == {}
    assert "too few" in report.links_failed[f"{sf.A} -> {sf.B}"]
    assert report.exit_code == 1
