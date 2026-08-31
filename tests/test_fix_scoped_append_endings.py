"""A scoped *addition* ends its lines the way the file it is added to does.

:func:`mcgyvr.worker.scoped.apply_scoped` splices a named definition and leaves
every other byte alone. When the file has no such definition the fragment is
appended instead — the outcome the module argues for at length, because refusing
throws away work that was done correctly and substituting deletes the file.

``_appended`` built that append out of ``\\n``: ``source.rstrip("\\n")`` for the
head, ``"\\n\\n\\n"`` for the separator, and the fragment exactly as
:func:`~mcgyvr.worker.reply.parse_reply` handed it over — which is always ``\\n``,
because that parser normalises line endings on entry as a stated transformation.
On a file whose lines end ``\\r\\n`` that is wrong three times over: the
``rstrip`` leaves the head's final ``\\r`` dangling with no ``\\n`` after it, the
separator's blank lines are LF, and so is every line of the new definition.

The consequence is not a file that fails to parse — Python reads all three
terminators. It is that the file now holds two kinds of line ending, so the next
``ruff format`` (or :func:`mcgyvr.cleanup.tidy`) normalises the lot, and a change
that added one definition is reported as having rewritten every line in the file.
:func:`mcgyvr.repair._terminator` was written for exactly that failure on exactly
that reasoning — *"a repair that added one import is recorded as having rewritten
every line in the file"* — and this is the same append one module over.

So the terminator is derived the same way, from :mod:`mcgyvr.lines`, which is
where this project keeps its one definition of where a line ends. The rejected
alternative is a second derivation local to ``scoped``: that module's own
neighbour states the rule (*"a second definition of line is the same kind of
defect, and it has already cost this project twice"*), and B4 was that defect
costing it the second time.

The sources below are written as byte literals and decoded, so a reader can see
which terminator each one actually carries rather than trusting an escape inside
a triple-quoted string.

**The controls.** An LF file must come back pure LF — a fix that reached for
``\\r\\n`` unconditionally, or that converted endings in the wrong direction,
passes the CRLF statement and breaks every file this project actually edits. An
empty file must still get the fragment and no leading blank lines, which is the
one branch ``_appended``'s docstring already argues for. And the *splice* path is
asserted to re-terminate only its fragment: ``apply_scoped`` replacing a node
that exists carries the head and tail across as the strings they already were,
derives the file's terminator for the fragment alone, and
``test_fix_b4_b9_text_handling`` pins the head and tail bytes — a "normalise the
whole file" fix would pass everything here and break that.
"""

from __future__ import annotations

import ast

from mcgyvr.worker.reply import ReplyError
from mcgyvr.worker.scoped import apply_scoped

#: The same two-definition file, once per terminator the parser counts. Byte
#: literals because the difference between them is the point.
CRLF = b'"""Fetching helpers."""\r\n\r\n\r\ndef fetch(url):\r\n    return url\r\n'
LF = b'"""Fetching helpers."""\n\n\ndef fetch(url):\n    return url\n'
CR = b'"""Fetching helpers."""\r\r\rdef fetch(url):\r    return url\r'

#: Two lines, so that a fix which re-terminates only the separator and not the
#: fragment still leaves an LF behind and is still caught.
ADDED = "def resolve(url):\n    return url.lower()\n"


def _reply(fragment: str) -> str:
    """``fragment`` as a worker's fenced reply."""
    return f"```python\n{fragment}```\n"


def _merged(source: bytes) -> str:
    """Append :data:`ADDED` to ``source``, failing the test if it refused."""
    merged = apply_scoped(
        source=source.decode("utf-8"), reply=_reply(ADDED), node="resolve"
    )
    assert not isinstance(merged, ReplyError), f"the append refused: {merged}"
    return merged


def _endings(text: str) -> set[str]:
    """Which of the three terminators ``text`` actually uses."""
    remaining = text.replace("\r\n", "\x00")
    found = {"\r\n"} if "\x00" in remaining else set()
    return found | {end for end in ("\r", "\n") if end in remaining}


def test_an_append_to_a_crlf_file_leaves_one_kind_of_line_ending() -> None:
    """The whole statement, as one assertion about the file's terminators.

    Held as a set rather than as ``"\\n" not in merged``, because the failure is
    a *mixture*: the file that comes out of the defect contains CRLF too, and
    every assertion that only looks for the ending it wants passes on it.
    """
    merged = _merged(CRLF)

    assert _endings(merged) == {"\r\n"}, (
        f"a one-definition append left {sorted(_endings(merged))!r} in a CRLF "
        f"file; the next formatter normalises all of it, and the change is "
        f"recorded as having rewritten every line"
    )


def test_the_appended_definition_itself_is_re_terminated() -> None:
    """The half a separator-only fix would miss.

    ``parse_reply`` normalises the reply to ``\\n`` on the way in, so the
    fragment arrives LF whatever the worker sent. Fixing only ``rstrip`` and the
    blank lines leaves a two-line definition with an LF inside it, which is
    still a mixed-ending file — and still a whole-file reformat next time
    anything runs.
    """
    merged = _merged(CRLF)

    assert "def resolve(url):\r\n    return url.lower()\r\n" in merged, (
        "the appended definition kept the LF endings `parse_reply` gave it, so "
        "the file it was appended to now has two kinds"
    )


def test_the_file_the_worker_was_editing_survives_the_append() -> None:
    """Nothing here may cost the property the whole module is built on.

    ``_appended`` exists because refusing loses correct work and substituting
    deletes the file; a fix that re-terminates by rebuilding the file could lose
    either. So the original is asserted whole, and the result still parses.
    """
    merged = _merged(CRLF)

    assert merged.startswith(CRLF.decode("utf-8").rstrip("\r\n")), (
        "the file being appended to was rewritten rather than carried across"
    )
    assert "def fetch(url):\r\n    return url\r\n" in merged, (
        "the definition the file already had did not survive the append"
    )
    assert merged.count("def resolve(url):") == 1, (
        "the new definition is not there once"
    )
    ast.parse(merged)


def test_two_blank_lines_still_separate_the_appended_definition() -> None:
    """The reason ``_appended`` writes a separator at all, kept in the fix.

    A module-level definition goes after two blank lines or the gate's style
    check spends an attempt on whitespace the worker was never shown. The count
    is the same; only the bytes each blank line is made of change.
    """
    merged = _merged(CRLF)

    assert "return url\r\n\r\n\r\ndef resolve(url):" in merged, (
        "the two blank lines a formatter puts before a module-level definition "
        "are not there, or are not the file's own line ending"
    )


def test_an_lf_file_is_still_appended_to_with_lf() -> None:
    """The control that rules out reaching for CRLF unconditionally.

    Every file in this repository ends its lines with ``\\n``; a fix that
    satisfied the statement above by writing CRLF would pass it and corrupt
    every ordinary append.
    """
    merged = _merged(LF)

    assert _endings(merged) == {"\n"}, (
        f"an append to an LF file introduced {sorted(_endings(merged))!r}"
    )
    assert "return url\n\n\ndef resolve(url):\n    return url.lower()\n" in merged


def test_a_bare_cr_file_is_appended_to_the_same_way() -> None:
    """The third terminator the parser counts, and the one nothing else covers.

    ``LINE_END`` counts all three deliberately (B4), and a fix that special-cased
    CRLF against LF would answer two of the three and leave this one mixed.
    """
    merged = _merged(CR)

    assert _endings(merged) == {"\r"}, (
        f"an append to a CR-terminated file left {sorted(_endings(merged))!r}"
    )


def test_an_empty_file_gets_the_fragment_and_no_blank_lines() -> None:
    """The branch ``_appended`` already argued for, unchanged by the fix.

    A file that starts with two blank lines is a file the formatter would
    immediately change back, so an empty source gets none — and with no line in
    it there is no ending to derive, which is where ``_terminator``'s ``\\n``
    default is the answer.
    """
    merged = _merged(b"")

    assert merged == ADDED, (
        f"an empty file did not become exactly the fragment: {merged!r}"
    )


def test_a_splice_into_a_crlf_file_reterminates_only_the_fragment() -> None:
    """The splice re-terminates its fragment, and nothing else.

    ``apply_scoped`` replacing a node the file *has* carries the head and tail
    across as the strings they already were; the worker's fragment arrives LF
    because ``parse_reply`` normalises it on entry, so it is re-terminated to
    the file's own ending before the splice. Only the fragment is touched —
    ``test_fix_b4_b9_text_handling`` pins the head and tail bytes exactly, and
    a fix that "normalises the file" instead would pass here and break that.
    """
    replacement = "def fetch(url):\n    return url.strip()\n"
    source = CRLF.decode("utf-8")
    head = source[: source.index("def fetch")]

    merged = apply_scoped(source=source, reply=_reply(replacement), node="fetch")

    assert merged == head + "def fetch(url):\r\n    return url.strip()\r\n", (
        "a splice rewrote bytes outside the node it was scoped to, or left the "
        "fragment on LF so the file holds two kinds of line ending"
    )
