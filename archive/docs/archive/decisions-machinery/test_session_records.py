"""The one field in a session record that a machine reads.

`baseline`'s FLOW-03 gates a lane on its newest session record carrying a
filled-in `next:`, and the reading is narrow: `extractNext`
(`tools/baseline/src/facts/git.mjs:65-75`) scans only the lines between a
`## Left open` heading and the next `##`. A `next:` line written anywhere else
parses as empty, and the record looks — to the only reader that acts on it —
like a session that recorded no next step.

**This has now cost the repo twice.** `records/sessions/lane/266/`'s newest
record is named `the-record-that-restores-flow-03`, and lane/286 hit it again on
2026-08-23 when a section appended to session 23's record landed between its
`## Left open` heading and its `next:` line. Both times the fix was another
record rather than a check, which is why the second time was possible.

The vendored baseline tree is hash-pinned (REC-06) and must not be edited, so
this is the rule restated on the repo's own side, over the repo's own records.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SESSIONS = REPO / "records" / "sessions"

#: `extractNext`'s two patterns, transcribed. Kept as literals rather than
#: imported: the source of truth is JavaScript in a pinned tree, and a
#: transcription that drifts fails loudly here rather than in CI on a lane.
_SECTION = re.compile(r"^##\s+Left open\b", re.IGNORECASE)
_NEXT = re.compile(r"^\s*next:\s*(.*)$", re.IGNORECASE)
_HEADING = re.compile(r"^##\s")


def _extract_next(markdown: str) -> str | None:
    """`extractNext`, line for line, including where it stops looking."""
    lines = markdown.split("\n")
    start = next((i for i, line in enumerate(lines) if _SECTION.match(line)), None)
    if start is None:
        return None
    for line in lines[start + 1 :]:
        if _HEADING.match(line):
            break
        found = _NEXT.match(line)
        if found:
            return found.group(1).strip() or None
    return None


def _newest_per_lane() -> list[Path]:
    """The record FLOW-03 would read for each lane, by its own rule.

    `newestLocalLog` sorts the directory's `*.md` names and takes the last, so
    the newest is a property of the FILENAME and not of the file's mtime or of
    git. Reproduced here rather than approximated.
    """
    return [
        sorted(directory.glob("*.md"))[-1]
        for directory in sorted(SESSIONS.rglob("*"))
        if directory.is_dir() and any(directory.glob("*.md"))
    ]


def test_every_lanes_newest_record_states_a_next_where_the_gate_reads_it() -> None:
    """The blocker itself: not "a `next:` exists" but "the gate can see it".

    Scoped to the newest record per lane because that is exactly what FLOW-03
    reads. Four older records in the tree have an unreadable `next:` and are
    left alone — they gate nothing, and rewriting a closed lane's history to
    satisfy a check would be the check reaching past what it protects.
    """
    unreadable = []
    for record in _newest_per_lane():
        text = record.read_text(encoding="utf-8")
        if _extract_next(text) is None:
            has_line = any(_NEXT.match(line) for line in text.split("\n"))
            unreadable.append(
                f"{record.relative_to(REPO)}: "
                + (
                    "a `next:` line exists but sits outside the `## Left open` "
                    "section, where extractNext cannot reach it"
                    if has_line
                    else "no `next:` under a `## Left open` heading"
                )
            )
    assert not unreadable, "FLOW-03 will block these lanes:\n" + "\n".join(unreadable)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("## Left open\n\nnext: #1 do the thing\n", "#1 do the thing"),
        # The 2026-08-23 defect, exactly: an appended section between the
        # heading and the line. `extractNext` stops at the `##` and answers
        # None, and FLOW-03 reads that as a session that recorded nothing.
        ("## Left open\n\n## Appended\n\nnext: #1 do the thing\n", None),
        # A `next:` with a heading but no text is the same failure FLOW-03
        # names in its own message: an empty next:.
        ("## Left open\n\nnext:\n", None),
        ("no headings at all\n\nnext: #1 do the thing\n", None),
    ],
)
def test_canary_the_transcribed_reader_stops_where_the_pinned_one_stops(
    body: str, expected: str | None
) -> None:
    """A reader copied from another language is worth exactly its canary.

    The second case is the one that cost a lane a green CI row, and a
    transcription that missed the `##` break would pass the check above while
    the pinned reader still failed the lane.
    """
    assert _extract_next(body) == expected
