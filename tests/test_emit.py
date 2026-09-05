"""Emitting is writing a file. It is never starting a process.

A rig is a machine with an operator; mcgyvr hands it a launch spec and stops.
Docker is one rendering of that spec, a bare command line is another, and the
two must not disagree -- a compose file that carries different arguments from
the command it replaces is a second configuration nobody is reading.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import EmitError, emit_all, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, Unit, unit_for

# An MoE is sized off its own GGUF geometry and nothing else: the row for
# Qwen3.6-35B-A3B at IQ3_XXS, as `ggufscan` read it (40 placeable blocks of
# 262 and 300 MiB, 12.3 GiB on disk). The name is the file's, because a
# geometry belongs to one file.
GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)
MOE = ModelSpec(
    name="Qwen3.6-35B-A3B-UD-IQ3_XXS",
    vram_gb=0.0,
    ram_gb=0.0,
    disk_gb=0.0,
    geometry=GEOMETRY["Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf"],
)
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
def units() -> dict[str, Unit]:
    one = machine("desktop-1", vram_mib=6144, ram_gb=48.0, threads=10)
    two = machine("desktop-2", vram_mib=12288, ram_gb=16.0, threads=20)
    return {
        "desktop-1": unit_for(one, MOE, engine="llama.cpp", width=8),
        "desktop-2": unit_for(two, SMALL, engine="llama.cpp", width=16),
    }


def service_of(document: str) -> dict[str, Any]:
    return next(iter(yaml.safe_load(document)["services"].values()))


def test_emitting_never_executes_anything(
    monkeypatch: pytest.MonkeyPatch, units: dict[str, Unit], tmp_path: Path
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("emit executed a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    emit_all(tuple(units.values()), root=tmp_path)


def test_one_compose_file_per_host(units: dict[str, Unit], tmp_path: Path) -> None:
    written = emit_all(tuple(units.values()), root=tmp_path)
    assert sorted(path.name for path in written) == [
        "compose.desktop-1.yml",
        "compose.desktop-2.yml",
    ]


def test_compose_reserves_the_gpu_the_scan_found(units: dict[str, Unit]) -> None:
    service = service_of(render_compose(units["desktop-1"]))
    devices = service["deploy"]["resources"]["reservations"]["devices"]
    assert devices[0]["device_ids"] == ["0"]


def test_compose_mounts_weights_rather_than_baking_them(
    units: dict[str, Unit],
) -> None:
    service = service_of(render_compose(units["desktop-1"]))
    assert any(str(volume).endswith(":/models:ro") for volume in service["volumes"])


def test_the_written_width_appears_in_the_launch_arguments(
    units: dict[str, Unit],
) -> None:
    command = service_of(render_compose(units["desktop-1"]))["command"]
    assert command[command.index("--parallel") + 1] == "8"


def test_the_offload_split_appears_in_the_launch_arguments(
    units: dict[str, Unit],
) -> None:
    command = service_of(render_compose(units["desktop-1"]))["command"]
    assert "--n-cpu-moe" in command


def test_the_same_unit_renders_to_a_bare_command(units: dict[str, Unit]) -> None:
    assert render_command(units["desktop-2"]).split()[0].endswith("llama-server")


def test_the_bare_command_and_compose_carry_identical_arguments(
    units: dict[str, Unit],
) -> None:
    service = service_of(render_compose(units["desktop-2"]))
    assert render_command(units["desktop-2"]).split()[1:] == [
        str(a) for a in service["command"]
    ]


def test_a_unit_from_an_unscanned_host_is_refused() -> None:
    with pytest.raises(EmitError, match="unscanned"):
        render_compose(None)


def test_emit_is_deterministic(units: dict[str, Unit]) -> None:
    assert render_compose(units["desktop-1"]) == render_compose(units["desktop-1"])


def test_nothing_is_written_outside_the_given_root(
    units: dict[str, Unit], tmp_path: Path
) -> None:
    written = emit_all(tuple(units.values()), root=tmp_path)
    assert all(tmp_path in path.parents for path in written)


def test_the_port_appears_in_the_launch_arguments(units: dict[str, Unit]) -> None:
    command = service_of(render_compose(units["desktop-1"]))["command"]
    assert command[command.index("--port") + 1] == str(units["desktop-1"].port)


def elsewhere(unit: Unit, weights: str) -> Unit:
    """The same unit with its weights at ``weights``.

    The path is written in two places -- the mount comes off ``weights`` and
    the argv off ``--model`` -- so a test that moved only one would be checking
    a unit no rig could produce.
    """
    return replace(unit, weights=Path(weights), args={**unit.args, "--model": weights})


def renamed(unit: Unit, model: str) -> Unit:
    """The same unit serving a differently *spelled* model, key included."""
    return replace(unit, model=model, key=replace(unit.key, model=model))


def test_the_bare_command_is_safe_to_paste_into_a_shell(units: dict[str, Unit]) -> None:
    """A metacharacter in a path must stay a character rather than become syntax.

    The compose ``command`` is a list, so ``/srv/w;id/qwen.gguf`` is one
    argument there whatever is in it; the bare rendering is one string a shell
    re-reads, and unquoted the same path is a command separator followed by a
    second command. That is the two-renderings drift this module exists to
    prevent, in its sharpest form -- one rendering loads a model, the other
    loads a shorter path and then runs something.

    A real shell is asked here, not a parser, because "safe to paste" is a
    claim about a shell and nothing else can falsify it.
    """
    unit = elsewhere(units["desktop-2"], "/srv/w;id/qwen-3b.gguf")
    echoed = subprocess.run(
        ["sh", "-c", f"printf '%s\\n' {render_command(unit)}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert echoed[1:] == [str(a) for a in service_of(render_compose(unit))["command"]]


def test_two_models_that_spell_one_service_name_are_refused(
    units: dict[str, Unit], tmp_path: Path
) -> None:
    """Two units on one host are two services or an error, never one service.

    ``qwen2.5-coder:3b`` and ``qwen2.5-coder-3b`` are two sets of weights and
    two processes, and compose spells both the same way. Merged, the file is
    correct-looking and serves one of them -- the rung bound to the other gets
    connection refused, on a rig whose compose file names the model it is
    asking for.
    """
    one = units["desktop-2"]
    two = renamed(one, "qwen2.5-coder:3b")
    with pytest.raises(EmitError, match=re.escape("qwen2.5-coder:3b")):
        emit_all((one, two), root=tmp_path)


def test_a_host_reached_over_ipv6_can_be_emitted(
    units: dict[str, Unit], tmp_path: Path
) -> None:
    """An IPv6 rig is a rig, and it has to reach a file name somehow.

    ``host_of("http://[fd00::1]:8080")`` is ``fd00::1``, and a colon is not a
    file name component anyone wants to carry around -- but refusing it means a
    source the ladder can reach is a source mcgyvr can never emit, which is the
    worse of the two answers.
    """
    one = units["desktop-2"]
    unit = replace(one, host="fd00::1", key=replace(one.key, host="fd00::1"))
    written = emit_all((unit,), root=tmp_path)
    assert len(written) == 1
    assert set(":/%").isdisjoint(written[0].name)
    assert len(yaml.safe_load(written[0].read_text(encoding="utf-8"))["services"]) == 1


def test_two_hosts_never_claim_one_compose_file(
    units: dict[str, Unit], tmp_path: Path
) -> None:
    """Whatever an address is spelled as, some host may already be called that.

    Spelling a host into a file name is many-to-one the moment it rewrites
    anything, and two hosts writing one path is the same silent loss as two
    models writing one service: the second file wins and the first rig is
    simply not in the output.
    """
    one = units["desktop-2"]
    ipv6 = replace(one, host="fd00::1", key=replace(one.key, host="fd00::1"))
    spelled = emit_all((ipv6,), root=tmp_path)[0].name[len("compose.") : -len(".yml")]
    twin = replace(one, host=spelled, key=replace(one.key, host=spelled))
    with pytest.raises(EmitError, match="fd00::1"):
        emit_all((ipv6, twin), root=tmp_path)


def test_one_model_on_two_ports_yields_two_services() -> None:
    """A throughput lane and a careful lane may be the same weights, twice.

    Two sources on one host, one model, two ports is the shape a ladder uses
    when one process is sized for volume and the other to drain its failure
    tail. The unit key already tells them apart; a compose service named after
    the model alone throws that away again, and the second rung dies.
    """
    rig = machine("desktop-4", vram_mib=49152, ram_gb=128.0, threads=20)
    fast = unit_for(rig, SMALL, engine="llama.cpp", width=16, port=8080)
    careful = unit_for(rig, SMALL, engine="llama.cpp", width=2, port=8081)
    written = emit_all((fast, careful), root=Path(tempfile.mkdtemp()))
    document = yaml.safe_load(written[0].read_text(encoding="utf-8"))
    assert len(document["services"]) == 2
    names = {service["container_name"] for service in document["services"].values()}
    assert len(names) == 2
