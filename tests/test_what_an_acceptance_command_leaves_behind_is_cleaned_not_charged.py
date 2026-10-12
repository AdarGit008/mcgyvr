"""What an acceptance command leaves behind is cleaned up, not charged.

A test runner writes as it runs: ``__pycache__``, ``.pytest_cache``, a uv cache
with its own ``.git``. In a repository with no ``.gitignore`` for them, the
preflight compared the tree before and after and refused the contract with
``acceptance-mutates-tree`` — naming no path (e2e run 1, F4; F13 was the same
mechanism). The owner's ruling: the preflight cleans up what the baseline run
left behind, so the model always starts on a clean copy, and does not refuse
for it. It says what it removed.

The gate-time run follows the same principle. The change is judged on what the
model wrote, and a runner's leftovers are removed after each command rather
than charged. The one guard kept is a command that rewrites a file of the
change itself: its verdict was then about bytes the model did not write, which
is the false acceptance the old check existed to stop.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.runner import Gate
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests import livejournal as lj

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

#: A test runner's droppings, in a repository that ignores none of them.
CACHES = (
    "mkdir -p pkg/__pycache__ .pytest_cache/v/cache"
    " && touch x.pyc pkg/__pycache__/mod.cpython-312.pyc"
    " && echo '{}' > .pytest_cache/v/cache/lastfailed"
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_IDENTITY},
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """No ``.gitignore`` at all: every cache a runner writes is visible to git."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def files_in(workspace: Path) -> set[str]:
    """Every file under the workspace but its own ``.git``, ignored ones too."""
    found: set[str] = set()
    for here, dirs, files in os.walk(workspace):
        if Path(here) == workspace:
            dirs[:] = [d for d in dirs if d != ".git"]
        found.update(
            (Path(here) / name).relative_to(workspace).as_posix() for name in files
        )
    return found


def clean(workspace: Path) -> bool:
    return _git(workspace, "status", "--porcelain", "--ignored") == ""


# --- preflight ---------------------------------------------------------------


@pytest.mark.parametrize("listed_as", ["acceptance", "demonstration"])
def test_a_baseline_that_writes_caches_passes_preflight_on_a_clean_copy(
    repo: Path, listed_as: str
) -> None:
    exit_code = 0 if listed_as == "acceptance" else 1
    command = ("sh", "-c", f"{CACHES}; exit {exit_code}")
    with TempDirSandbox(repo) as sandbox:
        if listed_as == "acceptance":
            acceptance = Acceptance(sandbox, (command,))
        else:
            acceptance = Acceptance(sandbox, (), demonstrations=(command,))
        baseline = acceptance.baseline()

        assert baseline.issue is None, baseline.issue
        assert clean(sandbox.workspace)
        assert files_in(sandbox.workspace) == {"pkg/mod.py"}

    (note,) = baseline.notes
    assert "x.pyc" in note
    assert ".pytest_cache/" in note
    assert "pkg/__pycache__/" in note


def test_the_note_names_five_paths_and_counts_the_rest(repo: Path) -> None:
    many = "touch a.pyc b.pyc c.pyc d.pyc e.pyc f.pyc g.pyc"
    with TempDirSandbox(repo) as sandbox:
        baseline = Acceptance(sandbox, (("sh", "-c", many),)).baseline()

    (note,) = baseline.notes
    assert "a.pyc, b.pyc, c.pyc, d.pyc, e.pyc (+2 more)" in note, note


def test_a_baseline_that_rewrites_a_tracked_file_is_reverted_not_refused(
    repo: Path,
) -> None:
    with TempDirSandbox(repo) as sandbox:
        command = ("sh", "-c", "echo MUTATED >> pkg/mod.py && rm -f nothing")
        baseline = Acceptance(sandbox, (command,)).baseline()

        assert baseline.issue is None
        assert (sandbox.workspace / "pkg/mod.py").read_text() == "VALUE = 1\n"
        assert clean(sandbox.workspace)
    assert "pkg/mod.py" in baseline.notes[0]


def test_a_baseline_that_leaves_a_nested_repository_is_cleaned(
    repo: Path, tmp_path: Path
) -> None:
    """F13's shape: uv's cache came with a ``.git`` of its own. It is removed
    before host git looks at the tree, so its config never runs on the host."""
    marker = tmp_path / "fsmonitor-ran"
    plant = (
        "mkdir -p .cache/uv && git init -q .cache/uv"
        f" && git -C .cache/uv config core.fsmonitor 'touch {marker}'"
        " && touch .cache/uv/CACHEDIR.TAG"
    )
    with TempDirSandbox(repo) as sandbox:
        baseline = Acceptance(sandbox, (("sh", "-c", plant),)).baseline()

        assert baseline.issue is None, baseline.issue
        assert not (sandbox.workspace / ".cache").exists()
        assert clean(sandbox.workspace)
    assert not marker.exists(), "host git ran the nested repository's config"
    assert ".cache/uv/.git" in baseline.notes[0]


def test_a_gitignored_cache_is_removed_too(tmp_path: Path) -> None:
    root = tmp_path / "ignoring"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    with TempDirSandbox(root) as sandbox:
        baseline = Acceptance(sandbox, (("sh", "-c", CACHES),)).baseline()

        assert baseline.issue is None
        assert files_in(sandbox.workspace) == {"app.py", ".gitignore"}
    assert ".pytest_cache/" in baseline.notes[0]


def test_a_clean_baseline_says_nothing(repo: Path) -> None:
    with TempDirSandbox(repo) as sandbox:
        baseline = Acceptance(sandbox, (("sh", "-c", "exit 0"),)).baseline()
    assert baseline.issue is None
    assert baseline.notes == ()


def test_mcgyvr_run_says_what_the_preflight_cleaned_and_goes_on(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The note reaches the operator on the run's ``note:`` lines, and the
    attempt that follows is accepted over the same leftovers at gate time."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "messy.py").write_text("x = 0\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    writes = "sh -c 'touch x.pyc && mkdir -p .pytest_cache && touch .pytest_cache/v'"
    contract = lj.make_contract(
        tmp_path / "impl.yaml",
        lj.MODEL_CONTRACT.replace(
            "acceptance: [\"python -c 'import sys; sys.exit(0)'\"]",
            f'acceptance: ["{writes}"]',
        ),
    )
    assert writes in contract.read_text()
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")

    code = lj.main(lj.run_args(contract, root, config))

    out = capsys.readouterr().out
    assert code == 0, out
    notes = [line for line in out.splitlines() if line.startswith("note: ")]
    assert any("x.pyc" in n and ".pytest_cache/" in n for n in notes), out
    # And the result file carries it, since that is the file a caller reads.
    filed = json.loads(lj.result_path(out).read_text())["notes"]
    assert any("x.pyc" in n and ".pytest_cache/" in n for n in filed), filed


# --- gate time ---------------------------------------------------------------


def test_a_gate_time_run_that_writes_caches_does_not_reject_the_change(
    repo: Path,
) -> None:
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "pkg" / "mod.py").write_text("VALUE = 2\n")
        changeset = ChangeSet.detect(sandbox.workspace)
        acceptance = Acceptance(sandbox, (("sh", "-c", CACHES),))

        report = acceptance.run()
        result = Gate().run(changeset, acceptance=acceptance)

        assert report.findings == (), report.findings
        assert result.accepted, result.findings
        assert files_in(sandbox.workspace) == {"pkg/mod.py"}
        assert (sandbox.workspace / "pkg" / "mod.py").read_text() == "VALUE = 2\n"
        assert ChangeSet.detect(sandbox.workspace).paths() == ("pkg/mod.py",)
    (note,) = report.notes
    assert "x.pyc" in note and ".pytest_cache/" in note


def test_each_command_starts_on_the_tree_the_change_left(repo: Path) -> None:
    """The second command does not see the first one's leftovers."""
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(
            sandbox,
            (("sh", "-c", "touch first.pyc"), ("sh", "-c", "test ! -e first.pyc")),
        ).run()
    assert report.findings == (), report.findings


def test_a_gate_time_write_to_a_file_outside_the_change_is_reverted(
    repo: Path,
) -> None:
    """The repository's own file, rewritten by its own suite: not the model's."""
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "new.py").write_text("NEW = 1\n")
        report = Acceptance(
            sandbox, (("sh", "-c", "echo regenerated > pkg/mod.py"),)
        ).run()

        assert report.findings == (), report.findings
        assert (sandbox.workspace / "pkg" / "mod.py").read_text() == "VALUE = 1\n"
        assert (sandbox.workspace / "new.py").read_text() == "NEW = 1\n"


def test_a_gate_time_rewrite_of_the_changed_file_still_rejects_naming_it(
    repo: Path,
) -> None:
    """The guard that stays: the suite passed over bytes the model did not write."""
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "pkg" / "mod.py").write_text("VALUE = 2\n")
        report = Acceptance(
            sandbox, (("sh", "-c", "echo 'VALUE = 3' > pkg/mod.py"),)
        ).run()

        assert (sandbox.workspace / "pkg" / "mod.py").read_text() == "VALUE = 2\n"
    (finding,) = report.findings
    assert finding.code == "tree-altering"
    assert "pkg/mod.py" in finding.message
