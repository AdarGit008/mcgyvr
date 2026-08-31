"""F5 — a scoped edit in a CRLF repo re-terminates the fragment it splices in.

:func:`mcgyvr.worker.scoped.apply_scoped` splices a named definition over the
existing node's line span, carrying the head and tail across as the bytes they
already were. The fragment arrives with ``\\n`` endings —
:func:`~mcgyvr.worker.reply.parse_reply` normalises them on entry — so splicing
it into a CRLF file leaves the fragment on LF while the head and tail stay CRLF.
The file still parses, so nothing fails loudly; the failure is that the next
formatter normalises the whole file, and a one-definition change is recorded as
having rewritten every line.

The fix is the same derivation ``_appended`` already makes — the source's own
terminator, applied to the fragment alone. The head and tail are still carried
byte for byte, because the module's whole claim is that bytes outside the named
node do not change.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.worker.reply import ReplyError
from tests.red_port.conftest import required

BEHAVIOR = (
    "re-terminate the fragment a scoped edit splices in, so a CRLF file keeps "
    "one kind of line ending"
)

#: A CRLF file with a node to splice and a neighbour after it, written as a byte
#: literal so the reader can see which terminator each line carries.
CRLF = (
    b'"""Fetching helpers."""\r\n'
    b"\r\n"
    b"\r\n"
    b"def fetch(url):\r\n"
    b"    return url\r\n"
    b"\r\n"
    b"\r\n"
    b"def host(url):\r\n"
    b"    return url.lower()\r\n"
)


def _apply_scoped() -> Any:
    return required(
        BEHAVIOR,
        lambda: (
            __import__("mcgyvr.worker.scoped", fromlist=["apply_scoped"]).apply_scoped
        ),
    )


def _reply(fragment: str) -> str:
    """``fragment`` as a worker's fenced reply."""
    return f"```python\n{fragment}```\n"


def _endings(text: str) -> set[str]:
    """Which of the three terminators ``text`` actually uses."""
    remaining = text.replace("\r\n", "\x00")
    found = {"\r\n"} if "\x00" in remaining else set()
    return found | {end for end in ("\r", "\n") if end in remaining}


def test_a_splice_into_a_crlf_file_reterminates_the_fragment() -> None:
    """The whole statement, as one assertion about the file's terminators.

    Held as whole-file equality — the only assertion that actually says "and
    nothing else changed" — plus an explicit endings check, because the failure
    is a *mixture*: the file that comes out of the defect contains CRLF too,
    and an assertion that only looked for one ending would pass on it.
    """
    replacement = "def fetch(url):\n    return url.strip()\n"
    source = CRLF.decode("utf-8")
    expected = source.replace(
        "def fetch(url):\r\n    return url\r\n",
        "def fetch(url):\r\n    return url.strip()\r\n",
        1,
    )

    merged = _apply_scoped()(source=source, reply=_reply(replacement), node="fetch")

    assert not isinstance(merged, ReplyError), f"the splice refused: {merged}"
    assert merged == expected, (
        "a scoped splice into a CRLF file left the fragment on LF while the "
        "head and tail stayed CRLF, so the file now holds two kinds of line "
        "ending"
    )
    assert _endings(merged) == {"\r\n"}, (
        f"a scoped splice left {sorted(_endings(merged))!r} in a CRLF file; "
        f"the next formatter normalises all of it"
    )
