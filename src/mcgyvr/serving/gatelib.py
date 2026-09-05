#!/usr/bin/env python3
"""What every gate script needs and nothing else.

Importable, unlike the scripts under ``gate-scripts/``: this holds no policy,
only the plumbing each gate repeats. The moment something in here decides
whether a run may proceed it belongs in a gate instead, where the door can see
it in :data:`~mcgyvr.serving.run.SEQUENCE`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

#: The door hands facts back on a pipe, whose descriptor number it names in
#: RUN_EXPORT_FD. Not a hardcoded 3: `pass_fds` keeps a descriptor at the
#: number it already has, so a gate writing to a fixed 3 writes to whatever
#: happened to be there. A gate run BY HAND has no such variable and says so on
#: stderr instead of dying on a bad descriptor.
_EXPORT_FD = int(os.environ.get("RUN_EXPORT_FD") or -1)


def export(key: str, value: object) -> None:
    """Hand one named fact back to the door. Declared in SEQUENCE or refused."""
    line = f"{key}={value}\n".encode()
    if _EXPORT_FD < 0:
        sys.stderr.write(f"(no door) {line.decode()}")
        return
    try:
        os.write(_EXPORT_FD, line)
    except OSError:
        # The descriptor was named and is not writable: that is a broken door,
        # not a gate run by hand, so it is not swallowed.
        raise


def refuse(rule: str, status: int = 2) -> NoReturn:
    """Say which rule refused, then stop. Never returns.

    The message is the whole product of a refusal: an operator reads it at the
    moment they are most inclined to work around it, so it names what was
    checked and what to do, not merely that something failed.
    """
    sys.stderr.write(f"{Path(sys.argv[0]).name}: {rule}\n")
    raise SystemExit(status)


def need(key: str) -> str:
    """A variable the door promised. Absent means the gate ran out of order."""
    value = os.environ.get(key)
    if not value:
        refuse(
            f"{key} is not set. A gate reads the run from the environment the "
            "door exports; an empty one means this script was started outside "
            "mcgyvr.serving.run, where no gate has run and nothing is guarded"
        )
    return value


def root() -> Path:
    return Path(need("RUN_ROOT"))


def ssh(
    host: str, command: str, timeout: float = 120.0
) -> subprocess.CompletedProcess[str]:
    """The only way a gate reaches a rig.

    ``BatchMode=yes`` so a host that wants a password fails in seconds instead
    of hanging on a prompt nobody is watching, and a timeout because a rig that
    hard-locks takes the ssh pipe with it — three of those on srv1 in one
    campaign, each ending mid-log-stream.
    """
    return subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def ssh_or_refuse(host: str, command: str, what: str, timeout: float = 120.0) -> str:
    """``ssh``, refusing on a non-zero exit. A rig that cannot answer is not read."""
    try:
        done = ssh(host, command, timeout=timeout)
    except subprocess.TimeoutExpired:
        refuse(
            f"{what}: ssh to {host} did not answer within {timeout:.0f}s "
            f"({shlex.quote(command)[:80]}). A rig that cannot be read is not "
            "compared, and nothing is measured on it"
        )
        raise
    if done.returncode != 0:
        refuse(
            f"{what}: ssh to {host} exited {done.returncode}: "
            f"{done.stderr.strip()[:400] or '(no stderr)'}"
        )
    return done.stdout


def docker(host: str | None = None) -> str:
    """The docker CLI the whole run uses.

    One name, from the door, so a tag cannot be resolved against one daemon and
    a container started on another — which is the hole gate 3 exists to close.
    """
    del host
    return os.environ.get("RUN_DOCKER") or "docker"
