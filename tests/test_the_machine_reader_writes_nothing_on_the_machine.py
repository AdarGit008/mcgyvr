"""The machine reader writes nothing on the machine it reads.

The reader holds no here-string and no here-document, which bash may back with
a temporary file; every tool's output reaches it through a pipe. Where the
system can trace it, a run over a tool that prints a large answer, traced with
every process it starts, opens no file for writing and makes no call that
creates, removes, renames, links or truncates a file or folder, outside the
stub tools' own folder and ``/dev/null``. What is traced is those calls; a
write through another call is not seen.
"""

from __future__ import annotations

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
_CHANGE_CALL = re.compile(r"^\d+\s+(?:" + "|".join(_CHANGES) + r")\(")


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
    staged = Staged(
        first_tool=rows.encode(),
        first_tool_processes={i: (b"", 0) for i in range(20)},
    )
    trace = tmp_path / "reader.trace"
    ran = run(
        staged,
        tmp_path / "machine",
        command=(
            strace,
            "-f",
            "-e",
            "trace=open,openat,openat2," + ",".join(_CHANGES),
            "-o",
            str(trace),
            bash,
            "-s",
        ),
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.count("\ncard=") == 20
    written = [
        line
        for line in trace.read_text("utf-8", errors="replace").splitlines()
        if _writes(line)
        and "/dev/null" not in line
        and "= -1" not in line
        and str(tmp_path / "machine" / "stubs") not in line
    ]
    assert not written, written[:5]
