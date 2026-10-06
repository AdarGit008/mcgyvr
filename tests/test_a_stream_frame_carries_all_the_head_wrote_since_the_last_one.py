"""A frame of a relayed answer carries all the head wrote since the last one.

The agent sends no more than its frame rate, for every relay of the rig
together, and a head writes each token as an event of its own. A frame per
event would make that rate a cap on tokens, shared by all the rig's streams.
So a relay's ``relay_data`` frame is filled when the agent takes it to send,
not when it is queued: it carries whatever the head wrote up to then, at most
the protocol's chunk, and one frame of a relay waits at a time. The first
event waits for nothing (its frame is queued as it is read, and sent at
once when the agent has room), the bytes reach the hub unchanged and in
order, and a relay whose full frame waits stops reading its head, which is
the backpressure a full outbox was.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests import rig_schema
from tests.test_a_lending_agent_offers_in_its_hello_and_sends_what_its_sessions_say_within_the_rate import (  # noqa: E501
    _made,
)
from tests.test_a_relayed_request_reaches_only_the_heads_loopback_api_and_streams_back_within_credit import (  # noqa: E501
    Head,
    Heads,
    _body,
    _serve,
)
from tests.test_a_rig_agent_says_hello_keeps_beating_and_backs_off_when_the_hub_drops import (  # noqa: E501
    Clock,
    Hub,
)


class Held:
    """An outbox whose frames wait until the test takes them, as they wait
    for the agent's rate: a frame is made only when it is taken."""

    def __init__(self) -> None:
        self.waiting: list[str | Callable[[], str]] = []
        self.changed = threading.Condition()

    def put(self, frame: str | Callable[[], str], timeout: float | None = None) -> bool:
        with self.changed:
            self.waiting.append(frame)
            self.changed.notify_all()
        return True

    def take(self, timeout: float = 5.0) -> dict[str, Any]:
        """The next frame, as the agent would send it now."""
        with self.changed:
            assert self.changed.wait_for(lambda: bool(self.waiting), timeout)
            frame = self.waiting.pop(0)
        message: dict[str, Any] = json.loads(
            frame if isinstance(frame, str) else frame()
        )
        rig_schema.validate(message, rig_schema.load(), "#/$defs/AgentMessage")
        return message

    def until(self, kind: str, timeout: float = 5.0) -> None:
        """Wait until a frame of ``kind`` waits (one already made: a string)."""

        def there() -> bool:
            return any(
                isinstance(f, str) and json.loads(f)["type"] == kind
                for f in self.waiting
            )

        with self.changed:
            assert self.changed.wait_for(there, timeout)


@pytest.fixture
def held() -> Iterator[tuple[Head, Held, Any]]:
    from mcgyvr.rig import commands, relay

    head = Head(content_type="text/event-stream")
    head.server = _serve(head)
    box = Held()
    relays = relay.Relays(heads=Heads(head.port), send=box.put)
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, relays)
    yield head, box, dispatcher
    relays.cancel_all()
    head.server.shutdown()


def _ask(dispatcher: Any, body: bytes, **changes: Any) -> None:
    from tests import rig_pool_fakes as fakes

    fields: dict[str, Any] = {
        "session_id": "s1",
        "request_id": "q1",
        "endpoint": "chat_completions",
        "body_bytes": len(body),
        "stream": True,
        "timeout_s": 10,
        "max_response_bytes": 1 << 20,
        "window": 8,
    }
    fields.update(changes)
    assert (
        dispatcher.dispatch(fakes.frame("relay_request", "r1", **fields), fakes.Stub())
        is None
    )
    assert (
        dispatcher.dispatch(
            fakes.frame(
                "relay_data",
                "d0",
                request_id="q1",
                seq=0,
                data_b64=base64.b64encode(body).decode(),
            ),
            fakes.Stub(),
        )
        is None
    )


def _raw(frame: dict[str, Any]) -> bytes:
    assert frame["type"] == "relay_data"
    return base64.b64decode(frame["body"]["data_b64"])


def test_a_frame_that_waited_carries_every_event_the_head_wrote_meanwhile(
    held: tuple[Head, Held, Any],
) -> None:
    head, box, dispatcher = held
    head.chunks = [f"data: token {i}\n\n".encode() for i in range(40)]
    head.pause_s = 0.002
    _ask(dispatcher, _body())
    box.until("relay_end")  # the head wrote it all while no frame was taken
    assert box.take()["type"] == "relay_response"
    data = box.take()
    assert data["body"]["seq"] == 0
    assert _raw(data) == b"".join(head.chunks)  # one frame, unchanged, in order
    assert box.take()["body"] == {"request_id": "q1", "outcome": "complete"}
    assert not box.waiting


def test_frames_taken_as_the_head_writes_carry_the_bytes_in_order_numbered_from_0(
    held: tuple[Head, Held, Any],
) -> None:
    head, box, dispatcher = held
    head.chunks = [f"data: token {i}\n\n".encode() for i in range(60)]
    head.pause_s = 0.002
    _ask(dispatcher, _body(), window=64)
    assert box.take()["type"] == "relay_response"
    frames = []
    while (frame := box.take())["type"] == "relay_data":
        frames.append(frame)
        time.sleep(0.01)  # the agent's rate: several events are written meanwhile
    assert frame["body"]["outcome"] == "complete"
    assert [f["body"]["seq"] for f in frames] == list(range(len(frames)))
    assert b"".join(_raw(f) for f in frames) == b"".join(head.chunks)
    assert len(frames) < len(head.chunks)  # fewer frames than events
    assert _raw(frames[0]).startswith(head.chunks[0])


def test_a_frame_is_never_over_the_protocols_chunk_and_a_full_one_holds_the_head(
    held: tuple[Head, Held, Any],
) -> None:
    from mcgyvr.rig import sessionwire

    head, box, dispatcher = held
    limit = sessionwire.RELAY_MAX_CHUNK_BYTES
    answer = bytes(range(256)) * ((3 * limit + 7) // 256 + 1)
    answer = answer[: 3 * limit + 7]
    head.chunks = [answer]
    _ask(dispatcher, _body(), window=64, max_response_bytes=8 * limit)
    assert box.take()["type"] == "relay_response"
    frames = []
    while True:
        time.sleep(0.05)  # time to read past the chunk, were nothing to stop it
        frame = box.take()
        if frame["type"] != "relay_data":
            break
        with box.changed:  # one frame of a relay waits at a time
            assert sum(1 for f in box.waiting if not isinstance(f, str)) <= 1
        frames.append(frame)
    assert frame["body"]["outcome"] == "complete"
    assert all(0 < len(_raw(f)) <= limit for f in frames)
    assert b"".join(_raw(f) for f in frames) == answer


def test_the_agent_makes_a_waiting_frame_when_it_sends_it() -> None:
    from mcgyvr.rig import outbox, sessionwire

    clock = Clock()
    box = outbox.Outbox()
    written = [b"data: one\n\n"]

    def frame() -> str:
        return sessionwire.relay_data("q1", seq=0, data=b"".join(written))

    def online() -> None:
        assert box.put(frame)
        written.append(b"data: two\n\n")  # written after the frame was queued

    agent, channels = _made(
        [Hub(interval=15, beats=1)], clock, outbox=box, on_online=online
    )
    agent.run()
    (data,) = [m for _, m in channels[0].sent if m["type"] == "relay_data"]
    assert _raw(data) == b"data: one\n\ndata: two\n\n"
