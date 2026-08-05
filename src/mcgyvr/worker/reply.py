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

**A block that carries no code is a refusal, not a file.** #174's finding: a
model that declines inside the fence satisfies every structural rule above. One
comment (``# I cannot complete this task.``) or one status object
(``{"status": "blocked"}``) is exactly one unambiguous block, is valid Python,
and passes syntax and lint — so it is written to the file and the task is
recorded as done. That is worse than a wrong answer, because escalation fires on
failure: a rung that declines silently looks identical to a rung that succeeded,
and the cascade never climbs. So this is a *named* outcome
(``ReplyError("refusal", ...)``) distinct from a failed check, since the routing
consequence differs — a refusal means this rung will not do this task, so
escalate now rather than retrying the same rung with notes.

This is the same kind of judgement the ``empty-block`` rule already makes
("empty is not a file"), carried one step: a body of nothing but comments is
empty of *code*, and a bare data blob written to a source file is not source.

**It is judged only against a known target, and never guessed.** ``# I cannot``
is a comment in Python and a *heading* in Markdown; ``{"status": "blocked"}`` is
a refusal in a ``.py`` file and a perfectly good ``.json`` one. Nothing in the
reply says which, so the check needs ``target`` and applies only to the
languages the gate itself owns (#35/#36 — Python and JS/TS). Any other target,
or no target at all, is left alone: an unrecognised language is not judged
rather than judged badly, which is this module's rule everywhere else.

**Stubs are deliberately ruled out of it.** A body of ``raise
NotImplementedError``, ``pass`` or ``...`` reads like a dodge and is legitimate
output for some contract types, so it parses. What refuses a stub is an
acceptance command (#146), not a pattern match here — and #132 is the measure of
how often no such command is declared, which is the condition under which this
whole class goes unnoticed.

Line endings are normalised to ``\\n`` on entry — a stated transformation, so a
CRLF reply parses identically to an LF one instead of failing on a fence line
that carries a stray carriage return.
"""

from __future__ import annotations

import json
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


# The languages this parser will judge for content, and how each one spells a
# comment. Deliberately the same set the gate's adapters own (#35 Python, #36
# JS/TS) rather than a table invented here: a language the gate cannot check is
# one this module has no business forming an opinion about either. Adding a
# language means adding it in both places, which is the honest cost of the
# coupling — the alternative, importing the adapters, would make the parser
# depend on the gate for a question about text.
_PY_EXTENSIONS = (".py", ".pyi")
_JS_EXTENSIONS = (".ts", ".mts", ".cts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_LINE_COMMENTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (_PY_EXTENSIONS, ("#",)),
    (_JS_EXTENSIONS, ("//",)),
)

# A ``/* ... */`` comment occupying whole lines. Anchored at line start so that
# a ``/*`` inside a string literal cannot swallow the rest of a real file.
_BLOCK_COMMENT = re.compile(r"(?m)^[ \t]*/\*.*?\*/[ \t]*$", re.DOTALL)


def _leaders(target: str) -> tuple[str, ...] | None:
    """How ``target``'s language spells a line comment, or ``None`` if unknown."""
    for extensions, leaders in _LINE_COMMENTS:
        if target.endswith(extensions):
            return leaders
    return None


def _carries_no_code(body: str, target: str) -> bool:
    """Whether ``body`` is a source file in name only — comments, or a data blob.

    Answers ``False`` for anything it cannot judge, including every target whose
    language is not in :data:`_LINE_COMMENTS`. A parser that guessed here would
    refuse real files, which is the more expensive mistake: a missed refusal
    costs one task, a wrongly refused file costs every task of that shape.
    """
    leaders = _leaders(target)
    if leaders is None:
        return False

    # A whole reply that is one data literal. Valid Python as an expression
    # statement and valid JS as an object literal, but source in neither — and
    # it is the shape a model reaches for when it declines structurally
    # (``{"status": "blocked", "reason": ...}``). Scalars and bare strings are
    # excluded: a module whose whole body is a docstring is a real file.
    try:
        blob = json.loads(body)
    except ValueError:
        blob = None
    if isinstance(blob, dict | list):
        return True

    stripped = _BLOCK_COMMENT.sub("", body)
    for line in stripped.split("\n"):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(leaders):
            return False
    return True


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
    target: str | None = None,
) -> ParsedFile | ReplyError:
    """Extract one file's content from a worker's reply, or refuse by name.

    ``stop_reason`` defaults to ``COMPLETE`` so the parser is testable on bare
    strings, but a caller holding a real
    :class:`~mcgyvr.runner.Completion` must pass its actual reason — that is
    the only evidence that the text is all of the text.

    ``target`` is the path the content is destined for, and the refusal check
    (#174) runs only when it is given: the same bytes are a refusal in one file
    and a legitimate file in another, and nothing in the reply says which. A
    caller that omits it gets the structural rules alone.
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
    content = "\n".join(body)
    if not content.strip():
        return ReplyError(
            "empty-block",
            "the reply's fenced block is empty, which is not a file",
        )
    if target is not None and _carries_no_code(content, target):
        return ReplyError(
            "refusal",
            f"the reply's fenced block carries no code — it is a refusal "
            f"dressed as {target!r}, and writing it would record this rung as "
            f"having done the task; escalate rather than retrying this rung",
        )
    return ParsedFile(content=content + "\n", info_string=info)
