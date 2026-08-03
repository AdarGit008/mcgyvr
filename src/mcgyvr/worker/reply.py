"""The single-file output protocol: one file's content, or a named refusal.

A worker's reply is prose-shaped by default. Models explain, apologise, offer
alternatives and wrap code in fences — all of which is fine to *read* and none
of which may ever reach a file. This module is the boundary where a reply stops
being text and becomes file content, and its whole design rule is that the
boundary never guesses.

**Exactly one fenced block, or nothing.** Not "the first block", not "the
longest block", not "the block that looks most like code". Every ambiguity
resolves to a named :class:`ReplyError` instead of a plausible file, because
the failure mode being designed out is a *quiet* one: a reply whose second
block was the real answer, or whose prose got written into a module, does not
announce itself — it produces a file that fails much later, somewhere the cause
is unreadable. A refusal costs one attempt and says why.

This mirrors the runner's stance on stop reasons: a backend that did not say
the answer is complete has not said it is complete
(:class:`~mcgyvr.runner.StopReason`). Here, a reply that did not clearly carry
one file has not carried one.

**Truncation is refused before parsing, not after.** A reply cut off at the
output cap can still contain a syntactically perfect fenced block — it is the
*rest* of the file that is missing, and nothing in the text says so. Only the
backend's own stop reason knows, so it is required here and anything short of
:attr:`~mcgyvr.runner.StopReason.COMPLETE` refuses. ADR-0009 chose the cap over
stop sequences precisely so that an over-long reply arrives *named* rather than
silently shortened; reading that name is this module's half of the bargain.

**Only ``whole_file`` parses.** ADR-0009 records it as "the default, and the
only shape #25 is scoped to". A contract declaring ``unified_diff`` is refused
by name rather than parsed as if it were whole-file content, which would apply
a patch's ``+``-prefixed body lines as source.

**No stop sequences are derived here.** ADR-0009 rejected them for v1 while
naming this parser as where the derivation would belong, since the sequence
that terminates a reply and the sequence a parser treats as the end are one
fact. The absence is the recorded decision, not an omission.

**A fence closes only on one at least as wide.** That is CommonMark's rule, and
it is kept because it resolves the one nesting case that is not actually
ambiguous: a file that itself contains fences, wrapped by the worker in a
longer fence, is a single unambiguous block and parses. Nesting at equal widths
has nothing to distinguish an inner fence from a closing one, reads as two
blocks, and refuses like any other ambiguity.

Line endings are normalised to ``\\n`` on entry — a stated transformation, so a
CRLF reply parses identically to an LF one instead of failing on a fence line
that carries a stray carriage return.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mcgyvr.runner import StopReason

# The shape this module implements. A contract declaring anything else is
# refused rather than best-effort parsed.
WHOLE_FILE = "whole_file"

# An opening fence: up to three spaces of indent (CommonMark's allowance), at
# least three backticks, an optional info string. Tildes are deliberately not
# fences here — the bundles instruct backticks, so a tilde-delimited reply is a
# reply that did not follow the protocol, and saying that is more useful than
# quietly accepting a second syntax.
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,})[ \t]*([A-Za-z0-9_+.#-]*)[ \t]*$")


def _is_close(line: str, width: int) -> bool:
    """Whether ``line`` closes a fence opened with ``width`` backticks."""
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    if not stripped.startswith("`" * width):
        return False
    return stripped.rstrip("`").strip() == ""


@dataclass(frozen=True)
class ParsedFile:
    """One file's complete content, safe to write."""

    content: str
    info_string: str = ""
    """The fence's language tag, reported and never enforced.

    A worker that tagged a Python file ```js` wrote the right file with the
    wrong label; refusing it would spend an attempt on a cosmetic mismatch.
    Kept so telemetry can notice a model that consistently mislabels.
    """


@dataclass(frozen=True)
class ReplyError:
    """A reply that will not become a file, and the reason in one word."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"reply[{self.code}]: {self.message}"


def parse_reply(
    text: str,
    *,
    output_schema: str = WHOLE_FILE,
    stop_reason: StopReason = StopReason.COMPLETE,
) -> ParsedFile | ReplyError:
    """Extract one file's content from a worker's reply, or refuse by name.

    ``stop_reason`` defaults to ``COMPLETE`` so the parser is testable on bare
    strings, but a caller holding a real
    :class:`~mcgyvr.runner.Completion` must pass its actual reason — that is
    the only evidence that the text is all of the text.
    """
    if output_schema != WHOLE_FILE:
        return ReplyError(
            "unsupported-schema",
            f"output_schema {output_schema!r} has no parser; only "
            f"{WHOLE_FILE!r} is implemented (ADR-0009)",
        )
    if stop_reason is not StopReason.COMPLETE:
        return ReplyError(
            "incomplete-reply",
            f"the backend stopped with {stop_reason.value!r}, so the reply is "
            f"not known to be a whole file; a truncated file can parse cleanly "
            f"and still be missing its tail",
        )

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(lines):
        opened = _FENCE_OPEN.match(lines[index])
        if opened is None:
            index += 1
            continue
        width = len(opened.group(1))
        closed_at = None
        cursor = index + 1
        while cursor < len(lines):
            if _is_close(lines[cursor], width):
                closed_at = cursor
                break
            cursor += 1
        if closed_at is None:
            return ReplyError(
                "unterminated-fence",
                f"a fence opened at line {index + 1} is never closed — the "
                f"usual signature of a reply that ran out of room",
            )
        blocks.append((opened.group(2), lines[index + 1 : closed_at]))
        index = closed_at + 1

    if not blocks:
        return ReplyError(
            "no-fenced-block",
            "the reply contains no fenced block, so there is no file content "
            "to write; prose is never written to a file",
        )
    if len(blocks) > 1:
        return ReplyError(
            "ambiguous-blocks",
            f"the reply contains {len(blocks)} fenced blocks and the protocol "
            f"is one file per reply; which one is the file is a guess, and a "
            f"guess here writes the wrong content",
        )

    info, body = blocks[0]
    if not "\n".join(body).strip():
        return ReplyError(
            "empty-block",
            "the reply's fenced block is empty, which is not a file",
        )
    return ParsedFile(content="\n".join(body) + "\n", info_string=info)
