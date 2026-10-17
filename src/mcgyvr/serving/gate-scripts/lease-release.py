#!/usr/bin/env python3
# The lease release: give back the rig's lease when it still names this run,
# and say so when the rig cannot be reached.
"""Release the rig's lease, which run.py calls from the settling path of a run.

The lease this run took is read from RUN_LEASE; a run that holds none has
nothing to give back and exits 0. Otherwise the lease is released over ssh on
RUN_HOST, which removes ~/.mcgyvr/lease there only if the file still carries
this lease id, so a lease another run has since taken is left alone.

A rig that cannot be reached is not a refusal to retry: the lease file there
may still name this run, and once this pid is gone that lease reads as stale to
the next run on this machine. The script says so on stderr, naming the lease it
could not release, and exits 1.
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
