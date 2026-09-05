#!/usr/bin/env python3
"""The rig's own account of itself, filed in the envelope.

Gate 2 already read the machine and compared it with a declaration. This writes
that reading down as JSON where the placement scripts and the operator can both
reach it, and adds the two numbers a placement needs that no declaration
carries because they move minute to minute: what the card has free, and what
system memory is available.

WHY `free` AND NOT `total - reserved`. A card has four buckets — total =
reserved + used + free — and the two agree only on an idle card. Measured on
srv1 2026-09-04: foreign processes held 3,374 MiB with no container of ours
running, leaving 2,370 free against a 5,743 total-less-reserve. Deriving a
placement from the larger number puts experts on a card with no room for them,
and the cell OOMs at load having passed every gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, export, need, refuse


def main() -> int:
    door_required("the scan")
    reading = dict(
        pair.split("=", 1) for pair in need("RUN_PRE_RIG").split(" ") if "=" in pair
    )
    for key in ("gpu_free_mib", "gpu_vram_mib", "gpu_reserve_mib", "mem_available_kib"):
        if reading.get(key, "NA") == "NA" or not reading.get(key, "").isdigit():
            refuse(
                f"the scan has no usable {key} ({reading.get(key)!r}); a "
                "placement derived from a card or a host it could not read is "
                "a guess wearing a measurement's clothes"
            )

    free_mib = int(reading["gpu_free_mib"])
    total_mib = int(reading["gpu_vram_mib"])
    reserved_mib = int(reading["gpu_reserve_mib"])
    used_mib = int(reading.get("gpu_used_mib", "0"))
    scan = {
        "host": need("RUN_HOST"),
        "run_id": need("RUN_ID"),
        "uptime_since": reading.get("uptime_since"),
        "gpu": {
            "name": reading.get("gpu_name"),
            "total_mib": total_mib,
            "reserved_mib": reserved_mib,
            "used_mib": used_mib,
            # The only VRAM figure a placement may spend.
            "free_mib": free_mib,
            "driver": reading.get("driver"),
            "compute_cap": reading.get("gpu_cc"),
        },
        "host_mem_available_mib": int(reading["mem_available_kib"]) // 1024,
        "nproc": reading.get("nproc"),
        "docker": reading.get("docker"),
        "cpu_model": reading.get("cpu_model"),
        "cpu_max_mhz": reading.get("cpu_max_mhz"),
        "ram_mt_s": reading.get("ram_mt_s"),
        "pl1_uw": reading.get("pl1_uw"),
        "pl2_uw": reading.get("pl2_uw"),
    }
    # A card held by somebody else is not an error — run contract §4 says a cell
    # never repairs a machine it found wrong — but it IS the difference between
    # the two VRAM numbers, so it is said out loud rather than left in the JSON.
    if used_mib > 64:
        print(
            f"data-10-scan: {used_mib} MiB of the card is held by something "
            f"this run did not start; the placement gets free={free_mib} MiB, "
            f"not total-less-reserve={total_mib - reserved_mib}"
        )

    out = Path(need("RUN_OUT_DIR")) / "scan.json"
    out.write_text(json.dumps(scan, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    export("RUN_SCAN_JSON", out)
    print(
        f"data-10-scan: card free={free_mib} MiB, "
        f"host available={scan['host_mem_available_mib']} MiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
