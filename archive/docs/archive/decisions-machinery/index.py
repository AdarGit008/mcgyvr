"""Generate docs/decisions/INDEX.md from the decision records' own headers.

DEC-4 (#288, docs/plans/302/README.md §3): the index is generated, never
hand-kept — a hand-kept index is exactly the drift its absence already cost
(two records both numbered 0035, 2026-08-17). This tool is off-SURFACE on
purpose; `src/mcgyvr/docgen.py` is SURFACE and editing it would move the
product digest.

Reading rules, shared with tests/test_decisions.py (which imports this
module): the record number is the four-digit filename prefix; `Amends:`
targets and `Amended-by:` names are read across the whole wrapped field —
four records (0020, 0021, 0025, 0032) declare targets or names on
continuation lines — and parenthesized commentary never declares an edge,
which is what keeps a rationale that cites another record from minting one.

Deterministic by construction — sorted by number then filename, nothing
derived from the clock. `--check` fails when the committed index and the
records disagree; `make docs` regenerates, `make docs-check` verifies.
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DECISIONS = ROOT / "docs" / "decisions"

INDEX_MARKER = (
    "<!-- Code generated from docs/decisions/0*.md by `make docs` "
    "(tools/decisions/index.py). DO NOT EDIT. -->"
)

_TITLE = re.compile(r"^# ADR-(\d{4}) — (.*)$")
_FIELD = re.compile(r"^([A-Z][A-Za-z-]*):\s?(.*)$")
_REF = re.compile(r"ADR-(\d{4})")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclasses.dataclass(frozen=True)
class Record:
    """One decision record's header, as the index and the gate read it."""

    filename: str
    file_number: int
    title_number: int | None
    title: str
    status: str
    date: str
    amends: tuple[int, ...]
    amended_by: tuple[int, ...]


def strip_parenthesized(text: str) -> str:
    """Drop parenthesized commentary; an unclosed paren drops the rest."""
    depth = 0
    kept: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            kept.append(ch)
    return "".join(kept)


def header_fields(text: str) -> dict[str, list[str]]:
    """Field name -> physical lines, from the header above the first section."""
    header = text.split("\n## ", 1)[0]
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in header.split("\n")[1:]:
        match = _FIELD.match(line)
        if match:
            current = match.group(1)
            fields.setdefault(current, []).append(match.group(2))
        elif line.strip() and current is not None:
            fields[current].append(line)
        else:
            current = None
    return fields


def _refs(text: str) -> tuple[int, ...]:
    return tuple(int(number) for number in _REF.findall(text))


def parse_record(path: Path) -> Record:
    text = path.read_text(encoding="utf-8")
    title_match = _TITLE.match(text.split("\n", 1)[0])
    fields = header_fields(text)
    date_lines = fields.get("Date", [])
    date_match = _DATE.search(date_lines[0]) if date_lines else None
    return Record(
        filename=path.name,
        file_number=int(path.name[:4]),
        title_number=int(title_match.group(1)) if title_match else None,
        title=title_match.group(2) if title_match else "(unreadable title)",
        status=" ".join(fields.get("Status", ["(none)"])).strip(),
        date=date_match.group(0) if date_match else "(none)",
        amends=_refs(strip_parenthesized(" ".join(fields.get("Amends", [])))),
        amended_by=_refs(strip_parenthesized(" ".join(fields.get("Amended-by", [])))),
    )


def parse_records(directory: Path) -> list[Record]:
    records = [parse_record(path) for path in sorted(directory.glob("0*.md"))]
    return sorted(records, key=lambda record: (record.file_number, record.filename))


def _cell(numbers: tuple[int, ...]) -> str:
    return ", ".join(f"{number:04d}" for number in numbers) if numbers else "—"


def render(records: list[Record]) -> str:
    lines = [
        INDEX_MARKER,
        "",
        "# Decision records — index",
        "",
        "Generated from the records' own headers. Regenerate: `make docs`; "
        "drift fails `make docs-check`. The header conventions this reads are "
        "enforced by `tests/test_decisions.py`.",
        "",
        "| ADR | Title | Status | Date | Amends | Amended-by |",
        "|---|---|---|---|---|---|",
    ]
    for record in records:
        title = record.title.replace("|", "\\|")
        lines.append(
            f"| [{record.file_number:04d}]({record.filename}) | {title} "
            f"| {record.status} | {record.date} "
            f"| {_cell(record.amends)} | {_cell(record.amended_by)} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed index has drifted from the records",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=DECISIONS,
        help="record corpus to read (injectable so tests can hand a synthetic one)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="index path (default: <directory>/INDEX.md)",
    )
    args = parser.parse_args(argv)
    out: Path = args.out if args.out is not None else args.directory / "INDEX.md"
    text = render(parse_records(args.directory))
    if args.check:
        committed = out.read_text(encoding="utf-8") if out.exists() else None
        if committed != text:
            sys.stderr.write(f"{out} has drifted from the records; run `make docs`.\n")
            return 1
        return 0
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
