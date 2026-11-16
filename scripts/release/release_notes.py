#!/usr/bin/env python3
"""A release's notes, and its version before a tag names one, read from git.

    python scripts/release/release_notes.py v0.6.0
    python scripts/release/release_notes.py --next

Run from the repository. The first form prints the notes of a release of
HEAD as ``v0.6.0``: the pull requests merged into HEAD's first-parent line
since the previous release tag, one line each, newest first. The second
prints the version a rehearsal (`make release` without RELEASE_VERSION, or
the release workflow dispatched as a dry run from a branch) stamps when no
tag names one yet: the next version after the newest release tag behind HEAD.

Both are read from git alone, never from a forge: a pull request merged on
this forge lands on main as a merge commit titled ``Merge pull request
'<title>' (#N) from <branch> into <base>``, or squashed as one commit titled
``<title> (#N)``, and those subjects are the list. A commit on the first
parent that is neither shape (a direct push) is not a merged pull request and
is not listed.

Refusing is the point, as it was when the notes were a hand-written section:
a tag that is not a version, or a range with no merged pull request since the
previous release tag, stops the release and says why.

A release tag is ``v<digit>…``, the same ``--match`` pyproject.toml gives
hatch-vcs, so the previous release here is the tag the package's own version
is read from, and an ``archive/<lane>`` tag is never one.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

#: What a release tag looks like: the `--match` of pyproject.toml's
#: `git_describe_command`, which a test holds the two to.
RELEASE_TAG = "v[0-9]*"

#: A merged pull request, as its commit on the base branch is titled.
MERGED = re.compile(
    r"^Merge pull request '(?P<title>.+)' \(#(?P<number>\d+)\) from \S+ into \S+$"
)
SQUASHED = re.compile(r"^(?P<title>.+) \(#(?P<number>\d+)\)$")


class NoNotesError(Exception):
    """Why there is no release; the message is what the release prints."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )


def _version(tag: str) -> Version:
    try:
        return Version(tag.removeprefix("v"))
    except InvalidVersion as invalid:
        raise NoNotesError(
            f"the tag {tag!r} is not a version; a release tag is v<PEP 440>"
        ) from invalid


def previous_tag(
    repo: Path, exclude: str | None = None, rev: str = "HEAD"
) -> str | None:
    """The newest release tag behind ``rev`` (``exclude`` left out), or None.

    "Newest" as `git describe` counts it, the nearest one, which is the tag
    hatch-vcs reads the version from. ``exclude`` is the tag being released:
    when it already names ``rev`` its notes still start at the one before.
    """
    if _git(repo, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}").returncode:
        raise NoNotesError(f"{rev} is not a commit in {repo}")
    args = ["describe", "--tags", "--abbrev=0", "--match", RELEASE_TAG]
    if exclude:
        args += ["--exclude", exclude]
    found = _git(repo, *args, rev)
    return found.stdout.strip() if found.returncode == 0 else None


def merged_prs(
    repo: Path, since: str | None, rev: str = "HEAD"
) -> list[tuple[int, str]]:
    """(number, title) of each pull request merged since ``since``, newest first."""
    span = f"{since}..{rev}" if since else rev
    log = _git(repo, "log", "--first-parent", "--format=%s", span)
    if log.returncode:
        raise NoNotesError(f"git log {span} failed: {log.stderr.strip()}")
    found: list[tuple[int, str]] = []
    for subject in log.stdout.splitlines():
        if match := MERGED.match(subject) or SQUASHED.match(subject):
            found.append((int(match["number"]), match["title"]))
    return found


def notes_for(tag: str, repo: Path, rev: str = "HEAD") -> str:
    """The notes of releasing ``rev`` as ``tag``, or ``NoNotesError``."""
    _version(tag)
    since = previous_tag(repo, exclude=tag, rev=rev)
    prs = merged_prs(repo, since, rev)
    if not prs:
        # The owner's default, unconfirmed: nothing merged is no release.
        raise NoNotesError(
            f"no pull request was merged since {since or 'the first commit'}; "
            "a release of nothing merged has no notes"
        )
    heading = (
        f"Merged pull requests since {since}:" if since else "Merged pull requests:"
    )
    return heading + "\n\n" + "".join(f"- {title} (#{n})\n" for n, title in prs)


def next_version(repo: Path, rev: str = "HEAD") -> Version:
    """The version a rehearsal stamps when no tag names ``rev``.

    The default the owner has not confirmed yet, kept in this one function:
    the newest release tag behind ``rev`` with its last number bumped
    (v0.5.1 -> 0.5.2, v0.6.0rc1 -> 0.6.0rc2). That is setuptools-scm's
    guess-next-dev, the version an untagged build of ``rev`` already carries
    (``0.5.2.dev<N>+g<sha>``), without its distance.
    """
    since = previous_tag(repo, rev=rev)
    if since is None:
        raise NoNotesError(
            f"no release tag ({RELEASE_TAG}) is behind {rev}; name the first "
            "version with RELEASE_VERSION"
        )
    bumped = re.fullmatch(r"(.*?)(\d+)", _version(since).public)
    assert bumped, since  # a normalised version always ends in a number
    return Version(f"{bumped[1]}{int(bumped[2]) + 1}")


def main(argv: list[str], repo: Path | None = None) -> int:
    if len(argv) != 1:
        print(f"usage: {Path(sys.argv[0]).name} TAG|--next", file=sys.stderr)
        return 2
    where = repo or Path.cwd()
    try:
        if argv[0] == "--next":
            print(next_version(where))
            return 0
        notes = notes_for(argv[0], where)
    except NoNotesError as why:
        print(f"REFUSED — {why}", file=sys.stderr)
        return 1
    print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
