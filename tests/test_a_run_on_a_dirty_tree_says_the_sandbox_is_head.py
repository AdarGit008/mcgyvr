"""A run on a dirty tree says the sandbox is HEAD, and names what it left out.

The sandbox is a ``git archive`` of HEAD, on purpose: delivery diffs against a
concrete source revision. So an uncommitted edit or an untracked file is not
in it, and in e2e run 1 that hid the test the agent had just written; the run
said nothing and the agent replaced a real check with filler (F11). So it
warns, does not refuse, and does not change the base.

* ``mcgyvr run`` on a dirty tree says so on stderr and puts the same line in
  the result file's ``notes``, because the skill tells a caller to read the
  file and not the scrollback. A clean tree says nothing.
* ``mcgyvr sandbox``, which shows what a run here would get, says the same.
* ``mcgyvr delegate`` says the same before it drafts: its baseline is read from
  the working tree, while each contract it drafts runs on HEAD.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.orchestrator.repo import head_only_note

TARGET = "src/pkg/rows.py"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

_SESSION_VARS = ("CLAUDE_CODE_SESSION_ID", "PI_SESSION_FILE", "CLAUDE_CONFIG_DIR")

FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
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


def _repo(tmp_path: Path, *, dirty: bool) -> Path:
    """A committed repository; dirty adds an edit and a test nobody committed."""
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / TARGET).write_text("def add(rows):\n    rows.append( 1 )\n")
    (repo / "src" / "pkg" / "other.py").write_text("X = 1\n")
    (repo / "tests" / "__init__.py").write_text("")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    if dirty:
        (repo / "src" / "pkg" / "other.py").write_text("X = 2\n")
        (repo / "tests" / "test_rows.py").write_text("def test_rows(): ...\n")
    return repo


def _short(repo: Path) -> str:
    return _git(repo, "rev-parse", "--short", "HEAD").strip()


def _expected(repo: Path) -> str:
    return (
        f"note: the sandbox is built from commit {_short(repo)}; 2 uncommitted "
        f"or untracked path(s) are not in it: src/pkg/other.py, "
        f"tests/test_rows.py. Commit them if the contract's commands need them."
    )


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for name in (*_SESSION_VARS, "MCGYVR_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(home))


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: Path) -> int:
    from mcgyvr.cli import main

    _isolate(tmp_path, monkeypatch)
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (setup / "policy.yaml").write_text(
        f"ladder: [cheap]\njournal:\n  dir: {tmp_path / 'journal'}\n",
        encoding="utf-8",
    )
    contract = tmp_path / "tidy.yaml"
    contract.write_text(FORMAT, encoding="utf-8")
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


@needs_ruff
def test_a_run_on_a_dirty_tree_says_the_sandbox_is_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path, dirty=True)

    _run(tmp_path, monkeypatch, repo)

    err = capsys.readouterr().err
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert _expected(repo) in err.splitlines()
    assert result["notes"] == [_expected(repo).removeprefix("note: ")]


@needs_ruff
def test_a_run_on_a_clean_tree_says_nothing_about_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path, dirty=False)

    _run(tmp_path, monkeypatch, repo)

    err = capsys.readouterr().err
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert "the sandbox is built from" not in err
    assert result["notes"] == []


def test_the_sandbox_inspection_says_the_same(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main

    repo = _repo(tmp_path, dirty=True)
    _isolate(tmp_path, monkeypatch)

    assert main(["sandbox", "--repo", str(repo)]) == 0
    assert _expected(repo) in capsys.readouterr().err.splitlines()


def test_delegate_says_the_same_before_it_drafts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.delegate as delegate
    from mcgyvr.cli import main
    from mcgyvr.runner import RunnerError

    repo = _repo(tmp_path, dirty=True)
    _isolate(tmp_path, monkeypatch)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(
        FLEET + "ladder: [cheap]\norchestrator:\n  unit: cheap\n", encoding="utf-8"
    )

    # The note is said before the role is asked, so the role need not answer.
    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        raise RunnerError("the role is not asked in this test")

    monkeypatch.setattr(delegate, "dispatch_role", fake_dispatch_role)

    main(["delegate", "tidy rows", "--repo", str(repo), "--config", str(config)])
    assert _expected(repo) in capsys.readouterr().err.splitlines()


def test_a_long_list_is_cut_to_three_names_and_a_count(tmp_path: Path) -> None:
    repo = _repo(tmp_path, dirty=True)
    for name in ("a.txt", "b.txt", "c.txt"):
        (repo / name).write_text("x\n")

    note = head_only_note(repo)

    assert note is not None
    named = note.split(" are not in it: ")[1].split(". Commit them")[0]
    assert "5 uncommitted or untracked path(s)" in note
    assert len(named.split(" (+")[0].split(", ")) == 3
    assert named.endswith(" (+2 more)")


def test_a_directory_that_is_not_a_repository_has_no_note(tmp_path: Path) -> None:
    assert head_only_note(tmp_path) is None
