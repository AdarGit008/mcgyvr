"""The reads a gate makes of a rig over ssh, and the lease it holds the rig by.

Gate 1 and the door's `read config` ask :func:`config` which config a run is
made under. Gate 2 takes the rig's lease with :func:`take_lease`, reads what the
machine is with :func:`reading`, and reads what is on it with :func:`held`; gate
7 files :func:`snapshot` as the rig's end state. Every one of them is a read:
the readers are shipped over ssh and land nothing on the rig's disk, and the
lease is the one thing written there.

A read that cannot produce a whole answer refuses rather than returning part of
one. A rig that does not answer, a reader that prints a document this does not
take, a `snapshot` missing a card key, and a lease another live run holds each
stop the gate with the rule it was stopped by on stderr, so that no run is
measured on a machine nobody could read.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcgyvr import config as configlib
from mcgyvr.config import LAUNCHER_NATIVE
from mcgyvr.serving import gatelib, nativerig
from mcgyvr.serving.gatelib import (
    LOCAL_RIGS,
    Lease,
    held_by,
    lease_read,
    lease_take,
    need,
    new_lease,
    refuse,
    ssh,
    step_name,
)
from mcgyvr.serving.rigscan import SNAPSHOT_CARD_KEYS

#: The gate scripts beside this module: rig-units.sh is read from here, whole, and
#: sent to the rig.
_GATE_SCRIPTS = Path(__file__).resolve().parent / "gate-scripts"


def config() -> str:
    """The config this run is made under, as its path, or "none" for no config.

    "none" is a run that can still say what it ran under: `MCGYVR_CONFIG` names
    no config and no fleet is live, so the run is under no config at all, which
    gate 1 exports as `RUN_CONFIG=none`. Anything else that keeps the config
    from being read, or from even being named, is refused here instead: a config
    that is there and cannot be read is not a run made under none, and filing it
    as one would file the run under a fleet nobody can name.
    """
    try:
        loaded = configlib.load()
    except configlib.ConfigMissingError as absent:
        if configlib.named_config_path() is not None:
            refuse(
                f"gate 1: {absent}. {configlib.CONFIG_PATH_ENV} names a config "
                "that is not there, and a run made under some other one would "
                "not be the run that was asked for. Nothing is measured under "
                "a config nobody can name"
            )
        return "none"
    except configlib.ConfigError as error:
        refuse(
            f"gate 1: the config cannot be read: {error}. A run whose config "
            "cannot be read cannot say which fleet it ran under, and nothing "
            "is measured under an unknown one"
        )
    except (OSError, RuntimeError) as error:
        # Neither of the two above: the config's own path could not be worked
        # out. `expanduser` raises RuntimeError with no home to expand, resolving
        # raises OSError, and a fleet folder raises FolderError, a RuntimeError.
        refuse(
            f"gate 1: the config cannot be located: {error!r}. Nothing is "
            "measured under a config nobody can name"
        )
    return str(loaded.path)


def reading(host: str) -> dict[str, Any]:
    """What `host` is, as the machine reader on it prints it: the scan document.

    The reader is `rigscan`'s own source, echoed over ssh as base64 and run from
    stdin, so nothing lands on the rig. The document comes back whole or the gate
    refuses: no answer in 180s, a non-zero exit, output that is not one document
    holding a `snapshot`, or a `snapshot` missing one of the card keys are each a
    machine that cannot be read. The reason the reader itself gave for a field it
    could not read is carried into the refusal that names that field.
    """
    sent = gatelib.scan_read(gatelib.shipping_os(host))
    try:
        done = (
            ssh(host, sent.command, timeout=180)
            if sent.stdin is None
            else ssh(host, sent.command, timeout=180, input=sent.stdin)
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
    """What holds `host` right now: its running containers and its card holders.

    `rig-units.sh` is shipped to the rig on the stdin of `bash -s`, so nothing
    lands on its disk and nothing there is started, stopped or leased. Its rows
    are read by `mcgyvr.fleet.read`, the one parser of that format, and come back
    as the two keys gate 2's idle check names, each "none" when there is nothing
    to report. A native run on this machine is read by the native launcher
    instead (:func:`mcgyvr.serving.native.held`): its supervised units stand
    where containers would.
    """
    from mcgyvr.fleet import read

    if os.environ.get("RUN_LAUNCHER") == LAUNCHER_NATIVE and host in LOCAL_RIGS:
        # A native rig is this machine, and its units are no daemon's
        # containers: the native launcher says what holds it, docker unasked.
        from mcgyvr.serving import native

        return native.held()
    if nativerig.remote(host):
        # A macOS or Windows rig runs native units: the launcher shipped to it
        # lists them in rig-units.sh's rows.
        try:
            listed = nativerig.rows(host)
        except nativerig.NativeRigError as exc:
            refuse(
                f"gate 2: {exc}. A rig whose card holders and units are unread "
                "is not compared"
            )
    else:
        units = (_GATE_SCRIPTS / "rig-units.sh").read_text(encoding="utf-8")
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
        listed = done.stdout
    try:
        found = read.parse(listed)
    except read.ReadError as exc:
        refuse(f"gate 2: what holds {host} reads wrong: {exc}")
    # One token each, no spaces and ids cut to docker's short 12: gate 2 exports
    # these as space-separated `key=value` pairs.
    # A native unit's id (native-<pid>) is kept whole: it is no docker id.
    containers = ";".join(
        c.id if c.id.startswith("native-") else c.id[:12] for c in found.containers
    )
    procs = ";".join(
        f"{h.pid},{h.process},{'unread' if h.mib is None else h.mib}MiB"
        for h in found.holders
    )
    return {"gpu_procs": procs or "none", "containers": containers or "none"}


def snapshot(host: str) -> dict[str, str]:
    """The rig's snapshot as gate 7 compares it: its card facts plus what holds it.

    `reading`'s `snapshot` — the card and machine facts `rigscan` prints as plain
    tokens — with `held`'s `gpu_procs` and `containers` laid over it, so one dict
    says both what the rig was and what was running on it.
    """
    return {**reading(host)["snapshot"], **held(host)}


def take_lease(host: str) -> Lease:
    """Take `host`'s lease for this run's step, or refuse while a live run holds it.

    The step is the name of the run's step file without its number. A stale
    lease, one whose process is gone from this machine, is reported on stderr and
    reclaimed with nothing of that run torn down. The lease is taken at most
    three times: a rig whose lease changes hands that often does not hold still,
    and nothing is measured on it.
    """
    step = step_name(Path(need("RUN_STEP_FILE")))
    # The gate's parent, not this script: the gate exits at once, the door stays.
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
