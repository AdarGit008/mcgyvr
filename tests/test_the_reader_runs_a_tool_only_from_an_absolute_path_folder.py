"""The reader runs a tool only from an absolute PATH folder, never the working one.

A PATH entry that is empty, ``.`` or relative names a different folder from
each working directory, where anyone may leave a program named ``sysctl`` or
``nvidia-smi``. Every tool the reader runs is found through
``hostos.which_absolute``, so such an entry is never searched and a tool there
is never run: the reader reads that tool as not installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from mcgyvr import hostos
from mcgyvr.serving import rigscan

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX scripts")


def _tool(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    tool = folder / name
    tool.write_text("#!/bin/sh\necho planted\n")
    tool.chmod(0o755)
    return tool


@pytest.mark.parametrize("entries", [["", "rel"], [".", "rel"], ["rel"]])
def test_a_tool_in_a_relative_path_entry_is_never_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entries: list[str]
) -> None:
    _tool(tmp_path, "sysctl")
    _tool(tmp_path / "rel", "sysctl")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", os.pathsep.join(entries))
    assert hostos.which_absolute("sysctl") is None
    assert rigscan._run(["sysctl", "-n", "hw.memsize"]) == (None, None)


def test_a_tool_in_an_absolute_path_entry_is_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tool = _tool(tmp_path / "bin", "sysctl")
    monkeypatch.setenv("PATH", os.pathsep.join([".", str(tmp_path / "bin")]))
    assert hostos.which_absolute("sysctl") == str(tool)
    text, why = rigscan._run(["sysctl"])
    assert (text, why) == ("planted\n", None)
