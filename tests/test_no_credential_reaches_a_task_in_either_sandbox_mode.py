"""No provider credential reaches a task, in either sandbox mode.

``SECURITY.md`` makes this load-bearing: API keys are read by the orchestrator
process only, and a task receives the repository and the worker endpoint,
never a key. A key can reach a task by two roads, and both are closed in both
modes:

* **the environment** — a key exported in the shell that started mcgyvr, a
  key a caller forwards to :meth:`~mcgyvr.sandbox.base.Sandbox.run`, or a key
  carried inside a URL's ``user:password@``;
* **files** — a key in the checkout's ignored ``.env``, or in the user's home
  directory, read by a command through a mount or through ``HOME``.

The container mode is proven up to the daemon: every argv handed to ``docker``
is recorded, and a key that is in none of them cannot be in the container.
The temp-directory mode is driven for real.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.base import Sandbox
from mcgyvr.sandbox.docker import DockerSandbox, _ExecResult
from mcgyvr.sandbox.image import DockerResult
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests import livejournal as lj

#: Invented keys, each under a name a provider or a tool really reads.
KEYS = {
    "ANTHROPIC_API_KEY": "sk-ant-test-0000000000000000",
    "OPENAI_API_KEY": "sk-test-1111111111111111111111",
    "HF_TOKEN": "hf_test_2222222222222222",
    "GITHUB_TOKEN": "ghp_test_3333333333333333",
    "MYSERVICE_SECRET": "test-secret-4444",
}

#: A credential under a name that says nothing, inside a URL.
INDEX_URL = ("PIP_INDEX_URL", "https://user:test-pass-5555@index.invalid/simple")

#: What a key in the checkout's ignored dotenv file looks like.
DOTENV_KEY = "test-dotenv-6666"

#: What a key in the user's own home directory looks like.
HOME_KEY = "test-home-7777"


class _Daemon:
    """Every argv the container mode hands to ``docker``, answered ok."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        self.argvs.append(list(args))
        return DockerResult(0, "container-id", "")

    def exec(self, args: Sequence[str], timeout: float | None) -> _ExecResult:
        self.argvs.append(list(args))
        return _ExecResult(0, "", "", False)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A host HOME holding a credential file, and every key exported."""
    home = tmp_path / "home"
    (home / ".config" / "provider").mkdir(parents=True)
    (home / ".config" / "provider" / "credentials").write_text(
        f"key = {HOME_KEY}\n", encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(name, raising=False)
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(*INDEX_URL)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    return home


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout whose ignored ``.env`` holds a key, as checkouts do."""
    repo = lj.make_repo(tmp_path / "repo")
    with (repo / ".gitignore").open("a", encoding="utf-8") as ignore:
        ignore.write(".env\n")
    lj.git(repo, "commit", "-qam", "ignore the dotenv file")
    (repo / ".env").write_text(f"API_KEY={DOTENV_KEY}\n", encoding="utf-8")
    return repo


def _secrets() -> list[str]:
    return [*KEYS.values(), "test-pass-5555", DOTENV_KEY, HOME_KEY]


@pytest.fixture(params=["tempdir", "docker"])
def opened(
    request: pytest.FixtureRequest,
    repo: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Sandbox, _Daemon]]:
    daemon = _Daemon()
    sandbox: Sandbox
    if request.param == "docker":
        monkeypatch.setattr(docker_module, "_docker_exec", daemon.exec)
        sandbox = DockerSandbox(
            repo,
            image="img:latest",
            endpoints=["http://user:test-pass-5555@localhost:11434"],
            runner=daemon,
            system="Linux",
        )
    else:
        sandbox = TempDirSandbox(repo)
    with sandbox:
        yield sandbox, daemon


def test_no_key_from_the_environment_reaches_a_command(
    opened: tuple[Sandbox, _Daemon],
) -> None:
    sandbox, daemon = opened
    result = sandbox.run(
        ["env"],
        env={"OPENAI_API_KEY": KEYS["OPENAI_API_KEY"], "PLAIN": "kept"},
    )
    seen = result.stdout + "\n".join(" ".join(argv) for argv in daemon.argvs)
    for secret in _secrets():
        assert secret not in seen
    if isinstance(sandbox, TempDirSandbox):
        # The filter drops keys, not the environment a command needs.
        assert "PLAIN=kept" in result.stdout


def test_the_checkouts_ignored_dotenv_is_not_in_the_workspace(
    opened: tuple[Sandbox, _Daemon],
) -> None:
    sandbox, _ = opened
    assert not (sandbox.workspace / ".env").exists()
    for path in sandbox.workspace.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            assert DOTENV_KEY not in path.read_text(encoding="utf-8", errors="replace")


def test_the_users_home_is_not_where_a_command_looks(
    opened: tuple[Sandbox, _Daemon], home: Path
) -> None:
    sandbox, daemon = opened
    result = sandbox.run(["sh", "-c", 'echo "$HOME"'])
    if isinstance(sandbox, DockerSandbox):
        run = next(argv for argv in daemon.argvs if argv[:1] == ["run"])
        assert "HOME=/workspace" in run
        assert not any(str(home) in token for argv in daemon.argvs for token in argv)
    else:
        assert result.stdout.strip() != str(home)
        assert not Path(result.stdout.strip()).is_relative_to(home)


def test_the_container_mounts_the_workspace_and_nothing_else(
    repo: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = _Daemon()
    monkeypatch.setattr(docker_module, "_docker_exec", daemon.exec)
    with DockerSandbox(repo, image="img:latest", runner=daemon) as sandbox:
        (run,) = [argv for argv in daemon.argvs if argv[:1] == ["run"]]
        workspace = str(sandbox.workspace)
    mounts = [run[i + 1] for i, token in enumerate(run) if token in ("--volume", "-v")]
    assert mounts == [f"{workspace}:/workspace", f"{workspace}/.git:/workspace/.git:ro"]
    for flag in ("--mount", "--env-file", "--privileged", "--volumes-from"):
        assert flag not in run
    assert not any("docker.sock" in token for token in run)
    assert os.environ["HOME"] == str(home)  # the host HOME was there to be mounted
