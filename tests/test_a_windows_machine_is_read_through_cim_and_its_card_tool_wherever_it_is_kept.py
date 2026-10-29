"""A Windows machine is read through CIM, and its card tool wherever it is kept.

On Windows the reader asks PowerShell once for the memory modules, the
processors, the system and the display adapters (never wmic, which Windows no
longer ships), and nvidia-smi.exe for the cards, looked for on PATH, then in the
system folder, then in the vendor's folder. A card the tool reads is sized; a
display adapter no tool reads is listed unsized under the Vulkan backend, since
Windows' own size field stops at 4 GiB; an adapter that is not a PCI card is
left out with a note. The machine id is the registry's MachineGuid, hashed as
any machine id is.
"""

from __future__ import annotations

import base64
import json
import os
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
from tests.machinereader import fingerprint, run, stage_host

WINDOWS = [m for m in host_shapes() if m.system == "windows"]
WITH_CARD = [m for m in WINDOWS if m.tool_cards]


@pytest.mark.parametrize("machine", WITH_CARD, ids=lambda m: m.label)
def test_a_card_the_tool_reads_is_sized_wherever_the_tool_is_kept(
    machine: HostShape, tmp_path: Path
) -> None:
    ran = run(stage_host(machine), tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert not ran.unexpected and not ran.elevated
    document = json.loads(ran.stdout)
    assert document == host_reading(machine)
    (card,) = document["cards"]
    (tool_card,) = machine.tool_cards
    assert (card["vendor"], card["name"], card["total_mib"]) == (
        "nvidia",
        tool_card.name,
        tool_card.total_mib,
    )
    assert (card["kind"], card["backend"]) == ("gpu", "cuda")
    assert document["card_sources"] == ["nvidia-smi"]
    (gpu,) = [r for r in document["resources"] if r["kind"] == "gpu"]
    assert (gpu["total_mb"], gpu["figure"]) == (tool_card.total_mib, "reading")


def test_a_card_no_tool_reads_is_listed_unsized_under_vulkan(tmp_path: Path) -> None:
    machine = host_shape("windows-other-gpu")
    ran = run(stage_host(machine), tmp_path)
    document = json.loads(ran.stdout)
    assert document == host_reading(machine)
    (card,) = document["cards"]
    assert (card["vendor"], card["total_mib"], card["backend"]) == (
        "amd",
        None,
        "vulkan",
    )
    assert document["unsized"] == ["card.amd.0"]
    assert (
        "4 GiB"
        in {u["field"]: u["why"] for u in document["unread"]}["card.amd.0.total"]
    )
    assert [r["kind"] for r in document["resources"]] == ["ram", "cpu"]
    notes = host_scan(machine).notes
    assert any("not a PCI card" in note for note in notes)


def test_the_machine_id_is_the_registry_guid_hashed() -> None:
    from mcgyvr.fleet import ids

    for machine in WINDOWS:
        document = host_reading(machine)
        seed = f"MachineGuid:{machine.machine_id}"
        assert document["machine"]["id"] == fingerprint(seed)
        assert document["machine"]["id_from"] == "registry MachineGuid"
        if machine.label != "windows-other-gpu":
            assert ids.rig_id(document).startswith("rig-")


def test_memory_falls_back_to_what_the_system_sees_without_modules() -> None:
    machine = host_shape("windows-no-modules")
    document = host_reading(machine)
    assert document["memory"]["total_gb"] == round(
        (machine.memory_mib * 1024 - 2048) / 1024 / 1024, 1
    )
    measured = host_scan(machine)
    assert any(
        fact.how == "Win32_OperatingSystem TotalVisibleMemorySize"
        for fact in measured.facts
    )


@pytest.mark.parametrize("machine", WINDOWS, ids=lambda m: m.label)
def test_the_cpu_and_host_are_read_from_cim(machine: HostShape) -> None:
    document = host_reading(machine)
    assert document["cpu"] == {
        "model": machine.cpu_model,
        "cores": machine.cores,
        "threads": machine.threads,
        "performance_cores": None,
    }
    assert document["host"] == {
        "os": "windows",
        "arch": "x86_64",
        "version": machine.version,
    }
    found = host_detection(machine)
    assert found.host is not None and found.host.os == "windows"
    assert not any(gpu.unified for gpu in found.gpus)


def test_the_one_powershell_call_is_cim_and_never_wmic() -> None:
    from mcgyvr.serving import rigscan

    assert rigscan.CIM_ARGS[:4] == (
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
    )
    script = base64.b64decode(rigscan.CIM_ARGS[4]).decode("utf-16-le")
    assert script == rigscan.CIM_SCRIPT
    assert "wmic" not in script.lower()
    for name in (
        "Win32_PhysicalMemory",
        "Win32_Processor",
        "Win32_OperatingSystem",
        "Win32_VideoController",
    ):
        assert f"Get-CimInstance {name}" in script
    assert "AdapterRAM" not in script


def test_a_card_tool_left_in_the_working_folder_is_never_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows' which() looks in the working folder first, so the reader never
    calls nvidia-smi by bare name: with the tool in no folder named in full, it
    asks no card tool at all, and the adapter stays unsized."""
    from mcgyvr.serving import rigscan
    from tests import machine_shapes

    here = tmp_path / "working"
    here.mkdir()
    for planted in ("nvidia-smi.exe", "nvidia-smi.bat", "nvidia-smi"):
        (here / planted).write_text("planted", encoding="utf-8")
    monkeypatch.chdir(here)
    monkeypatch.setenv("PATH", os.pathsep.join(["", ".", "bin"]))
    for variable in ("SYSTEMROOT", "PROGRAMW6432", "PROGRAMFILES"):
        monkeypatch.setenv(variable, str(tmp_path / "empty"))
    assert rigscan._windows_nvidia_smi() is None

    asked: list[tuple[str, ...]] = []
    serve = machine_shapes._host_run

    def recording(machine: HostShape) -> Any:
        run_tool = serve(machine)

        def run(argv: Any, *, bound: float = 0.0) -> Any:
            asked.append(tuple(argv))
            return run_tool(argv, bound=bound)

        return run

    monkeypatch.setattr(machine_shapes, "_host_run", recording)
    machine = host_shape("windows-other-gpu")
    document = host_reading(machine)
    host_scan(machine)
    assert asked and not [argv for argv in asked if "nvidia-smi" in argv[0]]
    assert document["unsized"] == ["card.amd.0"]
