"""hostos lets one holder at a time hold a lock file, on every system.

On POSIX a lock is ``flock``: a second holder, in another process, is refused
while the first holds it and gets it once released. On Windows it is
``msvcrt.locking`` of one byte far past the end, so the file's own bytes stay
readable, with the file position put back; a held lock is refused as a
``BlockingIOError`` the same way, and a blocking lock is tried again until had.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from mcgyvr import hostos
from tests.hostos_fakes import FakeMsvcrt, as_system

HOLDER = """
import os, sys
from mcgyvr import hostos
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
hostos.lock(fd)
print("held", flush=True)
sys.stdin.readline()
hostos.unlock(fd)
print("released", flush=True)
sys.stdin.readline()
"""


def _holder(path: Path) -> subprocess.Popen[str]:
    child = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "held"
    return child


def test_a_second_process_is_refused_until_the_first_releases(tmp_path: Path) -> None:
    path = tmp_path / "slot.lock"
    child = _holder(path)
    assert child.stdin is not None and child.stdout is not None
    fd = os.open(path, os.O_RDWR)
    try:
        with pytest.raises(BlockingIOError):
            hostos.lock(fd, blocking=False)
        child.stdin.write("\n")
        child.stdin.flush()
        assert child.stdout.readline().strip() == "released"
        hostos.lock(fd, blocking=False)
        hostos.unlock(fd)
    finally:
        os.close(fd)
        child.stdin.write("\n")
        child.stdin.close()
        child.wait(timeout=30)


def test_a_holder_that_dies_leaves_the_lock_free(tmp_path: Path) -> None:
    path = tmp_path / "slot.lock"
    child = _holder(path)
    child.kill()
    child.wait(timeout=30)
    fd = os.open(path, os.O_RDWR)
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                hostos.lock(fd, blocking=False)
                break
            except BlockingIOError:
                assert time.monotonic() < deadline, "the dead holder's lock stayed"
                time.sleep(0.05)
    finally:
        os.close(fd)


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> FakeMsvcrt:
    as_system(monkeypatch, "windows")
    fake = FakeMsvcrt()
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    return fake


@pytest.fixture
def journal(tmp_path: Path) -> Iterator[int]:
    fd = os.open(tmp_path / "journal", os.O_RDWR | os.O_CREAT, 0o600)
    os.write(fd, b"one line\n")
    os.lseek(fd, 3, os.SEEK_SET)
    yield fd
    os.close(fd)


def test_windows_locks_one_byte_past_the_end_and_puts_the_position_back(
    windows: FakeMsvcrt, journal: int
) -> None:
    hostos.lock(journal)
    hostos.unlock(journal)
    assert windows.calls == [
        (FakeMsvcrt.LK_NBLCK, hostos.WINDOWS_LOCK_AT, 1),
        (FakeMsvcrt.LK_UNLCK, hostos.WINDOWS_LOCK_AT, 1),
    ]
    assert os.lseek(journal, 0, os.SEEK_CUR) == 3


def test_windows_refuses_a_held_lock_as_posix_does(
    windows: FakeMsvcrt, journal: int
) -> None:
    windows.busy = 1
    with pytest.raises(BlockingIOError):
        hostos.lock(journal, blocking=False)
    assert os.lseek(journal, 0, os.SEEK_CUR) == 3


def test_windows_waits_for_a_held_lock_until_it_is_had(
    windows: FakeMsvcrt, journal: int
) -> None:
    windows.busy = 3
    hostos.lock(journal)
    assert len(windows.calls) == 4


def test_windows_raises_any_other_failure_as_it_is(
    windows: FakeMsvcrt, journal: int
) -> None:
    windows.error = errno.EBADF
    with pytest.raises(OSError) as raised:
        hostos.lock(journal)
    assert not isinstance(raised.value, BlockingIOError)
    assert raised.value.errno == errno.EBADF
