"""The container mode, with the daemon replaced by a recording runner.

The container path cannot run in CI — there is no daemon — so what is proven
here is everything up to the daemon: the argv that would be run, the
platform-specific host-loopback handling, the lifecycle's teardown, and the
security invariant that no credential-shaped variable can enter a container.
That last one is asserted, not reviewed, because ``SECURITY.md`` makes it
red-failing.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.base import credential_env_names
from mcgyvr.sandbox.docker import (
    ENDPOINTS_ENV,
    HOST_ALIAS,
    DockerSandbox,
    Resources,
    _exec_args,
    _ExecResult,
    _run_args,
    host_gateway_args,
    translate_endpoint,
)
from mcgyvr.sandbox.image import DockerResult


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('x')\n", encoding="utf-8")
    ident = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t.invalid",
    }
    import os

    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"],
        check=True,
        env={**os.environ, **ident},
    )
    return repo


class RecordingRunner:
    """Records docker management calls (run/rm/kill) and answers them ok."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        self.calls.append(list(args))
        return DockerResult(0, "container-id", "")

    def commands(self) -> list[str]:
        return [c[0] for c in self.calls]


# --- host-loopback translation (#31) -------------------------------------


def test_localhost_endpoint_is_rewritten_to_the_host_alias() -> None:
    assert translate_endpoint("http://localhost:11434") == f"http://{HOST_ALIAS}:11434"


def test_loopback_ip_is_rewritten_and_port_preserved() -> None:
    assert translate_endpoint("http://127.0.0.1:8080") == f"http://{HOST_ALIAS}:8080"


def test_a_remote_endpoint_is_left_untouched() -> None:
    url = "http://gpu-box.lan:11434"
    assert translate_endpoint(url) == url


def test_linux_maps_the_host_gateway_but_macos_does_not() -> None:
    assert host_gateway_args("Linux") == ["--add-host", f"{HOST_ALIAS}:host-gateway"]
    assert host_gateway_args("Darwin") == []


# --- argv construction ----------------------------------------------------


def test_run_args_bind_mount_bounds_and_keepalive(tmp_path: Path) -> None:
    args = _run_args(
        name="mcgyvr-task-abc",
        image="img:latest",
        workspace=tmp_path,
        resources=Resources(memory="1g", cpus="2", pids=256),
        gateway=["--add-host", f"{HOST_ALIAS}:host-gateway"],
        user="1000:1000",
        env={"HOME": "/workspace"},
    )
    assert args[:2] == ["run", "--detach"]
    assert "--volume" in args and f"{tmp_path}:/workspace" in args
    assert "--memory" in args and "1g" in args
    assert "--pids-limit" in args and "256" in args
    assert "--add-host" in args
    assert "--user" in args and "1000:1000" in args
    # Kept alive so many commands can exec into one container per task.
    assert args[-3:] == ["img:latest", "sleep", "infinity"]


def test_exec_args_target_the_workspace_and_container() -> None:
    args = _exec_args(
        name="c1", command=["pytest", "-q"], env={"MCGYVR_ENDPOINTS": "http://x"}
    )
    assert args[:3] == ["exec", "--workdir", "/workspace"]
    assert "--env" in args and "MCGYVR_ENDPOINTS=http://x" in args
    assert args[-3:] == ["c1", "pytest", "-q"]


# --- the credential invariant (#31, SECURITY.md) -------------------------


def test_container_ambient_env_carries_endpoints_and_no_credential(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Even with credentials in the host environment, none reach the container.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    sandbox = DockerSandbox(
        git_repo,
        image="img:latest",
        endpoints=["http://localhost:11434"],
        runner=RecordingRunner(),
        system="Linux",
    )
    env = sandbox._container_env()
    assert credential_env_names(env) == frozenset()
    # The endpoint is present, translated for reachability.
    assert env[ENDPOINTS_ENV] == f"http://{HOST_ALIAS}:11434"


def test_a_credential_forwarded_to_run_never_reaches_exec(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_exec(exec_args: Sequence[str], timeout: float | None) -> _ExecResult:
        captured["args"] = list(exec_args)
        return _ExecResult(0, "", "", False)

    monkeypatch.setattr(docker_module, "_docker_exec", fake_exec)
    with DockerSandbox(git_repo, image="img:latest", runner=RecordingRunner()) as sb:
        sb.run(["pytest"], env={"OPENAI_API_KEY": "leak", "SAFE_VAR": "ok"})

    env_pairs = [
        captured["args"][i + 1]
        for i, tok in enumerate(captured["args"])
        if tok == "--env"
    ]
    names = {pair.split("=", 1)[0] for pair in env_pairs}
    assert credential_env_names(dict(p.split("=", 1) for p in env_pairs)) == frozenset()
    assert "OPENAI_API_KEY" not in names
    assert "SAFE_VAR" in names


# --- lifecycle ------------------------------------------------------------


def test_start_runs_a_container_and_exit_removes_it(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        docker_module, "_docker_exec", lambda a, t: _ExecResult(0, "", "", False)
    )
    runner = RecordingRunner()
    with DockerSandbox(git_repo, image="img:latest", runner=runner):
        assert "run" in runner.commands()
    # Force-removed on exit.
    assert any(c[:2] == ["rm", "--force"] for c in runner.calls)


def test_container_is_removed_even_when_the_body_raises(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        docker_module, "_docker_exec", lambda a, t: _ExecResult(0, "", "", False)
    )
    runner = RecordingRunner()
    with (
        pytest.raises(RuntimeError),
        DockerSandbox(git_repo, image="img:latest", runner=runner),
    ):
        raise RuntimeError("task blew up")
    assert any(c[:2] == ["rm", "--force"] for c in runner.calls)


def test_a_timed_out_command_kills_the_container(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        docker_module, "_docker_exec", lambda a, t: _ExecResult(-1, "", "", True)
    )
    runner = RecordingRunner()
    with DockerSandbox(git_repo, image="img:latest", runner=runner) as sb:
        result = sb.run(["sleep", "100"], timeout=0.1)
        assert result.timed_out
    assert "kill" in runner.commands()


def test_run_before_open_is_an_error(git_repo: Path) -> None:
    from mcgyvr.sandbox.base import SandboxError

    sandbox = DockerSandbox(git_repo, image="img:latest", runner=RecordingRunner())
    with pytest.raises(SandboxError):
        sandbox.run(["pytest"])
