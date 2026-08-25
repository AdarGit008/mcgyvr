"""Where a run's intent lives, and the date its shape stops being provisional.

The repo records what a run **was** — `run.json`, `identity.KEY`, eleven fields
held by `identity.require_comparable`. Nothing recorded what a run is **for**:
not the question, not what else it could have carried, not what was left on the
table. #322 decided that every run declares a structured header before it
starts and that the gate **records rather than refuses**, so the register
emerges from real headers instead of being designed against code that P1-P5 is
about to churn. The owner then ruled "right mechanism, wrong size — split it".

This module is the half that is not the gate: the record type, the home, the
listing, and the review point. The gate — a driver that writes or checks a
header before a run starts — stays in #322 and writes this record type.

**Four properties, each one a rule below.**

1. *The closing condition is declared now.* :data:`REVIEW_AFTER` is 10, #322's
   own number ("before we have seen ten of the things it has to describe").
   When ten headers carrying a ``run`` block exist and no ``run-header/2``
   schema is on disk, ``list`` exits non-zero and says the review is owed. The
   owed state is code, not memory: nobody has to remember to look.
2. *A machine-readable spine, prose underneath.* :data:`KEYS` is closed — a key
   it does not name is refused — and free text goes under ``notes``. Open
   questions dispersed over 147 session records is what that rule is for.
3. *``unknown`` is a value and carries provenance.* An agent asked for a number
   it cannot source will invent one. ``{"unknown": true, "searched": [...]}``
   with a non-empty list is the way to say "I looked"; the bare string
   ``"unknown"`` and a bare ``{"unknown": true}`` are refused. A field nobody
   can fill is a gap discovered as a side effect of trying to fill it, which is
   the mechanism, not the fallback.
4. *A greppable home outside the dated evidence directory.* Questions kept in
   ``records/evidence/<date>/`` die with their campaign. They live in
   ``records/headers/<date>-<slug>.json`` instead, where ``<date>`` is the
   run's start date when there is a run and the declared date when there is
   not — so a question filed today and answered by a run next month keeps the
   date it was asked.

v1 requires four fields. Everything else is optional **on purpose**: which
fields become required is the review's decision, and requiring them now would
be inventing the shape before seeing the things it has to describe.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

#: The greppable home. One file per header, named for its date and a slug.
HOME = REPO / "records" / "headers"

#: Where ``run-header/2`` lands when the field review at ten is done, beside
#: the four record schemas already there. Its existence is what clears the
#: owed state — the review is finished when it has produced a schema, not when
#: someone says it is.
SCHEMA_V2 = REPO / "tools" / "baseline" / "schema" / "record.run-header.schema.json"

#: This record type. The version is in the value because ``run-header/2`` is a
#: planned successor, not a hypothetical one.
RECORD = "run-header/1"

#: Read the accumulated headers at ten and decide which fields are required.
#: #322's number, declared 2026-08-21 with the gate rather than after it: a
#: gate left open with no review date states no property (ADR-0026 lens 3).
REVIEW_AFTER = 10

#: v1's four. A header that cannot say what it is asking is not a header.
REQUIRED: tuple[str, ...] = ("record", "id", "declared", "question")

#: #322's other seven candidates, then the four this issue adds. All optional:
#: the review at ten promotes the ones that were filled every time and drops
#: the ones nobody could fill.
OPTIONAL: tuple[str, ...] = (
    "arms",
    "hosts",
    "cost",
    "could_have_carried",
    "left_on_table",
    "prerequisites",
    "void_if",
    "run",
    "answered_by",
    "retroactive",
    "notes",
)

KEYS: tuple[str, ...] = REQUIRED + OPTIONAL

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}(?::\d{2})?)?")


def load(path: Path) -> dict[str, Any]:
    """One header, or a raise. A malformed header is not a silent absence."""
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: a header is an object, not {type(loaded).__name__}")
    return loaded


def headers(home: Path = HOME) -> list[tuple[Path, dict[str, Any]]]:
    """Every header in ``home``, by filename. Prose files are not headers."""
    return [(path, load(path)) for path in sorted(home.glob("*.json"))]


def started(header: dict[str, Any]) -> str | None:
    """The date the run started, or ``None`` for a question-only header."""
    run = header.get("run")
    if not isinstance(run, dict):
        return None
    stamp = _STAMP.match(str(run.get("started") or ""))
    return stamp.group(1) if stamp else None


def _walk(value: Any, field: str = "") -> Iterator[tuple[str, Any]]:
    """Every value in a header, by dotted path. Nested, because an unknown
    buried two levels down is the same claim as one at the top."""
    yield field, value
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from _walk(inner, f"{field}.{key}" if field else str(key))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from _walk(inner, f"{field}[{index}]")


def _unknown_problems(field: str, value: Any) -> list[str]:
    """Rule 3, on one value."""
    if isinstance(value, str) and value.strip().lower() == "unknown":
        return [
            f"{field} is the bare string 'unknown': say what was searched, as "
            '{"unknown": true, "searched": [...]}'
        ]
    if not (isinstance(value, dict) and "unknown" in value):
        return []
    found = []
    if value.get("unknown") is not True:
        found.append(f"{field}.unknown is {value.get('unknown')!r}, not true")
    searched = value.get("searched")
    if not (isinstance(searched, list) and searched):
        found.append(
            f"{field} is unknown and names nothing it searched: an unknown "
            "that did not look is a guess with better manners"
        )
    return found


def problems(header: dict[str, Any], path: Path) -> list[str]:
    """Everything wrong with one header, in the order a reader would find it."""
    found = []
    if header.get("record") != RECORD:
        found.append(f"record is {header.get('record')!r}, not {RECORD!r}")
    for field in REQUIRED:
        if field not in header:
            found.append(f"{field} is missing")
    for field in header:
        if field not in KEYS:
            found.append(
                f"{field!r} is not a key the spine names: prose belongs under "
                "'notes', so free text cannot enter the aggregatable layer"
            )
    if header.get("id") != path.stem:
        found.append(f"id is {header.get('id')!r} and the file is {path.stem!r}")
    declared = str(header.get("declared") or "")
    if not _DATE.match(declared):
        found.append(f"declared is {header.get('declared')!r}, not a YYYY-MM-DD date")
    question = header.get("question")
    if not (isinstance(question, str) and question.strip()):
        found.append("question is empty: a header with no question asks nothing")
    for field, value in _walk(header):
        if field:
            found.extend(_unknown_problems(field, value))

    began = started(header)
    if began is None and "run" in header:
        found.append("run is present and carries no readable 'started' stamp")
    if began is not None:
        if not path.stem.startswith(began):
            found.append(
                f"the file is named {path.stem!r} and the run started {began}: a "
                "header with a run is named for the run's start date"
            )
        if declared > began and header.get("retroactive") is not True:
            found.append(
                f"declared {declared} is after the run started {began} and the "
                "header does not say retroactive: true"
            )
    elif declared and not path.stem.startswith(declared):
        found.append(
            f"the file is named {path.stem!r} and it was declared {declared}: a "
            "header with no run is named for the date it was declared"
        )
    return found


def unknown_fields(header: dict[str, Any]) -> list[str]:
    """The fields this header answered with an unknown, by dotted path."""
    return sorted(
        field
        for field, value in _walk(header)
        if field and isinstance(value, dict) and value.get("unknown") is True
    )


def listing(
    home: Path = HOME, schema: Path = SCHEMA_V2
) -> tuple[list[str], int, int, bool]:
    """``(lines, run header count, problem count, review owed)``.

    Counted at read time rather than kept in a tally file: a count that is
    derived cannot disagree with the directory it describes.
    """
    lines = []
    counted = 0
    broken = 0
    for path, header in headers(home):
        began = started(header)
        counted += began is not None
        unknown = unknown_fields(header)
        lines.append(
            f"{path.stem:<34} {header.get('declared', '?'):<12} "
            f"{(header.get('run') or {}).get('started') or 'no run':<17} "
            f"{'unknown: ' + ', '.join(unknown) if unknown else ''}".rstrip()
        )
        for problem in problems(header, path):
            broken += 1
            lines.append(f"  ! {problem}")
    owed = counted >= REVIEW_AFTER and not schema.exists()
    return lines, counted, broken, owed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "The run headers: what each run is FOR, beside what run.json says "
            "it WAS (#330, the half of #322 that is not the gate)."
        )
    )
    parser.add_argument("command", choices=("list",))
    parser.add_argument("--home", type=Path, default=HOME)
    parser.add_argument("--schema", type=Path, default=SCHEMA_V2)
    args = parser.parse_args(argv)

    lines, counted, broken, owed = listing(args.home, args.schema)
    for line in lines:
        print(line)
    print(f"{counted} of {REVIEW_AFTER} run headers before the field review")
    if owed:
        where = args.schema
        if where.is_relative_to(REPO):
            where = where.relative_to(REPO)
        print(
            f"review owed: {counted} headers carry a run and no {RECORD[:-1]}2 "
            f"schema is at {where}. Read them, promote every field filled on "
            "all of them, drop every field filled on none, and append the "
            "decision to #330."
        )
    return 1 if broken or owed else 0


if __name__ == "__main__":
    sys.exit(main())
