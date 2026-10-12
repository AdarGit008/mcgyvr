"""Bind mcorch's two seams from a loaded config: the rung and Jev.

The server holds no address. The rung is the ``orchestrator`` role reached
through :func:`mcgyvr.runner.dispatch_role`, the harness's turns and tools on
the wire; Jev is the ``jev`` role reached through
:func:`mcgyvr.decision.classify_role`. Both cross the pool seam inside those
two functions, so this module — like the loop above it — names roles and never
an endpoint, and re-pointing either is a line in ``policy.yaml``. Capacity
holds the unit's slot for the length of each call, as a dispatch does: the
agent shares its card with the ladder it drives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.capacity import Capacity
from mcgyvr.config import JOURNAL_DIR_DEFAULT, Config
from mcgyvr.decision import (
    JEV_ROLE,
    Decision,
    Question,
    UnboundRoleError,
    classify_role,
)
from mcgyvr.delegate import ORCHESTRATOR_ROLE
from mcgyvr.local_pool import SourceMap, source_map
from mcgyvr.mcorch import loop, prompt, serve
from mcgyvr.mcorch.anthropic import MessagesRequest
from mcgyvr.mcorch.authoring import Authoring, authoring_for
from mcgyvr.mcorch.transcript import Transcript, writer_id
from mcgyvr.mcorch.wire import Jev, Rung, RungCall, RungReply, RungToolCall
from mcgyvr.runner import GENERATE_TIMEOUT_S, Request, dispatch_role


@dataclass(frozen=True)
class Bound:
    """Everything a server needs, built once from the config."""

    rung: Rung
    jev: Jev
    system: str
    keep_tools: tuple[str, ...]
    internal: tuple[Authoring, ...]
    writer: str
    transcript: Transcript
    limits: loop.Limits


def journal_dir(config: Config) -> Path:
    """The journal directory the config names, or the schema's default."""
    configured = config.get("journal.dir")
    return Path(configured or JOURNAL_DIR_DEFAULT).expanduser()


def bind(config: Config, *, journal_dir: Path, pool: SourceMap | None = None) -> Bound:
    """The rung, Jev, prompt and transcript for one server, from ``config``.

    Raises :class:`~mcgyvr.decision.UnboundRoleError` when a role the loader
    let through has no unit that can serve it now (a credential unset, say),
    and :class:`~mcgyvr.mcorch.authoring.AuthoringUnavailableError` for a
    strategy this server cannot run.
    """
    resolved = pool if pool is not None else source_map(config)
    capacity = Capacity.of(config)
    for role in (ORCHESTRATOR_ROLE, JEV_ROLE):
        if resolved.role_model(role) is None:
            raise UnboundRoleError(
                f"{role}.unit: mcorch needs the {role} role bound to a unit that can "
                "serve, and none is."
            )
    unit = config.units[str(config.get("orchestrator.unit"))]
    timeout_s = unit.request_timeout_s or GENERATE_TIMEOUT_S

    def rung(call: RungCall) -> RungReply:
        completion = dispatch_role(
            resolved,
            ORCHESTRATOR_ROLE,
            Request(
                prompt="",
                max_output_tokens=call.max_output_tokens,
                system=call.system,
                timeout_s=timeout_s,
                turns=call.turns,
                tools=call.tools,
            ),
            capacity=capacity,
        )
        if completion is None:  # the role was bound a moment ago
            raise UnboundRoleError(
                f"the {ORCHESTRATOR_ROLE!r} role has no unit to dispatch to"
            )
        return RungReply(
            text=completion.text,
            tool_calls=tuple(
                RungToolCall(id=call.id, name=call.name, arguments=call.arguments)
                for call in completion.tool_calls
            ),
            truncated=completion.truncated,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )

    def jev(state: Any, questions: Mapping[str, Question]) -> Decision:
        decision = classify_role(
            resolved, JEV_ROLE, state, questions, capacity=capacity
        )
        if decision is None:  # the role was bound a moment ago
            raise UnboundRoleError(f"the {JEV_ROLE!r} role has no unit to answer")
        return decision

    writer = writer_id()
    strategy = authoring_for(
        str(config.get("orchestrator.authoring")), jev=jev, rung=rung, config=config
    )
    return Bound(
        rung=rung,
        jev=jev,
        system=prompt.render(writer=writer, authoring=strategy.name),
        keep_tools=tuple(config.get("orchestrator.tools") or ()),
        internal=(strategy,),
        writer=writer,
        transcript=Transcript.open(journal_dir, writer),
        limits=loop.Limits(),
    )


def facade(bound: Bound) -> serve.Facade:
    """The server's facade over ``bound``: the loop, and the transcript observing it."""

    def respond(request: MessagesRequest) -> loop.Turn:
        return loop.respond(
            request,
            rung=bound.rung,
            jev=bound.jev,
            system=bound.system,
            keep_tools=bound.keep_tools,
            internal=bound.internal,
            limits=bound.limits,
        )

    def observe(
        request: MessagesRequest, turn: loop.Turn, stop_reason: str, elapsed_s: float
    ) -> None:
        bound.transcript.record(
            turn.trace,
            model=request.model,
            stop_reason=stop_reason,
            elapsed_s=round(elapsed_s, 3),
        )

    return serve.Facade(respond=respond, on_turn=observe)
