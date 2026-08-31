"""C4 — an empty ``target_content`` is a new file, not an unprovided original.

:func:`~mcgyvr.verify.build_prompt` falls back to the contract's
``target_content`` when the caller passes no ``original``, but wrote the
fallback as ``view["target_content"] or None`` — and ``"" or None`` is ``None``.
An empty target content means "the file does not exist yet", which
:func:`_original_block` already renders as "the change creates a new file";
collapsing it to ``None`` renders it as "not supplied" instead. The reviewer is
told it is judging against a file it never saw, when the truth is there is no
file yet to see.

The fix is to stop coercing: the empty string is a real value with its own
sentence.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.gate import GateResult
from tests.red_port.conftest import required

BEHAVIOR = "assemble the verifier's fresh-context prompt from contract and gate"


def _build_prompt() -> Any:
    return required(
        BEHAVIOR,
        lambda: __import__("mcgyvr.verify", fromlist=["build_prompt"]).build_prompt,
    )


def test_an_empty_target_content_reads_as_a_new_file_not_an_unprovided_original(
    contract: Any,
) -> None:
    """The reviewer is told there is no file yet, not that one was withheld."""
    prompt = _build_prompt()(
        contract, gate=GateResult(), change="+def fetch():\n+    pass\n"
    )

    assert "creates a new file" in prompt, (
        "an empty target_content was not rendered as a new file; the reviewer "
        "is not told the change creates one"
    )
    assert "not supplied" not in prompt, (
        "an empty target_content was rendered as 'not supplied', which is the "
        "sentence for a caller that withheld the file — a different absence"
    )
