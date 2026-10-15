#!/usr/bin/env python3
"""gate 2 — the live machine is the rig the user's file describes.

WHY start==end IS NOT ENOUGH. A step's own check compares the rig with itself
before and after, which catches a machine that moves DURING a run and says
nothing at all about one that moved BEFORE it. The user's rig file is the
declaration — the rig as `mcgyvr scan --rig` saved it — and the rig is read
again here, once, by the one reader (:mod:`mcgyvr.serving.rigscan`, shipped as
``python3 -I -B -``) and held to that file (:mod:`mcgyvr.serving.rigfile`): what
moved — a card, RAM, the kernel, the driver, docker, the CPU's clock — is
said, and the run is refused only when the fleet no longer fits.

The reading's snapshot is exported for gate 7, which takes a second one after
the step and stamps any key that moved into the artifacts, because rows
produced under two machines have to say so. What holds the rig — its
containers and the processes on its card — is read beside it by the door's
runtime reader, ``rig-units.sh``.

THE RIG IS LEASED HERE, before it is read. Gate 5's claim on the RUN_ID is per
envelope, so two steps could still land on one rig together; the contended
resource is the rig, so the lease sits on it, at ``~/.mcgyvr/lease``, and every
run takes it before it spends rig time. No run takes a rig another live run
holds (owner's ruling, 2026-10-15: "no one can take from no one"), whichever
door wrote the lease: a held rig is refused here, in one line naming the
holder, before anything else reaches the rig — nothing is read, listed,
stopped or written. A lease whose holder is gone (:meth:`Lease.is_stale`: a
pid on this machine that no process has any more, or that a later process has
since been given) is stale: named, not silently ignored, and reclaimed; nothing
of the dead run is torn down. The door releases the lease on every way out.

A machine that is not idle is not refused: a container or a card holder up
before the run is reported and left as it is, since mcgyvr did not start it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcgyvr.serving import rigfile, servelib
from mcgyvr.serving.gatelib import (
    Lease,
    door_required,
    export,
    held_by,
    lease_read,
    lease_take,
    need,
    new_lease,
    refuse,
    scan_read_command,
    ssh,
    step_name,
)
from mcgyvr.serving.rigscan import SNAPSHOT_CARD_KEYS

HERE = Path(__file__).resolve().parent

#: The runtime readings that must read `none` for an idle rig: a card held by
#: a process, or a container up, before the step starts, is a machine somebody
#: else is using. The door does not repair a machine it found wrong, so the run
#: names them and leaves them.
IDLE_KEYS = ("gpu_procs", "containers")


def reading(host: str) -> dict[str, Any]:
    """The rig read whole by the one reader, shipped as ``python3 -I -B -``.

    Nothing lands on the rig's disk, so gate 7 has nothing extra to look for. A
    rig that cannot be read, or whose first card the reader cannot read, is
    not compared: the snapshot's card keys are what gate 7 holds the run to.
    """
    try:
        done = ssh(host, scan_read_command(), timeout=180)
    except subprocess.TimeoutExpired:
        refuse(
            f"gate 2: {host} did not answer in 180s. A rig that cannot be read "
            "is not compared, and nothing is measured on it"
        )
    if done.returncode != 0:
        refuse(
            f"gate 2: the rig could not be read: {done.stderr.strip()[:500]}. "
            "A machine that cannot be read is not compared"
        )
    try:
        document = json.loads(done.stdout)
    except ValueError:
        document = None
    if not isinstance(document, dict) or not isinstance(document.get("snapshot"), dict):
        refuse(
            f"gate 2: the reader on {host} printed no reading this takes. A machine "
            "that cannot be read is not compared"
        )
    why = {
        str(item.get("field")): str(item.get("why"))
        for item in document.get("unread") or ()
        if isinstance(item, dict)
    }
    missing = [key for key in SNAPSHOT_CARD_KEYS if key not in document["snapshot"]]
    if missing:
        refuse(
            f"gate 2: the reader on {host} does not read "
            + "; ".join(
                f"{key} ({why.get(f'snapshot.{key}', 'no reason')})" for key in missing
            )
            + ". A rig whose card is unread is not compared, and nothing is "
            "measured on it"
        )
    return document


def held(host: str) -> dict[str, str]:
    """What holds the rig now, by the runtime reader ``rig-units.sh``: the
    containers up, by short id, and the processes on its card, each ``;``-joined,
    or ``none``."""
    from mcgyvr.fleet import read

    units = (HERE / "rig-units.sh").read_text(encoding="utf-8")
    try:
        done = ssh(host, "bash -s", timeout=180, input=units)
    except subprocess.TimeoutExpired:
        refuse(f"gate 2: {host} did not say what holds it in 180s")
    if done.returncode != 0:
        refuse(
            f"gate 2: what holds {host} could not be read: "
            f"{done.stderr.strip()[:500]}. A rig whose card holders and "
            "containers are unread is not compared"
        )
    try:
        found = read.parse(done.stdout)
    except read.ReadError as exc:
        refuse(f"gate 2: what holds {host} reads wrong: {exc}")
    # `docker ps` names a container by the first 12 digits of its id.
    containers = ";".join(c.id[:12] for c in found.containers)
    procs = ";".join(
        f"{h.pid},{h.process},{'unread' if h.mib is None else h.mib}MiB"
        for h in found.holders
    )
    return {"gpu_procs": procs or "none", "containers": containers or "none"}


def snapshot(host: str) -> dict[str, str]:
    """The rig's snapshot and what holds it, as one map of tokens: what gate 7
    reads again after the step and diffs against gate 2's."""
    return {**reading(host)["snapshot"], **held(host)}


def take_lease(host: str) -> Lease:
    """This run's lease on ``host``, or refused (exit 2) if a live run holds it.

    Judged and written in a loop, because the rig is shared: what was read
    can change before it is written, and a write that finds a different
    holder comes back to be judged again rather than overwriting a run that
    was never named. Three changes of hands and the run gives up naming the
    last one.
    """
    step = step_name(Path(need("RUN_STEP_FILE")))
    # The door's pid, not this gate's: the gate exits, the door holds the run.
    mine = new_lease(step, os.getppid())
    held = lease_read(host)
    for _ in range(3):
        if held is None:
            held = lease_take(host, mine, held=None)
            if held is None:
                return mine
            continue
        if held.lease_id == mine.lease_id:
            return mine
        if not held.is_stale():
            refuse(f"gate 2: {held_by(host, held)}")
        print(
            f"gate 2: a stale lease on {host}: {held.describe()} — that "
            "run is gone from this machine, so it died without releasing. "
            "Reclaimed; nothing of it is torn down unasked",
            file=sys.stderr,
        )
        held = lease_take(host, mine, held=held)
        if held is None:
            return mine
    refuse(
        f"gate 2: the lease on {host} changed hands three times while this run "
        "tried to take it; last seen: "
        f"{held.describe() if held is not None else 'free'}. Nothing is "
        "measured on a rig that will not hold still"
    )


def main() -> int:
    door_required("gate 2")
    host = need("RUN_HOST")
    return main_user(host)


def main_user(host: str) -> int:
    """Gate 2: the lease, the reading, and the user's rig file.

    The rig file is asked for first, so a run with none reaches no rig. The
    lease is taken first; the rig is then read once, and that one reading is
    both what gate 7 diffs against and what is held to the rig file
    (:func:`rigfile.door_check`).
    """
    saved = rigfile.required(host, "gate 2")
    export("RUN_LEASE", take_lease(host).line())

    document = reading(host)
    live = {**document["snapshot"], **held(host)}
    compose = os.environ.get("RUN_COMPOSE")
    try:
        used = rigfile.cards_used(Path(compose)) if compose else None
    except servelib.ComposeError as exc:
        refuse(f"gate 2: the compose file cannot be read for its cards: {exc}")
    try:
        now = rigfile.from_reading(host, document)
    except rigfile.RigFileError as exc:
        refuse(f"gate 2: {exc}. A machine that cannot be read is not compared")
    rigfile.door_check(host, saved, now, used, "gate 2")

    busy = {key: live.get(key, "(unread)") for key in IDLE_KEYS}
    busy = {key: value for key, value in busy.items() if value != "none"}
    if busy:
        print(
            f"gate 2: {host} was not idle before this run ("
            + ", ".join(f"{key}={value}" for key, value in busy.items())
            + "); what mcgyvr did not start is reported and left as it is, and "
            "gate 7 names whatever this run leaves beyond it"
        )
    export("RUN_PRE_RIG", " ".join(f"{k}={v}" for k, v in sorted(live.items())))
    print(f"gate 2: {host} held to its rig file {rigfile.path(host)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
