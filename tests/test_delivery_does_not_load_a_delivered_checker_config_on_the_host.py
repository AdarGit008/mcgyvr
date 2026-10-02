"""Delivery does not run a checker that would load the delivered file as code.

Delivery judges the accepted bytes again in the user's own checkout, on the
host. eslint and prettier load their configuration from the tree they check,
and an ``eslint.config.mjs`` or a ``prettier.config.js`` is a module they
import. So when the delivered file is itself such a config, re-running that
checker in the checkout would run the task's code on the host, outside the
sandbox the change was judged in. That rung is not re-run there, the other
rungs still are, and the run says which tool was left out and why.

A JS file no checker loads as configuration is re-judged as before: both
tools run over it in the checkout.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

import mcgyvr.deliver as delivery
from mcgyvr.contract import Contract, load
from mcgyvr.deliver import Accepted, deliver, place
from mcgyvr.gate import GateResult
from mcgyvr.gate.adapter import ToolRunner
from mcgyvr.gate.adapters.javascript import JavaScriptAdapter
from mcgyvr.gate.adapters.python import PythonAdapter
from tests import livejournal as lj


class _Recorder(ToolRunner):
    """Says every file is clean, and keeps which tool was asked to run."""

    def __init__(self) -> None:
        self.tools: list[str] = []

    def run(
        self,
        tool: str,
        args: Sequence[str],
        cwd: Path,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.tools.append(tool)
        stdout = "[]" if tool == "eslint" else ""
        return subprocess.CompletedProcess([tool, *args], 0, stdout, "")


_CONTRACT = """
id: cfg
task_type: function_implementation
task: Export the config.
target: {target}
stop_conditions: ["The config is not stated."]
acceptance: ["true"]
limits:
  max_output_tokens: 256
scope:
  allow: ["{target}"]
"""

_BODY = "export default [];\n"


def _setup(tmp_path: Path, target: str) -> tuple[Path, Contract, str]:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(
        lj.make_contract(tmp_path / "cfg.yaml", _CONTRACT.format(target=target))
    )
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    return repo, contract, base


def _accepted(repo: Path, contract: Contract, target: str) -> Accepted:
    path = repo / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_BODY, encoding="utf-8")
    bound = Accepted.read(repo=repo, contract=contract, result=GateResult())
    path.unlink()
    return bound


def _adapters(recorder: _Recorder) -> tuple[PythonAdapter, JavaScriptAdapter]:
    return (PythonAdapter(), JavaScriptAdapter(recorder))


@pytest.mark.parametrize(
    ("target", "left_out"),
    [
        ("eslint.config.mjs", "eslint"),
        ("eslint.config.js", "eslint"),
        ("eslint.config.ts", "eslint"),
        (".eslintrc.cjs", "eslint"),
        ("web/eslint.config.mjs", "eslint"),
        ("prettier.config.js", "prettier"),
        (".prettierrc.mjs", "prettier"),
        ("web/prettier.config.cjs", "prettier"),
    ],
)
def test_the_tool_that_loads_the_delivered_config_is_not_run_on_the_host(
    tmp_path: Path, target: str, left_out: str
) -> None:
    repo, contract, base = _setup(tmp_path, target)
    recorder = _Recorder()

    result = deliver(
        repo=repo,
        contract=contract,
        content=_accepted(repo, contract, target),
        base=base,
        adapters=_adapters(recorder),
    )

    assert result.committed, result.reason
    assert left_out not in recorder.tools
    other = {"eslint", "prettier"} - {left_out}
    assert other <= set(recorder.tools), "the other rung is still re-run"


def test_place_leaves_the_config_unloaded_too(tmp_path: Path) -> None:
    target = "eslint.config.mjs"
    repo, contract, base = _setup(tmp_path, target)
    recorder = _Recorder()

    place(
        repo=repo,
        contract=contract,
        content=_accepted(repo, contract, target),
        base=base,
        adapters=_adapters(recorder),
    )

    assert (repo / target).read_text(encoding="utf-8") == _BODY
    assert "eslint" not in recorder.tools


def test_a_js_file_no_checker_loads_is_judged_by_both(tmp_path: Path) -> None:
    target = "src/app.mjs"
    repo, contract, base = _setup(tmp_path, target)
    recorder = _Recorder()

    result = deliver(
        repo=repo,
        contract=contract,
        content=_accepted(repo, contract, target),
        base=base,
        adapters=_adapters(recorder),
    )

    assert result.committed, result.reason
    assert {"eslint", "prettier"} <= set(recorder.tools)
    assert delivery.not_rerun_here(_adapters(recorder), target) == ""


def test_the_run_says_which_tool_was_left_out_and_why() -> None:
    adapters = _adapters(_Recorder())

    note = delivery.not_rerun_here(adapters, "web/eslint.config.mjs")

    assert "eslint" in note
    assert "prettier" not in note
    assert "web/eslint.config.mjs" in note
    assert "sandbox" in note
