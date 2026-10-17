#
#
""

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
    #
    #
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
        #
        #
        #
        #
        #
        #
        #
        #
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
