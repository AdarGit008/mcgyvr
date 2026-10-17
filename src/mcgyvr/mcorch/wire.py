"""The two callables mcorch is wired to, and the data they exchange.

A `Rung` sends one `RungCall` to the orchestrator's unit and returns the
`RungReply` it wrote; a `Jev` puts typed questions to the jev unit and returns
the `Decision` they were answered with. `bind` builds both over the source map,
so the loop and the authoring strategies take these interfaces rather than an
endpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcgyvr.decision import Decision, Question


@dataclass(frozen=True)
class RungToolCall:
    """One tool call the rung asked for: the id the provider gave it, the name of
    the tool, and the arguments as the JSON text the model wrote. Callers parse
    the text with `guard.arguments`, which returns None when it is not readable."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class RungCall:
    """One request to the rung: the `system` prompt, the conversation so far as
    `turns`, the tool specs offered as `tools`, and the room the reply is given
    as `max_output_tokens`."""

    system: str
    turns: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...]
    max_output_tokens: int


@dataclass(frozen=True)
class RungReply:
    """What the rung wrote: its `text`, the tool calls it asked for, whether it ran
    out of the room it was given (`truncated`), and the token counts the provider
    reported. A count left as None is estimated by the caller instead."""

    text: str
    tool_calls: tuple[RungToolCall, ...]
    truncated: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


# One turn sent to the orchestrator's unit: a `RungCall` in, its `RungReply` out.
# `bind` builds it over `dispatch_role` on `ORCHESTRATOR_ROLE`.
type Rung = Callable[[RungCall], RungReply]

# One typed ask of the jev unit: the state to decide on and the questions keyed by
# the name each is asked under, answered with a `Decision` keyed the same way.
# `bind` builds it over `classify_role` on `JEV_ROLE`.
type Jev = Callable[[Any, Mapping[str, Question]], Decision]
