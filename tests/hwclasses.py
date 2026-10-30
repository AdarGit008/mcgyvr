"""An invented table of device classes, shaped as data/hardware-classes.json is.

The names are invented: a chip that comes with two bandwidths told apart by its
GPU cores, a chip told apart by the machine's memory, and a card that comes
with two memory sizes. Every source is an invented page.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcgyvr import estimate

#: The invented chip a unified-memory shape of tests.machine_shapes carries.
CHIP = "Example Chip U1"
#: An invented chip told apart by memory, and an invented card by its own.
CHIP_BY_MEMORY = "Example Chip U2"
CARD = "Example Card 70"

ROWS: list[dict[str, Any]] = [
    {
        "id": "chip-u1-8c",
        "vendor": "apple",
        "name": CHIP,
        "gpu_cores": [8],
        "bandwidth_gbps": 300.0,
        "verified": True,
        "source": "chip-u1-8c",
    },
    {
        "id": "chip-u1-10c",
        "vendor": "apple",
        "name": CHIP,
        "gpu_cores": [10],
        "bandwidth_gbps": 400.0,
        "verified": True,
        "source": "chip-u1-10c",
    },
    {
        "id": "chip-u2-small",
        "vendor": "apple",
        "name": CHIP_BY_MEMORY,
        "gpu_cores": [12],
        "bandwidth_gbps": 150.0,
        "match_memory_gb": [16],
        "verified": True,
        "source": "chip-u2-small",
    },
    {
        "id": "chip-u2-large",
        "vendor": "apple",
        "name": CHIP_BY_MEMORY,
        "gpu_cores": [12],
        "bandwidth_gbps": 170.0,
        "match_memory_gb": [24, 32],
        "verified": False,
        "source": "chip-u2-large",
    },
    {
        "id": "card-70-6gb",
        "vendor": "nvidia",
        "name": CARD,
        "vram_gb": 6,
        "bandwidth_gbps": 210.0,
        "verified": True,
        "source": "card-70-6gb",
    },
    {
        "id": "card-70-10gb",
        "vendor": "nvidia",
        "name": CARD,
        "vram_gb": 10,
        "bandwidth_gbps": 330.0,
        "verified": True,
        "source": "card-70-10gb",
    },
]


def document(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = ROWS if rows is None else rows
    return {
        "_doc": "invented",
        "schema": estimate.CLASSES_SCHEMA,
        "classes": rows,
        "_sources": {
            row["id"]: {"url": f"https://example.com/{row['id']}", "quote": "invented"}
            for row in rows
        },
    }


def write(path: Path, doc: dict[str, Any] | None = None) -> Path:
    path.write_text(json.dumps(document() if doc is None else doc), encoding="utf-8")
    return path


def table(tmp: Path) -> tuple[estimate.HardwareClass, ...]:
    return estimate.load_classes(write(tmp / "classes.json"))
