"""The temp-directory mode, exercised end-to-end against real git and shells.

Docker is not available where this suite runs (CI has no daemon), which is
exactly the install the temp-directory mode exists for — so it can be driven
for real rather than stubbed. What is tested here is also most of what both
modes share: population, the git base, reset, teardown and the credential
filter all live in :mod:`mcgyvr.sandbox.base` and are inherited unchanged by
the container mode, so proving them here proves them for both (#30).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.sandbox import base as base_module
from mcgyvr.sandbox.base import open_sandbox
from mcgyvr.sandbox.tempdir import TempDirSandbox


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A real git repository with one committed file, as a sandbox source."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (repo / "keep.txt").write_text("tracked\n", encoding="utf-8")
    env = {
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
        env={**_os_environ(), **env},
    )
    return repo


def _os_environ() -> dict[str, str]:
    import os

    return dict(os.environ)


# --- population and the git base -----------------------------------------


def test_populate_brings_repo_content_and_a_fresh_git_base(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        assert (sandbox.workspace / "app.py").read_text() == "print('hello')\n"
        # A git repository inside the sandbox, so the gate can diff and reset.
        assert (sandbox.workspace / ".git").exists()
        assert sandbox.base_changeset_ref()  # a real commit sha


def test_untracked_heavy_dirs_are_not_dragged_in(git_repo: Path) -> None:
    """`git archive` takes tracked content only — no stray node_modules/.venv."""
    (git_repo / "node_modules").mkdir()
    (git_repo / "node_modules" / "big.js").write_text("x" * 1000, encoding="utf-8")
    with TempDirSandbox(git_repo) as sandbox:
        assert not (sandbox.workspace / "node_modules").exists()


def test_non_git_source_is_copied(tmp_path: Path) -> None:
    source = tmp_path / "plain"
    source.mkdir()
    (source / "data.txt").write_text("payload\n", encoding="utf-8")
    with TempDirSandbox(source) as sandbox:
        assert (sandbox.workspace / "data.txt").read_text() == "payload\n"
        assert (sandbox.workspace / ".git").exists()


# --- running commands -----------------------------------------------------


def test_run_captures_stdout_and_exit_code(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(["sh", "-c", "echo out; exit 0"])
        assert result.ok
        assert result.exit_code == 0
        assert result.stdout.strip() == "out"


def test_run_reports_a_failing_command(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(["sh", "-c", "echo boom >&2; exit 3"])
        assert not result.ok
        assert result.exit_code == 3
        assert "boom" in result.stderr


def test_run_runs_in_the_workspace(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(["sh", "-c", "pwd"])
        assert result.stdout.strip() == str(sandbox.workspace)


def test_missing_binary_does_not_raise_and_reports_a_did_not_run_code(
    git_repo: Path,
) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(["this-binary-does-not-exist-42"])
        # 127 (not found) or 126 (found, not executable) — a command that
        # never ran, surfaced as a result rather than an exception.
        assert result.exit_code in (126, 127)
        assert not result.ok


def test_timeout_is_distinct_from_failure(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(["sh", "-c", "sleep 5"], timeout=0.3)
        assert result.timed_out
        assert not result.ok


# --- reset ---------------------------------------------------------------


def test_reset_discards_untracked_and_tracked_changes(git_repo: Path) -> None:
    """A failed attempt leaves no trace in the next (#27)."""
    with TempDirSandbox(git_repo) as sandbox:
        (sandbox.workspace / "app.py").write_text(
            "print('mutated')\n", encoding="utf-8"
        )
        (sandbox.workspace / "scratch.tmp").write_text("junk\n", encoding="utf-8")
        sandbox.reset()
        assert (sandbox.workspace / "app.py").read_text() == "print('hello')\n"
        assert not (sandbox.workspace / "scratch.tmp").exists()


# --- teardown ------------------------------------------------------------


def test_workspace_is_removed_on_exit(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        workspace = sandbox.workspace
        assert workspace.exists()
    assert not workspace.exists()


def test_workspace_is_removed_even_when_the_body_raises(git_repo: Path) -> None:
    workspace: Path | None = None
    with pytest.raises(RuntimeError), TempDirSandbox(git_repo) as sandbox:
        workspace = sandbox.workspace
        raise RuntimeError("task blew up")
    assert workspace is not None and not workspace.exists()


def test_reaper_is_registered_while_open_and_cleared_after(git_repo: Path) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        assert id(sandbox) in base_module._LIVE_REAPERS
    assert id(sandbox) not in base_module._LIVE_REAPERS


# --- credentials stay out (weaker mode still holds this) ------------------


def test_host_credential_is_scrubbed_from_the_command_env(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-appear")
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(["sh", "-c", "echo seen=${ANTHROPIC_API_KEY:-absent}"])
        assert "sk-should-never-appear" not in result.stdout
        assert "absent" in result.stdout


def test_caller_supplied_credential_is_dropped_but_benign_var_passes(
    git_repo: Path,
) -> None:
    with TempDirSandbox(git_repo) as sandbox:
        result = sandbox.run(
            ["sh", "-c", "echo k=${OPENAI_API_KEY:-none} m=${MCGYVR_ENDPOINTS:-none}"],
            env={"OPENAI_API_KEY": "leak", "MCGYVR_ENDPOINTS": "http://x"},
        )
        assert "leak" not in result.stdout
        assert "k=none" in result.stdout
        assert "m=http://x" in result.stdout


# --- factory -------------------------------------------------------------


def test_factory_tempdir_mode_returns_tempdir_with_weaker_note(git_repo: Path) -> None:
    sandbox = open_sandbox(git_repo, mode="tempdir", docker_available=True)
    assert isinstance(sandbox, TempDirSandbox)
    assert sandbox.isolation == "process"
    assert any("weaker" in note for note in sandbox.notes)


def test_factory_docker_without_daemon_falls_back_and_says_so(git_repo: Path) -> None:
    sandbox = open_sandbox(git_repo, mode="docker", docker_available=False)
    assert isinstance(sandbox, TempDirSandbox)
    assert any("no daemon answered" in note for note in sandbox.notes)
