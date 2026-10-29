"""On Windows the door runs its shims by argv and hands a gate its pipe as a handle.

Windows finds a program by its ``.exe`` and has no shebang, so under a run the
door's `ssh` and `docker` are its Python shims run on the door's interpreter,
and a `.cmd` launcher beside each lets a program that looks a command up by
PATHEXT (docker, for an ``ssh://`` daemon) find it. The real tool is looked up
as ``ssh.exe``, run and waited for, since Windows has no exec that keeps the
process. A gate's export pipe goes down as an inheritable handle in the
``handle_list``, not by ``pass_fds``. POSIX keeps every call it made. Each
Windows path is faked here.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hostos
from mcgyvr.serving import gatelib, run
from tests.hostos_fakes import as_system


def test_the_shims_are_run_by_direct_argv_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gatelib.tool("docker") == ["docker"]
    as_system(monkeypatch, "windows")
    assert gatelib.tool("docker") == [sys.executable, str(gatelib.SHIM_DIR / "docker")]
    assert gatelib.tool("ssh") == [sys.executable, str(gatelib.SHIM_DIR / "ssh")]


@pytest.mark.parametrize("name", run.SHIMS)
def test_each_shim_has_a_windows_launcher_on_the_doors_interpreter(name: str) -> None:
    text = (gatelib.SHIM_DIR / f"{name}.cmd").read_bytes().decode("utf-8")
    assert f'"%{gatelib.PYTHON_VAR}%" "%~dp0{name}" %*' in text
    assert "\r\n" in text


def test_a_missing_launcher_stops_the_door_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in run.SHIMS:
        (bin_dir / name).write_text("#!/bin/sh\n")
        (bin_dir / name).chmod(0o755)
    monkeypatch.setattr(run, "BIN", bin_dir)
    as_system(monkeypatch, "windows")
    with pytest.raises(run.RefusedError, match=r"docker\.cmd, ssh\.cmd"):
        run.check_manifest()


def test_the_real_tool_is_the_exe_past_the_shim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "docker.exe").write_text("")
    (real / "docker.exe").chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join([str(gatelib.SHIM_DIR), str(real)]))
    as_system(monkeypatch, "windows")
    found = gatelib.next_on_path("docker", skip=gatelib.SHIM_DIR)
    assert found == str(real / "docker.exe")


def test_a_shim_on_windows_runs_the_tool_and_ends_with_its_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 7, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(os, "execv", _no_exec)
    as_system(monkeypatch, "windows")
    with pytest.raises(SystemExit) as ended:
        gatelib.become("C:/tools/ssh.exe", ["C:/tools/ssh.exe", "-o", "x", "box1"])
    assert ended.value.code == 7
    assert ran == [["C:/tools/ssh.exe", "-o", "x", "box1"]]


class _Msvcrt:
    def __init__(self) -> None:
        self.opened: list[tuple[int, int]] = []

    def get_osfhandle(self, fd: int) -> int:
        return 1000 + fd

    def open_osfhandle(self, handle: int, flags: int) -> int:
        self.opened.append((handle, flags))
        return 9


class _StartupInfo:
    def __init__(self, *, lpAttributeList: dict[str, Any]) -> None:  # noqa: N803
        self.lpAttributeList = lpAttributeList


def test_a_gates_pipe_goes_down_as_an_inheritable_handle_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hostos.inherited_fd_kwargs(5) == ("5", {"pass_fds": (5,)})
    fake = _Msvcrt()
    inheritable: list[tuple[int, bool]] = []
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(
        os,
        "set_handle_inheritable",
        lambda h, v: inheritable.append((h, v)),
        raising=False,
    )
    monkeypatch.setattr(subprocess, "STARTUPINFO", _StartupInfo, raising=False)
    as_system(monkeypatch, "windows")
    name, kwargs = hostos.inherited_fd_kwargs(5)
    assert name == "1005"
    assert inheritable == [(1005, True)]
    assert kwargs["close_fds"] is True
    assert kwargs["startupinfo"].lpAttributeList == {"handle_list": [1005]}
    assert "pass_fds" not in kwargs
    assert hostos.inherited_fd("1005") == 9
    assert fake.opened == [(1005, os.O_WRONLY)]


def test_a_supervisor_is_started_out_of_its_starters_group_and_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hostos.popen_detached_kwargs() == {"start_new_session": True}
    as_system(monkeypatch, "windows")
    flags = hostos.popen_detached_kwargs()["creationflags"]
    assert flags == 0x200 | 0x8 | 0x0100_0000
    assert hostos.popen_detached_kwargs(breakaway=False)["creationflags"] == 0x208


def test_posix_has_no_job_and_ends_a_group_by_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX calls")
    assert hostos.kill_on_close_job(object()) is None  # type: ignore[arg-type]
    sent: list[tuple[str, int, int]] = []
    monkeypatch.setattr(os, "killpg", lambda p, s: sent.append(("group", p, s)))
    monkeypatch.setattr(os, "kill", lambda p, s: sent.append(("one", p, s)))
    assert hostos.end_pid(4242, group=True) is True
    assert hostos.end_pid(4242, force=True) is True
    assert sent == [("group", 4242, signal.SIGTERM), ("one", 4242, signal.SIGKILL)]


def test_a_process_start_time_names_one_process() -> None:
    if not Path("/proc/self/stat").exists():
        pytest.skip("reads /proc")
    mine = hostos.process_start_time(os.getpid())
    assert mine is not None and mine.isdigit()
    assert hostos.process_start_time(os.getpid()) == mine
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        assert hostos.process_start_time(child.pid) not in (None, "")
    finally:
        child.kill()
        child.wait()


def test_macos_reads_a_start_time_with_ps(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        return subprocess.CompletedProcess(argv, 0, "Thu Oct 29 08:00:01 2026\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    as_system(monkeypatch, "darwin")
    assert hostos.process_start_time(77) == "Thu Oct 29 08:00:01 2026"
    assert asked == [["/bin/ps", "-o", "lstart=", "-p", "77"]]


def _no_exec(*_a: object) -> None:
    raise AssertionError("Windows has no exec that keeps the process")
