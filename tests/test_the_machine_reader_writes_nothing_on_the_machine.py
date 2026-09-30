"""The machine reader writes nothing on the machine it reads.

The reader holds no here-string and no here-document, which bash may back with
a temporary file; every tool's output reaches it through a pipe. Where the
system can trace it, a run over a tool that prints a large answer and a tool
whose answer is read by python, traced with
every process it starts, opens no file for writing and makes no call that
creates, removes, renames, links or truncates a file or folder, outside the
stub tools' own folder and ``/dev/null``. What is traced is those calls; a
write through another call is not seen.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.machinereader import READER, Staged, run


def _code_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def test_the_reader_holds_no_here_string_and_no_here_document() -> None:
    lines = [line for line in _code_lines(READER.read_text("utf-8")) if "<<" in line]
    assert not lines, lines


def _tracing_works(where: Path) -> bool:
    strace = shutil.which("strace")
    if not strace:
        return False
    done = subprocess.run(
        [strace, "-f", "-o", str(where / "probe.trace"), "true"],
        capture_output=True,
        check=False,
        timeout=30,
    )
    return done.returncode == 0


_OPEN_WRITES = re.compile(r"O_WRONLY|O_RDWR|O_CREAT|O_TRUNC|O_APPEND")
_CHANGES = (
    "creat",
    "mkdir",
    "mkdirat",
    "rename",
    "renameat",
    "renameat2",
    "link",
    "linkat",
    "symlink",
    "symlinkat",
    "unlink",
    "unlinkat",
    "rmdir",
    "truncate",
    "mknod",
    "mknodat",
)
_CHANGE_CALL = re.compile(r"^(?:" + "|".join(_CHANGES) + r")\(")


def _writes(line: str) -> bool:
    if _CHANGE_CALL.search(line):
        return True
    return bool(re.search(r"\bopen(?:at2?)?\(", line) and _OPEN_WRITES.search(line))


def test_a_large_answer_is_read_without_a_file_being_written(tmp_path: Path) -> None:
    if not _tracing_works(tmp_path):
        pytest.skip("strace cannot trace here")
    strace = shutil.which("strace")
    bash = shutil.which("bash")
    assert strace and bash
    rows = "".join(
        f"{i}, 7919, 0, 7919, Example Card {'W' * 3900}\n" for i in range(20)
    )
    second = {
        "card0": {
            "Card series": "Example Card S",
            "VRAM Total Memory (B)": str(7919 * 1024 * 1024),
            "VRAM Total Used Memory (B)": "0",
        }
    }
    staged = Staged(
        first_tool=rows.encode(),
        first_tool_processes={i: (b"", 0) for i in range(20)},
        second_tool=json.dumps(second).encode(),
        tool_seconds=120,
    )
    # One file per process, so that no call is split over two lines.
    trace = tmp_path / "trace" / "reader"
    trace.parent.mkdir()
    ran = run(
        staged,
        tmp_path / "machine",
        command=(
            strace,
            "-ff",
            "-e",
            "trace=open,openat,openat2," + ",".join(_CHANGES),
            "-o",
            str(trace),
            bash,
            "-s",
        ),
    )
    assert ran.returncode == 0, ran.stderr
    unread = [line for line in ran.stdout.splitlines() if line.startswith("unread=")]
    assert ran.stdout.count("\ncard=") == 21, unread
    written = [
        line
        for one in sorted(trace.parent.iterdir())
        for line in one.read_text("utf-8", errors="replace").splitlines()
        if _writes(line)
        and "/dev/null" not in line
        and "= -1" not in line
        and str(tmp_path / "machine" / "stubs") not in line
    ]
    assert not written, written[:5]
