"""The notes on a release are the notes in the repository, or there is no release.

`gh release create --generate-notes` makes raw PR titles, in merge order, of the
range: a log of how the work landed, not a description of what the version is.
The release reads CHANGELOG.md instead, so the tag, the release page and the
file a reader opens carry one text.

That only helps if the tool is loud when there is nothing to read. Generated
notes cannot be empty — there are always commits to list — but reading a file
can reach "the notes are empty" two ways, and both stop the release here: the
version has no section at all, or it has one with nothing under it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.release.changelog_notes import (
    NoNotesError,
    main,
    notes_for,
    released,
    sections,
)

REPO = Path(__file__).resolve().parents[1]
CHANGELOG = REPO / "CHANGELOG.md"

#: A changelog shaped the way this repository's is: an open section, a written
#: release, an older release, and a prose heading over entries kept for the
#: record that names no version at all.
WRITTEN = """\
# Changelog

Format: [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]

## [0.2.0] - 2026-09-16

### Added
- `mcgyvr fleet` — lock a fleet and read what the lock approves.

### Fixed
- A shim registers the module it loads.

## [0.1.0] - 2026-09-06

### Added
- The first one.

## Entries written before 0.2.0

### Added
- Repo founded.
"""


def test_the_notes_are_that_versions_section_and_stop_at_the_next_heading() -> None:
    notes = notes_for("v0.2.0", WRITTEN)
    assert "`mcgyvr fleet`" in notes
    assert "### Added" in notes and "### Fixed" in notes
    assert "The first one." not in notes, "the notes ran into the older release"
    assert "Repo founded." not in notes, "the notes ran into the kept entries"


def test_a_version_with_no_section_is_refused_and_says_what_to_write() -> None:
    with pytest.raises(NoNotesError) as refused:
        notes_for("v0.3.0", WRITTEN)
    assert "0.3.0" in str(refused.value)
    assert "## [0.3.0]" in str(refused.value)


def test_a_section_that_exists_but_is_empty_is_refused() -> None:
    """The bug being removed: notes that are silently nothing. A heading with
    no entries under it is that, and is not a release."""
    empty = WRITTEN.replace(
        "### Added\n- `mcgyvr fleet` — lock a fleet and read what the lock approves.\n"
        "\n### Fixed\n- A shim registers the module it loads.\n",
        "",
    )
    assert "## [0.2.0] - 2026-09-16" in empty
    with pytest.raises(NoNotesError) as refused:
        notes_for("v0.2.0", empty)
    assert "empty" in str(refused.value)


def test_the_open_unreleased_section_is_never_a_releases_notes() -> None:
    """`[Unreleased]` names no version, so a tag cannot fall back onto it and
    ship the next version's half-written entries as its own."""
    assert released("[Unreleased]") is None
    assert released("Entries written before 0.2.0") is None
    with pytest.raises(NoNotesError):
        notes_for("v0.9.0", WRITTEN)


def test_a_pre_release_tag_is_the_section_it_normalises_to() -> None:
    """Compared as versions, as the wheel check compares them: `v0.2.0-rc1`
    normalises to 0.2.0rc1, which is the heading `## [0.2.0rc1]`."""
    text = WRITTEN.replace("## [0.2.0] - 2026-09-16", "## [0.2.0rc1] - 2026-09-16")
    assert "`mcgyvr fleet`" in notes_for("v0.2.0-rc1", text)
    with pytest.raises(NoNotesError):
        notes_for("v0.2.0", text)


def test_a_tag_that_is_not_a_version_is_refused() -> None:
    """This repository also tags `archive/<lane>`; one of those is not a
    release and has no notes to find."""
    with pytest.raises(NoNotesError) as refused:
        notes_for("archive/review-9", WRITTEN)
    assert "not a version" in str(refused.value)


def test_this_repositorys_changelog_has_written_notes_for_its_newest_release() -> None:
    """The file in the tree, not a fixture: the newest version with a section
    must have something under it, or tagging it would refuse."""
    text = CHANGELOG.read_text(encoding="utf-8")
    newest = next(
        version
        for heading, _ in sections(text)
        if (version := released(heading)) is not None
    )
    assert notes_for(f"v{newest}", text).strip()


def test_the_command_prints_the_notes_and_refuses_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the workflow sees: notes on stdout for `--notes-file`, and a
    non-zero exit with the reason on stderr when there are none."""
    path = tmp_path / "CHANGELOG.md"
    path.write_text(WRITTEN, encoding="utf-8")
    assert main(["v0.2.0", str(path)]) == 0
    assert "`mcgyvr fleet`" in capsys.readouterr().out
    assert main(["v9.9.9", str(path)]) == 1
    assert "REFUSED" in capsys.readouterr().err
    assert main(["v9.9.9"]) == 2
