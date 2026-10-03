"""A task container sees the dependency folders its image installed.

The image mcgyvr builds installs the repository's dependencies in
``/workspace``: ``uv sync`` makes ``/workspace/.venv`` and ``npm ci`` makes
``/workspace/node_modules``. The task's workspace is bind-mounted over
``/workspace``, which hides both, so an acceptance command lost the project's
own libraries and a checker installed with them was not on the PATH.

So each folder the image actually populated is kept visible: an anonymous
volume over its path, which Docker fills from the image when the container is
created. The image is asked once which of the two it holds. A folder it does
not hold gets no volume, and an image the user names (``sandbox.image``) is
run as it is.

The rest of the container holds as it did: the workspace's ``.git`` is mounted
read-only, and teardown removes the container *and* its anonymous volumes. A
reset between attempts runs ``git clean`` on the host, where each volume's
mount point is an empty folder; removing it would take the volume out of the
running container, so a reset leaves those mount points alone and sweeps
everything else.

What a real daemon does is checked up to the daemon, through recorded argv.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.docker import DockerSandbox, _ExecResult
from mcgyvr.sandbox.image import LABEL_BASE_DIGEST, DockerResult

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


@pytest.fixture
def uv_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (repo / "app.py").write_text("import six\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"],
        check=True,
        env={**os.environ, **_IDENTITY},
    )
    return repo


class _Daemon:
    """A daemon whose cached image holds the folders it is told it holds."""

    def __init__(self, holds: Sequence[str]) -> None:
        self.holds = tuple(holds)
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        cmd = list(args)
        self.calls.append(cmd)
        if cmd[:2] == ["image", "inspect"]:
            fmt = cmd[3] if len(cmd) > 3 else ""
            digest = "python:3.12-slim@sha256:pinned"
            return DockerResult(0, digest if LABEL_BASE_DIGEST in fmt else "", "")
        if cmd[:2] == ["run", "--rm"]:
            return DockerResult(0, "".join(f"{d}\n" for d in self.holds), "")
        return DockerResult(0, "container-id", "")

    def task_run(self) -> list[str]:
        (run,) = [c for c in self.calls if c[:2] == ["run", "--detach"]]
        return run

    def probes(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["run", "--rm"]]


def _volumes(run: list[str]) -> list[str]:
    return [run[i + 1] for i, token in enumerate(run) if token == "--volume"]


@pytest.fixture(autouse=True)
def _no_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        docker_module, "_docker_exec", lambda a, t: _ExecResult(0, "", "", False)
    )


def test_each_folder_the_image_holds_gets_a_volume_over_the_mount(
    uv_repo: Path,
) -> None:
    daemon = _Daemon([".venv", "node_modules"])
    with DockerSandbox(uv_repo, runner=daemon) as sandbox:
        workspace = sandbox.workspace
        volumes = _volumes(daemon.task_run())

    assert f"{workspace}:/workspace" in volumes
    assert f"{workspace}/.git:/workspace/.git:ro" in volumes
    assert "/workspace/.venv" in volumes
    assert "/workspace/node_modules" in volumes


def test_a_folder_the_image_does_not_hold_gets_no_volume(uv_repo: Path) -> None:
    daemon = _Daemon([".venv"])
    with DockerSandbox(uv_repo, runner=daemon):
        volumes = _volumes(daemon.task_run())

    assert "/workspace/.venv" in volumes
    assert "/workspace/node_modules" not in volumes


def test_the_image_is_asked_without_a_network_and_with_no_workspace(
    uv_repo: Path,
) -> None:
    daemon = _Daemon([".venv"])
    with DockerSandbox(uv_repo, runner=daemon):
        (probe,) = daemon.probes()

    assert "--network" in probe and probe[probe.index("--network") + 1] == "none"
    assert "--volume" not in probe


def test_an_image_the_user_names_is_run_as_it_is(uv_repo: Path) -> None:
    daemon = _Daemon([".venv"])
    with DockerSandbox(uv_repo, image="their/image:1", runner=daemon):
        volumes = _volumes(daemon.task_run())

    assert daemon.probes() == []
    assert not any(v.startswith("/workspace/") for v in volumes)


def test_teardown_removes_the_container_and_its_volumes(uv_repo: Path) -> None:
    daemon = _Daemon([".venv"])
    with DockerSandbox(uv_repo, runner=daemon):
        name = daemon.task_run()[daemon.task_run().index("--name") + 1]

    assert ["rm", "--force", "--volumes", name] in daemon.calls


def test_a_reset_leaves_the_volume_mount_points_and_sweeps_the_rest(
    uv_repo: Path,
) -> None:
    daemon = _Daemon([".venv", "node_modules"])
    with DockerSandbox(uv_repo, runner=daemon) as sandbox:
        workspace = sandbox.workspace
        # What the daemon leaves on the host side of the bind mount.
        (workspace / ".venv").mkdir()
        (workspace / "node_modules").mkdir()
        (workspace / "scratch.txt").write_text("left by an attempt\n")
        (workspace / "build").mkdir()
        (workspace / "build" / "out.o").write_text("x")

        sandbox.reset()

        assert (workspace / ".venv").is_dir()
        assert (workspace / "node_modules").is_dir()
        assert not (workspace / "scratch.txt").exists()
        assert not (workspace / "build").exists()


def test_a_restore_leaves_the_volume_mount_points_too(uv_repo: Path) -> None:
    daemon = _Daemon([".venv"])
    with DockerSandbox(uv_repo, runner=daemon) as sandbox:
        workspace = sandbox.workspace
        (workspace / ".venv").mkdir()
        snapshot = sandbox.checkpoint()
        (workspace / "scratch.txt").write_text("left by a draw\n")

        sandbox.restore_to(snapshot)
        sandbox.drop_checkpoint()

        assert (workspace / ".venv").is_dir()
        assert not (workspace / "scratch.txt").exists()
