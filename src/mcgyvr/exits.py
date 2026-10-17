""

from __future__ import annotations

from enum import IntEnum


class Exit(IntEnum):
    ""

    OK = 0
    ERROR = 1
    USAGE = 2
    REFUSED = 3
    MISMATCH = 4
