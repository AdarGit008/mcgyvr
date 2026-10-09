#!/usr/bin/env python3
"""gate 2 — the live machine is the rig the user's file describes.

WHY start==end IS NOT ENOUGH. A step's own check compares the rig with itself
before and after, which catches a machine that moves DURING a run and says
nothing at all about one that moved BEFORE it. The user's rig file is the
declaration — the rig as `mcgyvr scan --rig` saved it — and the rig is scanned
again here and held to that file (:mod:`mcgyvr.serving.rigfile`): what moved
is said, and the run is refused only when the fleet no longer fits.

The reading is exported for gate 7, which takes a second one after the step and
stamps any key that moved into the artifacts, because rows produced under two
machines have to say so.

THE RIG IS LEASED HERE, before it is read. Gate 5's claim on the RUN_ID is per
envelope, so two steps could still land on one rig together; the contended
resource is the rig, so the lease sits on it, at ``~/.mcgyvr/lease``, and every
run takes it before it spends rig time. Under a ``dev`` profile a held rig is a
refusal naming the holder and since when (owner's ruling R1, 2026-09-06: live
outranks dev). Under ``live`` the lease is taken whatever holds it, the
displaced run is named, and its containers — by the run id its lease carries —
are removed here, so this run's step opens on an idle rig, and again by gate 7
for anything that came back. A lease whose holder is a pid on this machine that
is gone is stale: named, not silently ignored, and taken. The door releases the
lease on every way out, and the shims refuse a displaced run's next touch of
the rig, so dev yields by the machine and not by convention.

A machine that is not idle is not refused: a container or a card holder up
before the run is reported and left as it is, since mcgyvr did not start it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving import rigfile, servelib
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
    ssh,
    step_name,
)

HERE = Path(__file__).resolve().parent

#: What the reader prints beyond the declared keys that must read `none`: a
#: card held by a process, or a container up, before the step starts, is a
#: machine somebody else is using. The door does not repair a machine it
#: found wrong, so the run names them and leaves them.
IDLE_KEYS = ("gpu_procs", "containers")


def snapshot(host: str) -> dict[str, str]:
    """Ship the reader to the rig on stdin and parse `key=value` back.

    On stdin, never installed: nothing lands on the rig's disk, so gate 7 has
    nothing extra to look for.
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


def teardown_displaced(
    host: str, displaced: Lease, who: str, keep: frozenset[str] = frozenset()
) -> None:
    """Remove the containers a displaced run left, by the names that are ours.

    The one place the door removes a container it did not start, and the
    exception is the point: the door does not repair a machine it found wrong,
    because it cannot know what it found — here it can. The lease names the
    run, the run names its containers (`<RUN_ID>-<role>`), and its serve units
    are named `mcgyvr-<host>-<service>` (`mcgyvr emit`), so both prefixes are
    torn down: R1 says the live run may take the rig from it, and a displaced
    dev serve must not keep holding the card.

    ``keep`` names containers that are not the displaced run's whatever their
    prefix: the units a live ``serve up`` has itself just started, which carry
    the same ``mcgyvr-`` prefix as the dev serve it displaced.
    """
    if displaced.run_id == "none":
        print(f"{who}: the displaced run had minted no run id; nothing to tear down")
        return
    prefixes = (f"{displaced.run_id}-", "mcgyvr-")
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
            f"run's containers; any named {displaced.run_id}-* or mcgyvr-* "
            "are still up",
            file=sys.stderr,
        )
        return
    names = [
        n.strip()
        for n in listed.stdout.splitlines()
        if n.startswith(prefixes) and n.strip() not in keep
    ]
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
    """This run's lease on ``host``, and the lease it displaced, if any.

    Judged and written in a loop, because the rig is shared: what was read
    can change before it is written over, and a write that finds a
    different holder comes back to be judged again rather than overwriting
    a run that was never named. Three changes of hands and the run gives up
    naming the last one.
    """
    profile = need("RUN_PROFILE")
    step = step_name(Path(need("RUN_STEP_FILE")))
    # The door's pid, not this gate's: the gate exits, the door holds the run.
    mine = new_lease(profile, need("RUN_CAMPAIGN"), step, os.getppid())
    held = lease_read(host)
    for _ in range(3):
        if held is None:
            held = lease_take(host, mine, held=None)
            if held is None:
                return mine, None
            continue
        if held.lease_id == mine.lease_id:
            return mine, None
        if held.is_stale():
            print(
                f"gate 2: a stale lease on {host}: {held.describe()} — that "
                "run is gone from this machine, so it died without releasing. "
                "Taken over; nothing of it is torn down unasked",
                file=sys.stderr,
            )
            held = lease_take(host, mine, held=held)
            if held is None:
                return mine, None
            continue
        if profile == DEV:
            refuse(
                f"gate 2: {host} is leased by {held.describe()}, and this run "
                "is under a dev profile: dev yields, live outranks dev (owner's "
                "ruling R1, 2026-09-06). Wait for that run, or run under the "
                "live config if this IS the live run"
            )
        print(
            f"gate 2: {host} is leased by {held.describe()}; this live run "
            "takes it (R1) and tears down what it displaced"
        )
        displaced = held
        held = lease_take(host, mine, held=held)
        if held is None:
            return mine, displaced
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
    lease and the reading gate 7 diffs against are taken first; the rig is
    then scanned again and held to its file (:func:`rigfile.door_check`).
    """
    saved = rigfile.required(host, "gate 2")
    mine, displaced = take_lease(host)
    export("RUN_LEASE", mine.line())
    export("RUN_DISPLACED", displaced.raw if displaced is not None else "")
    if displaced is not None:
        teardown_displaced(host, displaced, "gate 2")

    live = snapshot(host)
    compose = os.environ.get("RUN_COMPOSE")
    try:
        used = rigfile.cards_used(Path(compose)) if compose else None
    except servelib.ComposeError as exc:
        refuse(f"gate 2: the compose file cannot be read for its cards: {exc}")
    rigfile.door_check(host, saved, used, "gate 2")

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
