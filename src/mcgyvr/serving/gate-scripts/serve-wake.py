#!/usr/bin/env python3
# RUN_REWRITES: serve-wake.json
"""The door's serve step, wake: bring back every unit `serve sleep` put to sleep.

The inverse of serve-sleep. Each unit that says it is asleep is woken through
vLLM's three wake calls (`servelib.wake`: weights back, weights read from disk,
KV cache back), and then every unit is polled until it serves, as `serve up`
polls after a start. No container is started: a unit that is not running is
not one this step can wake, and the poll reports it as not answering.

Exit 1 when a wake call failed or a unit did not come back to serving.

`serve wake --unit C` (RUN_SERVE_ONLY) wakes and polls only the named
containers; a neighbour put to sleep to make room for this one stays asleep.
"""

from __future__ import annotations

from mcgyvr.serving import servelib


def main() -> int:
    ctx = servelib.serve_prologue("wake")
    if ctx is None:
        return 2

    # `--unit`: the units to wake, the rest of the card left as it is.
    only = ctx.only
    units = tuple(s for s in ctx.units if not only or s.container in only)
    woken: dict[str, bool | None] = {}
    for service in units:
        if servelib.sleeping(ctx.host, service.port) is True:
            print(f"serve-wake: waking {service.container} :{service.port}")
            woken[service.container] = servelib.wake(ctx.host, service.port)
        else:
            woken[service.container] = None
    rows = [servelib.wait_for(ctx.host, service) for service in units]
    for row in rows:
        state = "up" if row["healthy"] else "NOT SERVING"
        print(
            f"serve-wake: {row['container']} :{row['port']} {state} after "
            f"{row['seconds']}s"
        )
    servelib.write_serve_record(
        ctx,
        "wake",
        {"woken": woken, "units": rows},
    )
    if any(ok is False for ok in woken.values()):
        return 1
    if not all(row["healthy"] for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
