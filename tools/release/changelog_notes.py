#!/usr/bin/env python3
"""Print one version's CHANGELOG.md section, or refuse to release without it.

    python tools/release/changelog_notes.py v0.2.0 CHANGELOG.md

The release workflow runs this between the wheel check and `gh release
create`, and hands what it prints to `--notes-file`. So the notes a reader
gets from the release are the notes a reader gets from the repository: one
text, written once, in CHANGELOG.md, rather than a second description of the
same changes that drifts from the first.

Refusing is the point. `--generate-notes` always produced something — the raw
PR titles of the range — so a release could carry notes nobody wrote and
nothing said so. Here a tag whose version has no section, or whose section is
empty, stops the release and names the heading that has to exist.

Compared as versions and not as strings, for the reason
tools/release/wheel_is_tag.py compares that way: a release tag is PEP
440-normalised on the way to being a version, so `v0.2.0-rc1` is the section
`## [0.2.0rc1]` and the two are not a mismatch.
"""

from __future__ import annotations

import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version


class NoNotesError(Exception):
    """Why a tag has no written notes; the message is what the release prints."""


def released(heading: str) -> Version | None:
    """The version a `## ` heading names, or None when it names no release.

    Keep a Changelog spells a released section `## [0.2.0] - 2026-09-16` and
    the open one `## [Unreleased]`. A heading that is neither — a plain prose
    heading over entries kept for the record — names no release, and is passed
    over rather than being an error.
    """
    if not heading.startswith("["):
        return None
    label, _, _rest = heading[1:].partition("]")
    try:
        return Version(label.strip())
    except InvalidVersion:
        return None


def sections(changelog: str) -> list[tuple[str, list[str]]]:
    """Each `## ` heading's text and the lines under it, in file order.

    A section runs to the next `## `, so the `### Added` / `### Fixed` groups
    inside it are its body and not boundaries of their own.
    """
    found: list[tuple[str, list[str]]] = []
    for line in changelog.splitlines():
        if line.startswith("## "):
            found.append((line[3:].strip(), []))
        elif found:
            found[-1][1].append(line)
    return found


def notes_for(tag: str, changelog: str) -> str:
    """``tag``'s section body, or raise ``NoNotesError`` naming what is missing."""
    try:
        wanted = Version(tag.removeprefix("v"))
    except InvalidVersion as invalid:
        raise NoNotesError(
            f"the tag {tag!r} is not a version; a release tag is v<PEP 440>"
        ) from invalid
    for heading, body in sections(changelog):
        if released(heading) != wanted:
            continue
        written = "\n".join(body).strip()
        if not written:
            raise NoNotesError(
                f"the section '## {heading}' is empty; a release whose notes are "
                "empty is a release nobody wrote"
            )
        return written + "\n"
    raise NoNotesError(
        f"the changelog has no section for {wanted}; write "
        f"'## [{wanted}] - <date>' in it before tagging that version"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} TAG CHANGELOG", file=sys.stderr)
        return 2
    tag, changelog = argv[0], Path(argv[1])
    try:
        notes = notes_for(tag, changelog.read_text(encoding="utf-8"))
    except NoNotesError as why:
        print(f"REFUSED — {why}", file=sys.stderr)
        return 1
    print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
