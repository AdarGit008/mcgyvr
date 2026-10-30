"""Invented remote rigs a test reaches through a fake ssh: their rig files and shells.

:func:`record_rig` writes the rig file of an invented machine of
:mod:`tests.machine_shapes` (a Mac, a Windows machine, a Linux box) under the
folder ``MCGYVR_RIGS`` names, as ``mcgyvr scan --rig`` would.

:class:`FakeShell` stands where ``gatelib.ssh`` (or ``servelib.ssh``) reaches a
rig: it is handed what the door sends and answers as that rig's shell would.
A POSIX shell (Linux, macOS) runs the shipped line
``echo <base64> | base64 -d | python3 -I -B - ARGS``, ``bash -s`` and
``python3 -``; a Windows shell runs only ``powershell`` (cmd.exe has no
base64 nor bash) and, for the shipped launcher, does what its script does: the
program from the first stdin line written to a file, run with ``-I -B`` and the
quoted arguments, the second line fed to it. Every program runs here, on this
interpreter, with ``HOME`` (and ``USERPROFILE``/``LOCALAPPDATA``) at the rig's
own folder, so what it writes lands there and nowhere else. A test may answer a
command itself instead (:attr:`FakeShell.answer`). Nothing of the machine the
tests run on is read as the rig's.
"""

from __future__ import annotations

import base64
import os
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.machine_shapes import host_scan_document, host_shape
from tests.records import RIGS_ENV

#: What cmd.exe says for a program it cannot find.
NOT_RECOGNIZED = "is not recognized as an internal or external command"


def record_rig(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rig: str, label: str
) -> Path:
    """Write the rig file of the invented machine `label` under `rig`."""
    from mcgyvr.serving import rigfile

    folder = tmp_path / "rigs"
    monkeypatch.setenv(RIGS_ENV, str(folder))
    reading = host_scan_document(host_shape(label))
    return rigfile.write(rigfile.from_reading(rig, reading))


@dataclass
class FakeShell:
    """One rig's shell: `system` is linux, darwin or windows; `home` its folder."""

    system: str
    home: Path
    #: Answers a test gives itself: called with (command, stdin); None runs it.
    answer: Callable[[str, str | None], subprocess.CompletedProcess[str] | None] = (
        lambda _command, _stdin: None
    )
    #: Every (command, stdin) the rig was sent, in order.
    sent: list[tuple[str, str | None]] = field(default_factory=list)
    #: Whether each call asked ssh's keepalive (an unbounded call does).
    kept_alive: list[bool] = field(default_factory=list)

    def __call__(
        self,
        host: str,
        command: str,
        timeout: float | None = None,
        *,
        input: str | None = None,
        keepalive: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        self.sent.append((command, input))
        self.kept_alive.append(keepalive)
        given = self.answer(command, input)
        if given is not None:
            return given
        if self.system == "windows":
            return self._windows(command, input)
        return self._posix(command, input)

    # --- what each shell runs -------------------------------------------------

    def _env(self) -> dict[str, str]:
        self.home.mkdir(parents=True, exist_ok=True)
        local = self.home / "AppData" / "Local"
        return {
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "LOCALAPPDATA": str(local),
            "PATH": os.environ.get("PATH", ""),
            "LC_ALL": "C",
        }

    def _python(
        self, argv: list[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[str]:
        done = subprocess.run(
            [sys.executable, *argv],
            input=stdin,
            capture_output=True,
            env=self._env(),
            cwd=self.home,
            timeout=120,
            check=False,
        )
        return subprocess.CompletedProcess(
            argv,
            done.returncode,
            done.stdout.decode("utf-8", "replace"),
            done.stderr.decode("utf-8", "replace"),
        )

    def _posix(
        self, command: str, stdin: str | None
    ) -> subprocess.CompletedProcess[str]:
        line = " | base64 -d | python3 "
        if command.startswith("echo ") and line in command:
            blob, _sep, tail = command[len("echo ") :].partition(line)
            return self._python(shlex.split(tail), base64.b64decode(blob))
        if command.startswith(line[3:]):
            tail = command[len(line[3:]) :]
            return self._python(shlex.split(tail), base64.b64decode(stdin or ""))
        words = shlex.split(command)
        if words[:1] == ["python3"]:
            return self._python(words[1:], (stdin or "").encode("utf-8"))
        if words[:2] == ["bash", "-s"]:
            done = subprocess.run(
                ["bash", *words[1:]],
                input=stdin,
                capture_output=True,
                text=True,
                env=self._env(),
                cwd=self.home,
                timeout=120,
                check=False,
            )
            return subprocess.CompletedProcess(
                words, done.returncode, done.stdout, done.stderr
            )
        return subprocess.CompletedProcess(
            words, 127, "", f"{words[0]}: command not found\n"
        )

    def _windows(
        self, command: str, stdin: str | None
    ) -> subprocess.CompletedProcess[str]:
        from mcgyvr.serving import gatelib

        def answer(
            code: int, out: str = "", err: str = ""
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([command], code, out, err)

        if not command.startswith(gatelib.POWERSHELL):
            word = command.split(" ", 1)[0]
            return answer(1, err=f"'{word}' {NOT_RECOGNIZED},\n")
        if command == gatelib.PROBE_WINDOWS:
            return answer(0, gatelib.WINDOWS_PLATFORM + "\n")
        lines = (stdin or "").split("\n")
        if command == gatelib.WINDOWS_DISCOVER:
            folder = Path(base64.b64decode(lines[0]).decode("utf-8"))
            found = sorted(str(p) for p in folder.glob("*.gguf") if p.is_file())
            return answer(0, "".join(f"{p}\n" for p in found))
        if command != gatelib.WINDOWS_SHIP or len(lines) < 3:
            return answer(1, err="a script this shell does not run\n")
        program = base64.b64decode(lines[0])
        arguments = base64.b64decode(lines[1]).decode("utf-8")
        feed = base64.b64decode(lines[2])
        folder = self.home / "AppData" / "Local" / "mcgyvr" / "tmp"
        folder.mkdir(parents=True, exist_ok=True)
        written = folder / "shipped-test.py"
        written.write_bytes(program)
        try:
            return self._python(
                ["-I", "-B", str(written), *gatelib.windows_split(arguments)], feed
            )
        finally:
            written.unlink()
