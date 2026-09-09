"""Attach holds the boundary the whole orchestrator sits behind: a repository
is required, and both a local checkout and a clone URL reach the *same*
internal state at a known revision.

These tests pin the three acceptance criteria of #46 — both input forms
converge, missing input fails immediately with an actionable message, and a
dirty local tree is reported before any work begins — plus the failure modes a
loose implementation would wave through: a non-git directory, a file where a
directory was expected, and an input that is neither a path nor a URL. The
clone path is exercised without a network by cloning a local repository through
a ``file://`` URL.

One more boundary sits here since 2026-09-05: an ssh remote is refused before
git runs, because ``git clone`` over ssh spawns ``ssh`` from PATH and nothing
in mcgyvr opens ssh except the rig door (``mcgyvr.serving.gatelib.ssh``).
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import pytest

from mcgyvr.orchestrator.repo import (
    _EMPTY_TREE,
    AttachedRepo,
    AttachError,
    _looks_remote,
    _ssh_form,
    attach,
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def init_repo(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    return repo


def commit_seed(repo: Path) -> None:
    (repo / "seed.txt").write_text("seed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")


def head(repo: Path) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    )
    return out.stdout.strip()


# --- missing / malformed input fails loud ----------------------------------


@pytest.mark.parametrize("source", [None, "", "   "])
def test_missing_input_fails_immediately(source: str | None) -> None:
    with pytest.raises(AttachError, match="no repository supplied"), attach(source):
        pass


def test_input_that_is_neither_path_nor_url_fails(tmp_path: Path) -> None:
    with (
        pytest.raises(AttachError, match="neither an existing directory"),
        attach(str(tmp_path / "does-not-exist")),
    ):
        pass


def test_a_file_is_not_a_repository_directory(tmp_path: Path) -> None:
    target = tmp_path / "a-file"
    target.write_text("x")
    with (
        pytest.raises(AttachError, match="is a file, not a repository"),
        attach(str(target)),
    ):
        pass


def test_a_plain_directory_is_not_a_git_repository(tmp_path: Path) -> None:
    with (
        pytest.raises(AttachError, match="not a git repository"),
        attach(str(tmp_path)),
    ):
        pass


# --- local checkout ---------------------------------------------------------


def test_local_checkout_reaches_expected_state(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    commit_seed(repo)

    with attach(str(repo)) as attached:
        assert isinstance(attached, AttachedRepo)
        assert attached.root == repo.resolve()
        assert attached.origin == "local"
        assert attached.ephemeral is False
        assert attached.revision == head(repo)
        assert attached.is_dirty is False
        assert attached.dirty == ()


def test_a_subdirectory_normalises_to_the_repo_root(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    commit_seed(repo)
    nested = repo / "src" / "deep"
    nested.mkdir(parents=True)

    with attach(str(nested)) as attached:
        assert attached.root == repo.resolve()


def test_dirty_working_tree_is_reported(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    commit_seed(repo)
    (repo / "seed.txt").write_text("changed\n")  # modify tracked
    (repo / "untracked.py").write_text("x = 1\n")  # add untracked

    with attach(str(repo)) as attached:
        assert attached.is_dirty is True
        assert "seed.txt" in attached.dirty
        assert "untracked.py" in attached.dirty


def test_a_staged_rename_is_a_single_dirty_path(tmp_path: Path) -> None:
    # A rename record carries an extra NUL-delimited origin path; it must be
    # skipped, not counted as a second unrelated dirty entry.
    repo = init_repo(tmp_path / "repo")
    commit_seed(repo)
    git(repo, "mv", "seed.txt", "renamed.txt")

    with attach(str(repo)) as attached:
        assert attached.is_dirty is True
        # Exactly one path is reported for the rename, not two.
        assert len(attached.dirty) == 1


def test_unborn_repository_uses_the_empty_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")  # no commit yet

    with attach(str(repo)) as attached:
        assert attached.revision == _EMPTY_TREE
        assert attached.is_unborn is True


# --- clone from a URL -------------------------------------------------------


def _file_url(path: Path) -> str:
    return f"file://{path.resolve()}"


def test_clone_reaches_the_same_state_as_local(tmp_path: Path) -> None:
    origin = init_repo(tmp_path / "origin")
    commit_seed(origin)

    with attach(_file_url(origin)) as attached:
        assert attached.origin == "clone"
        assert attached.ephemeral is True
        # A fresh clone carries the origin's revision and a clean tree — the
        # same shape a local checkout produced above.
        assert attached.revision == head(origin)
        assert attached.is_dirty is False
        assert attached.root.is_dir()
        assert (attached.root / "seed.txt").exists()


def test_ephemeral_clone_is_removed_on_exit(tmp_path: Path) -> None:
    origin = init_repo(tmp_path / "origin")
    commit_seed(origin)

    with attach(_file_url(origin)) as attached:
        root = attached.root
        assert root.is_dir()
    assert not root.exists()  # torn down with the context


def test_clone_into_a_named_directory_persists(tmp_path: Path) -> None:
    origin = init_repo(tmp_path / "origin")
    commit_seed(origin)
    dest = tmp_path / "kept"

    with attach(_file_url(origin), into=dest) as attached:
        assert attached.ephemeral is False
        assert attached.root == dest.resolve()
    assert dest.is_dir()  # caller owns the lifetime; left in place
    assert (dest / "seed.txt").exists()


def test_clone_failure_is_loud(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-repo"
    with (
        pytest.raises(AttachError, match="could not clone"),
        attach(_file_url(missing)),
    ):
        pass


@pytest.mark.parametrize(
    "source",
    [
        "https://github.com/owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "git://github.com/owner/repo.git",
        "file:///srv/repos/repo.git",
        "git@github.com:owner/repo.git",  # scp-like short form
    ],
)
def test_urls_are_recognised_as_remote(source: str) -> None:
    assert _looks_remote(source) is True


@pytest.mark.parametrize(
    "source",
    [
        "/home/user/repo",
        "./relative/repo",
        "repo",
        r"C:\Users\me\repo",  # a Windows drive path is not an scp-like URL
    ],
)
def test_local_paths_are_not_mistaken_for_remote(source: str) -> None:
    assert _looks_remote(source) is False


# --- ssh remotes: refused before git runs, so no ssh is ever spawned ------

SSH_REFUSED = (
    "an ssh remote is refused: nothing in mcgyvr opens ssh except the rig "
    "door; use https://, git://, file:// or a local path"
)


def _never(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError(f"git was spawned: {args}")


@pytest.mark.parametrize(
    "source",
    [
        "ssh://git@github.com/owner/repo.git",
        "SSH://github.com/owner/repo.git",
        "git+ssh://git@github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
        "srv1:/home/adaramir/repos/x.git",
        "adaramir@srv2:repos/x.git",
    ],
    ids=[
        "ssh-scheme",
        "SSH-upper",
        "git+ssh",
        "git-at-host",
        "host-path",
        "user-at-host-path",
    ],
)
def test_an_ssh_remote_is_refused_before_git_runs(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", _never)
    with pytest.raises(AttachError) as raised, attach(source):
        pass
    assert SSH_REFUSED in str(raised.value), str(raised.value)
    assert source in str(raised.value)
    assert _ssh_form(source) is not None


@pytest.mark.parametrize(
    "source",
    [
        "https://github.com/owner/repo.git",
        "http://github.com/owner/repo.git",
        "git://github.com/owner/repo.git",
        "file:///srv/repos/repo.git",
    ],
)
def test_a_transport_that_opens_no_ssh_is_handed_to_git(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: an admitted form reaches ``git clone``. git is a stub that
    fails, so the proof of admission is git's own failure, not a refusal."""
    seen: list[list[str]] = []

    def fake_run(
        argv: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.append(list(argv))
        return subprocess.CompletedProcess(list(argv), 128, "", "fatal: stub")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _ssh_form(source) is None
    with pytest.raises(AttachError, match="could not clone"), attach(source):
        pass
    assert seen and seen[0][:3] == ["git", "clone", "--quiet"], seen
    assert source in seen[0]


@pytest.mark.parametrize(
    "source",
    ["/home/user/repo", "./relative/repo", "repo", r"C:\Users\me\repo"],
)
def test_a_local_path_is_not_an_ssh_form(source: str) -> None:
    assert _ssh_form(source) is None
