"""Preflight refusal to write the target of a contract that is still open.

mcorch hands the tool calls over to the harness, so it sees every one of them
first. This module reads the conversation the request carries, remembers which
targets are the target of an open contract, and answers a write or edit call on
one of them with a refusal naming the contract instead of handing the call
over.

A target opens when an assistant write or edit call carries content that loads
as a non-session contract: its `target` is remembered against its `id`. It
closes when a user tool result arrives holding a run result document — JSON with
both `contract` and `outcome` — whose `contract` is that id. Only write and edit
tool calls are examined; a shell edit is outside what this sees.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from mcgyvr import contract

# The harness tool names that write or edit a file: the capitalized and the
# lower-case spellings, plus MultiEdit.
WRITE_TOOLS = frozenset({"Write", "write", "Edit", "edit", "MultiEdit"})

# The keys a write or edit call may carry the file it touches under, in the
# order they are tried; the first one holding a non-empty string is the path.
PATH_KEYS = ("file_path", "path", "filePath")

# The keys every `mcgyvr run` result document carries. A tool result missing
# either of them is not a run result, so it closes no contract.
RESULT_KEYS = ("contract", "outcome")


def arguments(text: str) -> dict[str, Any] | None:
    """The tool call's arguments as a mapping.

    Empty or blank input is an empty mapping. Text that is not JSON, or JSON
    that is not an object, is unreadable and comes back as `None`.
    """
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def path_of(input_: Mapping[str, Any]) -> str | None:
    """The file a write or edit call touches.

    The first of PATH_KEYS holding a non-empty string, or `None` when the call
    names no file under any of them.
    """
    for key in PATH_KEYS:
        value = input_.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def open_targets(messages: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """The targets of the contracts still open in `messages`, by contract id.

    Messages are read in order: an assistant write or edit call whose content
    loads as a non-session contract opens its target, and a user tool result
    holding a run result document for that contract closes it again. A target
    written twice keeps the id from the later write.
    """
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
        # A session writes nothing, so a target it gave anyway guards no file.
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
    """The id of the open contract whose target this call would edit, if any.

    Only a write or edit tool call on a named path is considered. A path
    matches a target when its trailing parts equal the target's parts, so an
    absolute path or a deeper path to the same file counts, while a file whose
    path merely ends the same letters does not.
    """
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
    """The answer handed back to the rung in place of the refused call.

    It names the call and the target that was held back, the contract that owns
    the target, and the way through: fix the contract and run it again, or ask
    the user. It says the refusal is about the contract and never a reason to
    edit the file by yourself.
    """
    return (
        f"refused: {name} on {target} was not handed to the harness — it is the "
        f"target of contract {contract_id!r}, which is open. Work on a target "
        "lands only through `mcgyvr run`: fix the contract (its acceptance, its "
        "scope, its task) and run it again, or ask the user. A preflight refusal "
        "is about the contract, never a reason to edit the file yourself."
    )
