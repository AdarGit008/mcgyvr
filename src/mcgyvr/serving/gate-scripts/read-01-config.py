#!/usr/bin/env python3
"""read, config — which config a read is under.

The config is settled exactly as gate 1 settles it (``01-round.py``'s
``config()``, loaded rather than copied): the config ``mcgyvr`` itself would
load, and ``none`` when there is none. A read starts nothing, so gate 1's
admission of a ``serve up`` is not run.
"""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, export

HERE = Path(__file__).resolve().parent


def main() -> int:
    door_required("read config")
    gate1 = SourceFileLoader("_gate01", str(HERE / "01-round.py")).load_module()
    source = gate1.config()
    export("RUN_CONFIG", source)
    print(f"read: config={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
