"""The probe times a link through the door and keeps it as your reading.

Promise: when ``mcgyvr fleet probe`` finds an awake unit split across cards or
rigs, it times the links that unit crosses -- at most one between two cards of
a rig and one between two rigs, since a reading is kept for its link's class --
and keeps what the timing fits as the user's own reading in the data folder,
where it replaces the shipped estimate and a stated setting still outranks it.
Every timing is a link run through the door: two cards of one rig are one run
on that rig; two rigs are a sink started on the worker, at the address the head
reaches it at, and a sender run on the head. A timing that fails, or answers
anything but a list of transfers, is refused naming the link.

The door here is a fake that answers as the timer would; no rig is reached.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mcgyvr.fleet import probe
from mcgyvr.fleet.linkread import (
    LinkEnds,
    LinkReadError,
    Ran,
    door_timer,
    time_link,
    worker_address,
)
from mcgyvr.fleet.spans import Shard, Span
from mcgyvr.serving import interconnect, linktime
from tests import link_fixture as lf

A = "box-a.example"
B = "box-b.example"
ADDR_B = "192.0.2.20"


def answer(transfers: Sequence[tuple[int, float]]) -> Ran:
    return Ran(0, json.dumps({"transfers": [list(t) for t in transfers]}) + "\n", "")


@dataclass
class FakeDoor:
    """Answers each link run as the timer would; records what was asked, in order."""

    peer: Ran = field(default_factory=lambda: answer(lf.timed()))
    send: Ran = field(default_factory=lambda: answer(lf.timed(0.1, 200.0)))
    sink: Ran = field(default_factory=lambda: Ran(0, '{"received": 1}\n', ""))
    asked: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)

    def _answer(self, host: str, args: Sequence[str]) -> Ran:
        return {"--peer": self.peer, "--send": self.send, "--sink": self.sink}[args[0]]

    def run(self, host: str, args: Sequence[str]) -> Ran:
        self.asked.append(("run", host, tuple(args)))
        return self._answer(host, args)

    def start(self, host: str, args: Sequence[str]) -> FakePending:
        self.asked.append(("start", host, tuple(args)))
        return FakePending(self, self._answer(host, args), host)


@dataclass
class FakePending:
    door: FakeDoor
    ran: Ran
    host: str

    def wait(self) -> Ran:
        self.door.asked.append(("wait", self.host, ()))
        return self.ran


PCIE_ENDS = LinkEnds(A, 0, A, 1)
NETWORK_ENDS = LinkEnds(A, 0, B, 0, ADDR_B)


# One timing.


def test_two_cards_of_one_rig_are_one_peer_run_on_that_rig() -> None:
    door = FakeDoor()
    transfers = time_link(door, PCIE_ENDS)
    assert door.asked == [("run", A, ("--peer", "0", "1"))]
    assert transfers == [tuple(t) for t in lf.timed()]


def test_two_rigs_are_a_sink_on_the_worker_then_a_send_from_the_head() -> None:
    door = FakeDoor()
    transfers = time_link(door, NETWORK_ENDS)
    port = str(linktime.LINK_PORT)
    assert door.asked == [
        ("start", B, ("--sink", ADDR_B, port)),
        ("run", A, ("--send", ADDR_B, port)),
        ("wait", B, ()),
    ]
    assert transfers == [tuple(t) for t in lf.timed(0.1, 200.0)]


def test_a_worker_with_no_address_is_refused_before_anything_runs() -> None:
    door = FakeDoor()
    with pytest.raises(LinkReadError, match=rf"{B}.*bind"):
        time_link(door, LinkEnds(A, 0, B, 0, None))
    assert door.asked == []


def test_what_the_timer_could_not_do_is_said_with_the_link() -> None:
    door = FakeDoor(peer=Ran(1, '{"error": "card 1 has 40 MiB free"}\n', ""))
    with pytest.raises(LinkReadError, match=r"box-a\.example card 0 -> card 1.*40 MiB"):
        time_link(door, PCIE_ENDS)


def test_a_sink_that_failed_fails_the_timing() -> None:
    door = FakeDoor(sink=Ran(1, '{"error": "cannot listen"}\n', ""))
    with pytest.raises(LinkReadError, match=r"sink on box-b\.example.*cannot listen"):
        time_link(door, NETWORK_ENDS)


@pytest.mark.parametrize(
    "stdout",
    ["", "not json\n", '{"transfers": []}\n', '{"transfers": [[1, "x"]]}\n'],
)
def test_an_answer_that_is_no_list_of_transfers_is_refused(stdout: str) -> None:
    with pytest.raises(LinkReadError, match="link"):
        time_link(FakeDoor(peer=Ran(0, stdout, "")), PCIE_ENDS)


def test_a_worker_is_reached_at_its_bind_or_at_its_rig_when_that_is_an_address() -> (
    None
):
    assert worker_address(B, ADDR_B) == ADDR_B
    assert worker_address(ADDR_B, None) == ADDR_B
    assert worker_address(B, None) is None


# What is kept.


def test_the_timing_is_kept_as_your_reading_and_replaces_the_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lf.own_folders(tmp_path, monkeypatch)
    timer = door_timer(FakeDoor())
    link = interconnect.read_link(
        A, A, lambda _a, _b: timer(PCIE_ENDS), how="mcgyvr fleet probe", at="now"
    )
    assert link.source == interconnect.READING
    assert link.gib_s == pytest.approx(lf.TRUE_GIB_S)
    kept = json.loads(interconnect.readings_path().read_text(encoding="utf-8"))
    assert interconnect.readings_path().is_relative_to(tmp_path / "data")
    assert kept["links"]["pcie"]["between"] == [A, A]


def test_your_stated_setting_still_outranks_the_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lf.own_folders(tmp_path, monkeypatch)
    lf.set_by_user(tmp_path, {"link_gib_s": {"pcie": 7.5}})
    timer = door_timer(FakeDoor())
    link = interconnect.read_link(
        A, A, lambda _a, _b: timer(PCIE_ENDS), how="mcgyvr fleet probe", at="now"
    )
    assert link.gib_s == 7.5
    assert link.gib_s_source == interconnect.OVERRIDE


# Which links a probe times.


def span(unit: str, *cards: tuple[str, int, str | None]) -> Span:
    shards = tuple(Shard(rig, gpu, None, bind) for rig, gpu, bind in cards)
    return Span(unit=unit, head=cards[0][0], shards=shards)


def test_a_probe_times_one_link_of_each_class_however_many_units_are_split() -> None:
    spanning = {
        "wide": span("wide", (A, 0, None), (A, 1, None), (B, 0, ADDR_B)),
        "pair": span("pair", (B, 0, None), (B, 1, None)),
    }
    measured = [(A, "wide"), (B, "pair")]
    ends = probe.link_ends(spanning, measured)
    assert ends == [
        NETWORK_ENDS,
        LinkEnds(A, 0, A, 1),
    ]


def test_a_unit_that_is_not_awake_is_not_timed() -> None:
    spanning = {"wide": span("wide", (A, 0, None), (B, 0, ADDR_B))}
    assert probe.link_ends(spanning, []) == []


def test_a_unit_on_one_card_crosses_no_link() -> None:
    spanning = {"pinned": span("pinned", (A, 1, None))}
    assert probe.link_ends(spanning, [(A, "pinned")]) == []
