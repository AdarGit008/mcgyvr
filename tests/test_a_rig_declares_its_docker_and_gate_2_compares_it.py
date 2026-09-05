"""The rig is held to its docker version, by gate 2 and again by gate 3.

On 2026-09-03 the same A3 image listed ``Vulkan0`` on srv2 and benched the CPU
on srv1, twice, with identical driver libraries injected. The difference was
docker: 29.7.1 on srv2 routes ``--gpus all`` through the CDI spec, which
mounts the NVIDIA Vulkan ICD manifest; 29.1.3 on srv1 routed it through the
legacy hook, which does not. Nothing in ``hosts.json`` said the two rigs ran
different dockers, so nothing could refuse the comparison.

Both rigs now run docker-ce 29.7.2 and ``hosts.json[host].rig.docker`` says
so. The reader gate 2 ships to the rig (``rig-snapshot.sh:docker_version``)
prints the daemon's version beside the hardware and refuses rather than
guesses when it cannot; gate 2 (``02-rig.py``) compares it with the
declaration like every other key. Gate 3 (``03-image.py``) then asks the
daemon the door's ``docker`` reaches — the rig's, over ``-H ssh://HOST`` —
for its name and version: the daemon a tag is resolved through must be the
machine gate 2 read, on the docker hosts.json declares.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

DOCKER = "29.7.2"
OLD = "29.1.3"


@pytest.mark.parametrize("host", ["srv1", "srv2"])
def test_hosts_json_declares_docker_for_each_rig(host: str) -> None:
    document = json.loads(onedoor.HOSTS_JSON.read_text(encoding="utf-8"))
    rig = document[host]["rig"]
    assert rig.get("docker") == DOCKER, (
        f"hosts.json[{host!r}].rig.docker is {rig.get('docker')!r}; both rigs "
        f"were upgraded to docker-ce {DOCKER} on 2026-09-03"
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def test_a_rig_on_the_old_docker_is_refused_at_gate_2(
    root: Path, tmp_path: Path
) -> None:
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", docker=OLD)
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    for word in ("docker", DOCKER, OLD):
        assert word in result.stderr, f"{word!r} is not in the refusal: {result.stderr}"
    assert onedoor.written_under_records(root) == []
    assert onedoor.docker_log(root) == [], "gate 3 ran after gate 2 refused"
    assert not (tmp_path / "e").exists()


def test_a_daemon_on_another_docker_than_declared_is_refused_at_gate_3(
    root: Path, tmp_path: Path
) -> None:
    """The rig reads as declared; the daemon ``docker`` reaches does not."""
    (onedoor.stubs_dir(root) / "docker-version").write_text(OLD, encoding="utf-8")
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "gate 3" in result.stderr, result.stderr
    for word in (OLD, DOCKER, "hosts.json"):
        assert word in result.stderr, f"{word!r} is not in the refusal: {result.stderr}"
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e").exists()


def test_a_daemon_that_is_not_the_machine_gate_2_read_is_refused_at_gate_3(
    root: Path, tmp_path: Path
) -> None:
    (onedoor.stubs_dir(root) / "docker-name").write_text("srv2", encoding="utf-8")
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "the daemon `docker` reaches calls itself" in result.stderr, result.stderr
    assert "srv2" in result.stderr and "srv1" in result.stderr, result.stderr
    assert onedoor.written_under_records(root) == []
    assert not (tmp_path / "e").exists()
