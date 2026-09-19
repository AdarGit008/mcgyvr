"""Every sandbox command ends within its timeout and leaves nothing running.

And a timeout never poisons the attempts after it. Three ways that failed:

- **Temp directory.** Only the direct child was killed on a timeout, so a
  grandchild outlived the task, and a command that exited 0 with a background
  child still holding its output pipe was reported as timed out.
- **Container.** A timeout killed the whole task container, and every later
  command in the task was exec'd into a dead container and charged to the
  worker. A background process a command left behind kept running between
  commands — the window in which it could swap a symlink in under a path the
  host has just checked and is about to write.
- **The docker CLI and the floor.** No docker call carried a bound, and the
  deterministic floor ran its tools with none.

Plus the two leaks next to them: a container whose start failed was never
removed, and a workspace the host could not list was left behind silently.
And the tidy-ups that run ruff did so under a different configuration than the
gate that judges their output.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from mcgyvr import cleanup, repair
from mcgyvr import drive as drive_module
from mcgyvr.contract import loads as load_contract
from mcgyvr.deterministic import tool_steps
from mcgyvr.drive import run_tool_step
from mcgyvr.gate.adapter import require_tool
from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox import image as image_module
from mcgyvr.sandbox.base import CommandResult, Sandbox, SandboxError
from mcgyvr.sandbox.docker import DockerSandbox, _ExecResult
from mcgyvr.sandbox.image import DockerResult
from mcgyvr.sandbox.tempdir import TempDirSandbox


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "src" / "pkg" / "messy.py").write_text("x = 1\n", encoding="utf-8")
    ident = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t.invalid",
    }
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"],
        check=True,
        env={**os.environ, **ident},
    )
    return repo


def _alive(pid: int) -> bool:
    """Whether ``pid`` is a live process: present and not a zombie."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, IndexError):
        return False
    return state not in {"Z", "X"}


def _gone_soon(pid: int) -> bool:
    """``pid`` is dead now or within a second: a kill takes a moment to land."""
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


# --- temp directory: the whole process group, not the direct child ----------


def test_a_command_that_exits_is_not_timed_out_by_a_child_it_left_behind(
    git_repo: Path,
) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        started = time.monotonic()
        result = sandbox.run(
            ["sh", "-c", "sleep 60 & echo $! > bg.pid; exit 0"], timeout=3
        )
        elapsed = time.monotonic() - started
        pid = int((sandbox.workspace / "bg.pid").read_text())
    assert not result.timed_out
    assert result.exit_code == 0
    assert elapsed < 2
    assert _gone_soon(pid), "the background child outlived its command"


def test_a_timed_out_command_leaves_no_grandchild_running(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(
            ["sh", "-c", "sleep 60 & echo $! > bg.pid; sleep 60"], timeout=1
        )
        pid = int((sandbox.workspace / "bg.pid").read_text())
    assert result.timed_out
    assert _gone_soon(pid), "the grandchild outlived the timeout"


def test_nothing_a_command_started_writes_after_the_command_returns(
    git_repo: Path,
) -> None:
    """The window ``scope.inside`` leaves between its check and the write.

    A path is checked on the host and then written. A process a command left
    running could swap a symlink in between the two; one that no longer exists
    cannot.
    """
    with TempDirSandbox(git_repo) as sandbox:
        sandbox.run(
            ["sh", "-c", "(sleep 1; ln -s /etc src/pkg/swapped) & exit 0"],
            timeout=10,
        )
        time.sleep(2)
        assert not (sandbox.workspace / "src" / "pkg" / "swapped").is_symlink()


# --- container: a timeout ends the command, never the container --------------


class FakeDaemon:
    """One container, modelled as far as a timeout and a leftover need.

    ``kill`` stops the container and everything in it, ``start`` runs its
    keepalive again, and an exec into a stopped container fails the way docker
    fails it — exit 1, which a gate reads as the worker's change failing.
    ``top`` lists the keepalive plus whatever an exec left behind.
    """

    def __init__(
        self,
        *,
        run_ok: bool = True,
        start_ok: bool = True,
        rm_ok: bool = True,
    ) -> None:
        self.calls: list[list[str]] = []
        self.running = False
        self.leftovers: list[str] = []
        self.execs: list[tuple[_ExecResult, list[str]]] = []
        self._run_ok = run_ok
        self._start_ok = start_ok
        self._rm_ok = rm_ok

    def runner(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        self.calls.append(list(args))
        verb = args[0]
        if verb == "run":
            if not self._run_ok:
                return DockerResult(125, "", "OCI runtime create failed")
            self.running = True
        elif verb in {"kill", "rm"}:
            if verb == "rm" and not self._rm_ok:
                return DockerResult(1, "", "Error response from daemon: hiccup")
            self.running = False
            self.leftovers = []
        elif verb in {"start", "restart"}:
            self.leftovers = []
            if not self._start_ok:
                self.running = False
                return DockerResult(1, "", "Error response from daemon: cannot start")
            self.running = True
        elif verb == "top":
            if not self.running:
                return DockerResult(1, "", "container is not running")
            rows = ["PID CMD", "101 sleep infinity"]
            rows += [f"{200 + i} {cmd}" for i, cmd in enumerate(self.leftovers)]
            return DockerResult(0, "\n".join(rows) + "\n", "")
        return DockerResult(0, "", "")

    def exec(self, exec_args: Sequence[str], timeout: float | None) -> _ExecResult:
        if not self.running:
            return _ExecResult(1, "", "Error response: container is not running", False)
        result, left = self.execs.pop(0) if self.execs else (_ok(), [])
        self.leftovers += left
        return result


def _ok() -> _ExecResult:
    return _ExecResult(0, "", "", False)


def _timed_out() -> _ExecResult:
    return _ExecResult(-1, "", "", True)


def _open(daemon: FakeDaemon, repo: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    monkeypatch.setattr(docker_module, "_docker_exec", daemon.exec)
    return DockerSandbox(repo, image="img:latest", runner=daemon.runner)


def test_a_timed_out_command_does_not_poison_the_next_one(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = FakeDaemon()
    daemon.execs = [(_timed_out(), ["sleep 60"])]
    with _open(daemon, git_repo, monkeypatch) as sandbox:
        first = sandbox.run(["sleep", "60"], timeout=1)
        second = sandbox.run(["true"], timeout=10)
        assert daemon.leftovers == []
    assert first.timed_out
    assert second.ok, second.stderr


def test_a_command_that_exits_leaves_nothing_running_in_the_container(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = FakeDaemon()
    daemon.execs = [(_ok(), ["sleep 60"])]
    with _open(daemon, git_repo, monkeypatch) as sandbox:
        result = sandbox.run(["sh", "-c", "sleep 60 &"], timeout=10)
        assert result.ok
        assert daemon.leftovers == [], "a background process outlived its command"
        assert daemon.running


def test_a_container_that_cannot_come_back_refuses_the_next_command(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not an exec into a dead container, which the gate charges to the worker."""
    daemon = FakeDaemon(start_ok=False)
    daemon.execs = [(_timed_out(), ["sleep 60"])]
    with _open(daemon, git_repo, monkeypatch) as sandbox:
        sandbox.run(["sleep", "60"], timeout=1)
        with pytest.raises(SandboxError):
            sandbox.run(["true"], timeout=10)


def test_a_container_whose_start_failed_is_still_removed(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = FakeDaemon(run_ok=False)
    with pytest.raises(SandboxError), _open(daemon, git_repo, monkeypatch):
        pass
    (run,) = [c for c in daemon.calls if c[0] == "run"]
    name = run[run.index("--name") + 1]
    assert ["rm", "--force", name] in daemon.calls


def test_a_container_that_could_not_be_removed_is_named(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    daemon = FakeDaemon(rm_ok=False)
    with _open(daemon, git_repo, monkeypatch):
        pass
    (run,) = [c for c in daemon.calls if c[0] == "run"]
    name = run[run.index("--name") + 1]
    assert name in capsys.readouterr().err


# --- the docker CLI and the floor carry a bound -----------------------------


def test_a_docker_call_that_hangs_returns_within_its_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in image_module.DAEMON_OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    fake = tmp_path / "bin" / "docker"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(image_module, "DOCKER_CALL_TIMEOUT_S", 0.5, raising=False)

    started = time.monotonic()
    result = image_module.subprocess_runner(["rm", "--force", "mcgyvr-task-x"])
    assert time.monotonic() - started < 3
    assert not result.ok
    assert "rm" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ["pull", "python:3.12-slim"],
        ["build", "--tag", "t", "."],
        ["run", "--detach", "img", "sleep", "infinity"],
        ["rm", "--force", "c"],
        ["kill", "c"],
        ["image", "inspect", "t"],
    ],
)
def test_every_docker_call_carries_a_bound(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in image_module.DAEMON_OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "mcgyvr.sandbox.image.shutil.which", lambda _: "/usr/bin/docker"
    )
    seen: list[object] = []

    def fake_run(
        argv: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        seen.append(kwargs.get("timeout"))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    image_module.subprocess_runner(args)
    (timeout,) = seen
    assert isinstance(timeout, int | float) and timeout > 0


class _RecordingSandbox(Sandbox):
    isolation = "recording"

    def __init__(self) -> None:
        super().__init__(".")
        self.timeouts: list[float | None] = []

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.timeouts.append(timeout)
        return CommandResult(command=tuple(command), exit_code=0, stdout="", stderr="")

    def _start(self) -> None:
        pass

    def _stop(self) -> None:
        pass


def test_a_floor_tool_step_is_held_to_the_task_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = load_contract(
        "id: tidy\ntask_type: format\ntask: Reformat the module.\n"
        'target: src/pkg/messy.py\nscope:\n  allow: ["src/**"]\n'
    )
    (step,) = tool_steps(contract)
    monkeypatch.setattr(drive_module, "task_ceiling", lambda: 7.0)
    sandbox = _RecordingSandbox()
    run_tool_step(step, sandbox)
    assert sandbox.timeouts == [7.0]


# --- teardown that fails is not silent --------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 directory")
def test_a_workspace_holding_an_unreadable_directory_is_still_removed(
    git_repo: Path,
) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        workspace = sandbox.workspace
        locked = workspace / "locked"
        (locked / "inner").mkdir(parents=True)
        (locked / "inner" / "f").write_text("x", encoding="utf-8")
        locked.chmod(0)
    try:
        assert not workspace.exists()
    finally:
        if workspace.exists():
            locked.chmod(0o700)
            subprocess.run(["rm", "-rf", str(workspace)], check=False)


# --- ruff under the gate's configuration ------------------------------------


@pytest.fixture
def users_ruff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A user-level ruff config that disagrees with the gate, and a bare repo."""
    config = tmp_path / "xdg" / "ruff"
    config.mkdir(parents=True)
    (config / "ruff.toml").write_text(
        'line-length = 120\nbuiltins = ["Path"]\n', encoding="utf-8"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config.parent))
    repo = tmp_path / "bare"
    repo.mkdir()
    return repo


def test_cleanup_formats_to_the_width_the_gate_checks(users_ruff: Path) -> None:
    long_line = (
        "result = some_function_name(argument_one, argument_two, "
        "argument_three, argument_four_xyz_long)\n"
    )
    tidied = cleanup._ruff_format(long_line, "a.py", users_ruff)
    assert tidied == (
        "result = some_function_name(\n"
        "    argument_one, argument_two, argument_three, argument_four_xyz_long\n"
        ")\n"
    )


def test_repair_finds_undefined_names_under_the_gates_config(users_ruff: Path) -> None:
    (users_ruff / "a.py").write_text('x = Path("a")\n', encoding="utf-8")
    issues: list[str] = []
    found = repair._undefined_names(users_ruff, require_tool("ruff"), ["a.py"], issues)
    assert found == {"a.py": {"Path"}}, issues
