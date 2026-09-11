#!/usr/bin/env python3
"""M8: read each rig's card reserve, idle, stamped with the boot it was read in.

    reserve.py srv1 srv2

Appends one row per rig to `results-reserve.json`. It refuses to record a rig whose
card holds a process or whose daemon runs a container, because the reserve is
measured idle. Run it once per boot. A reboot is the owner's call, never this
script's.
"""

from __future__ import annotations

import json
import sys
import time

import rig

OUT = rig.SCR / "results-reserve.json"


def main() -> None:
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    for host in sys.argv[1:]:
        apps = rig.gpu_apps(host)
        containers = rig.rig(host, "docker ps -q | wc -l").strip()
        if apps != "none" or containers != "0":
            raise SystemExit(f"{host}: not idle (gpu apps {apps}, containers {containers})")
        card = rig.gpu(host)
        row = {"rig": host, "uptime_since": rig.uptime_since(host), "gpu_name": card["name"],
               "driver": card["driver"], "gpu_reserve_mib": card["reserved"],
               "gpu_used_mib": card["used"], "gpu_free_mib": card["free"],
               "gpu_total_mib": card["total"], "gpu_procs": apps,
               "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rows.append(row)
        print(json.dumps(row))
    OUT.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
