"""One HTTP request is one turn of the loop: Jev decides, the rung reasons between.

The protocol is stateless — the harness sends the whole conversation every
time — so everything a turn needs is in the messages it carries, and the loop
recomputes its decisions from them. Inside one request the rung and mcorch's
internal tools iterate until the rung either calls a harness tool (the turn
ends with ``tool_use`` and the harness acts) or answers in text (the turn ends
with ``end_turn``).

Three decisions are Jev's, each a bounded question asked through the Jev seam
and handed to the rung as a ``Jev:`` note in its system prompt, never a hidden
branch:

* **J1 intent** — when the latest message is a new user request: is it chat or
  work?
* **J2 ready_to_run** — asked by the authoring strategy when the rung authors a
  contract (:mod:`mcgyvr.mcorch.authoring`).
* **J3 next** — when the latest message carries a ``mcgyvr run`` result the
  harness read back: done, replan, or ask the user?

The harness's system prompt is replaced by mcorch's own (a harness sends many
thousand tokens written for a frontier model; a local rung pays for every one
of them in prompt processing and in confusion) and the tools it offers are kept
only when named in the config's keep list. What was dropped is counted on the
:class:`Trace`, because a prompt that silently shrank is a prompt nobody can
reason about.

**A request that offers no tools is a side request** — a harness's title or
summary call. The rule is the shape and nothing else: without a harness behind
it to run tools, nothing can drive the mcgyvr flow, so nothing is spent
steering it. The rung answers alone, short, with the harness's own system
prompt and no Jev. Claude Code's documentation does not state what its side
requests look like, so this is mcorch's rule, stated here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from mcgyvr.decision import Choice, ChoiceAnswer
from mcgyvr.mcorch import anthropic, guard
from mcgyvr.mcorch.anthropic import MessagesRequest
from mcgyvr.mcorch.authoring import Authoring
from mcgyvr.mcorch.wire import Jev, Rung, RungCall, RungReply, RungToolCall

#: How many internal rounds one request may take before the turn is ended with
#: what the rung said last. Internal rounds are authoring and argument repairs;
#: a rung that needs more than this is looping, and the harness should see it.
MAX_ROUNDS = 6

#: The reply room a side request gets, in tokens, where the harness asked for
#: more: a title or a summary is short, and a local rung's time is the cost.
SIDE_REPLY_TOKENS = 512

#: How much of a user request Jev is shown when asked its intent, in
#: characters; the question is about kind, not detail.
REQUEST_CHARS = 2000

#: J1: a request is chat or work.
INTENT = Choice(
    "Is this request work for the repository — a change to make, a file to "
    "produce, a bug to fix — or conversation?",
    options={
        "work": "work: the user wants a change made in the repository",
        "chat": "chat: a question, a discussion, or an answer that changes nothing",
    },
)

#: J3: after a run result, what comes next.
NEXT = Choice(
    "A mcgyvr run came to this result. What should the orchestrator do next?",
    options={
        "done": "done: the work landed or nothing is left to do; report to the user",
        "replan": "replan: write a different contract from the findings",
        "ask_user": "ask_user: the result needs a decision only the user can make",
    },
)

#: The question names, stable so a transcript reads them by key.
INTENT_NAME = "intent"
NEXT_NAME = "next"


@dataclass(frozen=True)
class Limits:
    """The loop's bounds, carried rather than read from module constants so a
    caller — the server, a test — states them."""

    max_rounds: int = MAX_ROUNDS
    side_reply_tokens: int = SIDE_REPLY_TOKENS


@dataclass(frozen=True)
class Trace:
    """What one turn did, for the transcript: kind, decisions, drops, rounds."""

    kind: Literal["main", "side"]
    intent: str | None
    jev: tuple[tuple[str, str], ...]
    dropped_tools: tuple[str, ...]
    dropped_system_bytes: int
    dropped_blocks: tuple[str, ...]
    rounds: int
    internal_calls: tuple[str, ...]
    next: str | None
    #: Targets of open contracts the rung asked the harness to edit, refused.
    refused_edits: tuple[str, ...] = ()


@dataclass(frozen=True)
class Turn:
    """The rung's final reply for this request, and the trace of getting it."""

    reply: RungReply
    trace: Trace


def respond(
    request: MessagesRequest,
    *,
    rung: Rung,
    jev: Jev,
    system: str,
    keep_tools: Sequence[str],
    internal: Sequence[Authoring],
    limits: Limits,
) -> Turn:
    """Answer one request: a side request alone, a main request through the loop.

    ``system`` is the rendered mcorch prompt with its notes slot still open
    (:func:`mcgyvr.mcorch.prompt.with_notes` fills it here). ``keep_tools``
    names the harness tools kept; empty keeps all. ``internal`` are the
    strategies whose tools are offered beside the harness's and run here.
    """
    turns, dropped_blocks = anthropic.to_openai_turns(request.messages)
    if not request.tools:
        return _side(request, turns, dropped_blocks, rung=rung, limits=limits)

    kept, dropped_tools = _filter_tools(request.tools, keep_tools)
    harness_tools = anthropic.tools_to_openai(kept)
    internal_tools = tuple(tool for strategy in internal for tool in strategy.tools())
    internal_names = frozenset(str(tool["function"]["name"]) for tool in internal_tools)

    asked: list[tuple[str, str]] = []
    notes: list[str] = []
    intent = _intent(request.messages, jev, asked, notes)
    following = _next(request.messages, jev, asked, notes)
    prompt = system.replace("{jev_notes}", "\n".join(notes))

    rounds = 0
    internal_calls: list[str] = []
    refused_edits: list[str] = []
    targets = guard.open_targets(request.messages)
    history = list(turns)
    reply = RungReply(text="", tool_calls=())
    while rounds < limits.max_rounds:
        rounds += 1
        reply = rung(
            RungCall(
                system=prompt,
                turns=tuple(history),
                tools=harness_tools + internal_tools,
                max_output_tokens=request.max_tokens,
            )
        )
        unreadable = set(anthropic.unreadable_calls(reply))
        guarded = _guarded(reply.tool_calls, targets)
        mine = [
            call
            for call in reply.tool_calls
            if call.name in internal_names
            or call.id in unreadable
            or call.id in guarded
        ]
        if not mine:
            return Turn(
                reply=reply,
                trace=_trace(
                    intent,
                    following,
                    asked,
                    dropped_tools,
                    request,
                    dropped_blocks,
                    rounds,
                    internal_calls,
                    refused_edits,
                ),
            )
        theirs = [call for call in reply.tool_calls if call not in mine]
        history.append(_assistant_turn(reply.text, mine))
        for call in mine:
            if call.id in guarded:
                target, contract_id = guarded[call.id]
                refused_edits.append(target)
                answer = guard.refusal(call.name, target, contract_id)
            else:
                internal_calls.append(call.name)
                answer = _answer_internal(call, unreadable, internal)
            history.append({"role": "tool", "tool_call_id": call.id, "content": answer})
        if theirs:
            names = ", ".join(sorted({call.name for call in theirs}))
            history[-1]["content"] += (
                f"\nNote: your call(s) to {names} were not forwarded to the "
                "harness this round; read the results above, then call them again."
            )
    stopped = RungReply(
        text=(
            f"{reply.text}\n\nmcorch stopped after {limits.max_rounds} internal "
            "rounds without a reply for the harness."
        ).strip(),
        tool_calls=(),
        truncated=reply.truncated,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
    )
    return Turn(
        reply=stopped,
        trace=_trace(
            intent,
            following,
            asked,
            dropped_tools,
            request,
            dropped_blocks,
            rounds,
            internal_calls,
            refused_edits,
        ),
    )


def _side(
    request: MessagesRequest,
    turns: tuple[dict[str, Any], ...],
    dropped_blocks: tuple[str, ...],
    *,
    rung: Rung,
    limits: Limits,
) -> Turn:
    reply = rung(
        RungCall(
            system=request.system,
            turns=turns,
            tools=(),
            max_output_tokens=min(request.max_tokens, limits.side_reply_tokens),
        )
    )
    return Turn(
        reply=RungReply(
            text=reply.text,
            tool_calls=(),
            truncated=reply.truncated,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
        ),
        trace=Trace(
            kind="side",
            intent=None,
            jev=(),
            dropped_tools=(),
            dropped_system_bytes=0,
            dropped_blocks=dropped_blocks,
            rounds=1,
            internal_calls=(),
            next=None,
        ),
    )


def _guarded(
    calls: Sequence[RungToolCall], targets: Mapping[str, str]
) -> dict[str, tuple[str, str]]:
    """Call id → (target, contract id) for every call that would edit an open target."""
    found: dict[str, tuple[str, str]] = {}
    if not targets:
        return found
    for call in calls:
        input_ = guard.arguments(call.arguments)
        if input_ is None:
            continue
        contract_id = guard.edits_open_target(call.name, input_, targets)
        if contract_id is None:
            continue
        target = next(t for t, c in targets.items() if c == contract_id)
        found[call.id] = (target, contract_id)
    return found


def _trace(
    intent: str | None,
    following: str | None,
    asked: Sequence[tuple[str, str]],
    dropped_tools: Sequence[str],
    request: MessagesRequest,
    dropped_blocks: Sequence[str],
    rounds: int,
    internal_calls: Sequence[str],
    refused_edits: Sequence[str] = (),
) -> Trace:
    return Trace(
        kind="main",
        intent=intent,
        jev=tuple(asked),
        dropped_tools=tuple(dropped_tools),
        dropped_system_bytes=len(request.system.encode("utf-8")),
        dropped_blocks=tuple(dropped_blocks),
        rounds=rounds,
        internal_calls=tuple(internal_calls),
        next=following,
        refused_edits=tuple(refused_edits),
    )


def _filter_tools(
    offered: Sequence[Mapping[str, Any]], keep: Sequence[str]
) -> tuple[tuple[Mapping[str, Any], ...], tuple[str, ...]]:
    if not keep:
        return tuple(offered), ()
    wanted = set(keep)
    kept = tuple(tool for tool in offered if tool.get("name") in wanted)
    dropped = tuple(
        str(tool.get("name")) for tool in offered if tool.get("name") not in wanted
    )
    return kept, dropped


def _latest_user_text(messages: Sequence[Mapping[str, Any]]) -> str | None:
    """The last message's text when it is a new user request, else ``None``.

    A user message made of tool results is the harness reporting, not the user
    asking; it carries no new request to classify.
    """
    last = messages[-1]
    if last.get("role") != "user":
        return None
    content = last.get("content")
    if isinstance(content, str):
        return content
    texts = [
        str(block.get("text", ""))
        for block in content or ()
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    results = any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content or ()
    )
    if results or not texts:
        return None
    return "\n".join(texts)


def _intent(
    messages: Sequence[Mapping[str, Any]],
    jev: Jev,
    asked: list[tuple[str, str]],
    notes: list[str],
) -> str | None:
    text = _latest_user_text(messages)
    if text is None:
        return None
    decision = jev({"request": text[:REQUEST_CHARS]}, {INTENT_NAME: INTENT})
    answer = decision.answers.get(INTENT_NAME)
    if not isinstance(answer, ChoiceAnswer):
        return None
    asked.append((INTENT_NAME, answer.choice))
    notes.append(
        f"Jev: this request is {answer.choice} (confidence {answer.confidence:.2f})."
    )
    return answer.choice


def _run_result(messages: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """A RunResult the latest user message carries as a tool result, or ``None``."""
    last = messages[-1]
    if last.get("role") != "user" or not isinstance(last.get("content"), list):
        return None
    for block in last["content"]:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
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
            continue
        if isinstance(parsed, dict) and all(key in parsed for key in guard.RESULT_KEYS):
            return parsed
    return None


def _next(
    messages: Sequence[Mapping[str, Any]],
    jev: Jev,
    asked: list[tuple[str, str]],
    notes: list[str],
) -> str | None:
    result = _run_result(messages)
    if result is None:
        return None
    attempts = result.get("attempts")
    findings: list[str] = []
    for attempt in attempts if isinstance(attempts, list) else ():
        if isinstance(attempt, dict):
            findings.extend(str(line) for line in attempt.get("findings") or ())
    if not findings:
        findings = [str(line) for line in result.get("findings") or ()]
    state = {
        "contract": result.get("contract"),
        "outcome": result.get("outcome"),
        "detail": result.get("detail", ""),
        "findings": findings,
    }
    decision = jev(state, {NEXT_NAME: NEXT})
    answer = decision.answers.get(NEXT_NAME)
    if not isinstance(answer, ChoiceAnswer):
        return None
    asked.append((NEXT_NAME, answer.choice))
    notes.append(
        f"Jev: the run of contract {result.get('contract')!r} came to "
        f"{result.get('outcome')!r}; next: {answer.choice} "
        f"(confidence {answer.confidence:.2f})."
    )
    return answer.choice


def _assistant_turn(text: str, calls: Sequence[RungToolCall]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": text,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ],
    }


def _answer_internal(
    call: RungToolCall, unreadable: set[str], internal: Sequence[Authoring]
) -> str:
    if call.id in unreadable:
        return (
            f"error: the arguments of your call to {call.name} were not JSON; "
            "call it again with a JSON object."
        )
    for strategy in internal:
        answer = strategy.handle(call)
        if answer is not None:
            return answer
    return f"error: no tool named {call.name!r} is offered."
