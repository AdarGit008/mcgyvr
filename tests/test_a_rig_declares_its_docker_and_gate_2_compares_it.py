"""Gate 2 holds the rig to its docker version, not only its hardware.

On 2026-09-03 the same A3 image listed ``Vulkan0`` on srv2 and benched the CPU
on srv1, twice, with identical driver libraries injected. The difference was
docker: 29.7.1 on srv2 routes ``--gpus all`` through the CDI spec, which
mounts the NVIDIA Vulkan ICD manifest; 29.1.3 on srv1 routed it through the
legacy hook, which does not. Nothing in ``hosts.json`` said the two rigs ran
different dockers, so nothing could refuse the comparison.

Both rigs now run docker-ce 29.7.2, ``hosts.json[host].rig.docker`` says so,
``rig_snapshot`` reads it (``docker version --format '{{.Server.Version}}'``,
through the ``RUN_DOCKER`` seam), and gate 2 compares it with the rest.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests import onedoor

DOCKER = "29.7.2"


@pytest.mark.parametrize("host", ["srv1", "srv2"])
def test_hosts_json_declares_docker_for_each_rig(host: str) -> None:
    document = json.loads(onedoor.HOSTS_JSON.read_text(encoding="utf-8"))
    rig = document[host]["rig"]
    assert rig.get("docker") == DOCKER, (
        f"hosts.json[{host!r}].rig.docker is {rig.get('docker')!r}; both rigs "
        f"were upgraded to docker-ce {DOCKER} on 2026-09-03"
    )


def test_the_snapshot_reads_docker_through_the_seam(tmp_path: Path) -> None:
    stub = onedoor.executable(
        tmp_path / "docker",
        "#!/usr/bin/env bash\n"
        '[ "${1:-}" = version ] && { printf \'%s\\n\' "29.7.2"; exit 0; }\n'
        "exit 1\n",
    )
    result = subprocess.run(
        ["bash", "-c", '. "$1"; _rig_docker', "bash", str(onedoor.COMMON_SH)],
        env={"PATH": "/usr/bin:/bin", "RUN_DOCKER": str(stub)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "29.7.2", result.stdout


def test_a_daemon_that_does_not_answer_is_an_unread_rig(tmp_path: Path) -> None:
    stub = onedoor.executable(tmp_path / "docker", "#!/usr/bin/env bash\nexit 1\n")
    result = subprocess.run(
        ["bash", "-c", '. "$1"; _rig_docker', "bash", str(onedoor.COMMON_SH)],
        env={"PATH": "/usr/bin:/bin", "RUN_DOCKER": str(stub)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "docker" in result.stderr, result.stderr


def test_a_rig_on_the_old_docker_is_refused_at_gate_2(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    lines = onedoor.snapshot_lines("srv1", docker="29.1.3")
    reading = onedoor.executable(
        stubs / "rig-snapshot", f"#!/usr/bin/env bash\nprintf '%s' '{lines}'\n"
    )
    env = onedoor.door_env(root, stubs, rig=reading)
    result = onedoor.door(root, ["alpha", "probe", "--host", "srv1"], env)
    assert result.returncode == 2, (result.stdout, result.stderr)
    for word in ("docker", DOCKER, "29.1.3"):
        assert word in result.stderr, f"{word!r} is not in the refusal: {result.stderr}"
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e").exists()
