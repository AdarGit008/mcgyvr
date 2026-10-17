#
""

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
    ""
    try:
        where = live_fleet_dir()
    except LiveFleetError as exc:
        refuse(f"gate 1: {exc}. A live run cannot say which fleet it serves")
    if where is None:
        return set()
    #
    #
    #
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
    ""
    #
    #
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
