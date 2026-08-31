"""X5/X6 — a deeply nested reply is refused by name, never a RecursionError.

``json.loads`` raises ``RecursionError`` — not ``ValueError`` — on a reply whose
nesting exceeds the interpreter's limit, and both JSON readers in
:mod:`mcgyvr.worker.reply` catch only ``ValueError``. The error escapes the
reply parser and, through it, :func:`mcgyvr.worker.scoped.apply_scoped`, where a
hostile reply can raise out of a path that is otherwise all named refusals.

The fix catches the recursion error beside the value error, so a reply too deep
to read is the same category as one that will not parse: refused, not raised.
"""

from __future__ import annotations

from mcgyvr.worker.reply import ParsedFile, ReplyError, parse_reply
from mcgyvr.worker.scoped import apply_scoped

# Deep enough to exceed the interpreter's JSON recursion limit.
DEEP = "[" * 20000 + "]" * 20000
FENCED = "```python\n" + DEEP + "\n```\n"


def test_a_deeply_nested_reply_is_not_a_recursion_error_in_the_parser() -> None:
    """The reply parser reads a too-deep JSON blob as ordinary text, not a crash."""
    result = parse_reply(FENCED, target="x.py")

    assert isinstance(result, ParsedFile), (
        f"a deeply nested reply was not read as text: {result!r}"
    )


def test_a_deeply_nested_reply_is_a_refusal_in_the_splice() -> None:
    """The scoped splice turns a too-deep reply into a refusal, not a raise."""
    result = apply_scoped(
        source="def fetch(url):\n    return url\n",
        reply=FENCED,
        node="fetch",
        target="src/pkg/fetch.py",
    )

    assert isinstance(result, ReplyError), (
        f"a deeply nested reply was not refused by name: {result!r}"
    )
