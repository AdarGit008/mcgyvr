"""A refused delivery says so on stdout, not "gate accepted".

An ``import_sort`` run on a target with an uncommitted edit used to print
``sort-imports: gate accepted`` on stdout, then delivery refused to write over
the edit: exit 1, outcome ``delivery_refused``, and the refusal on stderr only.
Someone reading stdout saw an acceptance.

Now the stdout line states the real outcome —
``<id>: checks passed, but not written: <reason>`` — for every reason delivery
refuses, on the floor and on the ladder alike. The exit code, the result file
and the stderr detail stay as they were. A run that is accepted and delivered
prints as before.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests import livejournal as lj

TARGET = "src/pkg/rows.py"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
    window: 32768
"""

FORMAT = """
id: tidy-rows
task_type: code
operation: format
task: Reformat the module.
target: src/pkg/rows.py
scope:
  allow: ["src/**"]
"""

REFUSED = "checks passed, but not written: "
NOT_WRITTEN = ", but not written: "

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the floor's program for this contract is ruff; without it nothing runs",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_IDENTITY},
    ).stdout


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / TARGET).write_text("def add(rows):\n    return rows+ [ 1 ]\n")
    (repo / "src" / "pkg" / "other.py").write_text("X = 1\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: Path, *extra: str
) -> tuple[int, dict[str, object]]:
    from mcgyvr.cli import main

    lj.clean_env(monkeypatch, tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (setup / "policy.yaml").write_text(
        f"ladder: [cheap]\njournal:\n  dir: {tmp_path / 'journal'}\n",
        encoding="utf-8",
    )
    contract = tmp_path / "tidy.yaml"
    contract.write_text(FORMAT, encoding="utf-8")
    result = tmp_path / "result.json"
    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            "--config",
            str(setup),
            "--orchestrator",
            "t",
            "--result",
            str(result),
            *extra,
        ]
    )
    return code, json.loads(result.read_text(encoding="utf-8"))


@needs_ruff
def test_a_dirty_target_prints_not_written_on_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    edit = "def add(rows):\n    return rows+ [ 2 ]\n"
    (repo / TARGET).write_text(edit)

    code, result = _floor(tmp_path, monkeypatch, repo)

    captured = capsys.readouterr()
    assert code == 1
    assert result["outcome"] == "delivery_refused", result
    assert "gate accepted" not in captured.out, captured.out
    line = next((each for each in captured.out.splitlines() if REFUSED in each), None)
    assert line is not None, captured.out
    assert line.startswith(f"tidy-rows: {REFUSED}"), line
    assert "uncommitted" in line, line
    assert f"error: {result['detail']}" in captured.err
    assert (repo / TARGET).read_text() == edit, "the user's edit was overwritten"


@needs_ruff
def test_a_refused_commit_prints_not_written_on_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    (repo / "src" / "pkg" / "other.py").write_text("X = 2\n")

    code, result = _floor(tmp_path, monkeypatch, repo, "--commit")

    out = capsys.readouterr().out
    assert code == 1
    assert result["outcome"] == "delivery_refused", result
    assert "gate accepted" not in out, out
    assert f"tidy-rows: {REFUSED}" in out, out


@needs_ruff
def test_a_delivered_floor_run_still_says_gate_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)

    code, result = _floor(tmp_path, monkeypatch, repo)

    captured = capsys.readouterr()
    out = captured.out
    assert code == 0, (out, captured.err)
    assert result["outcome"] == "accepted", result
    assert "\ntidy-rows: gate accepted\n" in out, out
    assert REFUSED not in out
    assert out.index("gate accepted") < out.index("Left in ")


def test_a_refused_climb_prints_not_written_on_stdout(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    (repo / "src" / "pkg" / "messy.py").write_text("x = 5\n", encoding="utf-8")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    captured = capsys.readouterr()
    result = json.loads(lj.result_path(captured.out).read_text())
    assert code == 1
    assert result["outcome"] == "delivery_refused", result
    assert "impl: accepted on" not in captured.out, captured.out
    line = next(
        (each for each in captured.out.splitlines() if NOT_WRITTEN in each), None
    )
    assert line is not None, captured.out
    assert line.startswith("impl: checks passed on local_qwen-7b"), line
    assert f"error: {result['detail']}" in captured.err
    assert (repo / "src" / "pkg" / "messy.py").read_text() == "x = 5\n"


def test_a_delivered_climb_still_says_accepted_on_its_rung(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr().out
    assert code == 0
    assert "impl: accepted on local_qwen-7b" in out, out
    assert NOT_WRITTEN not in out
    assert out.index("impl: accepted on") < out.index("Left in ")
