"""A checker that runs the workspace's configuration runs where the task runs.

The type checker, eslint and prettier read their configuration from the tree
they check, and part of it is code: a ``mypy.ini`` names a plugin by file path,
an ``eslint.config.mjs`` or ``prettier.config.mjs`` is a module. Over a task's
workspace that code is the task's. So when the gate judges a workspace, those
checkers run through ``Sandbox.run``, as the contract's own commands do: in the
task's container in docker mode, where the code can reach nothing of the host;
on the host with the sandbox's credential-free environment in tempdir mode,
which is the declared weaker mode.

The container mode is proven up to the daemon: every ``docker exec`` is
recorded and answered here, and a host that ran a checker would have run its
configuration, which writes a file outside the workspace.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import gate_workspace
from mcgyvr.sandbox import docker as docker_module
from mcgyvr.sandbox.base import credential_env_names
from mcgyvr.sandbox.docker import DockerSandbox, _ExecResult
from mcgyvr.sandbox.image import DockerResult
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests import livejournal as lj

CONTRACT = load_contract(lj.MODEL_CONTRACT)

#: What a worker's change adds: a typed line under the base's ``x = 0``, and a
#: JS file, so every one of the three checkers has something to look at.
ADDED_PY = 'y: int = "a"\n'
ADDED_JS = "export const x = 1;\n"


def _workspace_config(repo: Path, outside: Path) -> None:
    """Config that, wherever it is loaded, writes a file into ``outside``."""
    (repo / "mypy.ini").write_text("[mypy]\nplugins = ./plug.py\n", encoding="utf-8")
    (repo / "plug.py").write_text(
        "import json, os, pathlib\n"
        f"out = pathlib.Path({str(outside)!r})\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'mypy').write_text(json.dumps(sorted(os.environ)))\n"
        "from mypy.plugin import Plugin\n"
        "def plugin(version):\n"
        "    return Plugin\n",
        encoding="utf-8",
    )
    for tool, value in (("eslint", "[]"), ("prettier", "{}")):
        (repo / f"{tool}.config.mjs").write_text(
            'import fs from "node:fs";\n'
            f"fs.mkdirSync({json.dumps(str(outside))}, {{ recursive: true }});\n"
            f"fs.writeFileSync({json.dumps(str(outside / tool))}, 'ran');\n"
            f"export default {value};\n",
            encoding="utf-8",
        )


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    return tmp_path / "outside"


@pytest.fixture
def repo(tmp_path: Path, outside: Path) -> Path:
    repo = lj.make_repo(tmp_path / "repo")
    _workspace_config(repo, outside)
    lj.git(repo, "add", "-A")
    lj.git(repo, "commit", "-qm", "the workspace's own checker config")
    return repo


def _change(workspace: Path) -> None:
    with (workspace / "src" / "pkg" / "messy.py").open("a", encoding="utf-8") as f:
        f.write(ADDED_PY)
    (workspace / "src" / "web").mkdir()
    (workspace / "src" / "web" / "app.js").write_text(ADDED_JS, encoding="utf-8")


class _Daemon:
    """Every docker call, recorded; each ``exec`` answered as a clean checker."""

    def __init__(self, mypy_says: dict[str, str] | None = None) -> None:
        self.execs: list[tuple[str, list[str]]] = []
        #: What mypy prints, by the directory it runs in.
        self.mypy_says = mypy_says or {}

    def __call__(self, args: Sequence[str], stdin: bytes | None = None) -> DockerResult:
        return DockerResult(0, "", "")

    def exec(self, args: Sequence[str], timeout: float | None) -> _ExecResult:
        workdir = args[args.index("--workdir") + 1]
        name = next(a for a in args if a.startswith("mcgyvr-task-"))
        command = list(args[args.index(name) + 1 :])
        self.execs.append((workdir, command))
        if command[0] == "eslint":
            return _ExecResult(0, "[]", "", False)
        if command[0] == "mypy":
            said = self.mypy_says.get(workdir, "")
            return _ExecResult(1 if said else 0, said, "", False)
        return _ExecResult(0, "", "", False)

    def ran(self, tool: str) -> list[tuple[str, list[str]]]:
        return [(where, cmd) for where, cmd in self.execs if cmd[0] == tool]


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> _Daemon:
    made = _Daemon()
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(docker_module, "_docker_exec", made.exec)
    return made


def _docker(repo: Path, daemon: _Daemon) -> DockerSandbox:
    return DockerSandbox(repo, image="img:latest", runner=daemon, system="Linux")


def test_in_docker_mode_the_three_checkers_run_in_the_container(
    repo: Path, outside: Path, daemon: _Daemon
) -> None:
    with _docker(repo, daemon) as sandbox:
        _change(sandbox.workspace)
        gate_workspace(CONTRACT, sandbox)

    assert [cmd[-1] for _, cmd in daemon.ran("mypy")] == ["src/pkg/messy.py"]
    assert [cmd[-1] for _, cmd in daemon.ran("eslint")] == ["src/web/app.js"]
    assert daemon.ran("prettier")
    for where, _ in daemon.ran("mypy") + daemon.ran("eslint") + daemon.ran("prettier"):
        assert where == "/workspace"


def test_in_docker_mode_no_workspace_config_runs_on_the_host(
    repo: Path, outside: Path, daemon: _Daemon
) -> None:
    with _docker(repo, daemon) as sandbox:
        _change(sandbox.workspace)
        gate_workspace(CONTRACT, sandbox)

    assert not outside.exists(), sorted(p.name for p in outside.iterdir())


def test_the_base_tree_is_checked_in_the_container_too(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diagnostic off the worker's lines is weighed against the base, there.

    The worker's tree reports line 1, which the worker did not add, with the
    absolute path the container prints. The base tree, checked in the same
    container, reports nothing, so line 1 is the worker's.
    """
    error = "/workspace/src/pkg/messy.py:1: error: Broken by the change  [misc]\n"
    daemon = _Daemon(mypy_says={"/workspace": error})
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(docker_module, "_docker_exec", daemon.exec)
    with _docker(repo, daemon) as sandbox:
        _change(sandbox.workspace)
        result = gate_workspace(CONTRACT, sandbox)
        assert not list(sandbox.workspace.glob(".mcgyvr-check-*"))

    (base_run,) = [w for w, _ in daemon.ran("mypy") if w != "/workspace"]
    assert base_run.startswith("/workspace/.mcgyvr-check-")
    typed = [f for f in result.findings if f.check == "typecheck"]
    assert [(f.path, f.line) for f in typed] == [("src/pkg/messy.py", 1)]


def test_in_tempdir_mode_a_checker_runs_on_the_host_with_no_credential(
    repo: Path, outside: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key-0000")
    with TempDirSandbox(repo) as sandbox:
        _change(sandbox.workspace)
        gate_workspace(CONTRACT, sandbox)

    names = json.loads((outside / "mypy").read_text(encoding="utf-8"))
    assert credential_env_names(dict.fromkeys(names, "")) == frozenset()
