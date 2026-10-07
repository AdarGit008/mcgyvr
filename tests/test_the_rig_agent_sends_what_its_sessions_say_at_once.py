"""The rig agent sends what its sessions say at once, not at its next read.

Between frames from the hub the agent waits on its channel, up to a second at
a time so it hears a stop. A session or relay that queues a frame in the
outbox meanwhile (a relayed answer's chunk, a session become ready) wakes the
agent, which sends the frame at once rather than when that wait ends: a
relayed answer's first token and every chunk after it go out as they come,
not in bursts a second apart. The read's timeout stays only as the fallback.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any

import pytest

from tests.rig_fake_hub import Peer, Server
from tests.test_a_rig_agent_says_hello_keeps_beating_and_backs_off_when_the_hub_drops import (  # noqa: E501
    Report,
)

if TYPE_CHECKING:
    from mcgyvr.rig.agent import Channel

#: How long the agent's read of its channel lasts in this test, in seconds:
#: far past the fake hub's patience (its socket gives up after 10 s), so a
#: frame that reaches the hub at all was sent by the put's wake, not by the
#: read's end. Measured by what arrived, not by a clock on a busy machine.
READ_LASTS_S = 600.0
#: The heartbeat interval the hub grants, in seconds: the protocol's largest,
#: so no heartbeat (nor the read begun ahead of one) cuts the read short.
BEAT_EVERY_S = 3600


class _Watched:
    """The agent's channel, telling the test each time a read begins."""

    def __init__(self, inner: Channel, reading: threading.Event) -> None:
        self._inner = inner
        self._reading = reading
        self.reads: list[float] = []  # each read's timeout, in order

    def receive(self, timeout: float) -> str | bytes | None:
        self.reads.append(timeout)
        self._reading.set()
        return self._inner.receive(timeout)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_a_frame_queued_while_the_agent_waits_on_the_hub_leaves_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.rig import agent, outbox, protocol, sessionwire, websocket

    monkeypatch.setattr(agent, "RECEIVE_SLICE_S", READ_LASTS_S)
    arrived: list[str] = []
    status = sessionwire.session_status(None, session_id="s1", state="ready")

    def hub(peer: Peer) -> None:
        peer.handshake()
        hello = json.loads(peer.recv_text())
        peer.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "ack",
                    "id": protocol.new_id(),
                    "re": hello["id"],
                    "body": {"rig_id": "r-1", "heartbeat_interval_s": BEAT_EVERY_S},
                }
            )
        )
        try:
            arrived.append(peer.recv_text())  # its socket gives up after 10 s
        finally:  # and the agent is ended either way, never left to retry
            peer.send_close(protocol.CloseCode.REVOKED, "done")
            peer.recv_frame()  # the agent's answer to the close

    box = outbox.Outbox()
    reading = threading.Event()  # set as each read of the channel begins
    queued_in: list[float] = []  # the timeout of the read the frame was put in
    channels: list[_Watched] = []

    def session_speaks() -> None:
        # Once the agent, online, is waiting on the hub: the read it is in
        # lasts far longer than the hub waits, so only the wake can send it.
        assert reading.wait(timeout=10.0), "the agent never read its channel"
        queued_in.append(channels[0].reads[-1])
        assert box.put(status)

    speaker = threading.Thread(target=session_speaks)

    def online() -> None:
        reading.clear()  # the reads that waited for the hello's ack are past
        speaker.start()

    def connect() -> _Watched:
        channel = _Watched(
            websocket.connect(server.url, headers={}, timeout=5.0, max_message=1 << 20),
            reading,
        )
        channels.append(channel)
        return channel

    with Server(hub) as server:
        running = agent.Agent(
            connect=connect,
            read_hardware=Report(),
            agent_version="0.1.0",
            say=lambda line: None,
            outbox=box,
            on_online=online,
        )
        ended: Any = running.run()
        speaker.join()
    assert not server.failures, server.failures
    assert not ended.stopped  # the hub's close ended it, as the script says
    assert queued_in and queued_in[0] > 10.0, queued_in  # past the hub's patience
    assert arrived == [status]
