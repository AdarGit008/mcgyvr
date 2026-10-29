"""A native rig lists its units in rig-units.sh's rows, and keeps its launcher.

On a Mac or Windows rig the units are the native launcher's, so the launcher
itself is rig-units.sh's twin (``native.unit_rows``): a row per supervised unit
(``native-<server pid>``, its restarts), a row per process nvidia-smi says
holds a card, named by the unit whose server it is, and a unit's ``/slots``
page when asked, all read by ``mcgyvr.fleet.read``, the one parser of them.

Shipped to the rig, ``up`` leaves a copy of the launcher under the rig's
mcgyvr home before it starts anything, since a supervisor outlives the ssh call
that started it, and the supervisors run that copy (``-I -B``); the copy is the
program itself and answers its verbs as a file.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hostos
from mcgyvr.fleet import read
from mcgyvr.serving import localrig, native, shipped


@pytest.fixture
def data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    folder = native.state_dir()
    folder.mkdir(parents=True)
    return folder


def test_a_supervised_unit_is_a_row_and_its_card_holder_is_named_by_it(
    data: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pid = os.getpid()
    record = {
        "server": {"pid": pid, "start": hostos.process_start_time(pid)},
        "restarts": 3,
        "state": native.RUNNING,
    }
    (data / "mcgyvr-box1-m-8080.json").write_text(json.dumps(record))
    lock = hostos.open_nofollow(
        data / "mcgyvr-box1-m-8080.lock", os.O_RDWR | os.O_CREAT
    )
    hostos.lock(lock)
    tool = tmp_path / "nvidia-smi"
    tool.write_text(f"#!/bin/sh\necho '{pid}, 9000, /opt/llama/llama-server'\n")
    tool.chmod(0o755)
    monkeypatch.setattr(native, "nvidia_smi", lambda: str(tool))
    asked: list[str] = []

    def ask(url: str, **_kw: Any) -> tuple[int, bytes]:
        asked.append(url)
        return 200, b'[{"id": 0}]'

    monkeypatch.setattr(localrig, "ask", ask)
    try:
        rows = native.unit_rows(["llama.cpp:8080:mcgyvr-box1-m-8080", "vllm:8001"])
    finally:
        hostos.unlock(lock)
        os.close(lock)
    found = read.parse(rows)
    ((name, ident, project, restarts),) = [
        (c.name, c.id, c.project, c.restarts) for c in found.containers
    ]
    assert (name, ident, project, restarts) == (
        "mcgyvr-box1-m-8080",
        f"native-{pid}",
        "-",
        3,
    )
    (holder,) = found.holders
    assert (holder.pid, holder.mib, holder.container) == (pid, 9000, f"native-{pid}")
    assert asked == ["http://127.0.0.1:8080/slots"]
    assert found.status == {8080: '[{"id": 0}]'}


def test_up_leaves_the_launcher_and_its_supervisors_run_that_copy(
    data: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program = shipped.native()
    monkeypatch.setitem(native.__dict__, "__shipped__", program)
    started: list[Any] = []

    def up_units(
        units: Any, names: Any, *, supervisor: Any
    ) -> subprocess.CompletedProcess[str]:
        started.append((units, list(names), supervisor))
        return subprocess.CompletedProcess(["native"], 0, "started\n", "")

    monkeypatch.setattr(native, "up_units", up_units)
    unit = native.NativeUnit(
        name="m",
        container="mcgyvr-box1-m-8080",
        program="llama-server",
        argv=("--port", "8080", "--host", "127.0.0.1"),
        env={},
        port=8080,
        cards=(0,),
        depends_on=(),
        asleep=False,
    )
    assert native.main(["up", native.units_text([unit]), "m"]) == 0
    (copy,) = (tmp_path / "home" / native.SHIPPED).iterdir()
    assert copy.read_bytes() == program
    assert started == [((unit,), ["m"], (sys.executable, "-I", "-B", str(copy)))]
    done = subprocess.run(
        [sys.executable, "-I", "-B", str(copy), "status"],
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state")},
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == []


def test_units_sent_to_a_rig_are_refused_unless_each_names_a_file_and_a_program() -> (
    None
):
    bad = base64.b64encode(
        json.dumps(
            [
                {
                    "name": "m",
                    "container": "../escape",
                    "program": "llama-server",
                    "argv": [],
                    "env": {},
                    "port": 1,
                    "cards": [],
                    "depends_on": [],
                    "asleep": False,
                }
            ]
        ).encode()
    ).decode()
    assert native.main(["up", bad]) == 1
    with pytest.raises(native.NativeError):
        native.units_from_text(bad)


@pytest.mark.parametrize(
    ("program", "argv", "env"),
    [
        ("llama-server", ("--port", "8080", "--host", "0.0.0.0"), {}),
        ("llama-server", ("--port", "8080", "--host=192.0.2.7"), {}),
        ("llama-server", ("--port", "8080"), {"LLAMA_ARG_HOST": "0.0.0.0"}),
        ("ggml-rpc-server", ("-p", "50052", "-H", "0.0.0.0"), {}),
    ],
)
def test_a_unit_that_would_listen_beyond_the_loopback_is_refused_where_it_starts(
    program: str, argv: tuple[str, ...], env: dict[str, str]
) -> None:
    unit = native.NativeUnit(
        name="m",
        container="mcgyvr-box1-m-8080",
        program=program,
        argv=argv,
        env=env,
        port=8080,
        cards=(),
        depends_on=(),
        asleep=False,
    )
    with pytest.raises(native.NativeError, match=r"127\.0\.0\.1 alone"):
        native.units_from_text(native.units_text([unit]))
    assert native.main(["up", native.units_text([unit])]) == 1


def test_a_listening_address_named_in_any_case_is_refused_and_dropped() -> None:
    from mcgyvr.serving import llamacpp

    # Windows reads a variable's name without case.
    assert llamacpp.beyond_loopback(("--port", "8080"), {"llama_arg_host": "0.0.0.0"})
    unit = native.NativeUnit(
        name="m",
        container="mcgyvr-box1-m-8080",
        program="llama-server",
        argv=("--port", "8080"),
        env={"Llama_Arg_Host": "0.0.0.0"},
        port=8080,
        cards=(),
        depends_on=(),
        asleep=False,
    )
    with pytest.raises(native.NativeError, match=r"127\.0\.0\.1 alone"):
        native.units_from_text(native.units_text([unit]))
    kept = native.supervisor_env(
        {
            "llama_arg_host": "0.0.0.0",
            "run_lease": "x",
            "Docker_Host": "tcp://x",
            "PATH": os.pathsep.join(["/door/shims", "/usr/bin", ""]),
            "RUN_BIN": "/door/shims",
            "HOME": "/home/u",
        }
    )
    assert kept == {"PATH": "/usr/bin", "HOME": "/home/u"}
