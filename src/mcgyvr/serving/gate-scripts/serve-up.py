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
real request (the lab's vllm-sleep measurement), so a
probe that asked only the first question would print `up` here, hand gate 7
exactly the containers it expects, and make the run green over a rig that is
serving nothing.

A unit that never answered is exit 1: a result, not a refusal. So is one that
answered while asleep. Gates 7 and 8 still run — 7 expects the declared names
and names anything else.

`serve up --unit C` (RUN_SERVE_ONLY) starts only the named containers, by
their compose services, with `--no-deps`: a neighbour the file orders ahead
of it is not started with it, and the file's other units are left as they
are, up or not (:func:`mcgyvr.serving.servelib.up`). This is how a unit that
cannot sleep is woken in a swap: its container is started.

A service under a compose profile starts asleep (a swap partner,
`role: sleeps-until-needed`): a whole `up` leaves it down, so it is not waited
for, and only naming it starts it.
"""

from __future__ import annotations

import sys

from mcgyvr.serving import servelib


def main() -> int:
    ctx = servelib.serve_prologue(
        "up",
        verify_refusal="; nothing is started from a file that changed under the run",
    )
    if ctx is None:
        return 2

    only = ctx.only
    # Named units alone; else the file's awake set, which is what a whole
    # `compose up` starts.
    if only:
        units = tuple(s for s in ctx.units if s.container in only)
    else:
        units = tuple(s for s in ctx.units if not s.asleep)
    names = [s.container for s in units]
    print(f"serve-up: docker compose up on {ctx.host}: {', '.join(names)}")
    started = servelib.up(ctx.compose_file, units if only else ())
    if started.returncode != 0:
        print(
            f"serve-up: docker compose up failed on {ctx.host}: "
            f"{started.stderr.strip()[:800]}",
            file=sys.stderr,
        )
    rows = [servelib.wait_for(ctx.host, service) for service in units]
    for row in rows:
        # ASLEEP and NOT ANSWERING are the same exit and different repairs. A
        # unit that never came up wants its container log read; one that is
        # asleep wants a wake (servelib.wait_for names the calls), and its log
        # is clean, so an operator sent to it by the wrong word finds nothing
        # wrong and believes the rig.
        # A sleeping vLLM unit answers /v1/models with 200 and then hangs on a
        # real request (the lab's vllm-sleep measurement); servelib.wait_for
        # is what stops that reading as `up` at all.
        if row["healthy"]:
            state = "up"
        elif row["sleeping"] is True:
            state = "ASLEEP"
        elif row["sleeping"] == servelib.SLEEP_UNREAD:
            state = "SLEEP UNREAD"
        else:
            state = "NOT ANSWERING"
        print(
            f"serve-up: {row['container']} :{row['port']} {state} after "
            f"{row['seconds']}s, models={row['models']}"
        )
    servelib.write_serve_record(
        ctx,
        "up",
        {
            "compose": ctx.compose_file.read_text(encoding="utf-8"),
            "compose_up_exit": started.returncode,
            "units": rows,
        },
    )
    if started.returncode != 0 or not all(row["healthy"] for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
