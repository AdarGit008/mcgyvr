"""Internal consistency of the #125 reach corpus.

``tools/reach/enumerate.py --check`` is the real reproduction check, but it
fetches two external repositories and cannot run in an offline suite. These
guard the property that check would otherwise be the only thing standing
between a hand-edited corpus and a quoted number: that the totals are the
frames, that every commit is a real sha, and that nothing is counted twice.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "records" / "corpora" / "reach-2026-08-02" / "corpus.json"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(CORPUS.read_text(encoding="utf-8"))
    return doc


def test_totals_are_the_frames(corpus: dict[str, Any]) -> None:
    """A total nobody recomputes is a number, not a measurement."""
    frames = corpus["frames"]
    assert corpus["totals"]["frames"] == len(frames)
    assert corpus["totals"]["changes"] == sum(len(f["changes"]) for f in frames)
    assert corpus["totals"]["added_source_lines"] == sum(
        c["added_source_lines"] for f in frames for c in f["changes"]
    )


def test_every_commit_is_a_full_sha(corpus: dict[str, Any]) -> None:
    """Abbreviations collide and refs move; the corpus pins neither."""
    for frame in corpus["frames"]:
        assert _SHA40.match(frame["pinned_commit"]), frame["repo"]
        for change in frame["changes"]:
            assert _SHA40.match(change["commit"]), f"{frame['repo']} {change['commit']}"


def test_no_change_is_counted_twice(corpus: dict[str, Any]) -> None:
    """A duplicated commit inflates a denominator silently."""
    for frame in corpus["frames"]:
        commits = [c["commit"] for c in frame["changes"]]
        assert len(commits) == len(set(commits)), f"{frame['repo']} repeats a commit"


def test_every_change_adds_source(corpus: dict[str, Any]) -> None:
    """A zero-add change is not in the rung's territory and skews reach."""
    for frame in corpus["frames"]:
        for change in frame["changes"]:
            assert change["added_source_lines"] > 0, change["commit"]
            assert change["source_files"], change["commit"]


def test_source_files_match_the_frame_glob(corpus: dict[str, Any]) -> None:
    """Each frame counts its own language, so a stray path corrupts the split."""
    for frame in corpus["frames"]:
        prefix, _, suffix = frame["source_glob"].partition("**/*")
        for change in frame["changes"]:
            for path in change["source_files"]:
                assert path.startswith(prefix) and path.endswith(suffix), (
                    f"{frame['repo']} counts {path!r}, "
                    f"outside its glob {frame['source_glob']!r}"
                )


def test_enumeration_limits_are_respected(corpus: dict[str, Any]) -> None:
    """The window is a stated bound; a frame over it means the data was edited."""
    limits = corpus["enumeration"]["limits"]
    for frame in corpus["frames"]:
        assert frame["repo"] in limits, f"{frame['repo']} has no declared limit"
        assert len(frame["changes"]) <= limits[frame["repo"]]


def test_both_launch_languages_are_represented(corpus: dict[str, Any]) -> None:
    """#125 asks for at least one external repository per shipped adapter."""
    external = {f["language"] for f in corpus["frames"] if f["role"] == "external"}
    assert external == {"python", "javascript"}, external
