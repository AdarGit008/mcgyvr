"""A unit with `launcher: native` is emitted as a program to run, not a container.

Its launch spec carries the native launcher's keys, the program of the pinned
build, the cards it may use, and the argv a container would be given, with
`--host 127.0.0.1` unless the unit names its own address to listen on. No
image, no volumes, no daemon's device reservation. A unit that states nothing
is a container as before, on the pinned image. vLLM has no native build, two
units of one process cannot run two ways, and a launch spec mixing the two
launchers is refused before anything runs.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from mcgyvr import emit
from mcgyvr.config import parse
from mcgyvr.fleet.sampler import unit_id
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    CARDS_KEY,
    LAUNCHER_KEY,
    PROGRAM_KEY,
    Unit,
    UnitError,
    llamacpp,
    servelib,
    units_for,
)

MODEL = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
SCANS = {
    "localhost": Scan.of(
        host="localhost",
        vram_mib=12288,
        ram_gb=48.0,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )
}


def config_text(launcher: str = "", *, engine: str = "", serve_args: str = "") -> str:
    return f"""
units:
  local_big:
    address: "http://localhost:8080"
    model: "{MODEL}"
    rig: this-machine
    width: 2
{launcher}{engine}    launch:
      vram_gb: 3.0
      disk_gb: 12.31
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
{serve_args}ladder:
- local_big
"""


def replace_host(scan: Scan, host: str) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=12288,
        ram_gb=48.0,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


def only_unit(text: str) -> Unit:
    (unit,) = units_for(parse(text), SCANS, specs=(), ctx_per_slot=4096)
    return unit


def service_of(unit: Unit) -> dict[str, object]:
    document = yaml.safe_load(emit.render_compose(unit))
    (service,) = document["services"].values()
    return dict(service)


def test_a_native_unit_is_a_program_on_the_loopback() -> None:
    unit = only_unit(config_text("    launcher: native\n"))
    assert unit.launcher == "native"
    service = service_of(unit)
    assert service[LAUNCHER_KEY] == "native"
    assert service[PROGRAM_KEY] == llamacpp.SERVER
    assert service[CARDS_KEY] == [0]
    command = list(service["command"])  # type: ignore[call-overload]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert "--model" in command and "--port" in command
    for container_only in ("image", "volumes", "deploy", "network_mode", "restart"):
        assert container_only not in service


def test_a_native_unit_that_names_another_address_is_refused() -> None:
    unit = only_unit(
        config_text(
            "    launcher: native\n",
            serve_args="      serve_args: ['--host', '0.0.0.0']\n",
        )
    )
    with pytest.raises(emit.EmitError, match=r"127\.0\.0\.1 alone"):
        emit.render_compose(unit)


def test_a_native_unit_on_another_rig_is_refused() -> None:
    text = config_text("    launcher: native\n").replace("localhost", "box1")
    scans = {"box1": replace_host(SCANS["localhost"], "box1")}
    (unit,) = units_for(parse(text), scans, specs=(), ctx_per_slot=4096)
    with pytest.raises(emit.EmitError, match="box1 is another"):
        emit.render_compose(unit)


def test_a_native_unit_keeps_a_path_with_a_space() -> None:
    unit = only_unit(config_text("    launcher: native\n"))
    unit = replace(unit, args={**unit.args, "--model": "/Users/Jane Doe/m.gguf"})
    command = list(service_of(unit)["command"])  # type: ignore[call-overload]
    assert "/Users/Jane Doe/m.gguf" in command
    with pytest.raises(emit.EmitError, match="whitespace"):
        emit.render_compose(replace(unit, launcher="docker"))


def test_a_unit_that_states_nothing_is_a_container_on_the_pinned_image() -> None:
    unit = only_unit(config_text())
    assert unit.launcher == "docker"
    service = service_of(unit)
    assert service["image"] == llamacpp.IMAGE
    assert LAUNCHER_KEY not in service


def test_vllm_has_no_native_build() -> None:
    vllm = '    engine: vllm\n    hf_cache: "/home/someone/.cache/huggingface"\n'
    unit = only_unit(config_text("    launcher: native\n", engine=vllm))
    with pytest.raises(emit.EmitError, match="vllm has none"):
        emit.render_compose(unit)


def test_two_units_of_one_process_cannot_run_two_ways() -> None:
    text = config_text("    launcher: native\n").replace(
        "ladder:\n- local_big\n",
        f"""  same_process:
    address: "http://localhost:8080"
    model: "{MODEL}"
    rig: this-machine
ladder:
- local_big
- same_process
""",
    )
    with pytest.raises(UnitError, match="one process runs one way"):
        units_for(parse(text), SCANS, specs=(), ctx_per_slot=4096)


def test_a_launch_spec_mixing_the_two_launchers_is_refused(tmp_path: Path) -> None:
    native = service_of(only_unit(config_text("    launcher: native\n")))
    docker = service_of(only_unit(config_text()))
    docker["container_name"] = "mcgyvr-localhost-other"
    path = tmp_path / "compose.localhost.yml"
    path.write_text(yaml.safe_dump({"services": {"a": native, "b": docker}}))
    units = servelib.services(path)
    assert {u.launcher for u in units} == {"native", "docker"}
    with pytest.raises(servelib.ComposeError, match="mixes"):
        servelib.launcher_of(units)


def test_a_native_service_is_read_with_its_cards(tmp_path: Path) -> None:
    path = tmp_path / "compose.localhost.yml"
    path.write_text(
        emit.render_compose(only_unit(config_text("    launcher: native\n")))
    )
    (service,) = servelib.services(path)
    assert service.launcher == "native"
    assert service.devices == ("0",)
    assert servelib.launcher_of((service,)) == "native"


def test_a_containers_unit_id_is_what_it_was_and_a_native_one_differs() -> None:
    block = {"address": "http://localhost:8080", "model": MODEL, "launch": {}}
    before = unit_id(block)
    assert unit_id({**block, "launcher": "docker"}) == before
    assert unit_id({**block, "launcher": "native"}) != before


def test_an_unknown_launcher_is_refused_by_the_config() -> None:
    with pytest.raises(Exception, match="launcher"):
        parse(config_text("    launcher: podman\n"))
