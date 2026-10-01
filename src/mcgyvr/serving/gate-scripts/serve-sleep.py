#!/usr/bin/env python3
# RUN_REWRITES: serve-sleep.json
"""The door's serve step, sleep: put every unit to sleep and keep it running.

A vLLM unit run with sleep mode can drop its weights and its KV cache from the
card and keep its process: a level-2 sleep (`servelib.sleep`, where level 1 is
banned). The container stays up, the card is free, and a wake reads the
weights back from disk into the same process instead of starting a container.
Gate 7 therefore expects the declared containers still running after this
step, as it does after `serve up`.

Every unit is asked first whether it has a sleep route at all. One that has
none — llama.cpp, or vLLM run without its development routes — has no way to
sleep, so nothing is asked of any unit and the step exits
`gatelib.NO_SLEEP_ROUTE`: the card is as it was, and the caller stops it with
`serve down` instead. A card sleeps whole or not at all. An answer that could
not be read is not a route either; nothing is guessed on a live rig.

A unit asked to sleep that does not then say it is asleep is exit 1, a result.

`serve sleep --unit C` (RUN_SERVE_ONLY) sleeps only the named containers: a
card's co-resident vLLM units are separate processes, and one can sleep to
make room for another. The rest of the card is not asked anything.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from mcgyvr.serving import servelib
from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE, door_required, need


def main() -> int:
    door_required("serve-sleep")
    host = need("RUN_HOST")
    compose_file = Path(need("RUN_COMPOSE"))
    out = Path(need("RUN_OUT_DIR")) / "serve-sleep.json"
    try:
        units = servelib.services(compose_file)
    except servelib.ComposeError as exc:
        print(f"serve-sleep: REFUSED — {exc}", file=sys.stderr)
        return 2
    expected = need("RUN_SERVE_EXPECTED").split()
    if sorted(expected) != sorted(s.container for s in units):
        print(
            "serve-sleep: REFUSED — the compose file no longer names the "
            "containers the door read from it",
            file=sys.stderr,
        )
        return 2

    # `--unit`: the units to sleep, the rest of the card left as it is.
    only = set(os.environ.get("RUN_SERVE_ONLY", "").split())
    units = tuple(s for s in units if not only or s.container in only)
    before = {s.container: servelib.sleeping(host, s.port) for s in units}
    routeless = sorted(
        name for name, said in before.items() if not isinstance(said, bool)
    )
    rows: list[dict[str, object]] = []
    if routeless:
        print(
            f"serve-sleep: {', '.join(routeless)} on {host} has no sleep route; "
            "nothing was asked of any unit, and the card can only be stopped"
        )
        status = NO_SLEEP_ROUTE
    else:
        status = 0
        for service in units:
            asked = servelib.sleep(host, service.port, 2)
            after = servelib.sleeping(host, service.port)
            rows.append(
                {
                    "container": service.container,
                    "port": service.port,
                    "asked": asked,
                    "sleeping": after,
                }
            )
            state = "ASLEEP" if after is True else "NOT ASLEEP"
            print(f"serve-sleep: {service.container} :{service.port} {state}")
            if not asked or after is not True:
                status = 1
    record = {
        "run_id": need("RUN_ID"),
        "host": host,
        "mode": "sleep",
        "compose_file": str(compose_file),
        "only": sorted(only),
        "sleeping_before": before,
        "no_sleep_route": routeless,
        "units": rows,
        "card_after": servelib.card(host),
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
