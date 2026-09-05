#!/usr/bin/env python3
"""gate 2 — the live machine equals its declaration.

WHY start==end IS NOT ENOUGH. A step's own check compares the rig with itself
before and after, which catches a machine that moves DURING a run and says
nothing at all about one that moved BEFORE it. RAM moved between srv1 and srv2
twice in six days and every artifact from that window is internally consistent
and wrong. hosts.json[HOST].rig is the declaration — read live on its read_on
date — and every declared key must match now.

The reading is exported for gate 7, which takes a second one after the step and
stamps any key that moved into the artifacts, because rows produced under two
machines have to say so.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import export, need, refuse, root

HERE = Path(__file__).resolve().parent


def snapshot(host: str) -> dict[str, str]:
    """Ship the reader to the rig on stdin and parse `key=value` back.

    On stdin, never installed: nothing lands on the rig's disk, so gate 7 has
    nothing extra to look for. Same transport as ggufscan.
    """
    reader = (HERE / "rig-snapshot.sh").read_text(encoding="utf-8")
    try:
        done = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, "bash -s"],
            input=reader,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
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
    reading: dict[str, str] = {}
    for line in done.stdout.splitlines():
        if not line.strip():
            continue
        if "=" not in line or " " in line:
            refuse(
                f"gate 2: the reader printed {line!r}, which is not one "
                "whitespace-free key=value; a snapshot line must be legal in a "
                "stamp exactly as printed"
            )
        key, _, value = line.partition("=")
        reading[key] = value
    return reading


def main() -> int:
    host = need("RUN_HOST")
    hosts_file = root() / "tools" / "runs" / "hosts.json"
    if not hosts_file.is_file():
        refuse(
            f"gate 2: {hosts_file} is missing; there is no declaration to compare with"
        )
    declared_all = json.loads(hosts_file.read_text(encoding="utf-8"))
    if host not in declared_all or "rig" not in declared_all.get(host, {}):
        known = sorted(
            k for k, v in declared_all.items() if isinstance(v, dict) and "rig" in v
        )
        refuse(
            f"gate 2: --host {host} carries no `rig` declaration in "
            f"tools/runs/hosts.json (declared: {', '.join(known)}). Nothing is "
            "measured on a machine nobody has described"
        )
    declared = declared_all[host]["rig"]

    live = snapshot(host)
    bad = [
        f"{key}: declared {value!r}, reads {live.get(key)!r}"
        for key, value in declared.items()
        if live.get(key) != value
    ]
    if bad:
        refuse(
            f"gate 2: THIS MACHINE IS NOT THE DECLARED {host} — "
            + "; ".join(bad)
            + f". tools/runs/hosts.json[{host}].rig is what the rig was read as "
            f"on {declared_all[host].get('read_on')}; either the wrong --host "
            "was named, or the rig moved before this run. Fix the machine or "
            "re-declare it deliberately"
        )

    # Gate 2b, only where a campaign says it serves: D8's rule is verify the
    # markers and launch as ONE step, so the verification happens here, before
    # any step. 1.5 h of rig time once went to a run whose patch never reached
    # the file it was supposed to patch.
    campaign_json = (
        root() / "tools" / "runs" / "campaigns" / need("RUN_CAMPAIGN") / "campaign.json"
    )
    if campaign_json.is_file():
        doc = json.loads(campaign_json.read_text(encoding="utf-8"))
        if doc.get("serving") is True:
            sys.path.insert(0, str(root()))
            from tools.bench.serving.launch import verify_markers

            problems = verify_markers(root())
            if problems:
                refuse(
                    "gate 2b: the serving harness on disk fails its own "
                    "markers: " + "; ".join(problems)
                )

    # Whitespace-free by construction (the reader's `tok`), so the whole
    # reading survives as one exported line and gate 7 can diff against it.
    export("RUN_PRE_RIG", " ".join(f"{k}={v}" for k, v in sorted(live.items())))
    print(f"gate 2: {host} matches its declaration on {len(declared)} keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
