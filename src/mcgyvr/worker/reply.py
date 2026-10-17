""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from mcgyvr.runner import Completion, StopReason

#
#
WHOLE_FILE = "whole_file"
PROSE = "prose"
MEDIA_ARTIFACT = "media_artifact"

#
#
#
#
_ENVELOPE_FIELD = "content"

#
#s.
#
#€”
#
#
# a
#
#
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,})[ \t]*([^`]*)$")


#
#
#
#
#
#er
#
_PY_EXTENSIONS = (".py", ".pyi")
_JS_EXTENSIONS = (".ts", ".mts", ".cts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_LINE_COMMENTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (_PY_EXTENSIONS, ("#",)),
    (_JS_EXTENSIONS, ("//",)),
)

#
#
_BLOCK_COMMENT = re.compile(r"(?m)^[ \t]*/\*.*?\*/[ \t]*$", re.DOTALL)


def _leaders(target: str) -> tuple[str, ...] | None:
    ""
    for extensions, leaders in _LINE_COMMENTS:
        if target.endswith(extensions):
            return leaders
    return None


def _carries_no_code(body: str, target: str) -> bool:
    ""
    leaders = _leaders(target)
    if leaders is None:
        return False

    #
    #nd
    #
    #
    #
    try:
        blob = json.loads(body)
    except (ValueError, RecursionError):
        #
        #er
        #
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
    ""
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
    ""
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
    ""
    kind = spec.get("type")
    if isinstance(kind, str):
        return kind == "string"
    return isinstance(kind, list) and "string" in kind


def _as_file(content: str) -> str:
    ""
    return content if content.endswith("\n") else content + "\n"


def _is_close(line: str, width: int) -> bool:
    ""
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    if not stripped.startswith("`" * width):
        return False
    return stripped.rstrip("`").strip() == ""


@dataclass(frozen=True)
class ParsedFile:
    ""

    content: str
    info_string: str = ""
    """The fence's language tag, reported and never enforced.

    A worker that tagged a Python file ```js` wrote the right file with the
    wrong label; refusing it would spend an attempt on a cosmetic mismatch.
    Kept so telemetry can notice a model that consistently mislabels.
    """


@dataclass(frozen=True)
class ReplyError:
    ""

    code: str
    message: str

    def __str__(self) -> str:
        return f"reply[{self.code}]: {self.message}"


def _unreadable(output_schema: str, stop_reason: StopReason) -> ReplyError | None:
    ""
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
    ""
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
        f"within the unit's ceiling â€” its `window` less the prompt, or its "
        f"`output_tokens`",
    )


def _prose(text: str) -> str:
    ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _refusal(target: str) -> ReplyError:
    ""
    return ReplyError(
        "refusal",
        f"the reply's fenced block carries no code â€” it is a refusal "
        f"dressed as {target!r}, and writing it would record this rung as "
        f"having done the task; escalate rather than retrying this rung",
    )


def _fenced(
    text: str, *, output_schema: str, stop_reason: StopReason
) -> ParsedFile | ReplyError:
    ""
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
                f"a fence opened at line {index + 1} is never closed â€” the "
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
    # a
    #
    #
    return ParsedFile(content=content + "\n", info_string=info)


def parse_reply(
    text: str,
    *,
    output_schema: str = WHOLE_FILE,
    stop_reason: StopReason = StopReason.COMPLETE,
    target: str | None = None,
) -> ParsedFile | ReplyError:
    ""
    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable
    if output_schema in (PROSE, MEDIA_ARTIFACT):
        return ParsedFile(content=_prose(text))
    parsed = _fenced(text, output_schema=output_schema, stop_reason=stop_reason)
    if isinstance(parsed, ReplyError):
        if parsed.code == "no-fenced-block" and target is None:
            # a
            #
            #
            #
            carried = _carried_file(text)
            if carried is not None:
                return ParsedFile(content=_as_file(carried))
        return parsed
    if target is None:
        #
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
    ""
    if response_schema is None:
        return parse_reply(
            text, output_schema=output_schema, stop_reason=stop_reason, target=target
        )

    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable
    if output_schema in (PROSE, MEDIA_ARTIFACT):
        #
        #
        #re
        #
        return ParsedFile(content=_prose(text))

    field = _schema_field(response_schema)
    info = ""
    carried = _carried_file(text, field)
    if carried is None:
        #
        #so
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
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
