"""A reply streams as the Anthropic SSE events a harness reads, in their order.

Claude Code streams; so a facade must emit the Messages API's own event
sequence (``message_start``, then per content block ``content_block_start`` /
``content_block_delta`` / ``content_block_stop``, then ``message_delta`` with
the stop reason and the output count, then ``message_stop``), and a ``ping``
while it has nothing to say yet. The text behind the events is buffered — the
rung's reply is complete before the first event — and that is allowed: what a
reader depends on is the sequence and the shapes, not the pacing. A tool call
streams as a ``tool_use`` block whose input arrives as one ``input_json_delta``.
"""

from __future__ import annotations

import json

from mcgyvr.mcorch import anthropic
from mcgyvr.mcorch.wire import RungReply, RungToolCall


def _events(reply: RungReply) -> list[tuple[str, dict[str, object]]]:
    message = anthropic.message_from(reply, model="mcorch", message_id="msg_09")
    return [(name, json.loads(data)) for name, data in anthropic.events_for(message)]


def test_a_text_reply_streams_start_block_delta_and_stop_in_order() -> None:
    events = _events(RungReply(text="hello there", tool_calls=()))
    names = [name for name, _ in events]
    assert names == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    start = events[0][1]
    assert start["type"] == "message_start"
    message = start["message"]
    assert isinstance(message, dict)
    assert message["content"] == []
    assert message["stop_reason"] is None
    assert events[1][1]["content_block"] == {"type": "text", "text": ""}
    assert events[2][1]["delta"] == {"type": "text_delta", "text": "hello there"}
    delta = events[4][1]
    assert delta["delta"] == {"stop_reason": "end_turn", "stop_sequence": None}
    usage = delta["usage"]
    assert isinstance(usage, dict) and isinstance(usage["output_tokens"], int)
    assert events[5][1] == {"type": "message_stop"}


def test_a_tool_call_streams_as_a_tool_use_block_with_one_json_delta() -> None:
    events = _events(
        RungReply(
            text="",
            tool_calls=(
                RungToolCall(id="call_1", name="Bash", arguments='{"command": "ls"}'),
            ),
        )
    )
    names = [name for name, _ in events]
    assert names == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    block = events[1][1]["content_block"]
    assert isinstance(block, dict)
    assert block["type"] == "tool_use"
    assert block["name"] == "Bash"
    assert block["input"] == {}
    delta = events[2][1]["delta"]
    assert isinstance(delta, dict)
    assert delta["type"] == "input_json_delta"
    assert json.loads(str(delta["partial_json"])) == {"command": "ls"}
    assert events[4][1]["delta"] == {"stop_reason": "tool_use", "stop_sequence": None}


def test_every_event_carries_its_type_and_block_events_their_index() -> None:
    events = _events(
        RungReply(
            text="first",
            tool_calls=(RungToolCall(id="c", name="Read", arguments="{}"),),
        )
    )
    for name, data in events:
        assert data["type"] == name
    indexed = [
        data["index"] for name, data in events if name.startswith("content_block")
    ]
    assert indexed == [0, 0, 0, 1, 1, 1]


def test_the_wire_form_is_event_and_data_lines_ending_in_a_blank_line() -> None:
    wire = anthropic.sse("ping", {"type": "ping"})
    assert wire == b'event: ping\ndata: {"type": "ping"}\n\n'
    assert wire == anthropic.PING
