"""The evidence mcorch gathers through the harness shell, and reads back.

Nothing here opens the repository: a work request becomes a harness shell call
`mcgyvr read "<request>" --json`, and the JSON that call prints travels back in
the conversation as a tool result. This module builds that command, recognises
it and its result among the messages, parses the document it prints (prompt
words, root label, file texts, resolution candidates, located checker commands)
and indexes the carried file texts for the proposer.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr.orchestrator.index import Index, IndexAssembler, index_source

# The names a harness offers a shell under (Claude Code `Bash`, pi `bash`),
# listed in the order `shell_tool` prefers them.
SHELL_TOOLS = ("Bash", "bash")

# The flag that makes `mcgyvr read` print the document instead of a summary.
JSON_FLAG = "--json"

_READ = "mcgyvr read "


def command(request: str) -> str:
    """The `mcgyvr read` shell command line asking for `request`, quoted."""
    return f"{_READ}{shlex.quote(request)} {JSON_FLAG}"


def is_read_command(text: str) -> bool:
    """Whether `text` is a `mcgyvr read ... --json` command line."""
    return text.strip().startswith(_READ) and JSON_FLAG in text


def shell_tool(tools: Sequence[Mapping[str, Any]]) -> str | None:
    """The first name in `SHELL_TOOLS` that `tools` offers, else `None`."""
    offered = {str(tool.get("name")) for tool in tools}
    return next((name for name in SHELL_TOOLS if name in offered), None)


@dataclass(frozen=True)
class Document:
    """What `mcgyvr read --json` printed, as far as mcorch reads it.

    `root` labels the repository the read happened in and is never opened;
    `files` holds the text of each file the read carried; `candidates` holds
    the paths the resolution shortlisted.
    """

    prompt: str
    root: str
    files: tuple[tuple[str, str], ...]
    candidates: tuple[str, ...]
    # The repository's type-checker argv per language adapter name; empty when
    # the document carried none.
    located: dict[str, tuple[str, ...]] = field(default_factory=dict)


def parse_document(text: str) -> Document | None:
    """The `Document` in `text`, or `None` when it is not a readable one.

    `None` for text that is not JSON, is not an object with a `files` list, or
    whose file entries lack string `path` and `text`. Missing or malformed
    `prompt`, `root`, `resolution.candidates` and `located` degrade to empty
    values instead of refusing the document.
    """
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("files"), list):
        return None
    files: list[tuple[str, str]] = []
    for entry in raw["files"]:
        if not isinstance(entry, dict):
            return None
        path, body = entry.get("path"), entry.get("text")
        if not isinstance(path, str) or not isinstance(body, str):
            return None
        files.append((path, body))
    resolution = raw.get("resolution")
    candidates = (
        tuple(
            str(c.get("path"))
            for c in resolution.get("candidates", ())
            if isinstance(c, dict)
        )
        if isinstance(resolution, dict)
        else ()
    )
    located: dict[str, tuple[str, ...]] = {}
    for name, argv in (raw.get("located") or {}).items():
        if isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv):
            located[str(name)] = tuple(argv)
    return Document(
        prompt=str(raw.get("prompt", "")),
        root=str(raw.get("root", "")),
        files=tuple(files),
        candidates=candidates,
        located=located,
    )


def index_from(document: Document) -> Index:
    """Index the file texts the document carries, rooted at its label.

    The file bytes come from `document.files` alone; `document.root` only names
    the index root and no path is read from disk.
    """
    assembler = IndexAssembler()
    for path, text in document.files:
        assembler.add(index_source(path, text.encode("utf-8", "surrogateescape")))
    return assembler.finish(Path(document.root or "."))


@dataclass(frozen=True)
class ReadResult:
    """A tool result that answered one read call: its id and its text."""

    tool_use_id: str
    text: str


def _result_text(block: Mapping[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(
        str(part.get("text", ""))
        for part in content or ()
        if isinstance(part, dict) and part.get("type") == "text"
    )


def read_calls(messages: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Map each read call's tool-use id to the position of its message."""
    found: dict[str, int] = {}
    for position, message in enumerate(messages):
        if message.get("role") != "assistant" or not isinstance(
            message.get("content"), list
        ):
            continue
        for block in message["content"]:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in SHELL_TOOLS:
                continue
            input_ = block.get("input")
            text = input_.get("command") if isinstance(input_, dict) else None
            if isinstance(text, str) and is_read_command(text):
                found[str(block.get("id"))] = position
    return found


def latest_result(messages: Sequence[Mapping[str, Any]]) -> ReadResult | None:
    """The first read result in the last message, or `None`.

    Only the final message is inspected, and only when it is a user message
    with a content list; a read result anywhere else is not reported.
    """
    calls = read_calls(messages)
    if not calls:
        return None
    last = messages[-1]
    if last.get("role") != "user" or not isinstance(last.get("content"), list):
        return None
    for block in last["content"]:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        tool_use_id = str(block.get("tool_use_id"))
        if tool_use_id in calls:
            return ReadResult(tool_use_id=tool_use_id, text=_result_text(block))
    return None


def gathered_since_request(messages: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a read call was made after the last plain user request.

    A user message is a plain request when its content is a string or carries
    no tool_result block; with no plain request in the history, every read call
    counts as gathered.
    """
    calls = read_calls(messages)
    latest_request = max(
        (
            position
            for position, message in enumerate(messages)
            if message.get("role") == "user" and _is_plain_request(message)
        ),
        default=-1,
    )
    return any(position > latest_request for position in calls.values())


def _is_plain_request(message: Mapping[str, Any]) -> bool:
    content = message.get("content")
    if isinstance(content, str):
        return True
    return not any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content or ()
    )
