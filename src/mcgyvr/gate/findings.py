"""What a gate check reports.

Every check — syntax, structure, lint, format, secrets, scope, acceptance
commands — speaks in the same currency: a list of :class:`Finding`. A finding
names the check that raised it, the path and (where meaningful) the line it
sits on, and a human-readable reason. Empty means the check passed.

A finding is always attributed to a worker-added line where the check can know
one, because the gate's core promise is that pre-existing state in a file
never fails a worker's change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """One reason a change did not pass, attributed as precisely as possible."""

    check: str
    path: str
    message: str
    line: int | None = None
    code: str | None = None

    def __str__(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        code = f" [{self.code}]" if self.code else ""
        return f"{where}: {self.check}{code}: {self.message}"
