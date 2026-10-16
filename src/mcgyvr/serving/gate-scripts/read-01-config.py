#!/usr/bin/env python3
"""read, config — which config a read is under.

The config is settled exactly as gate 1 settles it (``01-config.py``'s
``config()``, loaded rather than copied): the config ``mcgyvr`` itself would
load, and ``none`` when there is none. A read starts nothing, so gate 1's
admission of a ``serve up`` is not run.
"""

from __future__ import annotations

from mcgyvr.serving.gatelib import door_required, export
from mcgyvr.serving.rigread import config


def main() -> int:
    door_required("read config")
    source = config()
    export("RUN_CONFIG", source)
    print(f"read: config={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
