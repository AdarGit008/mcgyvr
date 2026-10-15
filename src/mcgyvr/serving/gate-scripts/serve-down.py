#!/usr/bin/env python3
# RUN_REWRITES: serve-down.json
"""The door's serve step, down: stop every unit the compose file names.

The inverse of serve-up, filed in the same envelope under its own name. After
`docker compose down` the rig's daemon is listed again, and any declared name
still up is exit 1 — a result gate 7 then repeats as a finding, because in
this mode gate 7 expects an empty daemon.

`serve down --unit C` (RUN_SERVE_ONLY) stops and removes only the named
containers, by their compose services, and leaves the file's other units
running (:func:`mcgyvr.serving.servelib.down`); a named one still up after
it is exit 1. This is how a unit that cannot sleep is put away in a swap.

A whole `down` also names the file's services that start asleep (a compose
profile, a swap partner) and removes them alone: a swap may have left one
running, and `compose down` is not promised to reach a profile.
"""

from __future__ import annotations

import sys

from mcgyvr.serving import servelib


def main() -> int:
    ctx = servelib.serve_prologue("down")
    if ctx is None:
        return 2

    only = ctx.only
    expected = ctx.expected
    if only:
        units = tuple(s for s in ctx.units if s.container in only)
        expected = [s.container for s in units]
    else:
        units = ctx.units

    print(f"serve-down: docker compose down on {ctx.host}: {', '.join(expected)}")
    stopped = servelib.down(ctx.compose_file, units if only else ())
    sleepers = () if only else tuple(s for s in units if s.asleep)
    if sleepers and stopped.returncode == 0:
        stopped = servelib.down(ctx.compose_file, sleepers)
    if stopped.returncode != 0:
        print(
            f"serve-down: docker compose down failed on {ctx.host}: "
            f"{stopped.stderr.strip()[:800]}",
            file=sys.stderr,
        )
    try:
        up = servelib.containers_up()
    except servelib.ComposeError as exc:
        print(f"serve-down: {exc}", file=sys.stderr)
        up = None
    remaining = sorted(name for name in (up or []) if name in expected)
    servelib.write_serve_record(
        ctx,
        "down",
        {
            "compose_down_exit": stopped.returncode,
            "expected": expected,
            "remaining": remaining,
            "daemon_read": up is not None,
        },
    )
    if remaining:
        print(
            f"serve-down: still up after compose down: {' '.join(remaining)}",
            file=sys.stderr,
        )
    if stopped.returncode != 0 or remaining or up is None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
