"""A rig's lease file, read and written one operation at a time, in Python.

The lease (:mod:`mcgyvr.serving.gatelib`) is one line in ``lease`` under the
rig's lease folder. This is its Python implementation: the one the door runs on
this machine when it reaches it without ssh, and the one it ships to a macOS or
Windows rig (``mcgyvr.serving.shipped.lease``), which has an interpreter but,
on Windows, no bash. A Linux rig is still sent gatelib's bash scripts, whose
statuses and writes these are.

Statuses: 0 done, 1 a free take found a lease there, 3 the lease is not the one
expected, 4 no lease folder, 5 the lease file could not be read. Each operation
holds ``lease.lock`` beside the file (:func:`mcgyvr.hostos.lock`), so two on
one machine do not interleave. Every write goes through a temporary file
renamed over the lease, as the scripts' ``mv -f`` does; a free take creates it
exclusively, as ``set -C`` does.

Run as a program: ``OP FOLDER [held=ID] [line=LINE]``, with the lease on
stdout and a failure on stderr, exiting with the status. Standard library and
``mcgyvr.hostos`` only.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from mcgyvr import hostos

#: The lease file and its lock, inside the lease folder.
FILE = "lease"
LOCK = "lease.lock"
#: The operations, by the names gatelib's scripts carry.
OPS = ("read", "take_free", "take_stale", "stamp", "release")


def read_nofollow(path: Path) -> str:
    """The text of `path`, refused (`OSError`) when it is a link."""
    fd = hostos.open_nofollow(path, os.O_RDONLY)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        return handle.read()


def operate(op: str, folder: str, fields: Mapping[str, str]) -> tuple[int, str, str]:
    """Run the lease operation `op` on the lease in `folder` (``~`` expanded).

    Answers ``(status, stdout, stderr)`` as the shell scripts do: the read
    prints the file, every other operation prints nothing.
    """
    if op not in OPS:
        return 2, "", f"lease: no operation {op!r}\n"
    where = Path(folder).expanduser()
    lease = where / FILE
    try:
        where.mkdir(parents=True, exist_ok=True)
        fd = hostos.open_nofollow(where / LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        return 4, "", f"{exc}\n"
    try:
        hostos.lock(fd)
        try:
            now = read_nofollow(lease)
        except FileNotFoundError:
            now = ""
        except OSError as exc:
            return 5, "", f"{exc}\n"
        held = f"lease_id={fields.get('held', '')} "
        if op == "read":
            return 0, now, ""
        if op == "release":
            if held in now:
                lease.unlink(missing_ok=True)
            return 0, "", ""
        line = fields["line"] + "\n"
        if op == "take_free":
            try:
                out = hostos.open_nofollow(
                    lease, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
                )
            except FileExistsError:
                return 1, "", ""
            with os.fdopen(out, "w", encoding="utf-8") as handle:
                handle.write(line)
            return 0, "", ""
        if op == "take_stale" and not fields.get("held"):
            if now.strip():
                return 3, "", ""
        elif held not in now:
            return 3, "", ""
        part = where / f"{FILE}.{os.getpid()}"
        part.unlink(missing_ok=True)
        out = hostos.open_nofollow(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(out, "w", encoding="utf-8") as handle:
            handle.write(line)
        os.replace(part, lease)
        return 0, "", ""
    finally:
        hostos.unlock(fd)
        os.close(fd)


def main(argv: Sequence[str] | None = None) -> int:
    """``OP FOLDER [key=value ...]``: one operation, its status as the exit."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print("usage: leasefile OP FOLDER [held=ID] [line=LINE]", file=sys.stderr)
        return 2
    fields = dict(arg.split("=", 1) for arg in args[2:] if "=" in arg)
    code, out, err = operate(args[0], args[1], fields)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
