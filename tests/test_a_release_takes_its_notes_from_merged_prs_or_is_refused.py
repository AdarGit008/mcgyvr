"""The notes on a release are the pull requests merged into it, or there is no release.

Read from git alone, in a temporary repository per test: a pull request lands on
main as a merge commit titled ``Merge pull request '<title>' (#N) from <branch>
into main``, or squashed as ``<title> (#N)``, and the notes of a tag are those
subjects on HEAD's first-parent line since the previous ``v*`` tag. Nothing
merged since that tag is no release, and says so.

The version a release takes when none is named is that of the ``v*`` tag on
HEAD, the version a build of HEAD reads from it, else the next one after the
newest ``v*`` tag, the version an untagged build already carries. A shallow
clone is refused: the range behind its boundary is not there.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.version import Version
from scripts.release.release_notes import (
    RELEASE_TAG,
    NoNotesError,
    main,
    next_version,
    notes_for,
)

from tests._paths import REPO

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, env=ENV
    )


def _commit(repo: Path, subject: str) -> None:
    """A commit straight on main: a direct push, or a squashed pull request."""
    _git(repo, "commit", "-q", "--allow-empty", "-m", subject)


def _merge(repo: Path, number: int, title: str, work: str = "") -> None:
    """Pull request ``number`` merged into main the way the forge merges it;
    ``work`` is the subject of the branch's own commit."""
    branch = f"pr-{number}"
    _git(repo, "checkout", "-q", "-b", branch)
    _commit(repo, work or f"work on {title}")
    _git(repo, "checkout", "-q", "main")
    message = f"Merge pull request '{title}' (#{number}) from {branch} into main"
    _git(repo, "merge", "-q", "--no-ff", "-m", message, branch)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, "the first commit")
    return tmp_path


def test_the_notes_are_the_prs_merged_since_the_previous_tag(repo: Path) -> None:
    """Both merge shapes, newest first; the branch's own commits (one titled
    like a squash), a direct push and a pull request released under the
    previous tag are not listed: only main's first-parent line is read."""
    _merge(repo, 1, "released before")
    _git(repo, "tag", "v0.1.0")
    _merge(repo, 2, "feat: a")
    _commit(repo, "fix: b (#3)")
    _commit(repo, "a direct push")
    _merge(repo, 4, "fix(x): it's quoted")
    _merge(repo, 5, "feat: c", work="fix: off the first-parent line (#9)")
    assert notes_for("v0.2.0", repo) == (
        "Merged pull requests since v0.1.0:\n\n"
        "- feat: c (#5)\n"
        "- fix(x): it's quoted (#4)\n"
        "- fix: b (#3)\n"
        "- feat: a (#2)\n"
    )


def test_a_range_with_no_merged_pr_is_refused_and_names_the_tag(repo: Path) -> None:
    _merge(repo, 1, "released before")
    _git(repo, "tag", "v0.1.0")
    _commit(repo, "a direct push")
    with pytest.raises(NoNotesError) as refused:
        notes_for("v0.1.1", repo)
    assert "since v0.1.0" in str(refused.value), refused.value


def test_a_tag_that_is_not_a_version_is_refused(repo: Path) -> None:
    """This repository also tags `archive/<lane>`; that is not a release. A
    pre-release tag is a version, as the wheel check reads it."""
    _merge(repo, 1, "feat: a")
    with pytest.raises(NoNotesError) as refused:
        notes_for("archive/review-9", repo)
    assert "not a version" in str(refused.value)
    assert "- feat: a (#1)" in notes_for("v0.2.0-rc1", repo)


def test_the_tag_being_released_is_not_its_own_previous(repo: Path) -> None:
    """The tag's own run reads the notes with the tag on HEAD: they still
    start at the release before, and an archive tag is never a release."""
    _git(repo, "tag", "v0.1.0")
    _merge(repo, 2, "feat: a")
    _git(repo, "tag", "v0.2.0")
    _git(repo, "tag", "archive/review-9")
    assert notes_for("v0.2.0", repo) == (
        "Merged pull requests since v0.1.0:\n\n- feat: a (#2)\n"
    )


def test_with_no_release_tag_behind_the_notes_are_the_whole_history(
    repo: Path,
) -> None:
    _merge(repo, 1, "feat: a")
    _merge(repo, 2, "feat: b")
    assert notes_for("v0.1.0", repo) == (
        "Merged pull requests:\n\n- feat: b (#2)\n- feat: a (#1)\n"
    )


def test_the_next_version_is_the_tag_on_head_or_bumps_the_newest(repo: Path) -> None:
    """On a commit a release tag names, its version, as a build of that commit
    reads it (distance 0). Past it, the newest tag's last number bumped:
    v0.5.1 -> 0.5.2, and a pre-release goes to the next pre-release. No
    release tag at all is refused: the first version is named by hand."""
    with pytest.raises(NoNotesError) as refused:
        next_version(repo)
    assert "RELEASE_VERSION" in str(refused.value)
    _git(repo, "tag", "v0.5.1")
    assert next_version(repo) == Version("0.5.1")
    _merge(repo, 1, "feat: a")
    _git(repo, "tag", "archive/review-9")
    assert next_version(repo) == Version("0.5.2")
    _git(repo, "tag", "-a", "v0.6.0-rc1", "-m", "an annotated pre-release")
    assert next_version(repo) == Version("0.6.0rc1")
    _commit(repo, "a direct push")
    assert next_version(repo) == Version("0.6.0rc2")


def test_a_shallow_clone_is_refused_not_listed_short(repo: Path) -> None:
    """A clone cut at depth 1 has no tag behind its boundary: its list would be
    the last commit alone, printed as if it were the whole range."""
    _git(repo, "tag", "v0.1.0")
    for n in (1, 2, 3):
        _merge(repo, n, f"feat: {n}")
    assert notes_for("v0.2.0", repo).count("\n- ") == 3
    shallow = repo / "shallow"
    _git(repo, "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow))
    with pytest.raises(NoNotesError) as refused:
        notes_for("v0.2.0", shallow)
    assert "shallow clone" in str(refused.value), refused.value
    with pytest.raises(NoNotesError) as refused:
        next_version(shallow)
    assert "shallow clone" in str(refused.value), refused.value


def test_a_release_tag_is_the_tag_the_package_version_is_read_from() -> None:
    """One spelling of "release tag": the previous release the notes start
    at is the tag hatch-vcs reads the version from."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    describe = project["tool"]["hatch"]["version"]["raw-options"][
        "git_describe_command"
    ]
    assert describe[describe.index("--match") + 1] == RELEASE_TAG, describe


def test_the_command_prints_and_refuses_loudly(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the workflow and `make release` see: notes or a version on stdout,
    and a non-zero exit with the reason on stderr when there is none."""
    _merge(repo, 1, "feat: a")
    _git(repo, "tag", "v0.1.0")
    assert main(["v0.1.1"], repo) == 1
    assert "REFUSED" in capsys.readouterr().err
    assert main(["--next"], repo) == 0
    assert capsys.readouterr().out == "0.1.0\n"
    _merge(repo, 2, "feat: b")
    assert main(["--next"], repo) == 0
    assert capsys.readouterr().out == "0.1.1\n"
    assert main(["v0.1.1"], repo) == 0
    assert capsys.readouterr().out.endswith("- feat: b (#2)\n")
    assert main([], repo) == 2
