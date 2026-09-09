"""Exit codes a caller can branch on without reading prose.

The CLI had two answers — it worked, or it did not — and three of the outcomes
this lane added are neither. A host nobody has scanned is a *refusal*: nothing
went wrong, mcgyvr declined to invent numbers it was never given, and the fix
is a command rather than a bug report. Hardware that stopped matching its last
scan is a *mismatch*: the scan succeeded and has something to say about the
machine underneath it. Collapsing either into ``1`` makes a script parse
English to tell "your rig lost a DIMM" from "the config is malformed", and a
wrapper that cannot tell those apart either retries a refusal forever or treats
a changed machine as a crash.

``2`` is argparse's own code for a usage error and is named here rather than
redefined, so the enum covers every value the process can leave behind.
"""

from __future__ import annotations

from enum import IntEnum


class Exit(IntEnum):
    """Every status ``mcgyvr`` exits with. ``int`` valued, because a shell reads it."""

    OK = 0
    ERROR = 1
    USAGE = 2
    REFUSED = 3
    MISMATCH = 4
