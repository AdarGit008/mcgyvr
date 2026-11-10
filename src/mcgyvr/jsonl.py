"""Append-only JSON-lines journals: one object per line, written whole, read leniently.

:func:`append_line` adds one line under an exclusive lock on the file, so
concurrent writers append whole lines rather than interleaving them, and it ends
a torn trailing line first, so a writer that died mid-line cannot have the next
record glued onto its stump. :func:`read_lines` reads a journal back as its JSON
objects with their line numbers, passing over a line that is blank, not UTF-8,
not JSON or not an object, so one damaged line cannot hide the rest. What a
record means — its fields, its version — is each journal's own: the dispatch
journal (:mod:`mcgyvr.telemetry`), the decision shadow log
(:mod:`mcgyvr.decision_log`) and the fleet read's rows (:mod:`mcgyvr.fleet.alerts`,
:mod:`mcgyvr.fleet.read`) share only this line discipline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcgyvr import hostos


def append_line(path: Path, line: bytes) -> None:
    """Append ``line`` (one JSON object and its newline) to ``path``.

    The parent directory and the file are created when missing. The write
    happens under an exclusive lock on the file, after a torn trailing line is
    ended, and a write the disk stops accepting raises rather than leaving a
    stump behind as if the line were written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | hostos.open_flags_binary()
    fd = os.open(path, flags, 0o666)
    try:
        hostos.lock(fd)
        try:
            _terminate_stump(fd)
            _write_all(fd, line)
        finally:
            hostos.unlock(fd)
    finally:
        os.close(fd)


def read_lines(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """The JSON objects in the journal at ``path`` with their 1-based line numbers.

    Oldest first. Lines that are blank, not decodable UTF-8, not JSON, or not
    JSON objects are passed over. A missing file reads as no lines at all.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return []
    rows: list[tuple[int, dict[str, Any]]] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            rows.append((number, parsed))
    return rows


def _terminate_stump(fd: int) -> None:
    """End the file in a newline before more is appended to it.

    A writer that died mid-line would otherwise leave a partial line for the next
    record to be glued onto, and the reader would pass over both of them.
    """
    end = os.lseek(fd, 0, os.SEEK_END)
    if end == 0:
        return
    os.lseek(fd, end - 1, os.SEEK_SET)
    if os.read(fd, 1) != b"\n":
        os.write(fd, b"\n")


def _write_all(fd: int, data: bytes) -> None:
    """Write all of ``data`` to ``fd``, looping while the kernel takes less.

    ``os.write`` may accept fewer bytes than it was given; a write that accepts
    none is raised as an error naming how much of the line reached the sink.
    """
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(
                f"journal sink accepted {len(data) - len(view)} of {len(data)} bytes"
            )
        view = view[written:]
