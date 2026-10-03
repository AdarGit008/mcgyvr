"""The rig websocket client's read ends at once when another thread wakes it.

The agent reads its channel with a timeout so it hears a stop, and empties
its outbox between reads. A frame a session queues while the agent waits on
the channel must not wait out that timeout: :meth:`WebSocket.wake`, safe to
call from any thread, ends a read that waits now (or the next one, when none
does) at once with ``None``. A wake loses nothing: a message the server sends
is still read whole, and a wake after the channel is closed is harmless.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from tests.rig_fake_hub import Peer, Server

#: How long a woken read may take to end, in seconds: far below the read's
#: own timeout, with room for a loaded test machine.
WOKEN_WITHIN_S = 0.1


def _connect(server: Server) -> Any:
    from mcgyvr.rig import websocket

    return websocket.connect(server.url, headers={}, timeout=5.0, max_message=1024)


def _hold(release: threading.Event, then: str | None = None) -> Any:
    def script(peer: Peer) -> None:
        peer.handshake()
        release.wait(10)
        if then is not None:
            peer.send_text(then)
        peer.recv_frame()  # the client's close

    return script


def test_a_read_that_waits_ends_at_once_when_woken_from_another_thread() -> None:
    release = threading.Event()
    with Server(_hold(release)) as server:
        ws = _connect(server)
        woken_at: list[float] = []

        def wake() -> None:
            time.sleep(0.2)
            woken_at.append(time.monotonic())
            ws.wake()

        waker = threading.Thread(target=wake)
        waker.start()
        assert ws.receive(timeout=5.0) is None
        ended_at = time.monotonic()
        waker.join()
        assert ended_at - woken_at[0] < WOKEN_WITHIN_S
        release.set()
        ws.close()
    assert not server.failures, server.failures


def test_a_wake_before_a_read_ends_that_read_and_loses_no_message() -> None:
    release = threading.Event()
    with Server(_hold(release, then="still here")) as server:
        ws = _connect(server)
        ws.wake()
        started = time.monotonic()
        assert ws.receive(timeout=5.0) is None
        assert time.monotonic() - started < WOKEN_WITHIN_S
        release.set()
        assert ws.receive(timeout=5.0) == "still here"
        ws.close()
        ws.wake()  # closed: harmless
    assert not server.failures, server.failures
