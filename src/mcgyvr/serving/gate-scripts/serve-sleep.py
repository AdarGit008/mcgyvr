#!/usr/bin/env python3
# RUN_REWRITES: serve-sleep.json
# Gate 6 of a `serve sleep` run: the door (`mcgyvr.serving.run`) spawns this
# script as the step, with the run exported to it, and nothing else calls it.
"""Put a serving card's units to sleep at level 2, keeping their processes.

The step of a `serve sleep` run. `servelib.serve_prologue("sleep")` gates it,
reads the run from the environment and re-reads the compose file; a refusal
there has already been printed, and the step answers 2 having touched nothing.
`--unit` narrows the step to the containers it names, otherwise every unit the
compose file declares is taken.

Each selected unit's sleep state is read once before anything is asked of it.
A unit that does not answer with a bool — the 404 of a unit with no sleep route
(llama.cpp, or vLLM without its dev routes), or a probe that could not be read
at all — stops the step there: sleeping is skipped for every unit, the ones
without the route are named on stdout, and the run answers
:data:`~mcgyvr.serving.gatelib.NO_SLEEP_ROUTE` so its caller falls back to
stopping the card. The card's containers are never stopped here, because a
level-2 sleep keeps them.

With a route on every unit, each one is asked to sleep at level 2 and read
again, and the run answers 1 if any request was not accepted or any unit did
not read back asleep, 0 otherwise. Either path files
`serve-<mode>.json` through `servelib.write_serve_record`: the states read
first, the units that had no route, and one row per unit asked, carrying what
the request answered and what the unit said afterwards. Level 1 is refused by
`servelib.sleep` itself, before any transport is dialled.
"""

from __future__ import annotations

from mcgyvr.serving import servelib
from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE


def main() -> int:
    ctx = servelib.serve_prologue("sleep")
    if ctx is None:
        return 2

    # `ctx.only` is the set of containers `--unit` named, empty for a
    # whole-stack step; either way the step acts on these units alone, so a
    # narrowed sleep leaves a card's other units exactly as they are.
    only = ctx.only
    units = tuple(s for s in ctx.units if not only or s.container in only)
    before = {s.container: servelib.sleeping(ctx.host, s.port) for s in units}
    routeless = sorted(
        name for name, said in before.items() if not isinstance(said, bool)
    )
    rows: list[dict[str, object]] = []
    if routeless:
        print(
            f"serve-sleep: {', '.join(routeless)} on {ctx.host} has no sleep route; "
            "nothing was asked of any unit, and the card can only be stopped"
        )
        status = NO_SLEEP_ROUTE
    else:
        status = 0
        for service in units:
            asked = servelib.sleep(ctx.host, service.port, 2)
            after = servelib.sleeping(ctx.host, service.port)
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
    servelib.write_serve_record(
        ctx,
        "sleep",
        {
            "sleeping_before": before,
            "no_sleep_route": routeless,
            "units": rows,
        },
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
