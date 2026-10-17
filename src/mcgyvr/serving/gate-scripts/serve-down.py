#!/usr/bin/env python3
# RUN_REWRITES: serve-down.json
# serve-down — the script gate 6 runs for the `serve down` direction: the one
# host the door named is taken back down to the containers the run expects, and
# whatever the daemon still reports up is printed and filed as `serve-down.json`.
"""Take this run's units down on the one host the door named, and file the step.

`serve_prologue("down")` gates the step and reads the run from the environment,
so `ctx` carries the host, the compose file re-read into `units`, the containers
the door read from that file as `expected`, and the `--unit` set as `only`. A
refusal there prints `serve-down: REFUSED — ...` on stderr and returns None,
which this answers with exit 2.

A `--unit` step is narrowed to the services whose container `only` names, and
`expected` becomes those containers; a whole-stack step keeps the door's list.
The narrowed step is one `docker compose rm --stop --force` on those services.
The whole-stack step is `docker compose down --remove-orphans`, and only if it
succeeded a second call names the services written under a compose profile
(`asleep`), which `down` is not promised to reach. A failed compose call prints
the first 800 characters of its trimmed stderr on stderr.

The daemon is then read again through `containers_up()`: the expected
containers still up become `remaining`, and a daemon that could not be read is
filed as `daemon_read: False` instead of being taken for a host with nothing
left running. `serve-down.json` carries `compose_down_exit`, `expected`,
`remaining` and `daemon_read`. The step exits 1 when the compose call failed,
an expected container is still up, or the daemon could not be read, and 0 when
the host was left clear.
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
