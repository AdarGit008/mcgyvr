"""Line splitting that matches the line numbers CPython's parser reports.

Two parsers in this package (the Python one and the tree-sitter one) number a
file by physical lines, and repairs rewrite the file through a splice at a
reported index. This module is the single cut they all splice through: it keeps
each terminator with the line it ends, so the pieces rejoin into exactly the
bytes that were read.
"""

from __future__ import annotations

import re

#: The three terminators CPython's line accounting recognises. `\n`, `\r\n` and
#: `\r` all advance the parser's line number by one, so the cut must agree with
#: them; a cut that knew only `\n` would sit one line off per CR-terminated line
#: and a splice at that index would move the file. Longer alternatives come first
#: so `\r\n` is one terminator rather than two.
LINE_END = re.compile(r"\r\n|\r|\n")


def parser_lines(source: str) -> list[str]:
    """`source` cut into physical lines, each keeping its own terminator.

    Indexing the result 0-based reaches the line the parsers call `lineno`, so
    `lines[lineno - 1]` is the text of line `lineno`. Nothing is dropped and
    nothing is added: `"".join(parser_lines(source)) == source`, which is what
    lets a caller splice a line and rejoin without rewriting other bytes.
    """
    cut: list[str] = []
    start = 0
    for terminator in LINE_END.finditer(source):
        cut.append(source[start : terminator.end()])
        start = terminator.end()
    if start < len(source):
        cut.append(source[start:])  # text after the last terminator, as the final line
    return cut


def terminator(source: str) -> str:
    """The first line terminator appearing in `source`, falling back to `\n`.

    Callers building a new line to insert use this to match the file's existing
    endings; an empty source or one holding a single unterminated line offers
    none, so `\n` is assumed.
    """
    found = LINE_END.search(source)
    return found.group(0) if found else "\n"
