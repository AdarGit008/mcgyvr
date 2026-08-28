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

**An envelope is opened only where leaving it closed would write it into a
file.** A worker told to answer in JSON — or one that has simply decided JSON
is tidier — sends ``{"content": "..."}``, and that is a reply that carried a
file and named the field it is in. Whether such an object *is* the file or
merely carries it is not answerable from the bytes, so the answer comes from
where every other content judgement here comes from: the target. With one, both
readings are already handled correctly — ``{"status": "blocked"}`` destined for
a ``.py`` file is #174's refusal, and the same object destined for a ``.json``
file is a real file — so nothing is unwrapped and nothing is guessed. With no
target neither rule can run, and the object would be written verbatim into a
file this module cannot name; that is the one outcome that is wrong under
either reading, and it is exactly where the envelope is opened. A caller that
wants one opened against a known target says so by pinning a schema, which is
not a guess: that shape was asked for.

Ported from local-ai's ``extract_code`` (``docs/port-from-local-ai.md``, D14).
Its second half — a regex that digs a Python triple-quoted string out of
*invalid* JSON — is deliberately not here: text that is not JSON is not read as
JSON, or this module has gone back to guessing.

**A pinned schema replaces the fence hunt rather than adding to it.** A
:class:`~mcgyvr.runner.Request` may carry a ``response_schema`` (D13), and a
backend that honours one answers with the object and no prose — nothing to hunt
for, and none of the ways a hunt is spent: a second block explaining the first,
a fence closed at the wrong width, an apology that fenced itself. Backends that
ignore it are the ordinary case on this ladder's cheap rungs, so
:func:`parse_pinned` falls back to the reader above rather than refusing, and
the two shapes produce the same :class:`ParsedFile` byte for byte, trailing
newline included. Two readers that disagreed about the bytes would hand the gate
a different file depending on which server answered, which would make a run's
reproducibility a property of the backend.

Line endings are normalised to ``\\n`` on entry — a stated transformation, so a
CRLF reply parses identically to an LF one instead of failing on a fence line
that carries a stray carriage return.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from mcgyvr.runner import StopReason

# The shape this module implements. A contract declaring anything else is
# refused rather than best-effort parsed.
WHOLE_FILE = "whole_file"

# The field a carrier object is assumed to hold the file in when the schema
# does not say otherwise. It is local-ai's name for it and the one the bundles
# would ask for; a schema that names a different field is read from the schema
# rather than from this constant.
_ENVELOPE_FIELD = "content"

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


def _carried_file(text: str, field: str = _ENVELOPE_FIELD) -> str | None:
    """The file a ``{"<field>": "..."}`` carrier holds, or ``None`` if not one.

    Strict JSON only, and only an object whose ``field`` is a non-empty string.
    Everything looser — an object without that field, a list, a number, a
    triple-quoted near-miss — is left to the caller to judge as the text it is.
    """
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        carrier = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(carrier, dict):
        return None
    carried = carrier.get(field)
    if not isinstance(carried, str) or not carried.strip():
        return None
    return carried


def _schema_field(schema: dict[str, Any]) -> str:
    """Which property of ``schema`` holds the file.

    Read from the schema rather than fixed, because the schema is the caller's:
    pinning one that spells the field ``file`` and then reading ``content`` out
    of the answer would be this module deciding what the caller asked for. The
    first required string property wins, then a lone string property, then
    :data:`_ENVELOPE_FIELD` — a schema this cannot read is not an error here,
    since the reply is parsed either way.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return _ENVELOPE_FIELD
    strings = [
        name
        for name, spec in properties.items()
        if isinstance(name, str)
        and isinstance(spec, dict)
        and spec.get("type") == "string"
    ]
    required = schema.get("required")
    if isinstance(required, list):
        for name in required:
            if isinstance(name, str) and name in strings:
                return name
    if len(strings) == 1:
        return strings[0]
    return _ENVELOPE_FIELD


def _as_file(content: str) -> str:
    """``content`` with the trailing newline a file ends with.

    Appended only when it is missing, which is what makes an unwrapped envelope
    and a fenced block carrying the same file compare equal: the fenced path
    ends its last body line the same way, so a carrier whose string already ends
    in ``\\n`` must not collect a second one.
    """
    return content if content.endswith("\n") else content + "\n"


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


def _unreadable(output_schema: str, stop_reason: StopReason) -> ReplyError | None:
    """The two refusals decided before a reply is read at all.

    Shared so that :func:`parse_pinned` cannot reach a different conclusion
    about a truncated reply or an unsupported schema than :func:`parse_reply`
    does. Both are facts about the dispatch rather than about the text, and a
    second copy of them would be a second chance to disagree.
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
    return None


def _refusal(target: str) -> ReplyError:
    """#174's named outcome, in one place because two readers reach it."""
    return ReplyError(
        "refusal",
        f"the reply's fenced block carries no code — it is a refusal "
        f"dressed as {target!r}, and writing it would record this rung as "
        f"having done the task; escalate rather than retrying this rung",
    )


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
    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable

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
        # No fence at all — but a reply that is one JSON object carrying a file
        # did carry a file, and with no target to judge it against the only
        # other outcome available is to lose work that was done correctly.
        carried = _carried_file(text) if target is None else None
        if carried is not None:
            return ParsedFile(content=_as_file(carried))
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
    if target is None:
        # The same carrier, fenced. The info string is kept as it arrived —
        # ```json over a carrier is a correct label for what was in the fence,
        # and this field reports what the worker said rather than what the file
        # turned out to be.
        carried = _carried_file(content)
        if carried is not None:
            return ParsedFile(content=_as_file(carried), info_string=info)
    if target is not None and _carries_no_code(content, target):
        return _refusal(target)
    return ParsedFile(content=content + "\n", info_string=info)


def parse_pinned(
    text: str,
    *,
    response_schema: dict[str, Any] | None,
    output_schema: str = WHOLE_FILE,
    stop_reason: StopReason = StopReason.COMPLETE,
    target: str | None = None,
) -> ParsedFile | ReplyError:
    """Read a reply to a request that pinned a response schema.

    ``response_schema`` is the schema the request carried
    (:attr:`~mcgyvr.runner.Request.response_schema`), passed through whether or
    not one was set: ``None`` means nothing was pinned and this is
    :func:`parse_reply` unchanged, so a caller holding a request has one reader
    rather than a branch it could get backwards.

    With a schema, the carrier is tried first and the fence hunt is the
    *fallback* rather than the other way round. Trying the fence first would
    make the pinned path depend on the reply happening not to contain one,
    which is the guess this module exists to avoid; trying the carrier first
    depends only on the reply being the object that was asked for.

    A backend that ignored the schema — Ollama's native path, an older
    llama-server, anything behind a proxy that drops unknown fields — reaches
    the fenced reader and its file comes out identical, trailing newline
    included. That is what keeps ``response_schema`` settable on the rungs
    where it would help most: pinning one can save an attempt and can never
    cost one.

    ``target`` still decides #174, and the judgement is made on the *file*
    rather than on the carrier holding it. A worker that declined inside a
    schema-shaped answer has declined.
    """
    if response_schema is None:
        return parse_reply(
            text, output_schema=output_schema, stop_reason=stop_reason, target=target
        )

    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable

    field = _schema_field(response_schema)
    info = ""
    carried = _carried_file(text, field)
    if carried is None:
        # The schema was not honoured. Read the reply the ordinary way, but
        # without the target: the carrier may still have arrived inside a
        # fence, and #174 would refuse it as a data blob before anything looked
        # inside. That judgement is made below instead, on what the carrier
        # holds.
        parsed = parse_reply(text, output_schema=output_schema, stop_reason=stop_reason)
        if isinstance(parsed, ReplyError):
            return parsed
        info = parsed.info_string
        carried = _carried_file(parsed.content, field) or parsed.content

    content = _as_file(carried)
    if target is not None and _carries_no_code(content, target):
        return _refusal(target)
    return ParsedFile(content=content, info_string=info)
