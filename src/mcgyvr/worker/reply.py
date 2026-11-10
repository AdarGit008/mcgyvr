"""Turn one reply's text into the bytes meant for a file, or a named refusal.

A reply is treated as a file only when the protocol can vouch for it: the
backend stopped complete, the output schema is one this module implements, and
the text holds exactly one closed fenced block. Everything else - no fence, two
blocks because the model offered an alternative, a fence the cap cut off, an
empty block - becomes a `ReplyError` carrying a code, so a caller can tell the
causes apart instead of writing a plausible file. Given a target path, a file
that holds no code for that extension is refused as a refusal rather than a
file, and a reply that spent its whole cap on hidden reasoning is named as empty.

Under `whole_file` the block is the file. Under `unified_diff` the block is a
unified diff of the target alone (:func:`parse_diff`), applied by `git apply`
onto the content the model was shown (:func:`apply_diff`); what comes back is
the whole resulting file, so the gate and delivery cannot tell the two apart. A
diff that names another file, deletes, renames, changes a mode or is binary is
refused before anything is applied, and one whose context does not match is a
named error the next attempt is told about, never a crash.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.contract import UNIFIED_DIFF as UNIFIED_DIFF
from mcgyvr.contract import WHOLE_FILE as WHOLE_FILE
from mcgyvr.gitcmd import run_git
from mcgyvr.runner import Completion, StopReason
from mcgyvr.scope import inside

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
    if output_schema not in (WHOLE_FILE, UNIFIED_DIFF):
        return ReplyError(
            "unsupported-schema",
            f"output_schema {output_schema!r} has no parser; only "
            f"{WHOLE_FILE!r} and {UNIFIED_DIFF!r} are implemented",
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
        f"no visible reply. The cap was the most the unit can give: raise the "
        f"unit's `output_tokens`, or its `window`, which less the prompt bounds "
        f"the reply, or run the work on a unit that serves more",
    )


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


# --- unified_diff ------------------------------------------------------------

#: The path a diff names for the side of a file that does not exist.
_DEV_NULL = "/dev/null"

#: A hunk header: `@@ -start[,count] +start[,count] @@`, anything after it kept.
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")

#: Header lines a git diff may carry before its `---`/`+++` pair that say nothing
#: the pair does not: they are dropped, and the pair is rebuilt from the target.
_INERT_HEADERS = ("diff --git ", "index ", "new file mode ")

#: Header lines that make the diff something other than an edit of one text
#: file's lines, each with what it would do. The contract writes one target's
#: content, so none of them is applied.
_REFUSED_HEADERS = (
    ("deleted file mode", "deletes the file"),
    ("rename from", "renames a file"),
    ("rename to", "renames a file"),
    ("copy from", "copies a file"),
    ("copy to", "copies a file"),
    ("similarity index", "renames or copies a file"),
    ("dissimilarity index", "rewrites a file under another name"),
    ("old mode", "changes a file's mode"),
    ("new mode", "changes a file's mode"),
    ("GIT binary patch", "is a binary patch"),
    ("Binary files ", "is a binary patch"),
)


@dataclass(frozen=True)
class ParsedDiff:
    """One diff reply the protocol accepted, not yet applied: the patch `git
    apply` is given, rebuilt from the target, and whether it creates the file."""

    patch: str
    creates: bool
    """Whether the old side is `/dev/null`: a new file, which is only applied
    onto a target that has no content yet."""


def _side(header: str, marker: str) -> str:
    """The path a `---` or `+++` header line names: the text after the marker,
    up to a tab (where `diff -u` puts a timestamp), with no trailing blanks."""
    return header[len(marker) :].split("\t", 1)[0].rstrip()


def _names_target(path: str, target: str) -> bool:
    """Whether a header `path` names `target`: as written, or behind git's `a/`
    or `b/` prefix, either with a leading `./` dropped."""
    candidates = {path, path.removeprefix("./")}
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            candidates.add(path[len(prefix) :].removeprefix("./"))
    return target.removeprefix("./") in candidates


def _is_hunk_line(line: str) -> bool:
    """Whether `line` belongs to a hunk body: context, a removal, an addition,
    git's no-newline marker, or an empty line (a context line whose single space
    a model or an editor stripped, which `git apply` reads as one)."""
    return line == "" or line[0] in " +-\\"


def parse_diff(body: str, *, target: str) -> ParsedDiff | ReplyError:
    """Read the body of a fenced diff block as a unified diff of `target` alone.

    The lines before the `---`/`+++` pair may be blank or git's own `diff
    --git`, `index` and `new file mode` lines; a header that deletes, renames,
    copies, changes a mode or carries a binary patch is refused, and anything
    else there is not a diff. The pair must name `target` on both sides (the old
    side may be `/dev/null` for a new file), then at least one hunk follows,
    whose lines are context, removals, additions or the no-newline marker. A
    second `---`/`+++` pair is a second file and refused. The patch handed on is
    the hunks under a header rebuilt from `target`, so what `git apply` is told
    to touch is the contract's file and nothing the model wrote.
    """
    lines = body.split("\n")
    while lines and not lines[-1].strip():
        # Blank lines after the last hunk would read as empty context lines.
        lines.pop()
    index = 0
    while index < len(lines) and not lines[index].startswith("--- "):
        line = lines[index]
        for prefix, does in _REFUSED_HEADERS:
            if line.startswith(prefix):
                return ReplyError(
                    "diff-not-a-text-edit",
                    f"the diff {does} (line {index + 1}: {line[:80]!r}); the "
                    f"reply may only edit the lines of {target!r}",
                )
        if line.strip() and not line.startswith(_INERT_HEADERS):
            return ReplyError(
                "malformed-diff",
                f"line {index + 1} of the diff block, {line[:80]!r}, is not part "
                f"of a unified diff; the block must be the diff and nothing else, "
                f"starting with `--- a/{target}` and `+++ b/{target}`",
            )
        index += 1
    if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
        return ReplyError(
            "malformed-diff",
            f"the diff block has no `--- a/{target}` line followed by a "
            f"`+++ b/{target}` line, so it names no file to change",
        )
    old = _side(lines[index], "--- ")
    new = _side(lines[index + 1], "+++ ")
    if new == _DEV_NULL:
        return ReplyError(
            "diff-not-a-text-edit",
            f"the diff deletes {target!r} (`+++ /dev/null`); the reply may only "
            f"edit its lines",
        )
    for side in (old, new):
        if side != _DEV_NULL and not _names_target(side, target):
            return ReplyError(
                "diff-outside-contract",
                f"the diff edits {side!r}, which is not this contract's target "
                f"{target!r}; a reply changes the target and no other file",
            )
    creates = old == _DEV_NULL
    hunks = lines[index + 2 :]
    if not hunks or not _HUNK.match(hunks[0]):
        return ReplyError(
            "malformed-diff",
            "the diff's file header is not followed by a hunk "
            "(`@@ -start,count +start,count @@`), so it changes nothing",
        )
    for offset, line in enumerate(hunks):
        number = index + 3 + offset
        if _HUNK.match(line):
            continue
        if (
            line.startswith("--- ")
            and offset + 1 < len(hunks)
            and hunks[offset + 1].startswith("+++ ")
        ) or line.startswith("diff --git "):
            return ReplyError(
                "diff-many-files",
                f"the diff starts a second file at line {number}; the reply is "
                f"one diff of {target!r} alone",
            )
        if line.startswith(tuple(prefix for prefix, _ in _REFUSED_HEADERS)):
            return ReplyError(
                "diff-not-a-text-edit",
                f"line {number} of the diff, {line[:80]!r}, is a file header "
                f"inside a hunk; the reply may only edit the lines of {target!r}",
            )
        if not _is_hunk_line(line):
            return ReplyError(
                "malformed-diff",
                f"line {number} of the diff, {line[:80]!r}, is not a hunk line: "
                f"each starts with a space (context), `-`, `+` or `\\`",
            )
    header = f"--- {_DEV_NULL if creates else 'a/' + target}\n+++ b/{target}\n"
    return ParsedDiff(patch=header + "\n".join(hunks) + "\n", creates=creates)


class _NotAppliedError(Exception):
    """`git apply` refused the patch; the message is git's own."""


def apply_diff(diff: ParsedDiff, *, target: str, base: str) -> str | ReplyError:
    """Apply `diff` onto `base`, the content of `target` the model was shown, and
    return the whole resulting file, or a ReplyError when it does not apply.

    The base is written at `target` in a scratch directory of its own - never the
    workspace, which the caller writes the result into - and `git apply` applies
    the patch there, all or nothing. Context lines must match the base exactly
    (no fuzz, no whitespace leniency); hunk line counts are recounted, since a
    model miscounts more often than it miscopies. An empty `base` with a diff
    that creates the file is applied onto no file at all. Bytes are carried with
    `surrogateescape`, so content that is not UTF-8 round-trips.
    """
    with tempfile.TemporaryDirectory(prefix="mcgyvr-diff-") as scratch:
        root = Path(scratch).resolve()
        path = inside(root, target)
        if base or not diff.creates:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base.encode("utf-8", "surrogateescape"))
        prefix = f"git apply failed in {root}: "
        try:
            run_git(
                root,
                "apply",
                "--recount",
                # The user's `apply.whitespace` must not turn a trailing blank
                # into a refusal; whitespace in context still has to match.
                "--whitespace=nowarn",
                "-",
                input=diff.patch.encode("utf-8", "surrogateescape"),
                # The scratch directory is no repository, and git must not climb
                # out of it into one: outside a repository `git apply` patches
                # the working directory, as `patch` does.
                env={"GIT_CEILING_DIRECTORIES": str(root.parent)},
                error=_NotAppliedError,
            )
        except _NotAppliedError as refused:
            detail = str(refused).removeprefix(prefix).strip()
            return ReplyError(
                "diff-does-not-apply",
                f"the diff does not apply to the current content of {target!r}: "
                f"{detail or 'git apply refused it'}. Diff against the current "
                f"content as shown, copying each context and removed line exactly",
            )
        if not path.is_file():
            return ReplyError(
                "diff-does-not-apply",
                f"applying the diff left no {target!r}",
            )
        return path.read_bytes().decode("utf-8", "surrogateescape")


def _diffed(
    text: str, *, stop_reason: StopReason, target: str, base: str
) -> ParsedFile | ReplyError:
    """A `unified_diff` reply turned into the whole file it describes: one fenced
    block, read by :func:`parse_diff`, applied by :func:`apply_diff`, and the
    result judged for code like a whole-file block is."""
    block = _fenced(text, output_schema=UNIFIED_DIFF, stop_reason=stop_reason)
    if isinstance(block, ReplyError):
        return block
    # A refusal dressed as a block (comments only, or a JSON status blob) is
    # named as one before it is read as a diff: as `malformed-diff` its retry
    # note would push the model to guess a diff instead of escalating. Every
    # diff line (`---`, `+++`, `@@`, hunk lines) is code to this check.
    if _carries_no_code(block.content, target):
        return _refusal(target)
    diff = parse_diff(block.content, target=target)
    if isinstance(diff, ReplyError):
        return diff
    # The prompt shows the base closed by a newline, so the diff is read against
    # that; a whole-file reply ends in one too.
    shown = _as_file(base) if base else base
    content = apply_diff(diff, target=target, base=shown)
    if isinstance(content, ReplyError):
        return content
    if _carries_no_code(content, target):
        return _refusal(target)
    return ParsedFile(content=content, info_string=block.info_string)


def parse_reply(
    text: str,
    *,
    output_schema: str = WHOLE_FILE,
    stop_reason: StopReason = StopReason.COMPLETE,
    target: str | None = None,
    base: str | None = None,
) -> ParsedFile | ReplyError:
    """Parse a reply into the text to write, or a ReplyError saying why not.

    A whole-file reply must be one closed fenced block, which an unpinned reply
    may itself wrap a JSON envelope around. With no `target`, nothing is judged
    about the content; with one, a block that carries no code for that extension
    is refused as a refusal.

    A `unified_diff` reply must be one closed fenced block holding a diff of
    `target`, which is applied onto `base` - the target's content as the model
    was shown it, empty for a file that does not exist yet - and the whole
    resulting file is returned. Both are required for that schema.
    """
    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable
    if output_schema == UNIFIED_DIFF:
        if target is None or base is None:
            raise ValueError(
                "a unified_diff reply is applied onto its target: pass the "
                "target and the base content the model was shown"
            )
        return _diffed(text, stop_reason=stop_reason, target=target, base=base)
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
    more in case the block itself is the envelope. No schema at all means
    `parse_reply`.
    """
    if response_schema is None:
        return parse_reply(
            text, output_schema=output_schema, stop_reason=stop_reason, target=target
        )

    unreadable = _unreadable(output_schema, stop_reason)
    if unreadable is not None:
        return unreadable
    if output_schema != WHOLE_FILE:
        # A pinned schema carries the file text in a field; a diff has no field
        # of its own to arrive in, so it is never asked for through a pin.
        return ReplyError(
            "unsupported-schema",
            f"a pinned response schema carries a {WHOLE_FILE!r} reply; "
            f"{output_schema!r} is parsed unpinned, by parse_reply",
        )

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
