"""A hello carries exactly what the rig lends, and the cards those resources make.

A rig that lends advertises its lent resources in the hub's contract
(:class:`mcgyvr.hubwire.Resource`): each lent card whole, host memory up to
the MiB the owner lends, and the cores the owner lends; nothing it does not
lend, nothing under its kind's lending floor, and nothing at all while it
offers no session role. Its legacy ``cards[]`` are exactly
:func:`mcgyvr.hubwire.cards_from_resources` of those, never every card the
machine has, so a card read as 0 MiB, which is no resource, is never on the
wire. Beside what it lends, the hello names the host it runs on
(:class:`mcgyvr.hubwire.Host`); a rig that lends nothing names none. A
card's bandwidth the reader did not read is its class's estimate
(:func:`mcgyvr.estimate.match`) and says so; a reading wins. A heartbeat
re-reads what the hello named, card readings again made from them
(:func:`mcgyvr.hubwire.card_readings_from`). Both frames, and the old shape a
rig that lends nothing sends, hold to the hub's published schema. A change in
what the rig lends is said in a new hello at once, since a hub re-reads only
what the hello named.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import estimate, hubwire
from tests import rig_schema
from tests.machine_shapes import Card, HostShape, host_reading, host_shape

#: An invented card the bandwidth table may name, and its invented class.
SIZED = "Example Card Q"
CLASS = estimate.HardwareClass(
    id="example-q",
    vendor="vendor-a",
    name=SIZED,
    bandwidth_gbps=448.0,
    verified=True,
    url="https://example.invalid/card-q",
)


def _linux(*cards: Card, **changed: Any) -> HostShape:
    fields: dict[str, Any] = {
        "label": "linux-lender",
        "system": "linux",
        "machine_id": "0123456789abcdef0123456789abcdf2",
        "memory_mib": 64 * 1024,
        "available_mib": 40000,
        "cpu_model": "Example CPU L12",
        "cores": 6,
        "threads": 12,
        "version": "6.1-example",
        "cards": cards,
    }
    return HostShape(**{**fields, **changed})


#: A card read as 0 MiB, beside a sized one: the 0-MiB one keeps its number.
ZERO = Card(index=0, name="Example Card Z", vendor="vendor-a", total_mib=0)
SIZED_CARD = Card(index=1, name=SIZED, vendor="vendor-a", total_mib=12288)


@pytest.fixture(autouse=True)
def _classes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(estimate, "shipped_classes", lambda: (CLASS,))


def _report(machine: HostShape) -> Any:
    import platform
    from unittest import mock

    from mcgyvr.rig import hardware

    # A Linux reading takes the kernel release and the machine name from the
    # interpreter: here they are the invented machine's, not the suite host's.
    with (
        mock.patch.object(platform, "release", lambda: machine.version),
        mock.patch.object(platform, "machine", lambda: "x86_64"),
    ):
        reading = host_reading(machine)
    return hardware.read(reader=lambda: reading)


def _share(models: Path | None, **changed: Any) -> Any:
    from mcgyvr.rig import sharing

    fields: dict[str, Any] = {
        "enabled": True,
        "roles": ("head", "worker"),
        "image": "engine:rpc",
        "models_dir": str(models) if models else None,
    }
    return sharing.Sharing(**{**fields, **changed})


def _hello(report: Any) -> dict[str, Any]:
    from mcgyvr.rig import hardware

    frame = json.loads(hardware.hello_frame(report, "h1", agent_version="1.0"))
    schema = rig_schema.load()
    rig_schema.validate(frame, schema, "#/$defs/AgentMessage")
    body: dict[str, Any] = frame["body"]
    return body


def _beat(report: Any) -> dict[str, Any]:
    from mcgyvr.rig import hardware

    frame = json.loads(hardware.heartbeat_frame(report, "b1"))
    rig_schema.validate(frame, rig_schema.load(), "#/$defs/AgentMessage")
    body: dict[str, Any] = frame["body"]
    return body


def _wire(resources: list[dict[str, Any]]) -> list[hubwire.Resource]:
    return [hubwire.Resource(**resource) for resource in resources]


def test_the_hello_carries_the_lent_resources_and_the_cards_they_make(
    tmp_path: Path,
) -> None:
    machine = _linux(ZERO, SIZED_CARD)
    report = _report(machine)
    assert [card.vram_total_mb for card in report.cards] == [0, 12288]
    share = _share(tmp_path, ram_mb=8192, cpu_cores=4)
    body = _hello(share.lendable(report))
    lent = _wire(body["resources"])
    assert [(r.kind, r.index) for r in lent] == [
        (hubwire.RESOURCE_GPU, 1),
        (hubwire.RESOURCE_RAM, 0),
        (hubwire.RESOURCE_CPU, 0),
    ]
    gpu, ram, cpu = lent
    assert (gpu.name, gpu.total_mb, gpu.backend) == (SIZED, 12288, "cuda")
    assert (ram.total_mb, ram.free_mb) == (8192, 8192)
    assert (cpu.cores, cpu.total_mb) == (4, 0)
    assert all(hubwire.counts_as_lent(r) for r in lent)
    # cards[] is exactly what the lent resources make: the 0-MiB card is not
    # one, and nothing the rig does not lend is on the wire.
    assert body["cards"] == hubwire.cards_from_resources(lent)
    assert [card["index"] for card in body["cards"]] == [1]
    assert body["host"]["os"] == "linux"
    assert body["host"] == {"os": "linux", "arch": "x86_64", "version": "6.1-example"}
    assert body["ram_total_mb"] == report.ram_total_mb


def test_a_cards_bandwidth_is_its_class_estimate_and_a_reading_wins(
    tmp_path: Path,
) -> None:
    report = _report(_linux(SIZED_CARD))
    (gpu,) = [r for r in report.resources if r["kind"] == hubwire.RESOURCE_GPU]
    assert gpu["bandwidth_gbps"] == CLASS.bandwidth_gbps
    assert gpu["bandwidth_figure"] == hubwire.FIGURE_ESTIMATE
    read = dataclasses.replace(
        report,
        resources=tuple(
            {**r, "bandwidth_gbps": 300.0, "bandwidth_figure": hubwire.FIGURE_READING}
            if r["kind"] == hubwire.RESOURCE_GPU
            else r
            for r in report.resources
        ),
    )
    (lent,) = _wire(_hello(_share(tmp_path).lendable(read))["resources"])
    assert (lent.bandwidth_gbps, lent.bandwidth_figure) == (
        300.0,
        hubwire.FIGURE_READING,
    )
    # A device no class names has no bandwidth, and so no bandwidth figure.
    other = _report(_linux(dataclasses.replace(SIZED_CARD, name="Example Card N")))
    (unnamed,) = [r for r in other.resources if r["kind"] == hubwire.RESOURCE_GPU]
    assert (unnamed["bandwidth_gbps"], unnamed["bandwidth_figure"]) == (None, None)


def test_a_rig_that_lends_nothing_sends_no_resources_and_no_cards() -> None:
    report = _report(_linux(SIZED_CARD))
    for share in (_share(None, enabled=False), _share(None, image=None)):
        body = _hello(share.lendable(report))
        assert body["cards"] == [] and "resources" not in body
        # The host (its version is the machine's patch level) goes only beside
        # what the rig lends.
        assert "host" not in body
        beat = _beat(share.lendable(report))
        assert beat["cards"] == [] and "resources" not in beat


def test_only_what_reaches_its_floor_is_advertised(tmp_path: Path) -> None:
    from mcgyvr.rig import sharing

    small = Card(index=0, name="Example Card S", vendor="vendor-a", total_mib=1024)
    report = _report(_linux(small, SIZED_CARD))
    share = _share(tmp_path, ram_mb=8192, cpu_cores=4)
    lent = _wire(_hello(share.lendable(report))["resources"])
    assert [(r.kind, r.index) for r in lent if r.kind in hubwire.CARD_KINDS] == [
        (hubwire.RESOURCE_GPU, 1)
    ]
    # Memory lent past what the machine has is held to what it has less the
    # owner's headroom; cores past the logical count to all but those kept.
    greedy = _share(tmp_path, ram_mb=10**6, cpu_cores=999)
    lent = _wire(_hello(greedy.lendable(report))["resources"])
    ram = next(r for r in lent if r.kind == hubwire.RESOURCE_RAM)
    cpu = next(r for r in lent if r.kind == hubwire.RESOURCE_CPU)
    assert ram.total_mb == report.ram_total_mb - sharing.RAM_HEADROOM_MB
    assert cpu.cores == 12 - sharing.CORES_KEPT


def test_memory_and_cores_are_lent_only_beside_the_head_role(tmp_path: Path) -> None:
    report = _report(_linux(SIZED_CARD))
    worker = _share(None, ram_mb=8192, cpu_cores=4)
    lent = _wire(_hello(worker.lendable(report))["resources"])
    assert [r.kind for r in lent] == [hubwire.RESOURCE_GPU]


def test_a_lender_of_no_card_advertises_memory_and_cores(tmp_path: Path) -> None:
    report = _report(_linux(SIZED_CARD))
    share = _share(tmp_path, cards=(), ram_mb=8192, cpu_cores=4)
    body = _hello(share.lendable(report))
    assert [r["kind"] for r in body["resources"]] == [
        hubwire.RESOURCE_RAM,
        hubwire.RESOURCE_CPU,
    ]
    assert body["cards"] == []


def test_a_heartbeat_reads_again_what_the_hello_named(tmp_path: Path) -> None:
    report = _report(_linux(ZERO, SIZED_CARD))
    told = _share(tmp_path, ram_mb=8192, cpu_cores=4).lendable(report)
    beat = _beat(told)
    readings = [hubwire.ResourceReading(**r) for r in beat["resources"]]
    assert [(r.kind, r.index) for r in readings] == [
        (hubwire.RESOURCE_GPU, 1),
        (hubwire.RESOURCE_RAM, 0),
    ]
    assert beat["cards"] == hubwire.card_readings_from(readings)
    named = {(r["kind"], r["index"]) for r in _hello(told)["resources"]}
    assert {(r.kind, r.index) for r in readings} <= named


def test_the_hello_builder_refuses_cards_the_resources_do_not_make() -> None:
    from mcgyvr.rig import protocol

    gpu = hubwire.Resource(
        kind=hubwire.RESOURCE_GPU,
        index=0,
        name="Example Card A",
        total_mb=8192,
        figure=hubwire.FIGURE_READING,
        backend="cuda",
    )
    every = (
        protocol.CardReport(
            index=0, name="Example Card A", vram_total_mb=8192, vram_free_mb=8192
        ),
        protocol.CardReport(
            index=1, name="Example Card B", vram_total_mb=8192, vram_free_mb=8192
        ),
    )
    with pytest.raises(ValueError, match=r"^cards: "):
        protocol.hello(
            "h",
            machine_id="m",
            agent_version="1",
            ram_total_mb=1,
            ram_free_mb=None,
            cards=every,
            resources=(gpu,),
        )
    made = protocol.hello(
        "h",
        machine_id="m",
        agent_version="1",
        ram_total_mb=1,
        ram_free_mb=None,
        cards=every[:1],
        resources=(gpu,),
    )
    assert json.loads(made)["body"]["resources"][0]["kind"] == hubwire.RESOURCE_GPU


def test_a_mac_lends_its_unified_gpu_whole_once_its_sessions_run_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import sharing

    machine = host_shape("unified-laptop")
    report = _report(machine)
    share = _share(tmp_path, ram_mb=0)
    # Until a session host runs here (macOS, Windows), no role is offered, so
    # nothing is advertised as lent.
    assert share.session_roles(report) == ()
    assert "resources" not in _hello(share.lendable(report))
    monkeypatch.setattr(
        sharing, "SESSION_SYSTEMS", sharing.SESSION_SYSTEMS | {"darwin"}
    )
    body = _hello(share.lendable(report))
    (unified,) = _wire(body["resources"])
    assert unified.kind == hubwire.RESOURCE_UNIFIED and unified.backend == "metal"
    assert unified.figure == hubwire.FIGURE_ESTIMATE
    assert unified.total_mb == machine.unified_mib
    assert body["cards"] == hubwire.cards_from_resources([unified])
    assert body["host"] == {"os": "darwin", "arch": "arm64", "version": "0.1-example"}


def test_a_change_in_what_the_rig_lends_is_said_in_a_new_hello_at_once() -> None:
    from tests.rigagents import Clock, Hub, Report, _agent

    class Taken(Report):
        """Lends its card for two reads, then the owner takes it back."""

        def __call__(self) -> Any:
            made = super().__call__()
            return made if self.reads <= 2 else dataclasses.replace(made, lent=())

    clock = Clock()
    said: list[str] = []
    first, second = Hub(interval=15, beats=5), Hub(interval=15, beats=1)
    agent, channels = _agent([first, second], clock, report=Taken(), said=said)
    agent.run()
    sent = [[m["type"] for _, m in channel.sent] for channel in channels]
    assert sent[0] == ["hello", "heartbeat"]
    assert sent[1][0] == "hello"
    hello = next(m for _, m in channels[1].sent if m["type"] == "hello")
    assert hello["body"]["cards"] == [] and "resources" not in hello["body"]
    assert any("what this rig lends changed" in line for line in said)
    # No backoff before the second hello: the one wait said is the second
    # hub's drop at its end.
    assert sum("trying again" in line for line in said) == 1
