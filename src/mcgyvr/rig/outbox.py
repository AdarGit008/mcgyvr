""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

#
CAPACITY = 256

#
type Frame = str | Callable[[], str]


class Outbox:
    ""

    def __init__(self, capacity: int = CAPACITY) -> None:
        self._frames: deque[Frame] = deque()
        self._capacity = capacity
        self._open = False
        self._changed = threading.Condition()
        self._wake: Callable[[], None] | None = None

    def open(self, wake: Callable[[], None] | None = None) -> None:
        ""
        with self._changed:
            self._open = True
            self._wake = wake
            self._changed.notify_all()

    def close(self) -> None:
        ""
        with self._changed:
            self._open = False
            self._wake = None
            self._frames.clear()
            self._changed.notify_all()

    def put(self, frame: Frame, timeout: float | None = None) -> bool:
        ""
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
        ""
        with self._changed:
            if not self._frames:
                return None
            frame = self._frames.popleft()
            self._changed.notify_all()
            return frame

    def pending(self) -> bool:
        ""
        with self._changed:
            return bool(self._frames)
