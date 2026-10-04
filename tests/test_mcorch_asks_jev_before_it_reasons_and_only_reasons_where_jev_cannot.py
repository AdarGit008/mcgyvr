"""mcorch asks Jev every bounded question and lets the rung reason only between them.

One HTTP request is one turn of the loop. Before the rung sees a new user
request, Jev says whether it is chat or work (J1); the rung reasons freely
only inside the room that answer leaves, and the answer reaches it as a
``Jev:`` note in its system prompt. After a ``mcgyvr run`` result comes back
through the harness, Jev is asked nothing: the "what comes next" question (J3)
is decommissioned until proven otherwise (lab issue #61 — it read at chance
on every Jev model measured), and the rung judges the result on its own, with
no ``Jev:`` note. A request that offers no
tools is a side request — a harness's title or summary call — answered by the
rung alone, short, with no Jev and no prompt replacement: nothing without a
harness behind it can drive the mcgyvr flow, so nothing is spent steering it.

The harness's system prompt is replaced by mcorch's own; the tools it offers
are kept only when named in the keep list; what was dropped is counted on the
trace, because a prompt that silently shrank is a prompt nobody can reason
about. Every id here is invented and no model is reached.
"""

from __future__ import annotations

import json

from mcgyvr.mcorch import loop
from mcgyvr.mcorch.anthropic import MessagesRequest
from tests.mcorch_fakes import ScriptedJev, ScriptedRung, calls, text

TOOLS: tuple[dict[str, object], ...] = (
    {"name": "Read", "description": "read", "input_schema": {"type": "object"}},
    {"name": "Bash", "description": "run", "input_schema": {"type": "object"}},
    {"name": "WebSearch", "description": "search", "input_schema": {"type": "object"}},
)
KEEP = ("Read", "Bash")
SYSTEM = "You are mcorch. {jev_notes}"


def _request(
    *messages: dict[str, object], tools: tuple[dict[str, object], ...] = TOOLS
) -> MessagesRequest:
    return MessagesRequest(
        model="mcorch",
        max_tokens=4000,
        messages=tuple(messages),
        system="x" * 20_000,
        tools=tools,
    )


def _turn(
    request: MessagesRequest,
    rung: ScriptedRung,
    jev: ScriptedJev,
) -> loop.Turn:
    return loop.respond(
        request,
        rung=rung,
        jev=jev,
        system=SYSTEM,
        keep_tools=KEEP,
        internal=(),
        limits=loop.Limits(max_rounds=3, side_reply_tokens=64),
    )


def test_a_new_request_is_classified_by_jev_before_the_rung_reasons() -> None:
    rung = ScriptedRung(text("Sure, formatting now."))
    jev = ScriptedJev(intent="work")
    turn = _turn(_request({"role": "user", "content": "format src/a.py"}), rung, jev)
    assert [name for name, _ in jev.asked] == ["intent"]
    assert jev.asked[0][1]["request"] == "format src/a.py"
    assert turn.trace.intent == "work"
    assert turn.trace.kind == "main"
    # The answer reaches the rung as a note, not as a hidden choice.
    assert "Jev:" in rung.calls[0].system
    assert "work" in rung.calls[0].system
    assert turn.reply.text == "Sure, formatting now."


def test_chat_is_still_answered_but_told_it_is_chat() -> None:
    rung = ScriptedRung(text("Hi."))
    jev = ScriptedJev(intent="chat")
    turn = _turn(_request({"role": "user", "content": "hello"}), rung, jev)
    assert turn.trace.intent == "chat"
    assert "chat" in rung.calls[0].system


RUN_RESULT = {
    "contract": "format-a",
    "task_type": "format",
    "target": "src/a.py",
    "orchestrator": "mcorch-x",
    "outcome": "rejected",
    "detail": "the gate refused",
    "attempts": [
        {"rung": "r", "attempt": 1, "verdict": "failed", "findings": ["lint: E501"]}
    ],
}

#: A conversation whose latest message is the harness reading a run result back.
RUN_RESULT_TURNS: tuple[dict[str, object], ...] = (
    {"role": "user", "content": "format src/a.py"},
    {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "Read",
                "input": {"file_path": "/x/results/format-a.json"},
            }
        ],
    },
    {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": json.dumps(RUN_RESULT),
            }
        ],
    },
)


def test_a_run_result_from_the_harness_is_not_put_to_jev_the_rung_judges_it() -> None:
    """J3 is decommissioned (lab issue #61): no question, no ``Jev:`` note.

    A ``ScriptedJev`` with no ``next`` answer raises the moment it is asked, so
    the loop asking J3 is a failure here, not a wrong answer.
    """
    rung = ScriptedRung(text("I will narrow the contract."))
    jev = ScriptedJev()
    turn = _turn(_request(*RUN_RESULT_TURNS), rung, jev)
    assert jev.asked == []
    assert turn.trace.next is None
    assert turn.trace.jev == ()
    assert turn.trace.intent is None  # a tool result is not a new request
    assert "Jev:" not in rung.calls[0].system
    assert turn.reply.text == "I will narrow the contract."


def test_a_new_request_after_a_run_result_still_asks_jev_its_intent() -> None:
    rung = ScriptedRung(text("Done."), text("Sure."))
    jev = ScriptedJev(intent="work")
    _turn(_request(*RUN_RESULT_TURNS), rung, jev)
    turn = _turn(
        _request(
            *RUN_RESULT_TURNS,
            {"role": "assistant", "content": "The run was refused; narrowing."},
            {"role": "user", "content": "also sort the imports in src/b.py"},
        ),
        rung,
        jev,
    )
    assert [name for name, _ in jev.asked] == ["intent"]
    assert jev.asked[0][1]["request"] == "also sort the imports in src/b.py"
    assert turn.trace.intent == "work"
    assert "Jev: this request is work" in rung.calls[1].system


def test_the_harness_system_prompt_is_replaced_and_tools_are_filtered() -> None:
    rung = ScriptedRung(text("ok"))
    jev = ScriptedJev(intent="work")
    turn = _turn(_request({"role": "user", "content": "do it"}), rung, jev)
    call = rung.calls[0]
    assert "x" * 100 not in call.system
    assert call.system.startswith("You are mcorch.")
    assert [tool["function"]["name"] for tool in call.tools] == ["Read", "Bash"]
    assert turn.trace.dropped_tools == ("WebSearch",)
    assert turn.trace.dropped_system_bytes == 20_000
    assert call.max_output_tokens == 4000


def test_an_empty_keep_list_keeps_every_tool() -> None:
    rung = ScriptedRung(text("ok"))
    turn = loop.respond(
        _request({"role": "user", "content": "do it"}),
        rung=rung,
        jev=ScriptedJev(intent="work"),
        system=SYSTEM,
        keep_tools=(),
        internal=(),
        limits=loop.Limits(max_rounds=3, side_reply_tokens=64),
    )
    assert len(rung.calls[0].tools) == 3
    assert turn.trace.dropped_tools == ()


def test_a_request_with_no_tools_is_a_side_request_the_rung_answers_alone() -> None:
    rung = ScriptedRung(text("A title"))
    jev = ScriptedJev()
    request = _request({"role": "user", "content": "name this conversation"}, tools=())
    turn = _turn(request, rung, jev)
    assert turn.trace.kind == "side"
    assert jev.asked == []
    call = rung.calls[0]
    assert call.system == request.system  # the harness's own words, untouched
    assert call.tools == ()
    assert call.max_output_tokens == 64
    assert turn.reply.text == "A title"
    assert turn.trace.dropped_system_bytes == 0


def test_a_harness_tool_call_ends_the_turn_and_is_handed_back() -> None:
    rung = ScriptedRung(calls(("Bash", '{"command": "mcgyvr contract c.yaml"}')))
    turn = _turn(
        _request({"role": "user", "content": "run it"}),
        rung,
        ScriptedJev(intent="work"),
    )
    assert len(rung.calls) == 1
    assert turn.reply.tool_calls[0].name == "Bash"
    assert turn.trace.rounds == 1


def test_unreadable_arguments_go_back_to_the_rung_not_to_the_harness() -> None:
    rung = ScriptedRung(
        calls(("Bash", "{not json")),
        calls(("Bash", '{"command": "ls"}')),
    )
    turn = _turn(
        _request({"role": "user", "content": "list"}), rung, ScriptedJev(intent="work")
    )
    assert len(rung.calls) == 2
    second = rung.calls[1]
    assert second.turns[-1]["role"] == "tool"
    assert "not JSON" in second.turns[-1]["content"]
    assert turn.reply.tool_calls[0].arguments == '{"command": "ls"}'
    assert turn.trace.rounds == 2


def test_the_internal_rounds_are_bounded() -> None:
    rung = ScriptedRung(*(calls(("Bash", "{bad")) for _ in range(5)))
    turn = _turn(
        _request({"role": "user", "content": "list"}), rung, ScriptedJev(intent="work")
    )
    assert len(rung.calls) == 3
    assert turn.reply.tool_calls == ()
    assert "3" in turn.reply.text
    assert turn.trace.rounds == 3
