""

from __future__ import annotations

import re

#
#he
#
LINE_END = re.compile(r"\r\n|\r|\n")


def parser_lines(source: str) -> list[str]:
    ""
    cut: list[str] = []
    start = 0
    for terminator in LINE_END.finditer(source):
        cut.append(source[start : terminator.end()])
        start = terminator.end()
    if start < len(source):
        cut.append(source[start:])  #
    return cut


def terminator(source: str) -> str:
    ""
    found = LINE_END.search(source)
    return found.group(0) if found else "\n"
