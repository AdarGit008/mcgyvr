"""Every reading states its host and its resources in the wire's names.

The hub hears a rig's resources and host in the names the resource contract
fixes: a resource has exactly the contract's fields, its kind, backend and
figure are of the contract's values, and a GPU resource is numbered as the
hardware report numbers its cards. Host RAM and the CPU are resources on every
system; a card is one only when it is sized. The host says its system, arch and
version on every system.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from tests.machine_shapes import HostShape, host_reading, host_shapes
from tests.machinereader import Staged, run

# until align/hubwire merges: the contract's names as the plan fixes them, read
# from the wire once it carries them.
RESOURCE_KINDS = getattr(hubwire, "RESOURCE_KINDS", ("gpu", "unified", "ram", "cpu"))
RESOURCE_BACKENDS = getattr(
    hubwire, "RESOURCE_BACKENDS", ("cuda", "metal", "vulkan", "rocm", "cpu")
)
FIGURE_KINDS = getattr(hubwire, "FIGURE_KINDS", ("estimate", "reading"))
HOST_OS = getattr(hubwire, "HOST_OS", ("linux", "darwin", "windows"))
HOST_ARCH = getattr(hubwire, "HOST_ARCH", ("x86_64", "arm64"))

RESOURCE = getattr(hubwire, "Resource", None)
RESOURCE_FIELDS = (
    {field.name for field in dataclasses.fields(RESOURCE)}
    if RESOURCE is not None
    else {
        "kind",
        "index",
        "name",
        "total_mb",
        "free_mb",
        "cores",
        "bandwidth_gbps",
        "bandwidth_figure",
        "figure",
        "backend",
    }
)


def _takes(resource: dict[str, Any]) -> None:
    """The wire takes the resource: its own record validates it, once it has one."""
    if RESOURCE is not None:
        RESOURCE(**resource).validate()


def test_the_reader_names_the_wires_systems() -> None:
    from mcgyvr.serving import rigscan

    assert tuple(rigscan.SYSTEMS) == tuple(HOST_OS)
    assert set(rigscan.ARCHES.values()) | set(rigscan.WINDOWS_ARCHES.values()) <= set(
        HOST_ARCH
    )


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_every_resource_has_the_contracts_fields_and_values(
    machine: HostShape,
) -> None:
    document = host_reading(machine)
    assert document["host"]["os"] == machine.system
    assert document["host"]["os"] in HOST_OS
    for resource in document["resources"]:
        assert set(resource) == RESOURCE_FIELDS
        _takes(resource)
        assert resource["kind"] in RESOURCE_KINDS
        assert resource["backend"] in RESOURCE_BACKENDS
        assert resource["figure"] in FIGURE_KINDS
        assert isinstance(resource["total_mb"], int) and resource["total_mb"] >= 0
        assert resource["bandwidth_gbps"] is None
        assert resource["bandwidth_figure"] is None
        assert (resource["cores"] is not None) == (resource["kind"] == "cpu")
    kinds = [r["kind"] for r in document["resources"]]
    assert kinds.count("ram") == 1 and kinds.count("cpu") == 1
    (ram,) = [r for r in document["resources"] if r["kind"] == "ram"]
    assert (ram["total_mb"], ram["free_mb"]) == (
        machine.memory_mib
        if machine.memory_modules
        else machine.memory_mib - 2,  # what the system sees, in MiB
        machine.available_mib,
    )
    (cpu,) = [r for r in document["resources"] if r["kind"] == "cpu"]
    assert cpu["cores"] == machine.threads and cpu["name"] == machine.cpu_model


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_a_card_resource_is_numbered_as_the_report_numbers_its_card(
    machine: HostShape,
) -> None:
    from mcgyvr.fleet import ids
    from mcgyvr.rig import hardware

    document = host_reading(machine)
    try:
        ids.rig_id(document)
    except ValueError:
        return
    report = hardware.read(reader=lambda: document)
    cards = [r for r in report.resources if r["kind"] in ("gpu", "unified")]
    assert [(r["index"], r["name"], r["total_mb"]) for r in cards] == [
        (c.index, c.name, c.vram_total_mb) for c in report.cards
    ]
    assert report.host is not None and report.host.os == machine.system


def test_a_system_the_reader_has_no_branch_for_is_named_and_not_used(
    tmp_path: Path,
) -> None:
    ran = run(Staged(environment={"MCGYVR_TEST_MACHINE_OS": "plan9"}), tmp_path)
    assert ran.returncode == 0, ran.stderr
    document = json.loads(ran.stdout)
    unread = {u["field"]: u["why"] for u in document["unread"]}
    assert "MCGYVR_TEST_MACHINE_OS" in unread["system"]
    assert document["host"]["os"] == "linux"
