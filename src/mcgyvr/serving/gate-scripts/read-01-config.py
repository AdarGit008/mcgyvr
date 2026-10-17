#
""

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
