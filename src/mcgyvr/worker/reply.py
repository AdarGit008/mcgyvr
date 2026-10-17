"""Turn one reply's text into the bytes meant for a file, or a named refusal.

A whole-file reply is treated as a file only when the protocol can vouch for it:
the backend stopped complete, the output schema is one this module implements,
and the text holds exactly one closed fenced block. Everything else - no fence,
two blocks because the model offered an alternative, a fence the cap cut off, an
empty block - becomes a `ReplyError` carrying a code, so a caller can tell the
causes apart instead of writing a plausible file. Given a target path, a block
that holds no code for that extension is refused as a refusal rather than a file,
and a reply that spent its whole cap on hidden reasoning is named as empty.
`prose` and `media_artifact` replies are the raw text, never a fence hunt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from mcgyvr.runner import Completion, StopReason

# The output schemas with a parser here. Each names what the reply is taken to be:
# a whole file, raw prose, or a raw media-artifact request.
WHOLE_FILE = "whole_file"
PROSE = "prose"
MEDIA_ARTIFACT = "media_artifact"

# The JSON field a schema-pinned reply is expected to carry the file text in, and the
# field assumed when a pinned schema names no single string property. It is also the
# field of the `{"content": ...}` envelope an unpinned whole-file reply may arrive in,
# which is unwrapped before its text is judged.
_ENVELOPE_FIELD = "content"

#: FENCE_OPEN matches a line that opens a fence: at most three leading spaces, three
#: or more backticks, then an optional info string containing no backtick. The match
#: records the backtick count, which is the width a closing fence must reach, and the
#: info string, whose first word is kept as the language tag. Because closing needs at
#: least as many backticks, a wider outer fence carries an inner one through as content.
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,})[ \t]*([^`]*)$")


# Which comment leader makes a line carry no code, keyed by target extension. Only
# Python (#) and JavaScript/TypeScript (//) are judged: the same leading character
# opens a real line of Markdown or Ruby, so an extension missing from this table
# leaves the refusal gate with no opinion rather than a wrong one. Leaders are
# matched against a stripped line, which is why JS lists the two-slash leader and
# not the single slash of a block comment.
_PY_EXTENSIONS = (".py", ".pyi")
_JS_EXTENSIONS = (".ts", ".mts", ".cts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_LINE_COMMENTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (_PY_EXTENSIONS, ("#",)),
    (_JS_EXTENSIONS, ("//",)),
)

# A whole-line /* ... */ block comment. Matched across lines and removed before the
# line-by-line check, so a JS/TS block comment cannot pass for code.
_BLOCK_COMMENT = re.compile(r"(?m)^[ \t]*/\*.*?\*/[ \t]*$", re.DOTALL)


def _leaders(target: str) -> tuple[str, ...] | None:
    """The comment leaders that make a line code-free for `target`, or None when
    the target's extension is not one this module judges."""
    for extensions, leaders in _LINE_COMMENTS:
        if target.endswith(extensions):
            return leaders
    return None


def _carries_no_code(body: str, target: str) -> bool:
    """Whether `body` holds no code for `target`: either a JSON object or array, or
    nothing but blank lines and comments. Callers read True as a refusal, so a
    target whose extension this module does not judge always answers False."""
    leaders = _leaders(target)
    if leaders is None:
        return False

    # A JSON object or array is a status blob ("what went wrong"), not a file body.
    # It is tested before the comment scan because such a blob is not comment-led
    # and would otherwise read as code. Only containers count: a scalar such as 42
    # or a lone string falls through to the scan, so a docstring-only module parses.
    try:
        blob = json.loads(body)
    except (ValueError, RecursionError):
        # Not JSON, so not a data blob; the comment scan below decides.
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
    """The text a JSON envelope carries in `field`, or None when `text` is not a
    JSON object, or that field is missing, blank, or not a string."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        carrier = json.loads(stripped)
    except (ValueError, RecursionError):
        return None
    if not isinstance(carrier, dict):
        return None
    carried = carrier.get(field)
    if not isinstance(carried, str) or not carried.strip():
        return None
    return carried


def _schema_field(schema: dict[str, Any]) -> str:
    """The property of a pinned schema that holds the file text: the first
    required string property, else the only string property, else `content`."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return _ENVELOPE_FIELD
    strings = [
        name
        for name, spec in properties.items()
        if isinstance(name, str) and isinstance(spec, dict) and _is_string_type(spec)
    ]
    required = schema.get("required")
    if isinstance(required, list):
        for name in required:
            if isinstance(name, str) and name in strings:
                return name
    if len(strings) == 1:
        return strings[0]
    return _ENVELOPE_FIELD


def _is_string_type(spec: dict[str, Any]) -> bool:
    """Whether a schema type spec admits a string: `"string"`, or a type list
    with `"string"` among its entries."""
    kind = spec.get("type")
    if isinstance(kind, str):
        return kind == "string"
    return isinstance(kind, list) and "string" in kind


def _as_file(content: str) -> str:
    """`content` with a trailing newline added when it does not already end in
    one."""
    return content if content.endswith("\n") else content + "\n"


def _is_close(line: str, width: int) -> bool:
    """Whether `line` closes a fence of `width` backticks: indented by at most
    three spaces, starting with that many backticks, then only backticks and
    whitespace."""
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    if not stripped.startswith("`" * width):
        return False
    return stripped.rstrip("`").strip() == ""


@dataclass(frozen=True)
class ParsedFile:
    """One reply the protocol accepted: the bytes to write, plus the fence's
    language tag."""

    content: str
    info_string: str = ""
    """The fence's language tag, reported and never enforced.

    A worker that tagged a Python file ```js` wrote the right file with the
    wrong label; refusing it would spend an attempt on a cosmetic mismatch.
    Kept so telemetry can notice a model that consistently mislabels.
    """


@dataclass(frozen=True)
class ReplyError:
    """One reply the protocol refused, carrying a stable `code` so a caller can
    tell an ambiguous reply from a truncated one or a refusal."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"reply[{self.code}]: {self.message}"


def _unreadable(output_schema: str, stop_reason: StopReason) -> ReplyError | None:
    """The reason `output_schema` and `stop_reason` alone make a reply unreadable,
    or None when its text may be parsed. Runs before any text is inspected, so an
    unsupported schema or an incomplete reply is reported by cause rather than as
    a malformed block."""
    if output_schema not in (WHOLE_FILE, PROSE, MEDIA_ARTIFACT):
        return ReplyError(
            "unsupported-schema",
            f"output_schema {output_schema!r} has no parser; only "
            f"{WHOLE_FILE!r}, {PROSE!r} and {MEDIA_ARTIFACT!r} are implemented",
        )
    if stop_reason is not StopReason.COMPLETE:
        return ReplyError(
            "incomplete-reply",
            f"the backend stopped with {stop_reason.value!r}, so the reply is "
            f"not known to be a whole file; a truncated file can parse cleanly "
            f"and still be missing its tail",
        )
    return None


def empty_at_cap(reply: Completion) -> ReplyError | None:
    """The error for a reply that was truncated with no visible text, meaning the
    cap went to hidden reasoning, or None for any other reply."""
    if reply.stop_reason is not StopReason.TRUNCATED or reply.text.strip():
        return None
    cap = reply.max_output_tokens
    spent = reply.output_tokens if reply.output_tokens is not None else cap
    of_cap = f" of its {cap}-token cap" if cap is not None else ""
    spent_on = (
        f"all {spent} output tokens{of_cap}" if spent is not None else "its output"
    )
    reasoning = (
        f" ({reply.reasoning_tokens} reported as reasoning)"
        if reply.reasoning_tokens is not None
        else ""
    )
    return ReplyError(
        "empty-reply",
        f"the model used {spent_on} on hidden reasoning{reasoning} and returned "
        f"no visible reply. Raise the contract's `limits.max_output_tokens` "
        f"within the unit's ceiling — its `window` less the prompt, or its "
        f"`output_tokens`",
    )


def _prose(text: str) -> str:
    """`text` with CRLF and lone CR newlines normalised to LF, and nothing else
    changed."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _refusal(target: str) -> ReplyError:
    """The error for a block that carries no code for `target`: a refusal dressed
    as file content, which has to escalate rather than be retried on this
    rung."""
    return ReplyError(
        "refusal",
        f"the reply's fenced block carries no code — it is a refusal "
        f"dressed as {target!r}, and writing it would record this rung as "
        f"having done the task; escalate rather than retrying this rung",
    )


def _fenced(
    text: str, *, output_schema: str, stop_reason: StopReason
) -> ParsedFile | ReplyError:
    """Parse `text` as exactly one fenced block and return its body.

    The schema and stop-reason gate runs first, then every fence in the text is
    collected: no block, more than one, one left unclosed, or an empty body is a
    named error. The chosen block's lines are joined with LF and closed with one
    newline, and the info string's first word is kept beside the content.
    """
    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(lines):
        opened = FENCE_OPEN.match(lines[index])
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
        info = opened.group(2).split()
        blocks.append((info[0] if info else "", lines[index + 1 : closed_at]))
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
    # The body is written as a file: the block's own lines joined with LF and
    # closed with one newline. The width test already settled which fence closed
    # this block, so the body is taken as-is rather than re-scanned for fences.
    return ParsedFile(content=content + "\n", info_string=info)


def parse_reply(
    text: str,
    *,
    output_schema: str = WHOLE_FILE,
    stop_reason: StopReason = StopReason.COMPLETE,
    target: str | None = None,
) -> ParsedFile | ReplyError:
    """Parse a reply into the text to write, or a ReplyError saying why not.

    `prose` and `media_artifact` are the raw text. A whole-file reply must be one
    closed fenced block, which an unpinned reply may itself wrap a JSON envelope
    around. With no `target`, nothing is judged about the content; with one, a
    block that carries no code for that extension is refused as a refusal.
    """
    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable
    if output_schema in (PROSE, MEDIA_ARTIFACT):
        return ParsedFile(content=_prose(text))
    parsed = _fenced(text, output_schema=output_schema, stop_reason=stop_reason)
    if isinstance(parsed, ReplyError):
        if parsed.code == "no-fenced-block" and target is None:
            # A reply with no fence may still be a JSON {content: ...} envelope,
            # and with no target there is nothing to judge it against, so the
            # envelope's field is taken. A reply without the envelope keeps the
            # no-fenced-block error.
            carried = _carried_file(text)
            if carried is not None:
                return ParsedFile(content=_as_file(carried))
        return parsed
    if target is None:
        # No target, so no content judgement: the block may itself be the envelope.
        carried = _carried_file(parsed.content)
        if carried is not None:
            return ParsedFile(content=_as_file(carried), info_string=parsed.info_string)
        return parsed
    if _carries_no_code(parsed.content, target):
        return _refusal(target)
    return parsed


def parse_pinned(
    text: str,
    *,
    response_schema: dict[str, Any] | None,
    output_schema: str = WHOLE_FILE,
    stop_reason: StopReason = StopReason.COMPLETE,
    target: str | None = None,
) -> ParsedFile | ReplyError:
    """Parse a reply whose request pinned a response schema.

    The file text is read from the schema's string field, falling back to a single
    fenced block when the text is not that envelope. A block that cannot be the
    file on its own terms (no target, or no code for the target) is unwrapped once
    more in case the block itself is the envelope. `prose` and `media_artifact`
    stay raw text, and no schema at all means `parse_reply`.
    """
    if response_schema is None:
        return parse_reply(
            text, output_schema=output_schema, stop_reason=stop_reason, target=target
        )

    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable
    if output_schema in (PROSE, MEDIA_ARTIFACT):
        # prose and media_artifact are the raw text even under a pinned schema: the
        # gate above already refused an incomplete reply, and a fence hunt here
        # would return an incidental fenced snippet as the answer.
        return ParsedFile(content=_prose(text))

    field = _schema_field(response_schema)
    info = ""
    carried = _carried_file(text, field)
    if carried is None:
        # Not the envelope at the top level, so the reply may be a plain fenced block,
        # or a fenced block whose body is the envelope. Either way the fence rules
        # still hold, so _fenced parses it and a malformed reply keeps its named error.
        # The block's text is then unwrapped from the field, but only where the block
        # cannot be the file itself: no target to judge it against, or content that
        # carries no code for the target.
        parsed = _fenced(text, output_schema=output_schema, stop_reason=stop_reason)
        if isinstance(parsed, ReplyError):
            return parsed
        info = parsed.info_string
        carried = parsed.content
        if target is None or _carries_no_code(carried, target):
            carried = _carried_file(carried, field) or carried

    content = _as_file(carried)
    if target is not None and _carries_no_code(content, target):
        return _refusal(target)
    return ParsedFile(content=content, info_string=info)
