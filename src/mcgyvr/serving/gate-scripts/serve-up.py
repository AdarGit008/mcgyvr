#!/usr/bin/env python3
# RUN_REWRITES: serve-up.json
# Gate step `serve up`: bring the run's compose stack up on the one host the
# door opened for, wait for each unit to answer, and file what was seen.
"""Start the run's compose stack, then say what each of its units answers.

The step descends from the door and acts on the compose file the door read:
`servelib.serve_prologue` reads that file again and refuses a file that no
longer names the containers the door took from it, since nothing is started
from a file that changed under the run. A refusal is exit 2.

`--unit` narrows the step to the containers it names, and those are started
without their compose neighbours, so a sleeper written under a profile comes
up without the partners it swaps with; a whole step starts everything the
file starts by default. Each selected unit is then polled until it serves,
and one line per unit states whether it is up, asleep, asleep with an
unreadable probe, or not answering. The step exits 1 when `docker compose
up` failed or any unit did not come up healthy, and 0 otherwise.
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
    # `--unit` selects the containers it names; a whole step selects the units
    # the file starts by default, so a unit under a profile is left down.
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
        # The row is read in one order: a unit that listed its models and does
        # not read as asleep is up, and only the rest have their sleep answer
        # classified. `sleeping` is `True` for a unit that says it is asleep,
        # `SLEEP_UNREAD` when the sleep route could not be read — reported
        # apart from both, because a failed probe is neither an awake nor an
        # asleep answer — None for a unit with no sleep route at all, and
        # `False` for one that says it is awake. What is left never listed its
        # models within the poll budget, so it reads as not answering.
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
