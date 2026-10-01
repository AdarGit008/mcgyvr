"""A checker run on the host is handed no credential.

The gate's checkers and the repair after it — ruff, the declared mypy or
pyright, eslint, prettier — run on the host, in the workspace, under the
workspace's own configuration. That configuration is part of the tree a task's
commands may have written, and some of it is code: a ``mypy.ini`` may name a
plugin by file path, an ``eslint.config.js`` is a module. Whatever it runs, it
runs with the environment the checker was given.

So that environment is built through the same filter a sandbox's is: no
credential-shaped name, and no value holding ``user:password@``. A task's
output then reaches no key by being checked, in either sandbox mode.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

import mcgyvr
from mcgyvr.gate.adapter import plain_env
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.typecheck import TypeCheck
from mcgyvr.sandbox.base import credential_env_names
from tests import livejournal as lj

#: A value no real key has, so finding it anywhere is finding the leak.
KEY = "sk-test-not-a-real-key-0000"

CREDENTIALS = {
    "ANTHROPIC_API_KEY": KEY,
    "OPENAI_API_KEY": KEY,
    "GITHUB_TOKEN": KEY,
    "PIP_INDEX_URL": f"https://user:{KEY}@pypi.example/simple",
}

#: Every module that runs a checker or a fixer on the host over a workspace.
#: The type checker, eslint and prettier reach the host through the runner in
#: ``gate/adapter.py`` (``HostRunner``), and only where no sandbox is open.
HOST_CHECKERS = (
    "gate/adapter.py",
    "gate/adapters/python.py",
    "gate/typecheck.py",
    "repair.py",
    "cleanup.py",
)

#: The ``subprocess`` functions that start a process.
_STARTS = frozenset({"run", "Popen", "call", "check_call", "check_output"})


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in CREDENTIALS.items():
        monkeypatch.setenv(name, value)


def test_the_checkers_environment_holds_no_credential(keyed: None) -> None:
    env = plain_env()
    assert credential_env_names(env) == frozenset()
    assert KEY not in "\n".join(env.values())


def test_the_checkers_environment_still_runs_a_toolchain(keyed: None) -> None:
    env = plain_env()
    assert env.get("PATH")  # a checker is found by name
    assert env["NO_COLOR"] == "1"
    assert env["RUFF_NO_CACHE"] == "true"


def _subprocess_calls(source: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        and node.func.attr in _STARTS
    ]


@pytest.mark.parametrize("module", HOST_CHECKERS)
def test_every_checker_on_the_host_is_run_in_that_environment(module: str) -> None:
    source = (Path(mcgyvr.__file__).parent / module).read_text(encoding="utf-8")
    calls = _subprocess_calls(source)
    assert calls, f"{module} runs nothing; the list above is stale"
    for call in calls:
        env = {kw.arg: kw.value for kw in call.keywords}.get("env")
        assert (
            isinstance(env, ast.Call)
            and isinstance(env.func, ast.Name)
            and env.func.id == "plain_env"
        ), f"{module}:{call.lineno} runs a tool without plain_env()"


@pytest.mark.skipif(shutil.which("mypy") is None, reason="a real mypy runs the plugin")
def test_a_plugin_the_workspace_names_reads_no_key(keyed: None, tmp_path: Path) -> None:
    dumped = tmp_path / "outside" / "environ.json"
    repo = lj.make_repo(tmp_path / "workspace")
    (repo / "mypy.ini").write_text("[mypy]\nplugins = ./dump.py\n", encoding="utf-8")
    # Names and one yes/no only: a run on a regressed tree must not write the
    # developer's own keys to disk while proving they leaked.
    (repo / "dump.py").write_text(
        "import json, os, pathlib\n"
        f"out = pathlib.Path({str(dumped)!r})\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_text(json.dumps({'names': sorted(os.environ),\n"
        f"    'key': any({KEY!r} in v for v in os.environ.values())}}))\n"
        "from mypy.plugin import Plugin\n"
        "def plugin(version):\n"
        "    return Plugin\n",
        encoding="utf-8",
    )
    lj.git(repo, "add", "-A")
    lj.git(repo, "commit", "-qm", "the workspace's own config")
    (repo / "src" / "pkg" / "typed.py").write_text("y: int = 'a'\n", encoding="utf-8")

    TypeCheck(repo=repo).run(ChangeSet.detect(repo))

    seen = json.loads(dumped.read_text(encoding="utf-8"))  # the plugin ran
    assert credential_env_names(dict.fromkeys(seen["names"], "")) == frozenset()
    assert seen["key"] is False
