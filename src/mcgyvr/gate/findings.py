""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    ""

    check: str
    path: str
    message: str
    line: int | None = None
    code: str | None = None

    #
    #
    #
    #is
    #d.
    names_a_file: bool = True

    def __str__(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        code = f" [{self.code}]" if self.code else ""
        return f"{where}: {self.check}{code}: {self.message}"

    def for_model(self) -> str:
        ""
        if self.names_a_file:
            return str(self)
        code = f" [{self.code}]" if self.code else ""
        return f"{self.check}{code}: {self.message}"
