""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from mcgyvr.decision import Choice, ChoiceAnswer
from mcgyvr.mcorch import anthropic, evidence, guard
from mcgyvr.mcorch.anthropic import MessagesRequest
from mcgyvr.mcorch.authoring import GATHER, Authoring, Evidenced
from mcgyvr.mcorch.wire import Jev, Rung, RungCall, RungReply, RungToolCall

#
#
#
MAX_ROUNDS = 6

#
#
SIDE_REPLY_TOKENS = 512

#
#
REQUEST_CHARS = 2000

#
INTENT = Choice(
    "Is this request work for the repository — a change to make, a file to "
    "produce, a bug to fix — or conversation?",
    options={
        "work": "work: the user wants a change made in the repository",
        "chat": "chat: a question, a discussion, or an answer that changes nothing",
    },
)

#
#
#
#
NEXT = Choice(
    "A mcgyvr run came to this result. What should the orchestrator do next?",
    options={
        "done": "done: the work landed or nothing is left to do; report to the user",
        "replan": "replan: write a different contract from the findings",
        "ask_user": "ask_user: the result needs a decision only the user can make",
    },
)

#
INTENT_NAME = "intent"
NEXT_NAME = "next"


@dataclass(frozen=True)
class Limits:
    ""

    max_rounds: int = MAX_ROUNDS
    side_reply_tokens: int = SIDE_REPLY_TOKENS


@dataclass(frozen=True)
class Trace:
    ""

    kind: Literal["main", "side"]
    intent: str | None
    jev: tuple[tuple[str, str], ...]
    dropped_tools: tuple[str, ...]
    dropped_system_bytes: int
    dropped_blocks: tuple[str, ...]
    rounds: int
    internal_calls: tuple[str, ...]
    #
    #
    next: str | None
    #
    refused_edits: tuple[str, ...] = ()
    #
    #
    #
    evidence: str | None = None
    #
    contracts: int = 0


@dataclass(frozen=True)
class Turn:
    ""

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
    ""
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
    #
    #
    following = None
    prompt = system.replace("{jev_notes}", "\n".join(notes))

    rounds = 0
    internal_calls: list[str] = []
    refused_edits: list[str] = []
    targets = guard.open_targets(request.messages)
    history = list(turns)

    #
    #
    #
    #
    evidenced = next((s for s in internal if isinstance(s, Evidenced)), None)
    gathered: str | None = None
    contracts = 0
    if evidenced is not None:
        latest = evidence.latest_result(request.messages)
        if latest is not None:
            document = evidence.parse_document(latest.text)
            if document is None:
                digest = _UNREADABLE
                gathered = "unreadable"
            else:
                digest = evidenced.propose(
                    document, max_output_tokens=request.max_tokens
                )
                contracts = digest.count(_READY)
                gathered = "used"
            _replace_tool_turn(history, latest.tool_use_id, digest)
        elif intent == "work" and not evidence.gathered_since_request(request.messages):
            return _gather(
                _latest_user_text(request.messages) or "",
                request,
                evidenced,
                intent,
                asked,
                dropped_tools,
                dropped_blocks,
            )
        #
        #
        for tool_use_id in evidence.read_calls(request.messages):
            if latest is None or tool_use_id != latest.tool_use_id:
                _replace_tool_turn(history, tool_use_id, _ALREADY_READ)
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
                    gathered,
                    contracts,
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
                if answer.startswith(GATHER) and evidenced is not None:
                    return _gather(
                        answer.removeprefix(GATHER),
                        request,
                        evidenced,
                        intent,
                        asked,
                        dropped_tools,
                        dropped_blocks,
                    )
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
            gathered,
            contracts,
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
    ""
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


#
_READY = "ready: contract "

_UNREADABLE = (
    "refused: the read's result could not be read as one whole document — a "
    "harness cuts a long result short. Have the harness run the same "
    "`mcgyvr read` command again with a smaller shortlist: add `--limit 3`."
)

_ALREADY_READ = (
    "(the repository was read here; the proposals that followed were acted on)"
)


def _replace_tool_turn(
    history: list[dict[str, Any]], tool_call_id: str, content: str
) -> None:
    for turn in history:
        if turn.get("role") == "tool" and turn.get("tool_call_id") == tool_call_id:
            turn["content"] = content


def _gather(
    request_text: str,
    request: MessagesRequest,
    evidenced: Authoring,
    intent: str | None,
    asked: Sequence[tuple[str, str]],
    dropped_tools: Sequence[str],
    dropped_blocks: Sequence[str],
) -> Turn:
    ""
    shell = evidence.shell_tool(request.tools)
    if shell is None:
        reply = RungReply(
            text=(
                f"mcorch: `orchestrator.authoring: {evidenced.name}` reads the "
                "repository through the harness's shell tool, and this harness "
                f"offers none ({' or '.join(evidence.SHELL_TOOLS)}). Offer one, or "
                "set `orchestrator.authoring: direct`."
            ),
            tool_calls=(),
        )
        gathered = "no-shell"
    else:
        reply = RungReply(
            text="",
            tool_calls=(
                RungToolCall(
                    id=anthropic.new_id("call"),
                    name=shell,
                    arguments=json.dumps({"command": evidence.command(request_text)}),
                ),
            ),
        )
        gathered = "asked"
    return Turn(
        reply=reply,
        trace=_trace(
            intent,
            None,
            asked,
            dropped_tools,
            request,
            dropped_blocks,
            0,
            (),
            (),
            gathered,
            0,
        ),
    )


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
    gathered: str | None = None,
    contracts: int = 0,
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
        evidence=gathered,
        contracts=contracts,
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
    ""
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
    ""
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
    ""
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
