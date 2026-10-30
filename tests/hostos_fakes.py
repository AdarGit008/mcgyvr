"""What a test needs to see, on one system, what ``mcgyvr.hostos`` does on another.

``hostos`` decides everything from ``sys.platform`` when called, so faking a
system is setting that, plus the few names the standard library defines only
on Windows (given their Windows values) and a stand-in for ``msvcrt``.
"""

from __future__ import annotations

import errno
import os
import signal
import subprocess
import sys

import pytest

#: Each system ``hostos.os_name`` answers, by the ``sys.platform`` it reads.
PLATFORMS = {"linux": "linux", "darwin": "darwin", "windows": "win32"}
#: The Windows values of the names the standard library defines there alone.
NEW_PROCESS_GROUP = 0x200
CTRL_BREAK_EVENT = 1
SIGBREAK = 21


def as_system(monkeypatch: pytest.MonkeyPatch, system: str) -> None:
    """Make ``hostos`` (and the clones of it) see `system` for this test."""
    monkeypatch.setattr(sys, "platform", PLATFORMS[system])
    if system == "windows":
        monkeypatch.setattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", NEW_PROCESS_GROUP, raising=False
        )
        monkeypatch.setattr(signal, "CTRL_BREAK_EVENT", CTRL_BREAK_EVENT, raising=False)
        monkeypatch.setattr(signal, "SIGBREAK", SIGBREAK, raising=False)


class FakeMsvcrt:
    """``msvcrt.locking`` as Windows answers it, recording every call.

    `busy` is how many more lock tries find the byte held by another handle;
    `error` is an errno every call fails with instead, when set.
    """

    LK_UNLCK = 0
    LK_LOCK = 1
    LK_NBLCK = 2

    def __init__(self, busy: int = 0, error: int | None = None) -> None:
        self.busy = busy
        self.error = error
        self.calls: list[tuple[int, int, int]] = []

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        self.calls.append((mode, os.lseek(fd, 0, os.SEEK_CUR), nbytes))
        if self.error is not None:
            raise OSError(self.error, os.strerror(self.error))
        if mode == self.LK_NBLCK and self.busy:
            self.busy -= 1
            raise OSError(errno.EACCES, "Permission denied")
