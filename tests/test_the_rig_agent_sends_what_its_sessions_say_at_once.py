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
import time
from typing import Any

from tests.rig_fake_hub import Peer, Server
from tests.test_a_rig_agent_says_hello_keeps_beating_and_backs_off_when_the_hub_drops import (  # noqa: E501
    Report,
)

#: How long a queued frame may take to reach the hub, in seconds: far below
#: the agent's one-second read, with room for a loaded test machine.
SENT_WITHIN_S = 0.1
#: How long after the agent is online the session speaks: well inside the
#: agent's first read of its channel.
SPEAKS_AFTER_S = 0.3


def test_a_frame_queued_while_the_agent_waits_on_the_hub_leaves_at_once() -> None:
    from mcgyvr.rig import agent, outbox, protocol, sessionwire, websocket

    arrived: list[tuple[float, str]] = []
    queued_at: list[float] = []
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
                    "body": {"rig_id": "r-1", "heartbeat_interval_s": 15},
                }
            )
        )
        said = peer.recv_text()
        arrived.append((time.monotonic(), said))
        peer.send_close(protocol.CloseCode.REVOKED, "done")
        peer.recv_frame()  # the agent's answer to the close

    box = outbox.Outbox()

    def session_speaks() -> None:
        time.sleep(SPEAKS_AFTER_S)
        queued_at.append(time.monotonic())
        assert box.put(status)

    speaker = threading.Thread(target=session_speaks)

    with Server(hub) as server:
        running = agent.Agent(
            connect=lambda: websocket.connect(
                server.url, headers={}, timeout=5.0, max_message=1 << 20
            ),
            read_hardware=Report(),
            agent_version="0.1.0",
            say=lambda line: None,
            outbox=box,
            on_online=speaker.start,
        )
        ended: Any = running.run()
        speaker.join()
    assert not server.failures, server.failures
    assert not ended.stopped  # the hub's close ended it, as the script says
    assert [said for _, said in arrived] == [status]
    assert arrived[0][0] - queued_at[0] < SENT_WITHIN_S
