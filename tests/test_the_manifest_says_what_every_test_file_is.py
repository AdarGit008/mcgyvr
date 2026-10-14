"""The manifest says what every test file is, and it has to be right.

``tests/MANIFEST.tsv`` is only worth having if it cannot drift from the
tests on disk. This checks that it names every test file and only test files
that exist, that every answer in it is a real level and a real kind, and
that the markers it hands pytest are the ones pytest has been told about.

The last test is a ratchet. The counts below are what is still unsettled:
files the two passes read differently, and files classified here off what
they do rather than by either pass. A new test file lands as neither, so the
count moves and the gate asks for it to be classified. The numbers come
down; they do not go up.
"""

from __future__ import annotations

import tomllib

from tests._paths import REPO
from tests.manifest import COLUMNS, KINDS, LEVELS, MANIFEST, OPEN, SOURCES, rows

#: What is still unsettled, and may only shrink.
STILL_DISPUTED = 277
STILL_DERIVED = 9
STILL_UNREVIEWED = 44


def _test_files() -> set[str]:
    return {str(p.relative_to(REPO)) for p in (REPO / "tests").rglob("test_*.py")}


def test_the_manifest_names_every_test_file_and_nothing_else() -> None:
    listed, here = set(rows()), _test_files()
    assert not here - listed, (
        "a test file is in no row of tests/MANIFEST.tsv, so nothing says "
        f"what it is: {sorted(here - listed)}"
    )
    assert not listed - here, (
        "a row of tests/MANIFEST.tsv names a file that is not there; drop "
        f"the row with the file: {sorted(listed - here)}"
    )


def test_every_answer_in_the_manifest_is_one_of_the_answers() -> None:
    for path, row in sorted(rows().items()):
        assert row.level_by in SOURCES, (path, row.level_by)
        assert row.marker_by in SOURCES, (path, row.marker_by)
        for level in row.levels:
            assert level in LEVELS, (path, level)
        for marker in row.markers:
            assert marker in KINDS, (path, marker)
        if row.level_by == "unreviewed":
            assert not row.levels, f"{path} is unreviewed but carries a level"
        else:
            assert row.levels, f"{path} has no level at all"
        if row.marker_by == "unreviewed":
            assert not row.markers, f"{path} is unreviewed but carries a kind"
        else:
            assert row.markers, f"{path} has no kind at all"


def test_a_disputed_row_carries_both_readings_and_a_derived_row_its_reason() -> None:
    for path, row in sorted(rows().items()):
        if row.level_by == "disputed":
            assert len(row.levels) == 2, (
                f"{path} is a disputed level but does not carry two readings"
            )
            assert row.levels[0] != row.levels[1], path
        elif row.level_by != "unreviewed":
            assert len(row.levels) == 1, (
                f"{path} carries two levels but is not marked disputed"
            )
        if row.marker_by == "disputed":
            assert len(row.markers) == 2, path
            assert row.markers[0] != row.markers[1], path
        elif row.marker_by != "unreviewed":
            assert len(row.markers) == 1, path
        if "derived" in (row.level_by, row.marker_by):
            assert row.why.strip(), (
                f"{path} was classified here, so the row has to say on what evidence"
            )
        else:
            assert not row.why, f"{path} gives a reason for an answer it was given"


def test_pytest_has_been_told_about_every_marker_the_manifest_hands_it() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {
        line.split(":", 1)[0]
        for line in config["tool"]["pytest"]["ini_options"]["markers"]
    }
    wanted = {mark for row in rows().values() for mark in row.marks()}
    assert wanted <= declared, (
        "the manifest marks tests with something pyproject.toml does not "
        f"declare, and --strict-markers will refuse it: {sorted(wanted - declared)}"
    )
    assert "--strict-markers" in config["tool"]["pytest"]["ini_options"]["addopts"], (
        "without --strict-markers a typo in a marker is silently a new marker"
    )


def test_what_is_still_unsettled_only_shrinks() -> None:
    found = rows().values()
    counted = (
        sum(1 for row in found if row.disputed),
        sum(1 for row in found if "derived" in (row.level_by, row.marker_by)),
        sum(1 for row in found if row.unreviewed),
    )
    expected = (STILL_DISPUTED, STILL_DERIVED, STILL_UNREVIEWED)
    assert counted == expected, (
        f"disputed, derived and unreviewed count {counted}, where this file "
        f"expects {expected}. Higher means a test file arrived without a "
        "level and a kind. Lower means some were settled: say so here, so "
        "they cannot creep back."
    )


def test_an_open_row_is_reachable_by_the_marker_that_says_it_is_open() -> None:
    """The open work has to be countable, or it is just a gap."""
    for path, row in sorted(rows().items()):
        marks = row.marks()
        for which in OPEN:
            if which in (row.level_by, row.marker_by):
                assert which in marks, (
                    f"{path} is {which} but carries no {which} marker, so "
                    "`pytest -m " + which + "` would not find it"
                )


def test_the_manifest_is_a_tab_separated_file_with_one_header() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    assert text.endswith("\n"), "tests/MANIFEST.tsv does not end in a newline"
    assert text.splitlines()[0] == "\t".join(COLUMNS)
    for number, line in enumerate(text.splitlines()[1:], start=2):
        assert "  " not in line, (
            f"tests/MANIFEST.tsv:{number} has run-together spaces; the "
            "columns are separated by tabs"
        )
