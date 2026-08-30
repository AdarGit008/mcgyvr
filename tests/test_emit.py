"""Emitting is writing a file. It is never starting a process.

A rig is a machine with an operator; mcgyvr hands it a launch spec and stops.
Docker is one rendering of that spec, a bare command line is another, and the
two must not disagree -- a compose file that carries different arguments from
the command it replaces is a second configuration nobody is reading.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from mcgyvr.emit import EmitError, emit_all, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, unit_for

MOE = ModelSpec(name="qwen3-coder-30b", vram_gb=5.0, ram_gb=13.6, disk_gb=18.6, moe=True)
SMALL = ModelSpec(name="qwen2.5-coder-3b", vram_gb=2.4, ram_gb=0.0, disk_gb=2.1)


def machine(host: str, *, vram_mib: int, ram_gb: float, threads: int) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=threads // 2,
        threads=threads,
        bandwidth_gbps=41.2,
    )


@pytest.fixture
def units() -> dict[str, object]:
    one = machine("desktop-1", vram_mib=6144, ram_gb=48.0, threads=10)
    two = machine("desktop-2", vram_mib=12288, ram_gb=16.0, threads=20)
    return {
        "desktop-1": unit_for(one, MOE, engine="llama.cpp", width=8),
        "desktop-2": unit_for(two, SMALL, engine="llama.cpp", width=16),
    }


def service_of(document: str) -> dict:
    return next(iter(yaml.safe_load(document)["services"].values()))


def test_emitting_never_executes_anything(monkeypatch, units, tmp_path: Path) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("emit executed a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    emit_all(tuple(units.values()), root=tmp_path)


def test_one_compose_file_per_host(units, tmp_path: Path) -> None:
    written = emit_all(tuple(units.values()), root=tmp_path)
    assert sorted(path.name for path in written) == [
        "compose.desktop-1.yml",
        "compose.desktop-2.yml",
    ]


def test_compose_reserves_the_gpu_the_scan_found(units) -> None:
    service = service_of(render_compose(units["desktop-1"]))
    devices = service["deploy"]["resources"]["reservations"]["devices"]
    assert devices[0]["device_ids"] == ["0"]


def test_compose_mounts_weights_rather_than_baking_them(units) -> None:
    service = service_of(render_compose(units["desktop-1"]))
    assert any(str(volume).endswith(":/models:ro") for volume in service["volumes"])


def test_the_written_width_appears_in_the_launch_arguments(units) -> None:
    command = service_of(render_compose(units["desktop-1"]))["command"]
    assert command[command.index("--parallel") + 1] == "8"


def test_the_offload_split_appears_in_the_launch_arguments(units) -> None:
    command = service_of(render_compose(units["desktop-1"]))["command"]
    assert "--n-cpu-moe" in command


def test_the_same_unit_renders_to_a_bare_command(units) -> None:
    assert render_command(units["desktop-2"]).split()[0].endswith("llama-server")


def test_the_bare_command_and_compose_carry_identical_arguments(units) -> None:
    service = service_of(render_compose(units["desktop-2"]))
    assert render_command(units["desktop-2"]).split()[1:] == [str(a) for a in service["command"]]


def test_a_unit_from_an_unscanned_host_is_refused() -> None:
    with pytest.raises(EmitError, match="unscanned"):
        render_compose(None)


def test_emit_is_deterministic(units) -> None:
    assert render_compose(units["desktop-1"]) == render_compose(units["desktop-1"])


def test_nothing_is_written_outside_the_given_root(units, tmp_path: Path) -> None:
    written = emit_all(tuple(units.values()), root=tmp_path)
    assert all(tmp_path in path.parents for path in written)
