""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from mcgyvr import contract

#
WRITE_TOOLS = frozenset({"Write", "write", "Edit", "edit", "MultiEdit"})

#
PATH_KEYS = ("file_path", "path", "filePath")

#
RESULT_KEYS = ("contract", "outcome")


def arguments(text: str) -> dict[str, Any] | None:
    ""
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def path_of(input_: Mapping[str, Any]) -> str | None:
    ""
    for key in PATH_KEYS:
        value = input_.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def open_targets(messages: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    ""
    opened: dict[str, str] = {}
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if message.get("role") == "assistant" and block.get("type") == "tool_use":
                _open(block, opened)
            elif message.get("role") == "user" and block.get("type") == "tool_result":
                _close(block, opened)
    return opened


def _open(block: Mapping[str, Any], opened: dict[str, str]) -> None:
    if block.get("name") not in WRITE_TOOLS:
        return
    input_ = block.get("input")
    if not isinstance(input_, dict):
        return
    text = input_.get("content")
    if not isinstance(text, str) or "task_type" not in text:
        return
    try:
        authored = contract.loads(text)
    except contract.ContractError:
        return
    if authored.is_session:
        #
        return
    opened[authored.target] = authored.id


def _close(block: Mapping[str, Any], opened: dict[str, str]) -> None:
    content = block.get("content")
    text = (
        content
        if isinstance(content, str)
        else "\n".join(
            str(part.get("text", ""))
            for part in content or ()
            if isinstance(part, dict) and part.get("type") == "text"
        )
    )
    try:
        parsed = json.loads(text)
    except ValueError:
        return
    if not isinstance(parsed, dict) or not all(key in parsed for key in RESULT_KEYS):
        return
    finished = parsed["contract"]
    for target, contract_id in list(opened.items()):
        if contract_id == finished:
            del opened[target]


def edits_open_target(
    name: str, input_: Mapping[str, Any], targets: Mapping[str, str]
) -> str | None:
    ""
    if name not in WRITE_TOOLS or not targets:
        return None
    path = path_of(input_)
    if path is None:
        return None
    parts = PurePosixPath(path.replace("\\", "/")).parts
    for target, contract_id in targets.items():
        wanted = PurePosixPath(target).parts
        if len(parts) >= len(wanted) and parts[-len(wanted) :] == wanted:
            return contract_id
    return None


def refusal(name: str, target: str, contract_id: str) -> str:
    ""
    return (
        f"refused: {name} on {target} was not handed to the harness — it is the "
        f"target of contract {contract_id!r}, which is open. Work on a target "
        "lands only through `mcgyvr run`: fix the contract (its acceptance, its "
        "scope, its task) and run it again, or ask the user. A preflight refusal "
        "is about the contract, never a reason to edit the file yourself."
    )
