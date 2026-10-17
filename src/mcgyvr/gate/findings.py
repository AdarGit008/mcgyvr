"""The finding the gate reports with: the check that raised it, where it landed,
and one-line renderings of it for a person and for a model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """One gate complaint: the check that raised it, the path it is about, the
    message, and optionally a line and a short code naming the kind of problem."""

    check: str
    path: str
    message: str
    line: int | None = None
    code: str | None = None

    # Some findings are keyed by something that is not a path in the tree — an
    # acceptance command's label, or a nested git entry — and printing that
    # token in the file position would read as a file the change touches. This
    # flag says whether ``path`` can be shown as one, and ``for_model`` is what
    # is honouring it when the path is dropped from the line.
    names_a_file: bool = True

    def __str__(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        code = f" [{self.code}]" if self.code else ""
        return f"{where}: {self.check}{code}: {self.message}"

    def for_model(self) -> str:
        """The line a model reads: the full form when the path names a file, and
        otherwise the check, code, and message without the file position."""
        if self.names_a_file:
            return str(self)
        code = f" [{self.code}]" if self.code else ""
        return f"{self.check}{code}: {self.message}"
