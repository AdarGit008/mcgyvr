"""D14 — a change scoped to one function edits one function, and the rest of the file
survives.

mcgyvr's reply protocol is whole-file and only whole-file: ``parse_reply`` refuses
anything but exactly one fenced block, ``output_schema`` accepts only
``whole_file``, and what comes back is written over the target. That is the right
default and a poor fit for the common case — a contract that names one function has
just asked a small model to re-emit every other line of the file correctly, and every
one of those lines is a chance to drop a decorator, a helper, or an import. The
worker is being charged output tokens for bytes nobody wanted changed, and the gate
can only tell you afterwards that something else moved.

*Only the named node changes* is asserted as full-file equality against the file
rebuilt from its own untouched pieces, and the neighbours are named in the assertion
one by one. This is the whole point of the test. A test that only checked the new
body was present would pass against a parser that threw the file away and wrote the
worker's fragment — which is precisely today's behaviour, and precisely the bug. So
the imports above the node, the helper below it, the decorator that must stay
attached to what it decorates, and the module docstring are each asserted present
verbatim, because each is a different way the splice can be off by a line.

*A named node the file does not have is appended* rather than treated as an error
that discards the reply, and rather than overwriting the file with the fragment. The
first is a wasted attempt on work that was done correctly; the second silently
deletes a file. Appending is the only outcome that loses nothing, and it is asserted
by requiring every byte of the original to still be there alongside the new node.

*A JSON-wrapped reply is unwrapped* because a model asked for structured output —
or one that has simply decided JSON is tidier — sends ``{"content": "..."}``, and
that is a reply that carried a file. Today the fenced form parses into a file whose
contents are a JSON object and the unfenced form refuses outright, so a correct
answer becomes either a corrupt file or a spent attempt. Both spellings are asserted
here, because a caller cannot control which one arrives.

Asserted at ``parse_reply``, which is where mcgyvr's own docstring puts the boundary
"where a reply stops being text and becomes file content" — the unwrapping belongs
wherever that boundary ends up, and the requirement is that the file content is the
code and never the envelope.
"""

from __future__ import annotations

import json
from typing import Any

from mcgyvr.worker.reply import ParsedFile, parse_reply
from tests.red_port.conftest import required

BEHAVIOR = (
    "apply a reply scoped to one named function or class without rewriting the rest "
    "of the file"
)

HEAD = '''"""Fetching helpers."""

import time
from functools import lru_cache
from urllib.parse import urlsplit


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


@lru_cache(maxsize=8)
'''

NODE = """def fetch(url):
    return url
"""

TAIL = """

def host(url):
    return urlsplit(url).netloc
"""

SOURCE = HEAD + NODE + TAIL

REPLACEMENT = """def fetch(url):
    for attempt in range(3):
        _sleep(2**attempt)
    return url
"""

REPLY = f"```python\n{REPLACEMENT}```\n"


def _apply_scoped() -> Any:
    return required(
        BEHAVIOR,
        lambda: (
            __import__("mcgyvr.worker.scoped", fromlist=["apply_scoped"]).apply_scoped
        ),
    )


def _content(reply: str) -> str:
    """The file content a reply becomes, or a failure naming what came back instead."""
    parsed = parse_reply(reply)
    assert isinstance(parsed, ParsedFile), (
        f"the reply did not become file content: {parsed}"
    )
    return parsed.content


def test_a_scoped_reply_replaces_its_node_and_nothing_else() -> None:
    """Every byte outside the named node is the byte that was there before.

    Held as whole-file equality first — the only assertion that actually says "and
    nothing else" — then repeated on each neighbour by name, so a failure says which
    part of the file was lost rather than dumping two files and leaving the reader to
    diff them.
    """
    merged = _apply_scoped()(source=SOURCE, reply=REPLY, node="fetch")

    assert merged == HEAD + REPLACEMENT + TAIL, "bytes outside the named node changed"
    assert "for attempt in range(3):" in merged, "the worker's new body did not land"
    for neighbour, what in (
        ('"""Fetching helpers."""', "the module docstring"),
        ("from urllib.parse import urlsplit", "an import the rest of the file needs"),
        ("def _sleep(seconds: float) -> None:", "a helper defined above the node"),
        ("@lru_cache(maxsize=8)", "the decorator attached to the node"),
        ("return urlsplit(url).netloc", "a function defined below the node"),
    ):
        assert neighbour in merged, f"{what} was dropped by a scoped edit"


def test_a_node_the_file_does_not_have_is_added_without_losing_the_file() -> None:
    """A scope that does not match is new work, not a reason to discard the file.

    The original is asserted whole, not sampled: the failure this rules out is a
    splice that, finding no node to replace, replaces everything.
    """
    added = """def resolve(url):
    return url.lower()
"""

    merged = _apply_scoped()(
        source=SOURCE, reply=f"```python\n{added}```\n", node="resolve"
    )

    assert "def resolve(url):" in merged, "the new node was not added"
    assert SOURCE.rstrip("\n") in merged, (
        "the file the worker was editing was not preserved when its node was not found"
    )
    assert "def fetch(url):\n    return url\n" in merged, (
        "the existing node was overwritten"
    )
    assert "def host(url):" in merged, "the file's other content was lost"


def test_a_reply_wrapped_in_json_is_unwrapped_into_its_content() -> None:
    """``{"content": ...}`` carried a file; what gets written is the file, not the
    envelope.

    Both spellings, because the worker chooses: a model told to answer in JSON sends
    the object bare, and a model that also remembers the fence sends it wrapped. One
    of those currently becomes a Python file containing a JSON object and the other
    is refused outright; both are the same reply.
    """
    envelope = json.dumps({"content": REPLACEMENT})

    fenced = _content(f"```json\n{envelope}\n```\n")
    assert fenced.strip() == REPLACEMENT.strip(), (
        f"a JSON-wrapped reply was written verbatim instead of unwrapped: {fenced!r}"
    )

    bare = _content(f"{envelope}\n")
    assert bare.strip() == REPLACEMENT.strip(), (
        f"an unfenced JSON reply carrying a file was not read as one: {bare!r}"
    )
