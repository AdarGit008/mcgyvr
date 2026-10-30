"""hostos starts a child at the head of its own group and ends it with all it started.

POSIX: a new session, ``killpg`` with ``SIGKILL`` or the signal passed on,
and ``SIGTERM``/``SIGHUP`` to stop an agent. Windows: a new console process
group, ``taskkill /F /T`` by full path then the leader itself,
``CTRL_BREAK_EVENT`` to the group, and ``SIGBREAK`` for ``SIGHUP``. A test of
POSIX's own calls is skipped on a real Windows, which has none of them.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hostos
from tests.hostos_fakes import (
    CTRL_BREAK_EVENT,
    NEW_PROCESS_GROUP,
    SIGBREAK,
    as_system,
)

linux = pytest.mark.skipif(sys.platform != "linux", reason="reads /proc")
posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX calls")


class _Child:
    """A started child as hostos sees it: a pid, and what was done to it."""

    pid = 4242

    def __init__(self) -> None:
        self.done: list[Any] = []

    def kill(self) -> None:
        self.done.append("kill")

    def send_signal(self, signum: int) -> None:
        self.done.append(signum)


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return True
    return state in ("Z", "X")


def test_posix_starts_a_child_in_a_session_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "linux")
    assert hostos.popen_group_kwargs() == {"start_new_session": True}


def test_windows_starts_a_child_in_a_console_group_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "windows")
    assert hostos.popen_group_kwargs() == {"creationflags": NEW_PROCESS_GROUP}


@linux
def test_posix_kills_the_child_and_what_it_started() -> None:
    leader = subprocess.Popen(
        ["sh", "-c", "sleep 60 & echo $!; wait"],
        stdout=subprocess.PIPE,
        text=True,
        **hostos.popen_group_kwargs(),
    )
    assert leader.stdout is not None
    started = int(leader.stdout.readline())
    hostos.kill_group(leader)
    leader.wait(timeout=30)
    leader.stdout.close()
    deadline = time.monotonic() + 10
    while not _gone(started):
        assert time.monotonic() < deadline, "the child's own child outlived the kill"
        time.sleep(0.05)


@posix
def test_posix_passes_a_signal_to_the_whole_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "linux")
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: sent.append((pid, sig)))
    child = _Child()
    hostos.signal_group(child, signal.SIGTERM)  # type: ignore[arg-type]
    hostos.kill_group(child)  # type: ignore[arg-type]
    assert sent == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]


@pytest.mark.parametrize("taskkill", ["answers", "cannot run"])
def test_windows_ends_the_tree_by_taskkill_then_the_leader_itself(
    taskkill: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    ran: list[list[str]] = []

    def run(argv: list[str], **_kwargs: Any) -> None:
        ran.append(argv)
        if taskkill == "cannot run":
            raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", run)
    child = _Child()
    hostos.kill_group(child)  # type: ignore[arg-type]
    named = os.path.join(r"C:\Windows", "System32", "taskkill.exe")
    assert ran == [[named, "/F", "/T", "/PID", "4242"]]
    assert child.done == ["kill"]


def test_windows_passes_a_break_to_the_group(monkeypatch: pytest.MonkeyPatch) -> None:
    as_system(monkeypatch, "windows")
    child = _Child()
    hostos.signal_group(child, signal.SIGTERM)  # type: ignore[arg-type]
    assert child.done == [CTRL_BREAK_EVENT]


@posix
def test_an_agent_stops_on_term_and_hup_on_posix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "linux")
    assert hostos.stop_signals() == (signal.SIGTERM, signal.SIGHUP)


def test_an_agent_stops_on_term_and_break_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "windows")
    assert hostos.stop_signals() == (signal.SIGTERM, SIGBREAK)
