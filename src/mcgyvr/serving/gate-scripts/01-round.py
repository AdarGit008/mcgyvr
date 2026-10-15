#!/usr/bin/env python3
"""gate 1 — name the config this run is under.

Runs first and reaches no rig, so the config is settled before any rig time
is spent. The config is the one `mcgyvr` itself would load — `$MCGYVR_CONFIG`,
else the live fleet folder the config folder's `live.json` names — and where
it was read from is exported as RUN_CONFIG. No config at all is the live
fleet's (owner's ruling R4: the default is prod, and forgetting the variable
lands there); a config that is there and cannot be read, or a
`$MCGYVR_CONFIG` naming a file that is not there, is a refusal, because a run
whose config cannot be read cannot say which fleet it ran under. A run held
to the live lock (:func:`mcgyvr.fleet.roots.runs_live`: whenever a fleet is
live, but under a setup in the data folder) has a `serve up` admitted only for
units the fleet lock names for this rig, and a `serve down` always; any other
— the staging folder `mcgyvr setup` starts and samples, which nothing has
locked yet — runs everything, `serve up` and `down` included (the owner ruled
N11 on 2026-09-10).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcgyvr import config as configlib
from mcgyvr.fleet.admit import unsampled_containers
from mcgyvr.fleet.roots import (
    LOCK_DIR,
    LiveFleetError,
    live_file,
    live_fleet_dir,
    runs_live,
)
from mcgyvr.serving.gatelib import (
    door_required,
    export,
    refuse,
)


def config() -> str:
    """Where the run's config was read from: ``none`` when there is no config.

    Refuses on a config that is there and cannot be read, and on a named
    (``$MCGYVR_CONFIG``) config that is not there: both are files somebody
    chose, and a run that went on under some other config would be the
    silent landing gate 1 exists to prevent. The absent *default* is the one
    silence: nobody chose it, and it is the live fleet's.
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
        # A `~nobody` in the variable, a working directory that went away:
        # a config the gate cannot even locate is refused with the reason,
        # not left as a traceback.
        refuse(
            f"gate 1: the config cannot be located: {error!r}. Nothing is "
            "measured under a config nobody can name"
        )
    return str(loaded.path)


def units_the_fleet_lock_names(rig: str) -> set[str]:
    """The containers the live fleet lock names for ``rig``.

    The lock's combination records under its rigs tree name each locked unit
    by its container, under the live fleet's folder
    (:func:`mcgyvr.fleet.roots.live_fleet_dir`: the fleet folder the config
    folder's ``live.json`` names, and no lock at all without one) and never
    under the run root. Gate 1 reaches no rig, so this is a read of local
    files only: a live serve up is matched against the lock offline, before
    any rig time is spent.

    A lock approved on no evidence (``mcgyvr setup``'s own, written by
    :func:`mcgyvr.fleet.lock.write_unsampled`) has no combination record; its
    containers are the ones its layout places on ``rig``, and only while the
    ``fleet.yaml`` beside it still hashes to its pin
    (:func:`mcgyvr.fleet.admit.unsampled_containers`).
    """
    try:
        where = live_fleet_dir()
    except LiveFleetError as exc:
        refuse(f"gate 1: {exc}. A live run cannot say which fleet it serves")
    if where is None:
        return set()
    # A lock approved on no evidence writes no record, as nothing was
    # validated; for it the pinned layout answers, by the rule the waker reads
    # (`mcgyvr.fleet.admit.host_is_locked`).
    locked = unsampled_containers(where, rig)
    rigs = where / LOCK_DIR / "rigs"
    if not rigs.is_dir():
        return locked
    for path in sorted(rigs.glob("*/cmb-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("rig") != rig:
            continue
        approved = record.get("approved")
        if not isinstance(approved, dict):
            continue
        for entry in approved.values():
            if not isinstance(entry, dict):
                continue
            container = entry.get("container")
            if isinstance(container, str) and container:
                locked.add(container)
    return locked


def refuse_unless_the_fleet_lock_names(serve: str, source: str) -> None:
    """A live ``serve up`` admits only units the fleet lock names for this rig.

    A run that is not held to the live lock (``source``, the config's folder,
    and :func:`mcgyvr.fleet.roots.runs_live`) runs everything,
    ``serve up`` and ``down`` included (the owner ruled N11 on 2026-09-10),
    and a live ``serve down`` is always admitted: stopping
    starts nothing unapproved, and it is the way out of a rig left in a state
    nobody locked. A live ``serve up`` is the one direction that starts
    processes, so it is matched against the fleet lock here
    (:func:`units_the_fleet_lock_names`) — offline, before any rig is read.
    A ``serve up --unit`` starts only the units it names, so only those are
    matched; a ``serve fetch`` starts nothing.
    """
    # No config at all is the live fleet's (owner's ruling R4): held to the
    # lock, live or not, which refuses every unit of a fleet nobody named live.
    if serve != "up" or (source != "none" and not runs_live(Path(source))):
        return
    host = os.environ.get("RUN_HOST", "")
    wanted = set(os.environ.get("RUN_SERVE_ONLY", "").split()) or set(
        os.environ.get("RUN_SERVE_EXPECTED", "").split()
    )
    locked = units_the_fleet_lock_names(host)
    missing = sorted(wanted - locked)
    if missing:
        refuse(
            f"gate 1: this live `serve up` names {', '.join(missing)}, which "
            f"the fleet lock for {host} does not name. A live run starts only "
            f"units the live fleet lock names — the fleet {live_file()} "
            "names; lock them with `mcgyvr setup`, and `mcgyvr fleet use` the "
            "fleet"
        )


def main() -> int:
    door_required("gate 1")
    source = config()
    serve = os.environ.get("RUN_SERVE")
    if serve:
        refuse_unless_the_fleet_lock_names(serve, source)

    export("RUN_CONFIG", source)
    print(f"gate 1: config={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
