"""What a gate check reports.

Every check — syntax, structure, lint, format, secrets, scope, acceptance
commands — speaks in the same currency: a list of :class:`Finding`. A finding
names the check that raised it, the path and (where meaningful) the line it
sits on, and a human-readable reason. Empty means the check passed.

A finding is always attributed to a worker-added line where the check can know
one, because the gate's core promise is that pre-existing state in a file
never fails a worker's change.

**Two renderings, because a finding has two audiences.** :meth:`Finding.__str__`
is the orchestrator's: everything the check knows, for a log, a report or a
console. :meth:`Finding.for_model` is what may be quoted back to a model —
retry notes and the reviewer's gate summary — and it is not the same text,
because ``path`` is not always a path. The acceptance rung puts the command it
ran there, and that command is a contract field #94 keeps off every model-facing
surface. Which rendering to use is the caller's choice; whether a finding has
anything to withhold is the raising check's, declared once on
:attr:`Finding.names_a_file` rather than relearned by every consumer.
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

    #: Whether ``path`` names a file in the change. True for every check that
    #: reads the worker's diff; False for the acceptance rung, whose ``path`` is
    #: the orchestrator's own command. The default is the safe direction for a
    #: new check to inherit — a file path shown to a model is what the gate is
    #: for — so the exception states itself where it is raised.
    names_a_file: bool = True

    def __str__(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        code = f" [{self.code}]" if self.code else ""
        return f"{where}: {self.check}{code}: {self.message}"

    def for_model(self) -> str:
        """This finding as model-facing text may quote it (#94).

        Identical to :meth:`__str__` wherever ``path`` names a file, which is
        every check but one. For an acceptance finding the location is dropped
        and the reason kept: what a retry needs is the failure, and a worker
        told which command to satisfy can satisfy the command instead of the
        contract — the reason ``acceptance`` is orchestrator-only in the first
        place.
        """
        if self.names_a_file:
            return str(self)
        code = f" [{self.code}]" if self.code else ""
        return f"{self.check}{code}: {self.message}"
