"""Acceptance command execution (#38), driven for real against the sandbox.

The temp-directory mode runs commands on the host in a real git workspace, so
these exercise the whole rung — run the command, snapshot the tree, classify
the outcome — without needing a Docker daemon (CI has none), which is the same
reason the sandbox suite itself uses that mode.

The three properties the issue makes acceptance criteria are pinned directly:
a missing dependency is an environment issue and never a finding; a
tree-altering command fails by name; and a failing command's excerpt carries
the tail, not a head that may be all passes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate.acceptance import CHECK, Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.runner import Gate
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**_os_environ(), **_IDENTITY},
    )


def _os_environ() -> dict[str, str]:
    import os

    return dict(os.environ)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A git repo whose ``.gitignore`` excludes a cache dir, as a sandbox source."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / ".gitignore").write_text("cache/\n*.log\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


# --- the classifier: one command, five outcomes --------------------------


def test_passing_command_yields_an_empty_report(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        report = Acceptance(sandbox, (("sh", "-c", "exit 0"),)).run()
    assert report.findings == ()
    assert report.environment_issues == ()


def test_failing_command_is_a_finding(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        report = Acceptance(sandbox, (("sh", "-c", "echo nope; exit 1"),)).run()
    assert report.environment_issues == ()
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.check == CHECK
    assert finding.code == "failed"
    assert "nope" in finding.message


def test_missing_dependency_is_an_environment_issue_never_a_finding(
    git_repo: Path,
) -> None:
    """Acceptance criterion: a missing dependency is never a rejected change."""
    with TempDirSandbox(git_repo) as sandbox:
        report = Acceptance(sandbox, (("this-binary-does-not-exist-42",),)).run()
    assert report.findings == ()  # the worker is not blamed
    assert len(report.environment_issues) == 1
    assert "could not run" in report.environment_issues[0]


def test_tree_altering_command_fails_by_name(git_repo: Path) -> None:
    """Acceptance criterion: a command that changes the tree fails, named."""
    with TempDirSandbox(git_repo) as sandbox:
        # Exits 0, but rewrites a tracked file — a formatter masquerading as a
        # check. It must still fail, because the gate can no longer judge the
        # worker's diff alone.
        report = Acceptance(sandbox, (("sh", "-c", "echo MUTATED >> app.py"),)).run()
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.code == "tree-altering"
    assert finding.path == "sh -c 'echo MUTATED >> app.py'"  # named by command


def test_tree_alteration_stops_the_run(git_repo: Path) -> None:
    """A contaminated tree invalidates everything after it, so the run stops."""
    with TempDirSandbox(git_repo) as sandbox:
        report = Acceptance(
            sandbox,
            (
                ("sh", "-c", "echo x >> app.py"),  # alters the tree
                ("sh", "-c", "touch ran-second.marker"),  # must never run
            ),
        ).run()
        assert not (sandbox.workspace / "ran-second.marker").exists()
    assert [f.code for f in report.findings] == ["tree-altering"]


def test_a_gitignored_write_is_not_treated_as_tree_alteration(
    git_repo: Path,
) -> None:
    """A test runner writing its caches (ignored paths) is not the diff changing."""
    with TempDirSandbox(git_repo) as sandbox:
        report = Acceptance(
            sandbox,
            (("sh", "-c", "mkdir -p cache && echo junk > cache/x && echo run.log"),),
        ).run()
    # The command wrote only gitignored paths, so the change-set is untouched
    # and the command passed.
    assert report.findings == ()
    assert report.environment_issues == ()


def test_timeout_is_a_finding_distinct_from_a_failure(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        report = Acceptance(sandbox, (("sh", "-c", "sleep 5"),), timeout=0.3).run()
    assert len(report.findings) == 1
    assert report.findings[0].code == "timeout"


def test_excerpt_carries_the_failing_tail_not_a_head_of_passes(
    git_repo: Path,
) -> None:
    """Acceptance criterion: the surfaced output holds the failing part."""
    passes = "".join(f"echo PASS line {i}\n" for i in range(100))
    script = passes + "echo FAILED boom\nexit 1\n"
    with TempDirSandbox(git_repo) as sandbox:
        report = Acceptance(sandbox, (("sh", "-c", script),)).run()
    message = report.findings[0].message
    assert "FAILED boom" in message  # the failing part survived
    assert "PASS line 1\n" not in message  # the head of passes was dropped
    assert "earlier output omitted" in message  # and the elision is marked


# --- the precondition: is the suite a usable signal at all? ---------------


def test_precondition_passes_on_a_green_read_only_suite(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        issue = Acceptance(sandbox, (("sh", "-c", "exit 0"),)).precondition()
    assert issue is None


def test_precondition_flags_an_already_failing_suite(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        issue = Acceptance(sandbox, (("sh", "-c", "exit 1"),)).precondition()
    assert issue is not None
    assert issue.reason == "acceptance-baseline-failing"


def test_precondition_flags_a_missing_dependency_as_environment(
    git_repo: Path,
) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        issue = Acceptance(sandbox, (("no-such-tool-99",),)).precondition()
    assert issue is not None
    assert issue.reason == "acceptance-unavailable"


def test_precondition_flags_a_tree_mutating_command(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        issue = Acceptance(sandbox, (("sh", "-c", "echo x >> app.py"),)).precondition()
    assert issue is not None
    assert issue.reason == "acceptance-mutates-tree"


# --- wiring into the gate as the last rung -------------------------------


def _repo_with_clean_change(tmp_path: Path) -> Path:
    repo = tmp_path / "gate"
    repo.mkdir()
    (repo / "seed.py").write_text("SEED = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "good.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )
    return repo


def test_gate_runs_acceptance_as_the_last_rung(tmp_path: Path) -> None:
    repo = _repo_with_clean_change(tmp_path)
    changeset = ChangeSet.detect(repo)
    with TempDirSandbox(repo) as sandbox:
        acc = Acceptance(sandbox, (("sh", "-c", "echo tests-red; exit 1"),))
        result = Gate().run(changeset, acceptance=acc)
    assert not result.accepted
    assert {f.check for f in result.findings} == {CHECK}
    assert "tests-red" in result.findings[0].message


def test_gate_short_circuits_acceptance_when_a_cheaper_check_fails(
    tmp_path: Path,
) -> None:
    """A diff that already fails a cheap check never spins the expensive suite."""
    repo = tmp_path / "sc"
    repo.mkdir()
    (repo / "seed.py").write_text("SEED = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "broken.py").write_text("def f(:\n    pass\n", encoding="utf-8")  # syntax

    changeset = ChangeSet.detect(repo)
    with TempDirSandbox(repo) as sandbox:
        # If acceptance ran it would drop a marker into the workspace and add a
        # finding; neither must happen.
        acc = Acceptance(sandbox, (("sh", "-c", "touch ran.marker; exit 1"),))
        result = Gate().run(changeset, acceptance=acc)
        assert not (sandbox.workspace / "ran.marker").exists()
    assert {f.check for f in result.findings} == {"syntax"}
