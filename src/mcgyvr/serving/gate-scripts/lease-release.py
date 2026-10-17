#
""

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
