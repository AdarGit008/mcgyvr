"""The seams a loaded config is resolved into before `mcgyvr mcorch serve` listens.

`bind` builds the two callables the loop dispatches through: `rung` sends the
harness conversation to the `orchestrator` role through
`mcgyvr.runner.dispatch_role`, and `jev` puts one bounded question to the `jev`
role through `mcgyvr.decision.classify_role`. Alongside them it renders the
prompt under a writer id, keeps the tools the harness is allowed to call,
chooses the authoring strategy and opens the transcript. `facade` pairs that
binding with `loop.respond` and journals every turn the server answers. No
address lives here, so re-pointing either role is a line in the config.
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
from mcgyvr.runner import Request, dispatch_role


@dataclass(frozen=True)
class Bound:
    """One mcorch server's seams, prompt and recording, fixed at bind time.

    `rung` and `jev` are the two roles the loop dispatches through, `system` is
    the rendered prompt, `keep_tools` the tool names left to the harness,
    `internal` the authoring strategies, `writer` the id this server files its
    transcript under, `transcript` that file, and `limits` the loop's ceilings.
    """

    rung: Rung
    jev: Jev
    system: str
    keep_tools: tuple[str, ...]
    internal: tuple[Authoring, ...]
    writer: str
    transcript: Transcript
    limits: loop.Limits


def journal_dir(config: Config) -> Path:
    """The journal directory the config names under `journal.dir`.

    A `~` is expanded, and `JOURNAL_DIR_DEFAULT` stands in when the config names
    no directory at all.
    """
    configured = config.get("journal.dir")
    return Path(configured or JOURNAL_DIR_DEFAULT).expanduser()


def bind(config: Config, *, journal_dir: Path, pool: SourceMap | None = None) -> Bound:
    """Resolve a config into the seams, prompt and transcript one server uses.

    Both the `orchestrator` and the `jev` role must be bound to a unit that can
    serve; a config that binds neither is refused with `UnboundRoleError` before
    anything is built. `rung` dispatches the harness conversation to the
    orchestrator role, on the capacity read from the config and with the
    orchestrator unit's `request_timeout_s`. `jev` asks the jev role one bounded
    question per call. The prompt is rendered for a fresh writer id, the kept
    tools are `orchestrator.tools`, and the authoring strategy is the one
    `orchestrator.authoring` names.

    `pool` is a source map the caller has already built; without one the map is
    read from the config here.
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
    # `orchestrator.unit` names the declared unit that serves the rung, so a
    # rung reply is made on that unit's terms.
    # The reply is given the unit's own `request_timeout_s`; `None` states no
    # timeout here and leaves the transport's default in force.
    timeout_s = unit.request_timeout_s

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
        if completion is None:  # the role lost its unit: refuse rather than reply empty
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
        if decision is None:  # the role lost its unit: refuse rather than answer
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
    """The facade the HTTP handler calls, answering and journaling through `bound`.

    `respond` runs one Messages request through `loop.respond` with the bound
    rung, jev, prompt, kept tools, authoring strategies and limits. `on_turn`
    appends the turn's trace to the transcript, stamped with the model the
    request named, the stop reason and the elapsed seconds rounded to
    milliseconds.
    """

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
