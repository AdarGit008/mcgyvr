""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr.orchestrator.index import Index, IndexAssembler, index_source

#
SHELL_TOOLS = ("Bash", "bash")

#
JSON_FLAG = "--json"

_READ = "mcgyvr read "


def command(request: str) -> str:
    ""
    return f"{_READ}{shlex.quote(request)} {JSON_FLAG}"


def is_read_command(text: str) -> bool:
    ""
    return text.strip().startswith(_READ) and JSON_FLAG in text


def shell_tool(tools: Sequence[Mapping[str, Any]]) -> str | None:
    ""
    offered = {str(tool.get("name")) for tool in tools}
    return next((name for name in SHELL_TOOLS if name in offered), None)


@dataclass(frozen=True)
class Document:
    ""

    prompt: str
    root: str
    files: tuple[tuple[str, str], ...]
    candidates: tuple[str, ...]
    #
    #d.
    located: dict[str, tuple[str, ...]] = field(default_factory=dict)


def parse_document(text: str) -> Document | None:
    ""
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
    ""
    assembler = IndexAssembler()
    for path, text in document.files:
        assembler.add(index_source(path, text.encode("utf-8", "surrogateescape")))
    return assembler.finish(Path(document.root or "."))


@dataclass(frozen=True)
class ReadResult:
    ""

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
    ""
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
    ""
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
    ""
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
