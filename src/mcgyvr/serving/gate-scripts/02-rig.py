#
""

from __future__ import annotations

import os
from pathlib import Path

from mcgyvr.serving import rigfile, servelib
from mcgyvr.serving.gatelib import (
    door_required,
    export,
    need,
    refuse,
)
from mcgyvr.serving.rigread import held, reading, take_lease

HERE = Path(__file__).resolve().parent

#
#
#
#
IDLE_KEYS = ("gpu_procs", "containers")


def main() -> int:
    door_required("gate 2")
    host = need("RUN_HOST")
    return main_user(host)


def main_user(host: str) -> int:
    ""
    saved = rigfile.required(host, "gate 2")
    export("RUN_LEASE", take_lease(host).line())

    document = reading(host)
    live = {**document["snapshot"], **held(host)}
    compose = os.environ.get("RUN_COMPOSE")
    try:
        used = rigfile.cards_used(Path(compose)) if compose else None
    except servelib.ComposeError as exc:
        refuse(f"gate 2: the compose file cannot be read for its cards: {exc}")
    try:
        now = rigfile.from_reading(host, document)
    except rigfile.RigFileError as exc:
        refuse(f"gate 2: {exc}. A machine that cannot be read is not compared")
    rigfile.door_check(host, saved, now, used, "gate 2")

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
