#!/usr/bin/env python3
"""Release the rig's lease on the way out — every way out.

Not an entry in SEQUENCE: the door spawns this in the `finally` that also
releases gate 5's claim, so a refusal at gate 3, a step that died, an
interrupt during the step and a clean finish all end here. The lease is
removed only if it is still this run's (its lease_id): a run that was
displaced under R1 leaves the displacing run's lease alone. A rig that cannot
be reached is said, not refused — this runs after the verdict, and the lease
it could not remove reads as stale to the next run on this machine, by pid.
"""

from __future__ import annotations

import sys

from mcgyvr.serving.gatelib import door_required, lease_of_run, lease_release, need


def main() -> int:
    door_required("lease release")
    lease = lease_of_run()
    if lease is None:
        return 0
    host = need("RUN_HOST")
    if not lease_release(host, lease.lease_id):
        print(
            f"lease release: {host} could not be reached; ~/.mcgyvr/lease there "
            f"may still name this run ({lease.describe()}) and will read as "
            "stale once this pid is gone",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
