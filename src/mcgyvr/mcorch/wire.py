""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcgyvr.decision import Decision, Question


@dataclass(frozen=True)
class RungToolCall:
    ""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class RungCall:
    ""

    system: str
    turns: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...]
    max_output_tokens: int


@dataclass(frozen=True)
class RungReply:
    ""

    text: str
    tool_calls: tuple[RungToolCall, ...]
    truncated: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


#
type Rung = Callable[[RungCall], RungReply]

#he
#
type Jev = Callable[[Any, Mapping[str, Question]], Decision]
