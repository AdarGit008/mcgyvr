#!/usr/bin/env python3
# RUN_ARTIFACTS: serve-down.json
"""The door's serve step, down: stop every unit the compose file names.

The inverse of serve-up, filed in the same envelope under its own name. After
`docker compose down` the rig's daemon is listed again, and any declared name
still up is exit 1 — a result gate 7 then repeats as a finding, because in
this mode gate 7 expects an empty daemon.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcgyvr.serving import servelib
from mcgyvr.serving.gatelib import door_required, need


def main() -> int:
    door_required("serve-down")
    host = need("RUN_HOST")
    compose_file = Path(need("RUN_COMPOSE"))
    out = Path(need("RUN_OUT_DIR")) / "serve-down.json"
    expected = need("RUN_SERVE_EXPECTED").split()

    print(f"serve-down: docker compose down on {host}: {', '.join(expected)}")
    stopped = servelib.compose(compose_file, "down")
    if stopped.returncode != 0:
        print(
            f"serve-down: docker compose down failed on {host}: "
            f"{stopped.stderr.strip()[:800]}",
            file=sys.stderr,
        )
    try:
        up = servelib.containers_up()
    except servelib.ComposeError as exc:
        print(f"serve-down: {exc}", file=sys.stderr)
        up = None
    remaining = sorted(name for name in (up or []) if name in expected)
    record = {
        "run_id": need("RUN_ID"),
        "host": host,
        "mode": "down",
        "compose_file": str(compose_file),
        "compose_down_exit": stopped.returncode,
        "expected": expected,
        "remaining": remaining,
        "daemon_read": up is not None,
        "card_after": servelib.card(host),
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
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
