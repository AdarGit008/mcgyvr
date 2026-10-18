#!/usr/bin/env python3
# RUN_REWRITES: serve-wake.json
# The `wake` serve step: the gate-6 script a `serve ... wake` run ends at.
# It wakes the units that read as asleep, waits for all, and files its record.
"""Wake the sleeping units of this run, then wait for every one of them to serve.

The units are the ones `serve_prologue` re-read from the emitted compose file,
narrowed by `--unit` when the door was given it. A unit is asked to wake only
when its `/is_sleeping` route answered True, so an awake unit is neither woken
twice nor reported as woken; the rest are recorded without a wake answer. Every
unit in the set is then polled by `servelib.wait_for`, healthy or not, and the
step files `woken` and `units` as `serve-wake.json`.

The exit status is the step's: 2 when the prologue refused and nothing was
touched, 1 when a wake call did not land or a unit is not serving, 0 otherwise.
"""

from __future__ import annotations

from mcgyvr.serving import servelib


def main() -> int:
    ctx = servelib.serve_prologue("wake")
    if ctx is None:
        return 2

    # No --unit narrowing means every unit; otherwise only the named ones.
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
