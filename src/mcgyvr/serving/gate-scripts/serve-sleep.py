#
#
""

from __future__ import annotations

from mcgyvr.serving import servelib
from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE


def main() -> int:
    ctx = servelib.serve_prologue("sleep")
    if ctx is None:
        return 2

    #
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
