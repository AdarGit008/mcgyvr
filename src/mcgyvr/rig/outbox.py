"""The bounded queue of frames an agent's sessions hand to its one sending thread.

An agent owns a single websocket, so everything a session says — a relayed
answer, a session become ready, a stream chunk — is put here instead of being
sent from the session's own thread. :class:`Outbox` is that hand-off: a
`threading.Condition`-guarded deque that `put` fills and blocks on when full,
`take` empties one frame at a time, and `open`/`close` gate around a live
session. The `wake` callback given to `open` lets a producer interrupt the
sending thread's wait on a read, so a frame queued between reads goes out at
once.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

#: How many frames the queue holds before `put` waits for the sender to make room.
CAPACITY = 256

#: A queued frame: text ready to send, or a thunk rendered when the sender takes it.
type Frame = str | Callable[[], str]


class Outbox:
    """A thread-safe, capacity-bounded queue of frames, closed until opened.

    Frames are dropped, not kept, while the outbox is closed: a session that
    puts to a closed outbox is told so, and `close` empties whatever was still
    queued.
    """

    def __init__(self, capacity: int = CAPACITY) -> None:
        self._frames: deque[Frame] = deque()
        self._capacity = capacity
        self._open = False
        self._changed = threading.Condition()
        self._wake: Callable[[], None] | None = None

    def open(self, wake: Callable[[], None] | None = None) -> None:
        """Open the outbox for a session, calling `wake` after each frame is put.

        `wake` is the sending thread's way out of a blocking read; the caller
        passes the channel's own wake here.
        """
        with self._changed:
            self._open = True
            self._wake = wake
            self._changed.notify_all()

    def close(self) -> None:
        """Close the outbox and drop the frames still queued, releasing any waiters."""
        with self._changed:
            self._open = False
            self._wake = None
            self._frames.clear()
            self._changed.notify_all()

    def put(self, frame: Frame, timeout: float | None = None) -> bool:
        """Queue a frame and return whether it was queued.

        While the outbox is open and full, wait for the sender to take one:
        `timeout` seconds at most, or forever when it is None. Return False if
        the outbox is closed, or if the wait ran out — the frame is then
        dropped rather than the producer blocking. `wake` is called outside the
        lock so the sending thread is not woken while this one holds it.
        """
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

    def take(self) -> Frame | None:
        """Take the oldest frame, or None when the outbox holds none."""
        with self._changed:
            if not self._frames:
                return None
            frame = self._frames.popleft()
            self._changed.notify_all()
            return frame

    def pending(self) -> bool:
        """Return whether any frame is waiting, so the sender need not block on
        a read."""
        with self._changed:
            return bool(self._frames)
