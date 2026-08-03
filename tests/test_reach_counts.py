"""Offline invariants over #129's three counts.

``test_reach_corpus.py`` guards the denominator; these guard the numerators. All
of it runs from the checked-in rows — no Docker, no network, no clone — because
a test that needed the measurement rig to re-run would be skipped in CI and
would therefore guard nothing.

The property worth having is the one #129's acceptance asks for: *each count
re-runs to the same number from the checked-in corpus*. That splits in two, and
only the second half can be a unit test. Re-running the instrument is the rig's
job (``--run``). What is checkable here, and what actually catches the mistakes,
is that the published totals are a faithful reduction of the rows beneath them
and that the rows still line up with the pinned corpus — a count that drifted
from its own evidence, or from the denominator, fails before anyone quotes it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "records" / "corpora" / "reach-2026-08-02" / "corpus.json"
MEASUREMENTS = REPO / "records" / "measurements" / "reach-2026-08-03"

COUNT1 = MEASUREMENTS / "count1-reach.jsonl"
COUNT2 = MEASUREMENTS / "count2-absence.jsonl"
COUNT3 = MEASUREMENTS / "count3-falsepos.jsonl"

# ghostcall parses Python, so Count 3's denominator is the Python frames only.
PYTHON_FRAMES = frozenset({"AdarGit008/mcgyvr", "pallets/click"})


def _rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        json.loads(line) for line in path.read_text().splitlines() if line
    ]
    return rows


def _corpus() -> dict[str, Any]:
    corpus: dict[str, Any] = json.loads(CORPUS.read_text(encoding="utf-8"))
    return corpus


def _pinned() -> dict[tuple[str, str], int]:
    """(frame, commit) -> the added source lines the corpus pins for it."""
    return {
        (frame["repo"], change["commit"]): change["added_source_lines"]
        for frame in _corpus()["frames"]
        for change in frame["changes"]
    }


@pytest.mark.parametrize("path", [COUNT1, COUNT2, COUNT3])
def test_rows_exist(path: Path) -> None:
    """A vacuous pass here would hide every property below."""
    assert path.is_file(), f"{path.name} has not been measured"
    assert _rows(path), f"{path.name} is empty"


@pytest.mark.parametrize("path", [COUNT1, COUNT2])
def test_every_corpus_change_is_measured_exactly_once(path: Path) -> None:
    """The numerator's population is the denominator's, with nothing counted twice."""
    keys = [(row["frame"], row["commit"]) for row in _rows(path)]
    assert len(keys) == len(set(keys)), "a change appears twice"
    assert set(keys) == set(_pinned()), (
        "the measured changes are not the corpus's changes — a count over a "
        "different population than the pinned denominator is not comparable to it"
    )


def test_count3_covers_the_python_frames_exactly() -> None:
    """ghostcall is Python-only, and the skipped frame must be visibly skipped."""
    keys = [(row["frame"], row["commit"]) for row in _rows(COUNT3)]
    expected = {k for k in _pinned() if k[0] in PYTHON_FRAMES}
    assert len(keys) == len(set(keys)), "a change appears twice"
    assert set(keys) == expected
    assert {k[0] for k in keys} == PYTHON_FRAMES


def test_count1_added_lines_match_the_pinned_corpus() -> None:
    """The rig recomputes which lines changed; this pins that they are the same ones.

    ``count1.py`` raises when a recomputed total disagrees with the corpus, so
    this is the same assertion made durable: it would also catch a row edited
    after the fact, which the rig cannot.
    """
    pinned = _pinned()
    for row in _rows(COUNT1):
        key = (row["frame"], row["commit"])
        assert row["added_source_lines"] == pinned[key], (
            f"{key[0]} {key[1][:9]}: row says {row['added_source_lines']} added "
            f"lines, corpus pins {pinned[key]}"
        )


def test_count1_classifies_every_added_line_exactly_once() -> None:
    """Reached + unreached + non-executable + not-reported == added.

    This is the invariant that keeps the headline honest. The tempting error is
    to report "added lines the checks never executed" as added minus reached,
    which silently folds blank lines and comments into the gap and inflates the
    size #123 is being handed. If the four buckets did not partition the added
    lines, that arithmetic would be unavailable and the error invisible.
    """
    for row in _rows(COUNT1):
        if not row["report_present"]:
            continue
        totals = row["totals"]
        parts = (
            totals["reached"]
            + totals["unreached"]
            + totals["non_executable"]
            + totals["not_reported"]
        )
        assert parts == totals["added"] == row["added_source_lines"], (
            f"{row['frame']} {row['commit'][:9]}: buckets sum to {parts} but "
            f"{totals['added']} lines were added"
        )


def test_count1_file_entries_sum_to_their_row() -> None:
    """Per-file detail and the row's totals are the same measurement."""
    keys = ("added", "reached", "unreached", "non_executable", "not_reported")
    for row in _rows(COUNT1):
        if not row["report_present"]:
            continue
        for key in keys:
            summed = sum(entry[key] for entry in row["files"])
            assert summed == row["totals"][key], (
                f"{row['frame']} {row['commit'][:9]}: files sum to {summed} "
                f"for {key!r}, row totals say {row['totals'][key]}"
            )


def test_count2_records_a_signal_whenever_it_claims_a_declaration() -> None:
    """ "Declared" must name the file and the signal, so a reader can disagree."""
    for row in _rows(COUNT2):
        assert row["declared"] == bool(row["signals"])
        for signal in row["signals"]:
            assert signal["file"] and signal["signal"]


def test_count2_agrees_with_the_corpus_declared_check() -> None:
    """The corpus asserts each frame declares a check; Count 2 re-derives it per commit.

    Two independent statements of the same fact — one written by hand into
    ``corpus.json`` during #125, one recomputed from each commit's tree here. If
    they disagreed, one of them is wrong and the absence figure is unusable.
    """
    declared_by_frame = {
        frame["repo"]: frame["declared_check"] for frame in _corpus()["frames"]
    }
    for row in _rows(COUNT2):
        assert declared_by_frame[row["frame"]]["command"], "corpus declares no command"
        assert row["declared"], (
            f"{row['frame']} {row['commit'][:9]}: the corpus says this frame "
            "declares a check, but Count 2 found no declaration at this commit"
        )


def test_count3_added_line_flags_are_a_subset_of_whole_file_flags() -> None:
    """The restricted count cannot exceed the count it restricts."""
    for row in _rows(COUNT3):
        if not row.get("measured"):
            continue
        assert row["calls_on_added_lines"] <= row["calls_in_files"]
        assert row["hallucinated_on_added_lines"] <= row["hallucinated_in_files"]
        assert row["module_missing_on_added_lines"] <= row["module_missing_in_files"]


def test_count3_lists_every_flag_it_counts() -> None:
    """A presumptive false positive is only checkable by hand if it is written down.

    The count is an argument for or against blocking; a bare total would ask the
    reader to trust it. Each flag carries its path, line and chain so the
    presumption ("this code shipped, so a flag is wrong") can be tested against
    the actual call.
    """
    for row in _rows(COUNT3):
        if not row.get("measured"):
            continue
        assert len(row["flags"]) == row["hallucinated_in_files"], (
            "every flag must be written down, not only the ones on added lines "
            "— the off-line flags are the only evidence this corpus yields "
            "about what the resolver objects to"
        )
        on_added = sum(1 for flag in row["flags"] if flag["on_added_line"])
        assert on_added == row["hallucinated_on_added_lines"]
        for flag in row["flags"]:
            assert flag["path"] and flag["chain"]
            assert isinstance(flag["line"], int)
