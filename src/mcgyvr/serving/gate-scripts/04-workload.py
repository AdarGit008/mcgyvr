#!/usr/bin/env python3
"""gate 4 — the workload module generates the pinned prompts.

The digest is over generated OUTPUT and not over the file's text, so a
formatter pass cannot void a comparison and a changed decile cannot hide behind
one. Every driver imports this one module, so one check covers all of them.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, refuse, root


def main() -> int:
    door_required("gate 4")
    repo = root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    try:
        from tools.runs.rows import WORKLOAD_DIGEST, workload_digest
    except Exception as error:
        refuse(f"gate 4: tools.runs.rows will not import: {error!r}")
        raise

    module = repo / "tools" / "runs" / "workload.py"
    if not module.is_file():
        refuse(f"gate 4: {module} is missing; every comparison would be void")
    got = workload_digest(Path(module))
    if got != WORKLOAD_DIGEST:
        refuse(
            f"gate 4: tools/runs/workload.py generates workload {got}, not the "
            f"pinned {WORKLOAD_DIGEST}. Every comparison in the campaign would "
            "be against different prompts, so nothing is measured"
        )
    print(f"gate 4: workload {got[:16]}... matches the pin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
