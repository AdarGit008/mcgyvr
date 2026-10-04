"""The two seams mcorch holds: a rung to converse with, and Jev to decide with.

Both are callables rather than objects that know where a model runs, for the
reason :mod:`mcgyvr.gate.jev` gives for its ``decide`` seam: the loop above
them never learns an address, and a test hands in a scripted double in place of
either. :mod:`mcgyvr.mcorch.bind` builds the production pair from a config.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcgyvr.decision import Decision, Question


@dataclass(frozen=True)
class RungToolCall:
    """One function call the rung asked for, with its arguments as JSON text."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class RungCall:
    """One request to the rung: a system prompt, the turns so far, the tools."""

    system: str
    turns: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...]
    max_output_tokens: int


@dataclass(frozen=True)
class RungReply:
    """What the rung answered: text, the tools it called, whether it was cut."""

    text: str
    tool_calls: tuple[RungToolCall, ...]
    truncated: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


#: The rung seam: one call in, one reply out.
type Rung = Callable[[RungCall], RungReply]

#: The Jev seam: a state and typed questions in, a typed decision out — the
#: same shape :class:`mcgyvr.delegate.ClassifierProposer` holds.
type Jev = Callable[[Any, Mapping[str, Question]], Decision]
