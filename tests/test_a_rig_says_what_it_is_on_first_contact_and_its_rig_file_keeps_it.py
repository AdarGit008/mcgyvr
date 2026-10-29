"""A rig says what it is on first contact, and its rig file keeps it.

A rig with no rig file is sent the POSIX reader line, as every rig always was:
a Linux or macOS rig answers it and is asked nothing more, and its reading
names its system (``host.os``). A rig whose shell cannot run that line is asked
the PowerShell question; a Windows rig answers it and is sent the reader the
Windows way. ``mcgyvr scan --rig`` files the reading, so from then on the rig
file says the system and no question is asked: a recorded Windows rig is sent
the Windows reader first, a recorded Linux rig the POSIX line only. A shell that
answers neither is a rig nobody could read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.serving import gatelib, rigfile
from tests.machine_shapes import host_reading, host_shape
from tests.remote_rigs import FakeShell, record_rig


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path / "rigs"))
    monkeypatch.setattr(scan_module, "_WINDOWS_FOUND", set())


def _reads_as(label: str, shell: FakeShell) -> FakeShell:
    """`shell`, answering the shipped reader (whichever way it came) with the
    reading of the invented machine `label`."""
    document = json.dumps(host_reading(host_shape(label)))
    posix = gatelib.scan_read_command()
    windows = gatelib.scan_read(gatelib.WINDOWS)

    def answer(command: str, stdin: str | None) -> object:
        if command == posix and shell.system != "windows":
            return _done(document)
        if (command, stdin) == (windows.command, windows.stdin):
            return _done(document)
        return None

    shell.answer = answer  # type: ignore[assignment]
    return shell


def _done(out: str, code: int = 0) -> object:
    import subprocess

    return subprocess.CompletedProcess(["ssh"], code, out, "")


def _read_only(shell: FakeShell) -> object:
    def ssh_read_only(
        host: str,
        command: str,
        timeout: float | None = None,
        *,
        input: str | None = None,
    ) -> object:
        assert gatelib._read_only_command(command, input), command[:80]
        return shell(host, command, timeout, input=input)

    return ssh_read_only


@pytest.mark.parametrize("label", ["linux-one-card", "unified-laptop"])
def test_a_posix_rig_is_sent_the_reader_line_and_asked_nothing_more(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, label: str
) -> None:
    system = host_shape(label).system
    shell = _reads_as(label, FakeShell(system, tmp_path / "rig"))
    monkeypatch.setattr(gatelib, "ssh_read_only", _read_only(shell))
    document = scan_module.read_over(scan_module.Reach.ssh("box1"))
    assert shell.sent == [(gatelib.scan_read_command(), None)]
    assert document["host"]["os"] == system


def test_a_windows_rig_answers_powershell_and_is_sent_the_windows_reader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    shell = _reads_as("windows-one-card", FakeShell("windows", tmp_path / "rig"))
    monkeypatch.setattr(gatelib, "ssh_read_only", _read_only(shell))
    document = scan_module.read_over(scan_module.Reach.ssh("box1"))
    windows = gatelib.scan_read(gatelib.WINDOWS)
    assert shell.sent == [
        (gatelib.scan_read_command(), None),
        (gatelib.PROBE_WINDOWS, None),
        (windows.command, windows.stdin),
    ]
    assert document["host"]["os"] == "windows"
    # Filed as `mcgyvr scan --rig` files it, the rig file says the system.
    rigfile.save("box1", document)
    assert gatelib.recorded_os("box1") == "windows"


def test_a_recorded_windows_rig_is_sent_the_windows_reader_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record_rig(monkeypatch, tmp_path, "box1", "windows-one-card")
    shell = _reads_as("windows-one-card", FakeShell("windows", tmp_path / "rig"))
    monkeypatch.setattr(gatelib, "ssh_read_only", _read_only(shell))
    scan_module.read_over(scan_module.Reach.ssh("box1"))
    windows = gatelib.scan_read(gatelib.WINDOWS)
    assert shell.sent == [(windows.command, windows.stdin)]


def test_a_recorded_posix_rig_that_fails_is_not_asked_powershell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record_rig(monkeypatch, tmp_path, "box1", "linux-one-card")
    shell = FakeShell("linux", tmp_path / "rig")
    shell.answer = lambda command, stdin: _done("", 1)  # type: ignore[assignment,return-value]
    monkeypatch.setattr(gatelib, "ssh_read_only", _read_only(shell))
    with pytest.raises(scan_module.ScannerMissing):
        scan_module.read_over(scan_module.Reach.ssh("box1"))
    assert [command for command, _ in shell.sent] == [gatelib.scan_read_command()]


def test_a_shell_that_answers_neither_question_is_a_rig_nobody_could_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    shell = FakeShell("linux", tmp_path / "rig")
    shell.answer = lambda command, stdin: _done("", 127)  # type: ignore[assignment,return-value]
    monkeypatch.setattr(gatelib, "ssh_read_only", _read_only(shell))
    with pytest.raises(scan_module.ScannerMissing):
        scan_module.read_over(scan_module.Reach.ssh("box1"))
    assert [command for command, _ in shell.sent] == [
        gatelib.scan_read_command(),
        gatelib.PROBE_WINDOWS,
    ]


def test_a_reading_from_before_readers_named_a_system_reads_as_linux(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = record_rig(monkeypatch, tmp_path, "box1", "linux-one-card")
    stored = json.loads(path.read_text())
    del stored["reading"]["host"]
    path.write_text(json.dumps(stored))
    assert gatelib.recorded_os("box1") == "linux"
    assert gatelib.rig_system("box1") == "linux"
    assert gatelib.recorded_os("nobox") is None
    assert gatelib.rig_system("nobox") == "linux"


def test_a_windows_rig_has_its_models_found_and_read_the_windows_way(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr import recommend

    record_rig(monkeypatch, tmp_path, "box1", "windows-one-card")
    shell = FakeShell("windows", tmp_path / "rig")
    shell.answer = lambda command, stdin: _done(  # type: ignore[assignment,return-value]
        "C:\\m\\a.gguf\n" if stdin is None else json.dumps([{"arch": "llama"}])
    )
    monkeypatch.setattr(gatelib, "ssh_read_only", _read_only(shell))
    assert recommend._discover("box1", "C:\\m") == ("C:\\m\\a.gguf",)
    assert recommend._read_header("box1", "C:\\m\\a.gguf") == {"arch": "llama"}
    header = gatelib.header_read(gatelib.WINDOWS, "C:\\m\\a.gguf")
    assert shell.sent == [
        (gatelib.windows_discover("C:\\m"), None),
        (header.command, header.stdin),
    ]
