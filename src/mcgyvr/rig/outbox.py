"""The frames the agent's sessions and relays send on their own, waiting their turn.

A command's answer is sent when its handler returns; everything else a
session or a relay says (a session became ready, a relayed answer's chunks,
its end) is said later, from a thread of its own, and goes here. The agent
takes frames out between reads of its channel, at no more than its frame
rate (:mod:`mcgyvr.rig.agent`); a put wakes the agent from a read that waits
(the ``wake`` the box is opened with), so a frame goes out at once rather than
when the read's timeout ends.

The box is bounded, and a put waits while it is full: a relay that streams
faster than the channel carries stops reading its upstream, which is the
backpressure. While the channel is down the box is closed: a put is refused
at once and what was waiting is dropped, since it was said to a hub that is
no longer listening (the hub asks again after a reconnect).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

#: How many frames wait at most before a put waits too.
CAPACITY = 256


class Outbox:
    """A bounded, closable queue of frames to send."""

    def __init__(self, capacity: int = CAPACITY) -> None:
        self._frames: deque[str] = deque()
        self._capacity = capacity
        self._open = False
        self._changed = threading.Condition()
        self._wake: Callable[[], None] | None = None

    def open(self, wake: Callable[[], None] | None = None) -> None:
        """Take frames: the channel is up. ``wake`` is called after each put,
        outside the box's lock, to have the sender send at once."""
        with self._changed:
            self._open = True
            self._wake = wake
            self._changed.notify_all()

    def close(self) -> None:
        """Refuse frames and drop those waiting: the channel is down."""
        with self._changed:
            self._open = False
            self._wake = None
            self._frames.clear()
            self._changed.notify_all()

    def is_open(self) -> bool:
        """Whether a frame put now would be sent."""
        with self._changed:
            return self._open

    def put(self, frame: str, timeout: float | None = None) -> bool:
        """Queue ``frame``; ``False`` when the box is closed, or stayed full
        for ``timeout`` seconds."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._changed:
            while self._open and len(self._frames) >= self._capacity:
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    return False
                self._changed.wait(left)
            if not self._open:
                return False
            self._frames.append(frame)
            self._changed.notify_all()
            wake = self._wake
        if wake is not None:
            wake()
        return True

    def take(self) -> str | None:
        """The next frame to send, or ``None``."""
        with self._changed:
            if not self._frames:
                return None
            frame = self._frames.popleft()
            self._changed.notify_all()
            return frame

    def pending(self) -> bool:
        """Whether a frame waits."""
        with self._changed:
            return bool(self._frames)
