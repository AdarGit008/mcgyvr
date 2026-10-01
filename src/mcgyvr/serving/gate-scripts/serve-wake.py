#!/usr/bin/env python3
# RUN_REWRITES: serve-wake.json
"""The door's serve step, wake: bring back every unit `serve sleep` put to sleep.

The inverse of serve-sleep. Each unit that says it is asleep is woken through
vLLM's three wake calls (`servelib.wake`: weights back, weights read from disk,
KV cache back), and then every unit is polled until it serves, as `serve up`
polls after a start. No container is started: a unit that is not running is
not one this step can wake, and the poll reports it as not answering.

Exit 1 when a wake call failed or a unit did not come back to serving.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcgyvr.serving import servelib
from mcgyvr.serving.gatelib import door_required, need


def main() -> int:
    door_required("serve-wake")
    host = need("RUN_HOST")
    compose_file = Path(need("RUN_COMPOSE"))
    out = Path(need("RUN_OUT_DIR")) / "serve-wake.json"
    try:
        units = servelib.services(compose_file)
    except servelib.ComposeError as exc:
        print(f"serve-wake: REFUSED — {exc}", file=sys.stderr)
        return 2
    expected = need("RUN_SERVE_EXPECTED").split()
    if sorted(expected) != sorted(s.container for s in units):
        print(
            "serve-wake: REFUSED — the compose file no longer names the "
            "containers the door read from it",
            file=sys.stderr,
        )
        return 2

    woken: dict[str, bool | None] = {}
    for service in units:
        if servelib.sleeping(host, service.port) is True:
            print(f"serve-wake: waking {service.container} :{service.port}")
            woken[service.container] = servelib.wake(host, service.port)
        else:
            woken[service.container] = None
    rows = [servelib.wait_for(host, service) for service in units]
    for row in rows:
        state = "up" if row["healthy"] else "NOT SERVING"
        print(
            f"serve-wake: {row['container']} :{row['port']} {state} after "
            f"{row['seconds']}s"
        )
    record = {
        "run_id": need("RUN_ID"),
        "host": host,
        "mode": "wake",
        "compose_file": str(compose_file),
        "woken": woken,
        "units": rows,
        "card_after": servelib.card(host),
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if any(ok is False for ok in woken.values()):
        return 1
    if not all(row["healthy"] for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
