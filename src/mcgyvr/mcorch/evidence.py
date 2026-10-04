"""Repository evidence, gathered the way a pi agent gathers it: through the harness.

Owner ruling: mcorch gets data the way pi does. The model emits a tool call,
the harness runs it in the working directory, and the output comes back as a
tool result. So under an authoring strategy that needs the repository's index
(``prose``, ``classifier``), the loop has the harness run mcgyvr's own
deterministic reader — ``mcgyvr read "<request>" --json`` — and this module
reads the document that comes back: the request, the resolver's shortlist,
the regions read, and the whole text of every shortlisted and read file. From
those texts it assembles the same :class:`~mcgyvr.orchestrator.index.Index`
the command built, so the decomposer runs server-side over the evidence and
nothing else. The repository never touches the server: ``root`` is a label the
index carries, never a path anything here opens.

The shell tool is whichever the harness offers — Claude Code's ``Bash``, pi's
``bash`` — picked from the tools the request names; offered none, the
strategy is refused by name (:func:`shell_tool`).
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr.orchestrator.index import Index, IndexAssembler, index_source

#: The shell tools a harness may offer, by the names Claude Code and pi use.
SHELL_TOOLS = ("Bash", "bash")

#: The flag that makes ``mcgyvr read`` print the document instead of a report.
JSON_FLAG = "--json"

_READ = "mcgyvr read "


def command(request: str) -> str:
    """The shell command that gathers evidence for ``request`` in the harness's cwd."""
    return f"{_READ}{shlex.quote(request)} {JSON_FLAG}"


def is_read_command(text: str) -> bool:
    """Whether a shell command is one of ours: a JSON read of the repository."""
    return text.strip().startswith(_READ) and JSON_FLAG in text


def shell_tool(tools: Sequence[Mapping[str, Any]]) -> str | None:
    """The shell tool the harness offers, by name, or ``None`` when it offers none."""
    offered = {str(tool.get("name")) for tool in tools}
    return next((name for name in SHELL_TOOLS if name in offered), None)


@dataclass(frozen=True)
class Document:
    """What ``mcgyvr read --json`` printed, as the server reads it."""

    prompt: str
    root: str
    files: tuple[tuple[str, str], ...]
    candidates: tuple[str, ...]
    #: The checker each adapter located where the repository is, by adapter
    #: name — the one lookup the server cannot make. Empty: none declared.
    located: dict[str, tuple[str, ...]] = field(default_factory=dict)


def parse_document(text: str) -> Document | None:
    """The document in ``text``, or ``None`` when it is not one whole document.

    A harness may cut a long tool result short; a document that does not
    parse, or lacks its files, is not evidence and is answered as such rather
    than guessed at.
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
    """The index the command built, assembled again from the texts it sent."""
    assembler = IndexAssembler()
    for path, text in document.files:
        assembler.add(index_source(path, text.encode("utf-8", "surrogateescape")))
    return assembler.finish(Path(document.root or "."))


@dataclass(frozen=True)
class ReadResult:
    """A read's result as the conversation carries it: the call's id and text."""

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
    """Tool-use id → message index, for every read command the assistant issued."""
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
    """The read result the latest message carries, or ``None``."""
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
    """Whether a read was issued after the latest plain user request."""
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
