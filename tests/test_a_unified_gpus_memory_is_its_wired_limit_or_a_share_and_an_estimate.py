"""A unified GPU's memory is the Metal reading, else its wired limit or a share.

The memory a Mac's GPU may use is, once a native server has started on it, the
working set llama.cpp logged at start-up (Metal's
``recommendedMaxWorkingSetSize``), which the native supervisor files in the
data folder with the wired limit in force: a reading, held to the machine's
memory, taken while that wired limit is still the one set. On a first run, with
nothing filed, it is the kernel's wired limit when one is set, else the stated
share of the machine's memory, and either is an estimate that names its basis.
A reading taken under another wired limit, one that names none (an older
supervisor's), or a file that holds no reading sizes by estimate and says why.
The reader finds the file in the data folder the product itself uses. Every
machine here is invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet import roots
from mcgyvr.serving import rigscan
from tests import machine_shapes

GIB_IN_MB = 1024
MIB = 1024 * 1024
#: A working set an invented Mac's llama.cpp logged, in bytes: below every
#: invented Mac's estimate, so a reading and an estimate never agree by chance.
WORKING_SET = 15_000_000_000

UNIFIED = [m for m in machine_shapes.host_shapes() if m.chip is not None]


def _file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: dict[str, Any] | str
) -> Path:
    """File `body` where the supervisor files the Metal reading, in a data
    folder of this test's own."""
    data = tmp_path / "data"
    monkeypatch.setenv(roots.DATA_ENV, str(data))
    path = data / roots.NATIVE_DIR / roots.METAL_FILE
    path.parent.mkdir(parents=True)
    text = body if isinstance(body, str) else json.dumps(body)
    path.write_text(text, encoding="utf-8")
    return path


def _filed(machine: machine_shapes.HostShape, **more: Any) -> dict[str, Any]:
    """What the supervisor files on `machine`: the working set as a reading,
    under the wired limit its kernel setting names."""
    return {
        "bytes": WORKING_SET,
        "figure": "reading",
        "source": rigscan.METAL_SOURCE,
        "wired_limit_mb": machine.wired_limit_mib,
        "unit": "mcgyvr-localhost-example",
        "tag": "b0",
        "read_at": "2026-01-01T00:00:00+00:00",
        **more,
    }


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_a_first_run_sizes_each_unified_gpu_by_its_wired_limit_or_a_share(
    machine: machine_shapes.HostShape,
) -> None:
    assert rigscan.metal_working_set() == (None, "")
    scan = machine_shapes.host_scan(machine)
    (gpu,) = scan.gpus
    assert gpu.vram.total_mib == machine.unified_mib
    assert gpu.figure == "estimate"
    assert not [n for n in scan.notes if "Metal reading" in n]
    if not machine.wired_limit_mib:
        assert gpu.vram.total_mib == int(machine.memory_mib * rigscan.UNIFIED_SHARE)


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_a_fit_listing_takes_the_usable_memory_as_the_unified_gpus_vram(
    machine: machine_shapes.HostShape,
) -> None:
    (gpu,) = machine_shapes.host_detection(machine).gpus
    assert machine.unified_mib is not None
    assert gpu.unified and gpu.figure == "estimate"
    assert gpu.vram_gb == round(machine.unified_mib / GIB_IN_MB, 1)
    assert gpu.vram_gb is not None and gpu.vram_gb < machine.memory_mib / GIB_IN_MB


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_the_filed_working_set_sizes_the_gpu_and_is_a_reading(
    machine: machine_shapes.HostShape,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _file(tmp_path, monkeypatch, _filed(machine))
    reading = machine_shapes.host_reading(machine)
    (card,) = reading["cards"]
    assert card["total_mib"] == WORKING_SET // MIB != machine.unified_mib
    assert card["figure"] == "reading"
    assert rigscan.METAL_SOURCE in card["how"]
    assert card["free_mib"] == min(card["total_mib"], machine.available_mib)
    assert roots.METAL_FILE in reading["card_sources"]
    (unified,) = [r for r in reading["resources"] if r["kind"] == "unified"]
    assert (unified["total_mb"], unified["figure"]) == (WORKING_SET // MIB, "reading")

    (gpu,) = machine_shapes.host_detection(machine).gpus
    assert gpu.figure == "reading"
    assert gpu.vram_gb == round(WORKING_SET / MIB / GIB_IN_MB, 1)


def test_a_reading_is_held_to_the_machines_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine = UNIFIED[0]
    _file(tmp_path, monkeypatch, _filed(machine, bytes=machine.memory_mib * MIB * 2))
    (gpu,) = machine_shapes.host_scan(machine).gpus
    assert (gpu.vram.total_mib, gpu.figure) == (machine.memory_mib, "reading")


@pytest.mark.parametrize("machine", UNIFIED, ids=lambda m: m.label)
def test_a_reading_taken_under_another_wired_limit_is_not_taken(
    machine: machine_shapes.HostShape,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = machine.wired_limit_mib + 4096
    _file(tmp_path, monkeypatch, _filed(machine, wired_limit_mb=other))
    scan = machine_shapes.host_scan(machine)
    (gpu,) = scan.gpus
    assert (gpu.vram.total_mib, gpu.figure) == (machine.unified_mib, "estimate")
    (said,) = [n for n in scan.notes if "Metal reading" in n]
    assert f"{rigscan.SYSCTL_WIRED_LIMIT} at {other}" in said
    assert "until a native server starts again" in said


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ({"wired_limit_mb": None}, f"names no {rigscan.SYSCTL_WIRED_LIMIT}"),
        ({"figure": "estimate"}, "holds no working set read as a reading"),
        ({"bytes": 0}, "holds no working set read as a reading"),
        ({"bytes": True}, "holds no working set read as a reading"),
        ({"bytes": 1.5e10}, "holds no working set read as a reading"),
        ("not json", "is not a JSON object"),
        ("[1, 2]", "is not a JSON object"),
    ],
    ids=["no-wired-limit", "estimate", "zero", "bool", "float", "text", "list"],
)
def test_a_file_that_holds_no_usable_reading_sizes_by_estimate_and_says_why(
    body: dict[str, Any] | str,
    why: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = UNIFIED[0]
    if isinstance(body, dict):
        filed: dict[str, Any] | str = _filed(machine, **body)
    else:
        filed = body
    path = _file(tmp_path, monkeypatch, filed)
    scan = machine_shapes.host_scan(machine)
    (gpu,) = scan.gpus
    assert (gpu.vram.total_mib, gpu.figure) == (machine.unified_mib, "estimate")
    (said,) = [n for n in scan.notes if "Metal reading" in n]
    assert why in said and "sized by estimate" in said
    # The note names the file by its place in the data folder, never by a path
    # that holds the user's home.
    assert str(path.parent.parent) not in said


def test_a_relative_data_folder_is_not_looked_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(roots.DATA_ENV, "relative/data")
    assert rigscan.mcgyvr_data() is None
    found, why = rigscan.metal_working_set()
    assert found is None and f"${roots.DATA_ENV}" in why


@pytest.mark.parametrize(
    "env",
    [
        {},
        {roots.DATA_ENV: "/srv/example-data"},
        {roots.DATA_ENV: "~/example-data"},
        {"XDG_STATE_HOME": "/srv/example-state"},
        {"XDG_STATE_HOME": "relative-state"},
        {roots.DATA_ENV: "/srv/example-data", "XDG_STATE_HOME": "/srv/example"},
    ],
    ids=["default", "data", "data-home", "xdg", "xdg-relative", "both"],
)
def test_the_reader_looks_in_the_data_folder_the_product_uses(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert rigscan.mcgyvr_data() == str(roots.data_home())
