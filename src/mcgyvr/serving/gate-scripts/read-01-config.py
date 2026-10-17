#!/usr/bin/env python3
# Read, config: the read sequence's first entry, and all this script does —
# settle which config the read is under and export it, before any rig is read.
"""Read, config — the config a read is under, exported as ``RUN_CONFIG``.

`read`'s first entry, run by the door before read-02-rig.py. :func:`config`
(:mod:`mcgyvr.serving.rigread`) loads the setup the read runs under — the one
``$MCGYVR_CONFIG`` names, else the live fleet directory — and this script
exports its path through ``RUN_EXPORT_FD``, so the door hands it to the next
entry as ``RUN_CONFIG``. With no setup at all it exports ``none``, and
read-02-rig.py files its rows without a setup folder.

**Refused, not defaulted.** A setup named and not there, a setup that cannot be
read, or one that cannot be located stops the read here, as it stops a serve
run at gate 1: nothing is exported, and no rig is read.

Nothing reaches a rig — no ssh, no lease, no envelope, no teardown. The script
refuses unless an ancestor is the door and this run was exported to it, prints
``read: config=<path|none>``, and exits 0.
"""

from __future__ import annotations

from mcgyvr.serving.gatelib import door_required, export
from mcgyvr.serving.rigread import config


def main() -> int:
    door_required("read config")
    source = config()
    export("RUN_CONFIG", source)
    print(f"read: config={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
