"""Serving a Mac or Windows rig runs the native launcher there, over ssh, no docker.

A unit on a rig whose rig file records macOS or Windows is emitted as a native
program listening on 127.0.0.1 (K13). ``serve up`` and ``serve down`` ship the
native launcher to that rig, the way the reader is shipped, and ask it ``up``
with the units read from the launch spec here, or ``down`` with their names; a
Windows rig gets it through PowerShell. What holds such a rig, and which units
are up, is the launcher's twin of rig-units.sh (``units``), read by the one
parser of those rows. The health probe names ``curl.exe`` on Windows, where
PowerShell reads ``curl`` as something else. A Linux rig is still refused a
native spec.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import emit
from mcgyvr.config import NATIVE_BY_DEFAULT, parse
from mcgyvr.fleet import read
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    LAUNCHER_KEY,
    PROGRAM_KEY,
    gatelib,
    native,
    rigread,
    servelib,
    shipped,
    units_for,
)
from tests.remote_rigs import FakeShell, record_rig

MODEL = "Qwen3.6-35B-A3B-UD-IQ3_XXS"


def _config(host: str) -> str:
    return f"""
units:
  far_big:
    address: "http://{host}:8080"
    model: "{MODEL}"
    rig: far
    launcher: native
    launch:
      vram_gb: 3.0
      disk_gb: 12.31
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
ladder:
- far_big
"""


def _spec(tmp_path: Path, host: str) -> Path:
    scans = {
        host: Scan.of(
            host=host,
            vram_mib=12288,
            ram_gb=48.0,
            disk_free_gb=900.0,
            cores=6,
            threads=6,
            bandwidth_gbps=40.3,
        )
    }
    (unit,) = units_for(parse(_config(host)), scans, specs=(), ctx_per_slot=4096)
    spec = tmp_path / "compose.yml"
    spec.write_text(emit.render_compose(unit))
    return spec


def _verb(shell: FakeShell, system: str) -> list[str]:
    """The native launcher's verb and arguments in the one call `shell` got."""
    ((command, stdin),) = shell.sent
    program = shipped.packed(shipped.native())
    assert stdin is not None
    if system == "windows":
        assert command == gatelib.WINDOWS_SHIP
        sent, arguments, feed = stdin[:-1].split("\n")
        assert base64.b64decode(sent) == program
        verb = gatelib.windows_split(base64.b64decode(arguments).decode())
        if verb[:2] == ["up", "-"]:
            # The units go on the launcher's stdin, past Windows' command line.
            return ["up", base64.b64decode(feed).decode(), *verb[2:]]
        assert not feed
        return verb
    # The launcher is on stdin: it is too long for the door's own ssh argument.
    head = "base64 -d | python3 -I -B - "
    assert command.startswith(head)
    assert base64.b64decode(stdin) == program
    return command[len(head) :].split(" ")


@pytest.fixture(
    params=[
        ("unified-laptop", NATIVE_BY_DEFAULT[0]),
        ("windows-one-card", NATIVE_BY_DEFAULT[1]),
    ]
)
def rig(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[str, str]:
    label, system = request.param
    record_rig(monkeypatch, tmp_path, "box1", label)
    monkeypatch.setenv("RUN_HOST", "box1")
    monkeypatch.setenv("RUN_LAUNCHER", "native")
    return "box1", system


def test_a_unit_on_the_rig_is_emitted_native_on_the_loopback(
    rig: tuple[str, str], tmp_path: Path
) -> None:
    host, _system = rig
    (service,) = yaml.safe_load(_spec(tmp_path, host).read_text())["services"].values()
    assert service[LAUNCHER_KEY] == "native"
    assert service[PROGRAM_KEY] == "llama-server"
    command = list(service["command"])
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert "image" not in service


def test_serve_up_ships_the_launcher_with_the_units_of_the_spec(
    rig: tuple[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    host, system = rig
    spec = _spec(tmp_path, host)
    shell = FakeShell(system, tmp_path / "rig")
    shell.answer = lambda c, s: subprocess.CompletedProcess(["ssh"], 0, "started\n", "")
    monkeypatch.setattr(gatelib, "ssh", shell)
    done = servelib.up(spec)
    assert done.returncode == 0
    verb = _verb(shell, system)
    assert verb[0] == "up" and len(verb) == 2
    assert shell.kept_alive == [True]  # no time bound, so ssh's keepalive
    assert native.units_from_text(verb[1]) == native.parse(spec)
    (unit,) = native.units_from_text(verb[1])
    assert unit.argv[unit.argv.index("--host") + 1] == "127.0.0.1"


def test_serve_down_ships_the_launcher_with_the_unit_names(
    rig: tuple[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    host, system = rig
    spec = _spec(tmp_path, host)
    shell = FakeShell(system, tmp_path / "rig")
    shell.answer = lambda c, s: subprocess.CompletedProcess(["ssh"], 0, "", "")
    monkeypatch.setattr(gatelib, "ssh", shell)
    servelib.down(spec)
    (unit,) = native.parse(spec)
    assert _verb(shell, system) == ["down", unit.container]


def test_what_holds_the_rig_is_the_launchers_twin_of_rig_units(
    rig: tuple[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    host, system = rig
    spec = _spec(tmp_path, host)
    (unit,) = native.parse(spec)
    rows = (
        f"container={unit.container},native-4242,-,2\n"
        "gpu_app=4242,9000,native-4242,llama-server\n"
    )
    shell = FakeShell(system, tmp_path / "rig")
    shell.answer = lambda c, s: subprocess.CompletedProcess(["ssh"], 0, rows, "")
    monkeypatch.setattr(gatelib, "ssh", shell)
    held = rigread.held(host)
    assert held == {
        "gpu_procs": "4242,llama-server,9000MiB",
        "containers": "native-4242",
    }
    assert _verb(shell, system) == ["units"]
    shell.sent.clear()
    monkeypatch.setenv("RUN_COMPOSE", str(spec))
    assert servelib.containers_up("native") == [unit.container]
    shell.sent.clear()
    assert servelib.restart_count(unit.container) == 2


def test_the_launcher_run_on_the_rig_lists_nothing_where_nothing_runs(
    rig: tuple[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    host, system = rig
    shell = FakeShell(system, tmp_path / "rig")
    monkeypatch.setenv("PATH", str(tmp_path / "no-tools"))
    monkeypatch.setattr(gatelib, "ssh", shell)
    assert rigread.held(host) == {"gpu_procs": "none", "containers": "none"}
    found = read.parse(native.unit_rows())
    assert found.containers == [] and found.holders == []


def test_the_health_probe_names_the_curl_of_the_rigs_system(
    rig: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    host, system = rig
    calls: list[Any] = []

    def ssh(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(["ssh"], 0, '{"data": []}', "")

    monkeypatch.setattr(servelib, "ssh", ssh)
    assert servelib.models_served(host, 8080) == []
    curl = "curl.exe" if system == "windows" else "curl"
    assert calls == [(host, f"{curl} -sf http://localhost:8080/v1/models")]


def test_a_linux_rig_is_refused_a_native_spec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record_rig(monkeypatch, tmp_path, "box2", "linux-one-card")
    monkeypatch.setenv("RUN_HOST", "box2")
    spec = tmp_path / "compose.yml"
    spec.write_text(
        yaml.safe_dump(
            {
                "services": {
                    "m": {
                        LAUNCHER_KEY: "native",
                        "container_name": "mcgyvr-box2-m",
                        "command": ["--port", "8080"],
                    }
                }
            }
        )
    )
    with pytest.raises(servelib.ComposeError, match="macOS or Windows rig"):
        servelib.up(spec)
    with pytest.raises(emit.EmitError, match="records neither"):
        _spec(tmp_path, "box2")


def test_an_argument_that_cannot_be_shipped_is_a_refusal_not_a_traceback(
    rig: tuple[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr.serving import nativerig

    host, system = rig
    shell = FakeShell(system, tmp_path / "rig")
    monkeypatch.setattr(gatelib, "ssh", shell)
    done = nativerig.down(host, ["bad\0name"])
    assert done.returncode == 2 and "NUL" in done.stderr
    assert shell.sent == []
