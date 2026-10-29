"""hostos starts a child at the head of its own group and ends it with all it started.

POSIX: a new session, ``killpg`` with ``SIGKILL`` or the signal passed on,
``SIGTERM``/``SIGHUP`` to stop an agent, ``nice(19)``, and the kernel's boot
id. Windows: a new console process group, ``taskkill /F /T`` by full path
then the leader itself, ``CTRL_BREAK_EVENT`` to the group, ``SIGBREAK`` for
``SIGHUP``, the idle priority class, and no boot id.
"""

from __future__ import annotations

import ctypes
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
    with pytest.raises(ProcessLookupError):
        hostos.kill_group(leader)


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


def test_an_agent_stops_on_term_and_hup_on_posix_and_break_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "linux")
    assert hostos.stop_signals() == (signal.SIGTERM, signal.SIGHUP)
    as_system(monkeypatch, "windows")
    assert hostos.stop_signals() == (signal.SIGTERM, SIGBREAK)


@linux
def test_posix_lowers_the_process_to_the_lowest_priority() -> None:
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from mcgyvr import hostos; "
            "hostos.lower_priority(); print(os.nice(0))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "19"


def test_windows_lowers_the_process_to_the_idle_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "windows")
    asked: list[tuple[object, int]] = []

    class Kernel:
        def GetCurrentProcess(self) -> object:  # noqa: N802 - the Win32 name
            return "this process"

        def SetPriorityClass(self, process: object, level: int) -> int:  # noqa: N802
            asked.append((process, level))
            return 1

    class Windll:
        kernel32 = Kernel()

    monkeypatch.setattr(ctypes, "windll", Windll(), raising=False)
    hostos.lower_priority()
    assert asked == [("this process", 0x40)]
    monkeypatch.delattr(ctypes, "windll")
    hostos.lower_priority()


def test_linux_reads_the_boot_id_or_answers_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "linux")
    found = tmp_path / "boot_id"
    monkeypatch.setattr(hostos, "BOOT_ID", found)
    assert hostos.boot_id() is None
    found.write_text("")
    assert hostos.boot_id() is None
    found.write_text("0f1e2d3c-aaaa-bbbb-cccc-001122334455\n")
    assert hostos.boot_id() == "0f1e2d3c-aaaa-bbbb-cccc-001122334455"


@pytest.mark.parametrize(
    ("answer", "code", "boot"),
    [("ABCD-1234\n", 0, "ABCD-1234"), ("", 0, None), ("ABCD\n", 1, None)],
)
def test_macos_asks_sysctl_for_the_boot_session(
    answer: str, code: int, boot: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "darwin")
    asked: list[Any] = []

    def run(argv: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        return subprocess.CompletedProcess(argv, code, stdout=answer, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    assert hostos.boot_id() == boot
    assert asked == [hostos.DARWIN_BOOT_ID]


def test_macos_with_no_sysctl_and_windows_answer_no_boot_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_system(monkeypatch, "darwin")

    def missing(argv: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", missing)
    assert hostos.boot_id() is None
    as_system(monkeypatch, "windows")
    assert hostos.boot_id() is None
