#!/usr/bin/env python3
# Gate 2 of a serve run: the rig is leased to this run, read again, and held to
# the user's rig file.
"""Gate 2: the rig is leased, read again, and held to the user's rig file.

The door names the rig (``RUN_HOST``). This gate takes the rig's lease first
and exports it as ``RUN_LEASE``, so a rig another live run holds is refused
here, untouched, while a dead run's stale lease is reclaimed with a note on
stderr. It then reads the rig twice: the one machine reader
(:mod:`mcgyvr.serving.rigread.reading`) for the facts the rig file records,
and the runtime reader (``rig-units.sh``, on stdin to ``bash -s``) for the
processes holding the card and the containers up.

**Held to the user's rig file, never rewritten.** The saved file
(:func:`mcgyvr.serving.rigfile.required`, written by ``mcgyvr scan --rig``) is
required before the lease is taken, so a rig nobody described is refused
before it is claimed. The fresh reading is compared to it
(:func:`mcgyvr.serving.rigfile.door_check`): what moved is printed, and the
run is refused only when the fleet no longer fits — a card the compose file
uses is gone, or it holds less VRAM than the file records. The cards the
compose file asks for are :func:`mcgyvr.serving.rigfile.cards_used`, or every
recorded card when no compose file is named.

**Read, not tidied.** Whatever already held the rig before the run is printed
and left as it is, and the whole reading is exported as ``RUN_PRE_RIG``
(space-separated ``key=value``) for gate 3's hostname and gate 7's
before/after comparison, which names what this run leaves beyond it.
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

#: The runtime reading's two keys that say whether the rig was already busy: the
#: processes holding a card ("pid,process,MiB" each) and the containers up
#: ("<first 12 characters of the id>" each). rigread.held() says "none" for
#: either when it found nothing there, and a key the reading does not carry at
#: all is reported as "(unread)"; only the keys that are not "none" are named.
IDLE_KEYS = ("gpu_procs", "containers")


def main() -> int:
    door_required("gate 2")
    host = need("RUN_HOST")
    return main_user(host)


def main_user(host: str) -> int:
    """Lease the rig, read it, hold it to its rig file; 0 when the run may go on.

    The rig file is required before anything is claimed, then the lease is
    taken and exported as ``RUN_LEASE``. The fresh reading is the snapshot's
    facts overlaid with what holds the rig now, and it is compared to the saved
    file against the cards the compose file asks for: what moved is said, and
    the run is refused when the fleet no longer fits. A rig that was not idle
    is said and left as it is, the whole reading is exported as
    ``RUN_PRE_RIG``, and the rig file the run was held to is named.
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
