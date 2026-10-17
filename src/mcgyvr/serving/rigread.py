""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcgyvr import config as configlib
from mcgyvr.serving.gatelib import (
    Lease,
    held_by,
    lease_read,
    lease_take,
    need,
    new_lease,
    refuse,
    scan_read_command,
    ssh,
    step_name,
)
from mcgyvr.serving.rigscan import SNAPSHOT_CARD_KEYS

#
_GATE_SCRIPTS = Path(__file__).resolve().parent / "gate-scripts"


def config() -> str:
    ""
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
        #
        #
        #
        refuse(
            f"gate 1: the config cannot be located: {error!r}. Nothing is "
            "measured under a config nobody can name"
        )
    return str(loaded.path)


def reading(host: str) -> dict[str, Any]:
    ""
    try:
        done = ssh(host, scan_read_command(), timeout=180)
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
    ""
    from mcgyvr.fleet import read

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
    try:
        found = read.parse(done.stdout)
    except read.ReadError as exc:
        refuse(f"gate 2: what holds {host} reads wrong: {exc}")
    #
    containers = ";".join(c.id[:12] for c in found.containers)
    procs = ";".join(
        f"{h.pid},{h.process},{'unread' if h.mib is None else h.mib}MiB"
        for h in found.holders
    )
    return {"gpu_procs": procs or "none", "containers": containers or "none"}


def snapshot(host: str) -> dict[str, str]:
    ""
    return {**reading(host)["snapshot"], **held(host)}


def take_lease(host: str) -> Lease:
    ""
    step = step_name(Path(need("RUN_STEP_FILE")))
    #
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
