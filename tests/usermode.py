"""A machine a user owns, behind the door's shims, for the tests of the user mode.

The door's user mode is the door run from an install: no lab checkout, so no
round, no lab ``hosts.json`` and no declared docker version. What it holds the rig
to instead is the user's own rig file, ``$MCGYVR_HOME/rigs/<rig>.json``, the
rig's read-only scan saved by ``mcgyvr scan --rig``.

These helpers stand the one-door stubs (:mod:`tests.onedoor`) behind the
door's shims for one invented machine, and run the door as an installed
``python -m mcgyvr.serving.run`` whose run root is a folder that is not a lab
checkout. Every host, card and container named here is invented.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving import run
from tests import onedoor

#: The rig as the user's ssh names it (RFC 6761 reserves ``.invalid``).
RIG = "box-a.invalid"
#: The name the rig's own hostname and its docker daemon answer to.
HOSTNAME = "box-a-host.invalid"
DOCKER = "27.1.0"
RUN_DATE = "2026-10-07"
#: Two invented units on card 0, as `mcgyvr emit` names a rig's units.
UNITS = ("mcgyvr-box-a-fast-8001", "mcgyvr-box-a-strong-8002")
#: A dev setup: a dev profile runs any compose file, so the stamped fleet
#: gate 1 holds a live `serve up` to is not in the way of these tests.
DEV_SETUP = """\
profile: dev
units:
  only:
    address: http://box-a.invalid:8001
    model: a-model
    rig: box-a
    engine: vllm
ladder:
- only
sandbox:
  mode: tempdir
"""


def scan_payload(
    *,
    hostname: str = HOSTNAME,
    cards: tuple[tuple[int, str, int], ...] = ((0, "Invented Card 16G", 16384),),
    ram_gb: float = 62.7,
    docker: str | None = DOCKER,
    machine_id: str = "0a1b2c3d4e5f6a7b",
) -> dict[str, object]:
    """What the shipped rig scanner prints for the invented rig."""
    return {
        "machine": {"id": machine_id, "host": hostname, "kernel": "6.8.0-invented"},
        "gpus": [
            {
                "index": index,
                "name": name,
                "vram": {
                    "total_mib": total,
                    "used_mib": 100,
                    "free_mib": total - 500,
                    "reserved_mib": 400,
                },
            }
            for index, name, total in cards
        ],
        "memory": {"total_gb": ram_gb, "available_gb": ram_gb - 4.0},
        "cpu": {"cores": 16, "threads": 16},
        "bandwidth": {"measured_gbps": 20.0, "how": "an invented copy"},
        "disk": {"path": "/home/user/.cache/mcgyvr/weights", "free_gb": 400.0},
        "docker": docker,
        "notes": [],
        "facts": [],
    }


def machine(
    tmp_path: Path,
    *,
    scan: dict[str, object] | None = None,
    containers: str = "none",
    gpu_procs: str = "none",
    pending: tuple[str, ...] = UNITS,
) -> Path:
    """The stub machine: the folder to put first on PATH.

    ``scan`` is what the rig scanner answers, ``containers`` and ``gpu_procs``
    what the rig reader prints before the run, and ``pending`` the containers
    a ``docker compose up`` brings up.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    onedoor.ssh_stub(stubs)
    onedoor.docker_stub(stubs)
    set_scan(stubs, scan or scan_payload())
    (stubs / "snapshot.txt").write_text(
        f"uptime_since=2026-10-01T00:00:00Z\nhostname={HOSTNAME}\n"
        f"docker={DOCKER}\ngpu_procs={gpu_procs}\ncontainers={containers}\n",
        encoding="utf-8",
    )
    if pending:
        (stubs / "serving-pending").write_text(
            "".join(f"{name}\n" for name in pending), encoding="utf-8"
        )
    return stubs


def set_scan(stubs: Path, scan: dict[str, object]) -> None:
    """What the rig scanner answers from now on."""
    (stubs / "rigscan.json").write_text(json.dumps(scan), encoding="utf-8")


def install_root(tmp_path: Path) -> Path:
    """A run root that is not a lab checkout: what an install runs from."""
    root = tmp_path / "install-root"
    root.mkdir(exist_ok=True)
    return root


def lab_root(tmp_path: Path) -> Path:
    """A run root that is a lab checkout: it holds the round's folder
    (:data:`mcgyvr.serving.run.LAB_MARK`), and a round module in it that
    admits the tree, as callergates' stand-in does."""
    root = tmp_path / "lab-root"
    onedoor.executable(
        root / run.LAB_MARK / "product.py",
        "class ProductError(Exception):\n"
        "    pass\n"
        "\n"
        "\n"
        "def ensure_open():\n"
        "    return 'round-invented', '0' * 64\n",
    )
    return root


def compose_file(where: Path, names: tuple[str, ...] = UNITS) -> Path:
    """A compose file of the invented units, each reserving card 0."""
    services = {
        f"unit{i}": {
            "image": "llamacpp:b10644-L3",
            "container_name": name,
            "command": ["--model", "/models/x.gguf", "--port", str(8001 + i)],
            "network_mode": "host",
            "deploy": {
                "resources": {
                    "reservations": {
                        "devices": [{"driver": "nvidia", "device_ids": ["0"]}]
                    }
                }
            },
        }
        for i, name in enumerate(names)
    }
    path = where / "compose.box-a.yml"
    path.write_text(json.dumps({"services": services}), encoding="utf-8")
    return path


def dev_setup(where: Path) -> Path:
    path = where / "fleet.yaml"
    path.write_text(DEV_SETUP, encoding="utf-8")
    return path


def door(
    argv: list[str],
    *,
    stubs: Path,
    run_root: Path,
    cwd: Path,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """``python -m mcgyvr.serving.run ARGV`` over the stub machine, to completion."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("RUN_", "DOCKER_"))
    }
    parts = [str(stubs), str(Path(sys.executable).parent)]
    parts += (env.get("PATH") or os.defpath).split(os.pathsep)
    env["PATH"] = os.pathsep.join(parts)
    env["MCGYVR_RUN_ROOT"] = str(run_root)
    env["STUB_RIG_HOME"] = "/home/user"
    env["STUB_FREE"] = "15884"
    env["STUB_USED"] = "100"
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "mcgyvr.serving.run", *argv],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def serve(
    direction: str,
    compose: Path,
    *,
    mode: str | None = "user",
    extra: tuple[str, ...] = (),
) -> list[str]:
    """``serve <direction>`` of the invented rig, with ``--mode`` when given."""
    argv = ["serve", direction, "--host", RIG, "--compose", str(compose)]
    argv += ["--date", RUN_DATE, *extra]
    return argv + (["--mode", mode] if mode is not None else [])


def door_logs(home: Path) -> list[Path]:
    """Every run folder the door's user-mode log holds, under the data folder."""
    base = home / ".local" / "state" / "mcgyvr" / "door"
    if not base.is_dir():
        return []
    return sorted(path for path in base.glob("*/*") if path.is_dir())


def home() -> Path:
    """The HOME this test runs under (``tests/conftest.py`` makes one per test)."""
    return Path(os.environ["HOME"])
