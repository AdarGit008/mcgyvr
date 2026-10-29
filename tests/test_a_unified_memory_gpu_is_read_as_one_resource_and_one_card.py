"""A unified-memory GPU is read as one resource and one card.

On a machine whose GPU shares the machine's memory (Apple silicon), the reader
lists that GPU once: one ``unified`` resource, and one card mirroring it so
that everything that places a model on "the roomiest card" finds it. Its size
is the memory the GPU may take, read from the kernel's cap when one is set and
otherwise three quarters of the memory, and it is labelled an estimate either
way. Its free memory is what the machine has available, held to that size. The
machine keeps its memory section, the rig id does not move when the cap does,
and a display data that lacks the core count is an unread field, not a crash.
A Mac that is not Apple silicon has no such GPU and says so.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import (
    HostShape,
    host_detection,
    host_reading,
    host_scan,
    host_shape,
    host_shapes,
)
from tests.machinereader import run, stage_host

UNIFIED = [m for m in host_shapes() if m.chip is not None]


def _unified(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in document["resources"] if r["kind"] == "unified"]


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_the_gpu_is_one_unified_resource_and_one_card(machine: HostShape) -> None:
    document = host_reading(machine)
    (resource,) = _unified(document)
    (card,) = document["cards"]
    assert machine.unified_mib is not None
    assert resource["total_mb"] == card["total_mib"] == machine.unified_mib
    assert resource["free_mb"] == card["free_mib"]
    assert card["free_mib"] == min(machine.unified_mib, machine.available_mib)
    assert resource["figure"] == card["figure"] == "estimate"
    assert "shared_with_ram" not in card and "shared_with_ram" not in resource
    assert resource["backend"] == card["backend"] == "metal"
    assert card["kind"] == "unified"
    assert card["name"] == f"{machine.chip} GPU"
    assert document["unsized"] == []
    assert document["memory"]["available_gb"] is not None
    assert document["host"] == {
        "os": "darwin",
        "arch": "arm64",
        "version": machine.version,
    }


def test_a_cap_the_kernel_is_told_is_the_gpus_size() -> None:
    capped = host_shape("unified-desktop-capped")
    (card,) = host_reading(capped)["cards"]
    assert card["total_mib"] == capped.wired_limit_mib
    assert "iogpu.wired_limit_mb" in card["how"]
    laptop = host_shape("unified-laptop")
    (card,) = host_reading(laptop)["cards"]
    assert card["total_mib"] == int(laptop.memory_mib * 0.75)
    assert "estimate" in card["how"]


def test_a_display_data_without_cores_is_an_unread_field_not_a_crash() -> None:
    capped = host_shape("unified-desktop-capped")
    assert capped.gpu_cores is None
    document = host_reading(capped)
    unread = {u["field"]: u["why"] for u in document["unread"]}
    assert "sppci_cores" in unread["card.apple.0.cores"]
    assert document["cards"][0]["gpu_cores"] is None
    laptop = host_reading(host_shape("unified-laptop"))
    assert laptop["cards"][0]["gpu_cores"] == host_shape("unified-laptop").gpu_cores


def test_the_rig_id_holds_when_the_cap_moves() -> None:
    from mcgyvr.fleet import ids

    laptop = host_shape("unified-laptop")
    capped = dataclasses.replace(laptop, wired_limit_mib=20000)
    before, after = host_reading(laptop), host_reading(capped)
    assert before["cards"][0]["total_mib"] != after["cards"][0]["total_mib"]
    assert ids.rig_id(before) == ids.rig_id(after)
    renamed = dataclasses.replace(laptop, chip="Example Chip U9")
    assert ids.rig_id(host_reading(renamed)) != ids.rig_id(before)


def test_a_mac_that_is_not_apple_silicon_has_no_unified_gpu() -> None:
    machine = host_shape("mac-without-unified")
    document = host_reading(machine)
    assert document["cards"] == [] and _unified(document) == []
    assert [r["kind"] for r in document["resources"]] == ["ram", "cpu"]
    assert document["host"]["os"] == "darwin"
    assert any("not Apple silicon" in note for note in host_scan(machine).notes)


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_detection_and_the_scan_carry_the_unified_gpu(machine: HostShape) -> None:
    from mcgyvr.scan import Scan

    assert machine.unified_mib is not None
    found = host_detection(machine)
    (gpu,) = found.gpus
    assert gpu.unified and gpu.vram_gb == round(machine.unified_mib / 1024, 1)
    assert found.host is not None and found.host.os == "darwin"
    assert found.provenance["ram_gb"].startswith("sysctl hw.memsize")

    measured = host_scan(machine)
    (card,) = measured.gpus
    assert (card.kind, card.backend, card.figure) == ("unified", "metal", "estimate")
    assert card.vram.total_mib == machine.unified_mib
    assert measured.gpus_determined
    assert measured.memory is not None and measured.memory.available_gb is not None
    assert measured.cpu is not None
    assert measured.cpu.performance_cores == machine.performance_cores
    assert Scan.from_json(measured.to_json()) == measured


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_placement_takes_the_unified_gpu_as_the_roomiest_card(
    machine: HostShape,
) -> None:
    from mcgyvr.serving import _free_vram_bytes, _roomiest_gpu

    measured = host_scan(machine)
    assert _roomiest_gpu(measured).kind == "unified"
    assert _free_vram_bytes(measured) == measured.gpus[0].vram.free_mib << 20


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_the_rig_reports_the_unified_gpu_and_lends_it_only_with_native_launch(
    machine: HostShape,
) -> None:
    from mcgyvr.rig import hardware, sharing

    document = host_reading(machine)
    report = hardware.read(reader=lambda: document)
    assert report.kinds == ("unified",)
    assert report.sources == (("apple", 0),)
    assert [r["kind"] for r in report.resources] == ["unified", "ram", "cpu"]
    assert report.host is not None and report.host.arch == "arm64"
    # A lent card is served by a CUDA worker in a container, which a unified GPU
    # cannot be; it is lent once units launch natively.
    assert sharing.Sharing(enabled=True).lends(0, report) is None
    assert ("apple", "unified") not in sharing.LENT_KINDS


def test_a_memory_total_without_available_memory_keeps_the_memory_section() -> None:
    from mcgyvr.scan import Scan

    scan = Scan.from_json(
        json.dumps({"machine": {}, "memory": {"total_gb": 16.0, "available_gb": None}})
    )
    assert scan.memory is not None
    assert (scan.memory.total_gb, scan.memory.available_gb) == (16.0, None)


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_the_shipped_reader_reads_the_same_unified_gpu(
    machine: HostShape, tmp_path: Path
) -> None:
    ran = run(stage_host(machine), tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert not ran.unexpected and not ran.elevated
    assert json.loads(ran.stdout) == host_reading(machine)
