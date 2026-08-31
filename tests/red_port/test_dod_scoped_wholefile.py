"""F6 — a reply that re-emits the whole file must be refused, not spliced.

A scoped reply is one definition and nothing else. When a worker ignores that
and sends the whole file back, the named definition is still present, so
:func:`mcgyvr.worker.scoped.apply_scoped` finds it and writes the *entire*
fragment over the node's line span — every other top-level statement comes back
duplicated, once from the carried head/tail and once from the fragment. The file
still parses, so nothing fails loudly; the change just records success with the
file wrong.

The refusal is the same named outcome as any other scope mismatch: one attempt
spent, a reason to say, and nothing changed. The message names what extra
statements came along, so a caller can read the refusal instead of opening the
reply to find out.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.worker.reply import ReplyError
from tests.red_port.conftest import required

BEHAVIOR = (
    "refuse a scoped reply that re-emits the whole file, instead of splicing it "
    "over one node and duplicating every other statement"
)

SOURCE = (
    '"""Fetching helpers."""\n'
    "\n"
    "import time\n"
    "from urllib.parse import urlsplit\n"
    "\n"
    "\n"
    "def _sleep(seconds: float) -> None:\n"
    "    time.sleep(seconds)\n"
    "\n"
    "\n"
    "def fetch(url):\n"
    "    return url\n"
    "\n"
    "\n"
    "def host(url):\n"
    "    return urlsplit(url).netloc\n"
)

#: The same file the worker was shown, with only the named node's body changed —
#: a whole-file reply, not the one-definition reply a scoped task asked for.
WHOLE_FILE = SOURCE.replace("    return url\n", "    return url.strip()\n", 1)


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


def test_a_reply_that_re_emits_the_whole_file_is_refused() -> None:
    """A whole-file reply spliced over one node duplicates every other statement.

    Asserted as a named refusal rather than as "the file does not duplicate",
    because the defect produces a file that *parses*: the only assertion that
    cannot be gamed by checking the new body is present is the refusal itself.
    """
    merged = _apply_scoped()(source=SOURCE, reply=_reply(WHOLE_FILE), node="fetch")

    assert isinstance(merged, ReplyError), (
        "a whole-file reply was spliced over one node instead of refused, so "
        "every other top-level statement is in the file twice"
    )
    assert merged.code == "scope-mismatch", (
        f"the refusal is not named as a scope mismatch: {merged}"
    )
    assert "host" in merged.message, (
        f"the refusal does not name the extra statement: {merged}"
    )
    assert "_sleep" in merged.message, (
        f"the refusal does not name the helper that came along: {merged}"
    )
