#!/usr/bin/env python3
# RUN_REWRITES: serve-up.json
"""The door's serve step, up: start every unit the compose file names and
leave it running — the one step whose containers gate 7 expects to find.

Reads the run from the environment the door exports (RUN_COMPOSE is the file
`mcgyvr emit` wrote for RUN_HOST, RUN_SERVE_EXPECTED the container names the
door read out of it), brings the file up through the docker shim — so the
daemon is the rig's — and then asks each unit through the ssh shim whether
it is serving, until it says so or the budget is spent. What it found is
serve-up.json: one row per unit, the card after, and the compose text itself,
so the envelope says exactly what was started and whether it came up.

Serving is two readings and not one: `servelib.wait_for` asks for the model
list and then, where the engine can answer, whether the unit is asleep. A vLLM
unit slept at level 2 lists its models with a 200 and then hangs forever on a
real request (`records/measurements/vllm-sleep-2026-09-09/README.md`), so a
probe that asked only the first question would print `up` here, hand gate 7
exactly the containers it expects, and make the run green over a rig that is
serving nothing.

A unit that never answered is exit 1: a result, not a refusal. So is one that
answered while asleep. Gates 7 and 8 still run — 7 expects the declared names
and names anything else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcgyvr.serving import servelib
from mcgyvr.serving.gatelib import door_required, need


def main() -> int:
    door_required("serve-up")
    host = need("RUN_HOST")
    compose_file = Path(need("RUN_COMPOSE"))
    out = Path(need("RUN_OUT_DIR")) / "serve-up.json"
    try:
        units = servelib.services(compose_file)
    except servelib.ComposeError as exc:
        print(f"serve-up: REFUSED — {exc}", file=sys.stderr)
        return 2
    expected = need("RUN_SERVE_EXPECTED").split()
    if sorted(expected) != sorted(s.container for s in units):
        print(
            "serve-up: REFUSED — the compose file no longer names the containers "
            "the door read from it; nothing is started from a file that changed "
            "under the run",
            file=sys.stderr,
        )
        return 2

    print(f"serve-up: docker compose up on {host}: {', '.join(expected)}")
    started = servelib.compose(compose_file, "up", "-d", "--remove-orphans")
    if started.returncode != 0:
        print(
            f"serve-up: docker compose up failed on {host}: "
            f"{started.stderr.strip()[:800]}",
            file=sys.stderr,
        )
    rows = [servelib.wait_for(host, service) for service in units]
    for row in rows:
        # ASLEEP and NOT ANSWERING are the same exit and different repairs. A
        # unit that never came up wants its container log read; one that is
        # asleep wants a `POST /wake_up`, and its log is clean, so an operator
        # sent to it by the wrong word finds nothing wrong and believes the rig.
        # A sleeping vLLM unit answers /v1/models with 200 and then hangs on a
        # real request (records/measurements/vllm-sleep-2026-09-09/README.md);
        # servelib.wait_for is what stops that reading as `up` at all.
        if row["healthy"]:
            state = "up"
        elif row["sleeping"]:
            state = "ASLEEP"
        else:
            state = "NOT ANSWERING"
        print(
            f"serve-up: {row['container']} :{row['port']} {state} after "
            f"{row['seconds']}s, models={row['models']}"
        )
    record = {
        "run_id": need("RUN_ID"),
        "host": host,
        "mode": "up",
        "compose_file": str(compose_file),
        "compose": compose_file.read_text(encoding="utf-8"),
        "compose_up_exit": started.returncode,
        "units": rows,
        "card_after": servelib.card(host),
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if started.returncode != 0 or not all(row["healthy"] for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
