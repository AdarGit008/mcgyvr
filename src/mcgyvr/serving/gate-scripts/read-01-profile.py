#!/usr/bin/env python3
"""read, profile — which profile a read is under, and no round.

The profile is settled exactly as gate 1 settles it (``01-round.py``'s
``profile()``, loaded rather than copied): the config ``mcgyvr`` itself would
load, and ``live`` when there is none. A read measures nothing a round pins and
must not append one to ``tools/bench/rounds.json`` (owner, 2026-09-15, D2), so
the round half of gate 1 is not run.
"""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, export

HERE = Path(__file__).resolve().parent


def main() -> int:
    door_required("read profile")
    gate1 = SourceFileLoader("_gate01", str(HERE / "01-round.py")).load_module()
    which, source = gate1.profile()
    export("RUN_PROFILE", which)
    export("RUN_CONFIG", source)
    print(f"read: profile={which} config={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
