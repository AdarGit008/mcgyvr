#!/usr/bin/env python3
"""Tear down whatever a host was last brought up with, using last-up (authoritative).

Run after every arm: each host's `logs/last-up-<host>.txt` names the compose the
last arm used, so this empties both rigs again regardless of which runner ran last.
"""
from __future__ import annotations

import rig

for host in ("srv1", "srv2"):
    last = rig.last_up(host)
    if not last:
        print(f"{host}: no last-up marker, nothing to tear down")
        continue
    proc = rig.door_or_die("down", host, last, f"final-{host}")
    print(f"{host}: tore down {last} (rc={proc.returncode})")
    print(proc.stdout[-800:])
