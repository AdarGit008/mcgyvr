"""Where a line ends, answered once for the whole project.

Python's tokenizer and :meth:`str.splitlines` disagree. ``splitlines`` breaks on
eleven characters; the tokenizer breaks on three. The eight it does not count —
``\\x0b \\x0c \\x1c \\x1d \\x1e \\x85 \\u2028 \\u2029`` — are all legal inside a
string literal, so a file holding one is ordinary source that ``ast`` numbers one
way and ``splitlines`` cuts another.

Every one of those disagreements is an off-by-one against an AST line number, and
a *silent* one: the splice still joins into something that parses, so the file is
accepted, the requested change is gone, and the caller reports success. It is the
shape of both defects the pressure test called "the silent ones" — :mod:`mcgyvr.
worker.scoped` splicing a node, and :mod:`mcgyvr.repair` splicing an import — and
they were the same bug written twice.

Hence one home. :mod:`mcgyvr.scope` states the rule this follows: there is exactly
one matcher, and a second, subtly different one elsewhere is a defect. A second
definition of *line* is the same kind of defect, and it has already cost this
project twice.
"""

from __future__ import annotations

import re

#: The line terminators the parser counts, longest first so ``\r\n`` is one line
#: rather than two. Deliberately not ``\\s`` or :meth:`str.splitlines` — see the
#: module docstring for the eight characters that difference is about.
LINE_END = re.compile(r"\r\n|\r|\n")


def parser_lines(source: str) -> list[str]:
    """``source`` cut where the parser cuts it, terminators kept.

    Worth a function only because the cut has to agree with ``lineno`` and
    ``end_lineno`` exactly: the list is indexed 0-based against their 1-based
    numbering, and any disagreement about where a line ends is an off-by-one per
    disagreeing character. Terminators are kept so that joining the slices back
    is the original bytes rather than a reconstruction of them.
    """
    cut: list[str] = []
    start = 0
    for terminator in LINE_END.finditer(source):
        cut.append(source[start : terminator.end()])
        start = terminator.end()
    if start < len(source):
        cut.append(source[start:])  # a last line nobody ended
    return cut


def terminator(source: str) -> str:
    """The line ending ``source`` already uses, or ``\\n`` for a file with none.

    A line written *into* a file has to end the way that file's other lines end.
    A ``\\n`` spliced into a CRLF file leaves a mixed-ending file behind, which
    the next formatter normalises — so a change that added one import, or one
    definition, is recorded as having rewritten every line in the file.

    Here rather than beside either caller for the reason this module exists:
    :func:`mcgyvr.repair._insert_imports` and
    :func:`mcgyvr.worker.scoped._appended` are the same splice written twice,
    and B4 was already the cost of two answers to "where does a line end".
    """
    found = LINE_END.search(source)
    return found.group(0) if found else "\n"
