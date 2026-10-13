"""The test suite's own index: what each test file is, read from one file.

``tests/MANIFEST.tsv`` says, for every test file, what level it sits at and
what kind of test it is. It is the only place that says so: the conftest
turns each row into pytest markers, so ``pytest -m "unit and logic"`` is a
question the suite can answer, and a gate checks the file against the tests
actually on disk.

Where the two classification passes read a file differently the row carries
both readings, ``level`` reads ``integration|e2e``, and the file is marked
``disputed`` rather than given an answer nobody has earned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from tests._paths import REPO

LEVELS = ("unit", "integration", "e2e")
KINDS = ("behavior", "functional", "infra", "logic", "operational", "tools")
COLUMNS = ("path", "level", "marker", "level_by", "marker_by", "why")
#: Who a row's answer came from. ``agreed``: both passes said it.
#: ``ponytail``/``stock``: only that pass saw the file. ``derived``: read off
#: what the file does, with the reason in the row. ``disputed``: the passes
#: disagreed and the row holds both readings. ``unreviewed``: no pass saw the
#: file and nobody has classified it, so the row holds no answer at all.
SOURCES = ("agreed", "ponytail", "stock", "derived", "disputed", "unreviewed")
#: The provenances that stand for an open question rather than an answer.
OPEN = ("disputed", "unreviewed")

MANIFEST = REPO / "tests" / "MANIFEST.tsv"


@dataclass(frozen=True)
class Row:
    path: str
    level: str
    marker: str
    level_by: str
    marker_by: str
    why: str

    @property
    def levels(self) -> tuple[str, ...]:
        """Every reading of the level: one, or the two that disagree."""
        return tuple(self.level.split("|")) if self.level else ()

    @property
    def markers(self) -> tuple[str, ...]:
        return tuple(self.marker.split("|")) if self.marker else ()

    @property
    def disputed(self) -> bool:
        return "disputed" in (self.level_by, self.marker_by)

    @property
    def unreviewed(self) -> bool:
        return "unreviewed" in (self.level_by, self.marker_by)

    def marks(self) -> tuple[str, ...]:
        """The pytest markers this row puts on its file.

        A settled reading becomes its own marker. An open one becomes
        ``disputed`` or ``unreviewed`` and nothing else: the suite will not
        claim a level it has not got. Either way the file is reachable --
        ``pytest -m unreviewed`` is the open work, counted.
        """
        found: list[str] = []
        if self.level_by not in OPEN and self.level:
            found.append(self.level)
        if self.marker_by not in OPEN and self.marker:
            found.append(self.marker)
        if self.disputed:
            found.append("disputed")
        if self.unreviewed:
            found.append("unreviewed")
        return tuple(found)


def rows(manifest: Path = MANIFEST) -> dict[str, Row]:
    """Every row, by path, checked as it is read."""
    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert lines, f"{manifest} is empty"
    head = tuple(lines[0].split("\t"))
    assert head == COLUMNS, f"{manifest} columns are {head}, expected {COLUMNS}"
    found: dict[str, Row] = {}
    for number, line in enumerate(lines[1:], start=2):
        field = line.split("\t")
        assert len(field) == len(COLUMNS), (
            f"{manifest}:{number} has {len(field)} columns, not {len(COLUMNS)}"
        )
        row = Row(*field)
        assert row.path not in found, f"{manifest}:{number} names {row.path} twice"
        found[row.path] = row
    return found


def mark(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark every collected test with what the manifest says it is.

    Called from each conftest that pytest loads. The manifest is the one
    place that says a file's level and kind, so the markers come from it
    rather than being written out again on each file, where the two would
    drift. A file the manifest does not name is left alone here; the
    manifest's own gate is what insists it be named.
    """
    import pytest as _pytest

    try:
        manifest = rows()
    except (OSError, AssertionError):
        return  # the manifest's own gate reports this properly
    root = Path(str(config.rootpath))
    for item in items:
        try:
            where = str(Path(str(item.path)).relative_to(root))
        except ValueError:
            continue
        row = manifest.get(where)
        if row is None:
            continue
        for name in row.marks():
            item.add_marker(getattr(_pytest.mark, name))
