"""Gate 3: the daemon a tag is resolved through must be the machine gate 2 read.

The same image can list ``Vulkan0`` on one rig and bench the CPU on another,
with identical driver libraries injected, when the dockers differ: a docker
that routes ``--gpus all`` through the CDI spec mounts the NVIDIA Vulkan ICD
manifest, and one that routes it through the legacy hook does not. A tag
resolved against one daemon and a container started on another is the hole
gate 3 closes, so the daemon the door's ``docker`` reaches must answer, and
must answer as the machine gate 2 read.

In user mode (a door run from an install, ``--mode user``) there is no
``hosts.json`` and no declared docker version: the daemon must answer and be
the machine gate 2 read, and the version it runs is said, not compared.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


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
