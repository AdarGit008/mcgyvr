"""X6 — a deeply nested reply is refused by name, never a RecursionError.

``json.loads`` raises ``RecursionError`` — not ``ValueError`` — on a reply whose
nesting exceeds the interpreter's limit, and both JSON readers in
:mod:`mcgyvr.worker.reply` catch only ``ValueError``. The error escapes the
reply parser as a crash out of a path that should be all named refusals.

The fix catches the recursion error beside the value error, so a reply too deep
to read is the same category as one that will not parse: refused, not raised.
"""

from __future__ import annotations

from mcgyvr.worker.reply import ParsedFile, parse_reply

# Deep enough to exceed the interpreter's JSON recursion limit.
DEEP = "[" * 20000 + "]" * 20000
FENCED = "```python\n" + DEEP + "\n```\n"


def test_a_deeply_nested_reply_is_not_a_recursion_error_in_the_parser() -> None:
    """The reply parser reads a too-deep JSON blob as ordinary text, not a crash."""
    result = parse_reply(FENCED, target="x.py")

    assert isinstance(result, ParsedFile), (
        f"a deeply nested reply was not read as text: {result!r}"
    )
