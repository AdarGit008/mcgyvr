#
#
""

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
