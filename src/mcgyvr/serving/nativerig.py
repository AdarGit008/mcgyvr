"""The native launcher on a macOS or Windows rig the door reaches over ssh.

A unit on a Mac or Windows rig runs as the pinned llama.cpp build under
mcgyvr's own supervisor (:mod:`mcgyvr.serving.native`), as it does on this
machine, with no docker there. The door ships that launcher to the rig as one
program assembled from this checkout (:func:`mcgyvr.serving.shipped.native`),
the way it ships the reader, and asks it one verb per call: ``up`` with the
units read from the launch spec here, ``down`` with their names, ``units`` for
what holds the rig (rig-units.sh's rows, :func:`mcgyvr.serving.native.unit_rows`).
The launcher leaves a copy of itself under the rig's mcgyvr home for the
supervisors it starts, which outlive the call; each binds 127.0.0.1 (K13).

Which rigs: a rig whose rig file records macOS or Windows
(:data:`mcgyvr.config.NATIVE_BY_DEFAULT`). A Linux rig keeps docker.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence

from mcgyvr.config import NATIVE_BY_DEFAULT
from mcgyvr.serving import gatelib


class NativeRigError(RuntimeError):
    """A native rig that could not be asked, or answered nothing this reads."""


def remote(host: str) -> bool:
    """Whether `host` is a rig over ssh whose units run natively there: its rig
    file records macOS or Windows (no ssh is made)."""
    return (
        host not in gatelib.LOCAL_RIGS and gatelib.rig_system(host) in NATIVE_BY_DEFAULT
    )


def call(
    host: str, args: Sequence[str], *, timeout: float | None = 600.0
) -> subprocess.CompletedProcess[str]:
    """Run the shipped launcher's verb `args` on `host`, as the door's ssh."""
    from mcgyvr.serving import shipped

    sent = gatelib.ship(
        gatelib.rig_system(host),
        shipped.packed(shipped.native()),
        tuple(args),
    )
    return gatelib.ssh(host, sent.command, timeout=timeout, input=sent.stdin)


def up(
    host: str, units: Sequence[object], names: Iterable[str] = ()
) -> subprocess.CompletedProcess[str]:
    """Start the native `units` (the named ones, else every awake one) on
    `host`. No time bound: the first start fetches the build there."""
    from mcgyvr.serving import native

    chosen = [unit for unit in units if isinstance(unit, native.NativeUnit)]
    return call(host, ["up", native.units_text(chosen), *names], timeout=None)


def down(host: str, names: Iterable[str]) -> subprocess.CompletedProcess[str]:
    """Stop the named native units on `host`."""
    return call(host, ["down", *names])


def rows(host: str, asked: Iterable[str] = ()) -> str:
    """What holds `host`, in rig-units.sh's rows, or :class:`NativeRigError`."""
    try:
        done = call(host, ["units", *asked], timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise NativeRigError(f"{host} did not say what holds it in 180s") from exc
    if done.returncode != 0:
        raise NativeRigError(
            f"what holds {host} could not be read: {done.stderr.strip()[:500]}"
        )
    return done.stdout


def running(host: str) -> dict[str, str]:
    """The supervised units on `host`, as id (``native-<pid>``) to name."""
    from mcgyvr.fleet import read

    try:
        found = read.parse(rows(host))
    except read.ReadError as exc:
        raise NativeRigError(f"what holds {host} reads wrong: {exc}") from exc
    return {c.id: c.name for c in found.containers}


def restarts(host: str, unit: str) -> int:
    """How often `unit`'s server was restarted on `host`; 0 when unread."""
    from mcgyvr.fleet import read

    try:
        found = read.parse(rows(host))
    except (NativeRigError, read.ReadError):
        return 0
    for container in found.containers:
        if container.name == unit and container.restarts is not None:
            return container.restarts
    return 0
