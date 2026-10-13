"""A rename splices at the byte the parser named, whatever precedes it on the line.

Both parsers give a column as a byte offset into the line's UTF-8, not a
character index: ``x = "café"; fetch_page()`` puts the call one byte further
right than it is characters. Spliced as text, the rename would cut one
character late — inside the name — and the byte check that guards every
splice exists so that a disagreement like that is reported, never written.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.orchestrator.references import Verdict, resolve
from mcgyvr.rename import apply as rename_apply
from tests.renaming import committed

SOURCE = 'def fetch_page():\n    pass\n\n\nx = "café"; fetch_page()\n'


def test_the_column_is_a_byte_offset_past_non_ascii_text() -> None:
    resolution = resolve(
        {"m.py": SOURCE.encode("utf-8")}, ["m.py"], "m.py", "fetch_page", "get_page"
    )

    (call,) = [o for o in resolution.occurrences if o.line == 5]
    assert call.verdict is Verdict.RENAME
    assert call.column == len('x = "café"; '.encode())
    assert call.column == len('x = "café"; ') + 1, "é is two bytes"


def test_a_line_with_non_ascii_text_before_the_name_is_renamed_cleanly(
    tmp_path: Path,
) -> None:
    repo = committed(tmp_path / "repo", {"m.py": SOURCE})

    report = rename_apply(repo, "fetch_page", "get_page")

    assert (repo / "m.py").read_text(encoding="utf-8") == SOURCE.replace(
        "fetch_page", "get_page"
    )
    assert report.unresolved == ()


def test_a_javascript_column_past_non_ascii_text_is_a_byte_offset_too(
    tmp_path: Path,
) -> None:
    source = 'const s = "café"; export function fetchPage() {} fetchPage();\n'
    repo = committed(tmp_path / "repo", {"a.js": source})

    rename_apply(repo, "fetchPage", "getPage")

    assert (repo / "a.js").read_text(encoding="utf-8") == source.replace(
        "fetchPage", "getPage"
    )


def test_a_crlf_file_renamed_on_several_lines_keeps_every_ending(
    tmp_path: Path,
) -> None:
    source = (
        b"from json import load\r\n\r\n\r\ndef fetch_page(url):\r\n"
        b"    return load(url)\r\n\r\n\r\nhandler = fetch_page; other = fetch_page\r\n"
    )
    repo = committed(tmp_path / "repo", {"m.py": source})

    report = rename_apply(repo, "fetch_page", "get_page")

    assert (repo / "m.py").read_bytes() == source.replace(b"fetch_page", b"get_page")
    assert report.locations == (("m.py", (4, 8)),)
    assert report.occurrences == 3
