#!/usr/bin/env python3
# Gate 1 of the serving sequence: the first gate, and the only one run before
# anything reaches a rig.
"""Name the config the run is under, and keep a live ``serve up`` to the fleet lock.

The gate asks :func:`mcgyvr.serving.rigread.config` which config the run was
made under — a path, or ``"none"`` when no config is named — and refuses when a
named config is missing, unreadable or unlocatable, since a run that cannot say
which fleet it serves is not measured. It then holds a live ``serve up`` to the
containers the live fleet lock names for the rig, and exports the config path as
``RUN_CONFIG`` for the gates that follow. No gate 1 path reaches a machine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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
from mcgyvr.serving.rigread import config


def units_the_fleet_lock_names(rig: str) -> set[str]:
    """The containers the live fleet lock names for ``rig``.

    A live run that names no live fleet names nothing; one that cannot say which
    fleet it serves is refused rather than read as unlocked. Otherwise the
    answer is two unions: the containers the lock's layout pins on ``rig``
    (:func:`mcgyvr.fleet.admit.unsampled_containers`), and the ``container`` of
    every approved unit in the lock's ``rigs/*/cmb-*.json`` combination records
    whose ``rig`` is ``rig``. A record that cannot be read or parsed, or one
    that carries no approved mapping, names nothing and is stepped over.
    """
    try:
        where = live_fleet_dir()
    except LiveFleetError as exc:
        refuse(f"gate 1: {exc}. A live run cannot say which fleet it serves")
    if where is None:
        return set()
    # A lock approved on no evidence writes no combination record, so the
    # containers it lays out on this rig are the only thing that names them.
    # A lock measured from dev evidence names its containers per unit inside
    # the combination records below, one record per validated setup.
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
    """Refuse a live ``serve up`` whose units the fleet lock for the rig does not name.

    Only ``up`` is judged: ``serve down`` starts nothing unapproved and is the
    way out of a rig left in a state nobody locked. A run whose setup folder is
    not live (staged under the data home, or shown by ``runs_live`` not to be
    the live fleet) is not judged either, but a run that named no config at all
    (``source`` is ``"none"``) cannot be shown to be staged and is judged as
    live, as is one whose liveness cannot be settled.
    """
    # The units wanted are the ones `--unit` named (RUN_SERVE_ONLY), or, when
    # `--unit` named none, every container the compose file declares
    # (RUN_SERVE_EXPECTED); each is a container name, and the lock is read for
    # the rig the door named in RUN_HOST.
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
