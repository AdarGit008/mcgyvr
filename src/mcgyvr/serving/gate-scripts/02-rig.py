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

import os
from pathlib import Path

from mcgyvr.serving import rigfile, servelib
from mcgyvr.serving.gatelib import (
    door_required,
    export,
    need,
    refuse,
)
from mcgyvr.serving.rigread import held, reading, take_lease

HERE = Path(__file__).resolve().parent

#: The runtime readings that must read `none` for an idle rig: a card held by
#: a process, or a container up, before the step starts, is a machine somebody
#: else is using. The door does not repair a machine it found wrong, so the run
#: names them and leaves them.
IDLE_KEYS = ("gpu_procs", "containers")


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
