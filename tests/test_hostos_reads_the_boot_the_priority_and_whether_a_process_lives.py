"""hostos reads the boot, lowers the priority and tells a live process from a gone one.

POSIX: the kernel's boot id (Linux) or ``kern.bootsessionuuid`` (macOS),
``nice(19)``, and signal 0. Windows: no boot id, so nothing is trusted past
one boot; the idle priority class; and the process opened for its exit code,
since ``os.kill(pid, 0)`` there sends a Ctrl-C event instead of asking.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hostos
from tests.hostos_fakes import as_system

linux = pytest.mark.skipif(sys.platform != "linux", reason="nice and /proc")
posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX calls")


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


@posix
def test_posix_counts_this_process_alive_and_a_reaped_child_gone() -> None:
    assert hostos.pid_alive(os.getpid())
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    assert not hostos.pid_alive(child.pid)


@posix
def test_posix_counts_a_pid_it_may_not_signal_as_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(_pid: int, _sig: int) -> None:
        raise PermissionError("another user's")

    monkeypatch.setattr(os, "kill", refused)
    assert hostos.pid_alive(4242)


class _Winapi:
    """``_winapi`` as Windows answers OpenProcess and GetExitCodeProcess."""

    def __init__(self, error: int | None, code: int) -> None:
        self.error, self.code = error, code
        self.closed: list[object] = []

    def OpenProcess(self, access: int, inherit: bool, pid: int) -> object:  # noqa: N802
        assert (access, inherit, pid) == (0x1000, False, 4242)
        if self.error is not None:
            failed = OSError("OpenProcess failed")
            failed.winerror = self.error  # type: ignore[attr-defined]
            raise failed
        return "handle"

    def GetExitCodeProcess(self, handle: object) -> int:  # noqa: N802
        return self.code

    def CloseHandle(self, handle: object) -> None:  # noqa: N802
        self.closed.append(handle)


@pytest.mark.parametrize(
    ("error", "code", "alive"),
    [(None, 259, True), (None, 0, False), (87, 0, False), (5, 0, True)],
)
def test_windows_asks_the_process_for_its_exit_code_and_never_signals(
    error: int | None, code: int, alive: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, "windows")
    winapi = _Winapi(error, code)
    monkeypatch.setitem(sys.modules, "_winapi", winapi)

    def never(_pid: int, _sig: int) -> None:
        raise AssertionError("os.kill sends Ctrl-C on Windows")

    monkeypatch.setattr(os, "kill", never)
    assert hostos.pid_alive(4242) is alive
    assert winapi.closed == (["handle"] if error is None else [])
