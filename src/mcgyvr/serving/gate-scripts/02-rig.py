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

THE RIG IS LEASED HERE, before it is read. Gate 5's claim on the RUN_ID is per
envelope, so two steps — or a laptop and srv1 — could still land on one rig
together; the contended resource is the rig, so the lease sits on it, at
``~/.mcgyvr/lease``, and every run takes it before it spends rig time. Under a
``dev`` profile a held rig is a refusal naming the holder and since when
(owner's ruling R1, 2026-09-06: live outranks dev). Under ``live`` the lease is
taken whatever holds it, the displaced run is named, and its containers — by
the run id its lease carries — are removed here, so this run's step opens on
an idle rig, and again by gate 7 for anything that came back. A lease whose
holder is a pid on this machine that is gone is stale: named, not silently
ignored, and taken. The door releases the lease on every way out, and the
shims refuse a displaced run's next touch of the rig, so dev yields by the
machine and not by convention.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import (
    DEV,
    Lease,
    door_required,
    export,
    lease_read,
    lease_take,
    need,
    new_lease,
    refuse,
    root,
    ssh,
)

HERE = Path(__file__).resolve().parent

#: What the reader prints beyond the declared keys that must read `none`: a
#: card held by a process, or a container up, before the step starts, is a
#: machine somebody else is using. Run contract §4 — a cell never repairs a
#: machine it found wrong — so the refusal names them and leaves them.
IDLE_KEYS = ("gpu_procs", "containers")


def snapshot(host: str) -> dict[str, str]:
    """Ship the reader to the rig on stdin and parse `key=value` back.

    On stdin, never installed: nothing lands on the rig's disk, so gate 7 has
    nothing extra to look for. Same transport as ggufscan.
    """
    reader = (HERE / "rig-snapshot.sh").read_text(encoding="utf-8")
    try:
        done = ssh(host, "bash -s", timeout=180, input=reader)
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


def teardown_displaced(host: str, displaced: Lease, who: str) -> None:
    """Remove the containers a displaced run left, by the name its lease gave it.

    The one place the door removes a container it did not start, and the
    exception is the point: run contract §4 says a cell never repairs a
    machine it found wrong, because it cannot know what it found — here it
    can. The lease names the run, the run names its containers
    (`<RUN_ID>-<role>`), and R1 says the live run may take the rig from it.
    """
    if displaced.run_id == "none":
        print(f"{who}: the displaced run had minted no run id; nothing to tear down")
        return
    prefix = f"{displaced.run_id}-"
    try:
        listed = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        listed = None
    if listed is None or listed.returncode != 0:
        print(
            f"{who}: the daemon on {host} could not be asked for the displaced "
            f"run's containers; any named {prefix}* are still up",
            file=sys.stderr,
        )
        return
    names = [n.strip() for n in listed.stdout.splitlines() if n.startswith(prefix)]
    if not names:
        print(f"{who}: nothing of the displaced run ({displaced.run_id}) is up")
        return
    removed = subprocess.run(
        ["docker", "rm", "-f", *names],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if removed.returncode != 0:
        print(
            f"{who}: could not remove {' '.join(names)}: "
            f"{removed.stderr.strip()[:300]}",
            file=sys.stderr,
        )
        return
    print(
        f"{who}: torn down what this live run displaced ({displaced.holder}, "
        f"run {displaced.run_id}): {' '.join(names)}"
    )


def take_lease(host: str) -> tuple[Lease, Lease | None]:
    """This run's lease on ``host``, and the lease it displaced, if any."""
    profile = need("RUN_PROFILE")
    step_name = re.sub(r"^\d+-", "", Path(need("RUN_STEP_FILE")).stem)
    # The door's pid, not this gate's: the gate exits, the door holds the run.
    mine = new_lease(profile, need("RUN_CAMPAIGN"), step_name, os.getppid())
    held = lease_read(host)
    if held is None:
        held = lease_take(host, mine, displace=False)
        if held is None:
            return mine, None
    if held.lease_id == mine.lease_id:
        return mine, None
    if held.is_stale():
        print(
            f"gate 2: a stale lease on {host}: {held.describe()} — that pid is "
            "gone from this machine, so the run died without releasing. Taken "
            "over; nothing of it is torn down unasked",
            file=sys.stderr,
        )
        lease_take(host, mine, displace=True)
        return mine, None
    if profile == DEV:
        refuse(
            f"gate 2: {host} is leased by {held.describe()}, and this run is "
            "under a dev profile: dev yields, live outranks dev (owner's ruling "
            "R1, 2026-09-06). Wait for that run, or run under the live config "
            "if this IS the live run"
        )
    print(
        f"gate 2: {host} is leased by {held.describe()}; this live run takes "
        "it (R1) and tears down what it displaced"
    )
    lease_take(host, mine, displace=True)
    return mine, held


def main() -> int:
    door_required("gate 2")
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

    # The lease first: it is what makes the reading below this run's to act
    # on. Exported before the reading so the door can release it on every
    # exit path from here on, a refusal of the reading included.
    mine, displaced = take_lease(host)
    export("RUN_LEASE", mine.line())
    export("RUN_DISPLACED", displaced.line() if displaced is not None else "")
    if displaced is not None:
        teardown_displaced(host, displaced, "gate 2")

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

    busy = {key: live.get(key, "(unread)") for key in IDLE_KEYS}
    busy = {key: value for key, value in busy.items() if value != "none"}
    if os.environ.get("RUN_SERVE") == "down":
        # Taking a live ladder down is the one run that opens on a busy rig by
        # design: the units it is here to stop hold the card and the daemon.
        # Nothing is admitted on that account beyond the run itself — gate 7
        # expects an EMPTY daemon after this mode's step and names whatever
        # is still up, ours or not.
        if busy:
            print(
                f"gate 2: {host} is serving ("
                + ", ".join(f"{key}={value}" for key, value in busy.items())
                + "); serve down opens on it to stop that, and gate 7 requires "
                "nothing left"
            )
        busy = {}
    if busy:
        refuse(
            f"gate 2: {host} is not idle — "
            + ", ".join(f"{key}={value}" for key, value in busy.items())
            + ". Nothing is measured on a card or a daemon something else is "
            "using, and the door does not clean a machine it found busy: kill "
            "what you started; okf/must-read/touching-rigs.md"
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
