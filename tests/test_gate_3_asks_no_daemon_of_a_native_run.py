"""Gate 3 asks no daemon of a native run, and takes Docker Desktop's name only here.

A native launch spec starts no container and resolves no tag, so gate 3
passes it without asking `docker` anything. A container run still holds the
daemon to the machine gate 2 read; Docker Desktop names its daemon
``docker-desktop``, which stands for this machine only when the door reaches
it through the local transport, never for a rig across ssh.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcgyvr.serving.run import GATE_SCRIPTS
from tests.test_serving_gatelib import clean_env, executable, fake_door, under

GATE = GATE_SCRIPTS / "03-image.py"


def docker_stub(where: Path, name: str) -> Path:
    log = where / "docker.log"
    return executable(
        where / "docker",
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{log}'\n"
        f'case "$1" in info) echo {name} ;; version) echo 27.3.1 ;; esac\n',
    )


def gate(tmp_path: Path, host: str, **extra: str) -> tuple[int, str, Path]:
    stub = docker_stub(tmp_path / "stubs", extra.pop("daemon", "docker-desktop"))
    env = clean_env(stub.parent)
    env.update(RUN_HOST=host, RUN_ID="run-1", RUN_PRE_RIG="hostname=studio", **extra)
    done = under(fake_door(tmp_path), [sys.executable, str(GATE)], env)
    return done.returncode, done.stdout + done.stderr, tmp_path / "stubs" / "docker.log"


def test_a_native_run_asks_no_daemon(tmp_path: Path) -> None:
    code, said, log = gate(tmp_path, "localhost", RUN_LAUNCHER="native")
    assert code == 0, said
    assert "natively" in said
    assert not log.exists(), "the daemon was asked"


def test_docker_desktop_stands_for_this_machine_reached_without_ssh(
    tmp_path: Path,
) -> None:
    code, said, log = gate(
        tmp_path, "localhost", RUN_LAUNCHER="docker", MCGYVR_LOCAL_TRANSPORT="direct"
    )
    assert code == 0, said
    assert log.read_text().splitlines()[0].startswith("info")


def test_docker_desktop_does_not_stand_for_a_rig_across_ssh(tmp_path: Path) -> None:
    code, said, _log = gate(tmp_path, "box1", RUN_LAUNCHER="docker")
    assert code == 2, said
    assert "'docker-desktop'" in said and "'studio'" in said
