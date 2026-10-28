"""Hold what one thread writes to stdout and stderr, and write it out whole.

Under `delegate --run --jobs N` several runs share one process and its two
streams, and a run's narrative is many `print` calls: unheld, the lines of two
runs would interleave, and a line of one could be cut by the other's. Inside
`routed()`, `sys.stdout` and `sys.stderr` are routers: a thread inside
`held()` keeps what it writes, in the order it wrote it across both streams,
and writes it all in one go, under one lock, when its block ends; every other
thread's writes go through a whole line at a time under the same lock, so no
held block lands inside one of its lines. Outside `routed()` nothing is
replaced and `held()` holds nothing, so a single run writes as it always has.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TextIO, cast


class _Routed:
    """What `routed()` shares between its two routers: one lock, who is held."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        #: Per thread, the (stream, text) chunks a held thread wrote, or None.
        self.held = threading.local()


class _Router:
    """A stand-in for one stream that holds a held thread's writes."""

    def __init__(self, real: TextIO, routed: _Routed) -> None:
        self.real = real
        self.routed = routed
        #: Per thread ident, the text written after its last newline.
        self._pending: dict[int, str] = {}

    def write(self, text: str) -> int:
        chunks: list[tuple[TextIO, str]] | None = getattr(
            self.routed.held, "chunks", None
        )
        if chunks is not None:
            chunks.append((self.real, text))
            return len(text)
        me = threading.get_ident()
        with self.routed.lock:
            pending = self._pending.pop(me, "") + text
            cut = pending.rfind("\n") + 1
            if cut:
                self.real.write(pending[:cut])
            if pending[cut:]:
                self._pending[me] = pending[cut:]
        return len(text)

    def flush(self) -> None:
        if getattr(self.routed.held, "chunks", None) is not None:
            return
        with self.routed.lock:
            pending = self._pending.pop(threading.get_ident(), "")
            if pending:
                self.real.write(pending)
            self.real.flush()

    def drain(self) -> None:
        """Write what every thread left after its last newline, and flush."""
        with self.routed.lock:
            for pending in self._pending.values():
                self.real.write(pending)
            self._pending.clear()
            self.real.flush()

    def __getattr__(self, name: str) -> Any:
        # `encoding`, `isatty`, `fileno` and the rest are the real stream's.
        return getattr(self.real, name)


@contextmanager
def routed() -> Iterator[None]:
    """Route `sys.stdout` and `sys.stderr` through routers for the block."""
    shared = _Routed()
    out, err = sys.stdout, sys.stderr
    routers = (_Router(out, shared), _Router(err, shared))
    sys.stdout, sys.stderr = (cast(TextIO, r) for r in routers)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = out, err
        for router in routers:
            router.drain()


@contextmanager
def held() -> Iterator[None]:
    """Hold what this thread writes for the block, then write it out whole.

    Inside `routed()` only; elsewhere the block writes as it would without.
    What was held is written even when the block raises.
    """
    router = sys.stdout
    if not isinstance(router, _Router):
        yield
        return
    shared = router.routed
    chunks: list[tuple[TextIO, str]] = []
    shared.held.chunks = chunks
    try:
        yield
    finally:
        shared.held.chunks = None
        with shared.lock:
            for stream, text in chunks:
                stream.write(text)
            for stream in {id(s): s for s, _ in chunks}.values():
                stream.flush()
