"""A run on the floor leaves a change the setup asked the gate to report.

End to end through ``mcgyvr run``: a deterministic contract whose program
(``ruff format``) rewrites a line that changes an object its caller passed in.
The rewritten line is an added line, so the gate judges it.

* A setup that says nothing: the gate rejects the change for the mutation and
  the target is left as it was.
* ``gate.param_mutation: report``: the sandbox gate accepts, delivery judges the
  bytes by the same setting and leaves them in the target, and the terminal
  says once that the finding was reported by that setting and not refused.
* ``gate.param_mutation: skip``: accepted and left in the target, and nothing
  is said about this family.

Nothing is dispatched, the setup is the default profile, the journal is under
the test's own directory, and ``HOME`` is a directory nothing may write to.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

TARGET = "src/pkg/rows.py"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

#: What the environment names a session with; a run inside one must not
#: journal as that session.
_SESSION_VARS = ("CLAUDE_CODE_SESSION_ID", "PI_SESSION_FILE", "CLAUDE_CONFIG_DIR")

FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
"""

FORMAT = """
id: tidy-rows
task_type: format
task: Reformat the module.
target: src/pkg/rows.py
scope:
  allow: ["src/**"]
"""

#: Committed as the base. The formatter rewrites line 2, so the mutation on it
#: is a line the run added.
UNTIDY = "def add(rows):\n    rows.append( 1 )\n"
TIDY = "def add(rows):\n    rows.append(1)\n"

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the floor's program for this contract is ruff; without it nothing runs",
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str | None) -> int:
    from mcgyvr.cli import main

    home = tmp_path / "home"
    home.mkdir()
    for name in (*_SESSION_VARS, "MCGYVR_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(home))

    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / TARGET).write_text(UNTIDY, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    setup = tmp_path / "setup"
    setup.mkdir()
    policy = f"ladder: [cheap]\njournal:\n  dir: {tmp_path / 'journal'}\n"
    if mode is not None:
        policy += f"gate:\n  param_mutation: {mode}\n"
    (setup / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (setup / "policy.yaml").write_text(policy, encoding="utf-8")
    contract = tmp_path / "tidy.yaml"
    contract.write_text(FORMAT, encoding="utf-8")

    try:
        return main(
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
                str(tmp_path / "result.json"),
            ]
        )
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2


def _mutation_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if "[PARAM-MUTATION]" in line]


@needs_ruff
def test_a_setup_that_says_nothing_refuses_the_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run(tmp_path, monkeypatch, None)
    printed = capsys.readouterr().out

    assert code == 1, printed
    lines = _mutation_lines(printed)
    assert len(lines) == 1 and "✗" in lines[0], printed
    assert (tmp_path / "repo" / TARGET).read_text(encoding="utf-8") == UNTIDY
    assert not any((tmp_path / "home").iterdir())


@needs_ruff
def test_report_leaves_the_change_and_says_once_that_the_setting_reported_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run(tmp_path, monkeypatch, "report")
    printed = capsys.readouterr().out

    assert code == 0, printed
    assert (tmp_path / "repo" / TARGET).read_text(encoding="utf-8") == TIDY
    lines = _mutation_lines(printed)
    assert len(lines) == 1, printed
    assert "✗" not in lines[0], lines[0]
    assert f"{TARGET}:2" in lines[0], lines[0]
    assert "gate.param_mutation" in lines[0] and "report" in lines[0], lines[0]
    assert not any((tmp_path / "home").iterdir())


@needs_ruff
def test_skip_leaves_the_change_and_says_nothing_about_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run(tmp_path, monkeypatch, "skip")
    printed = capsys.readouterr().out

    assert code == 0, printed
    assert (tmp_path / "repo" / TARGET).read_text(encoding="utf-8") == TIDY
    assert _mutation_lines(printed) == [], printed
    assert not any((tmp_path / "home").iterdir())
