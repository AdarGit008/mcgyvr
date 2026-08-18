"""The decision namespace has a gate (#304, P0 of the #302 plan).

Two records merged both numbered 0035 on 2026-08-17, seventy minutes apart
(#262 via PR #298, #301 via PR #303), because nothing read docs/decisions/:
no test, no index, and an amendment graph kept in one direction only. These
checks are that reader. The parser is tools/decisions/index.py's — one
implementation, imported here, so the index and the gate cannot disagree
about what a header says.

Allowlist contract — removing an entry is how a repair is proved:

- MISSING_BACKPOINTERS is frozen at the fifteen one-way edges open when this
  gate landed. (The lane's spec seeded eleven, derived from a first-line grep
  of `Amends:`; reading the whole wrapped field — 0020, 0021 and 0032 declare
  targets on continuation lines — surfaces four more: 20→18, 21→17, 21→18,
  32→27. The correction is recorded on #304.) The assertion is exact
  equality: repairing a header without deleting its entry fails, and a new
  one-way edge fails.
- SAME_DAY_AMENDMENTS records same-day churn with a reason; it does not
  forbid churn. Exact equality again: an undeclared same-day pair fails, and
  an entry whose edge stopped being same-day must go.

Populations are read through an injectable directory (the
tests/test_four_lenses.py idiom): every check takes its corpus as an
argument, and the canaries hand it a synthetic one to prove each check can
reject — a check that cannot be shown to reject is the defect this file is
about.
"""

from __future__ import annotations

import collections
import datetime
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
DECISIONS = _REPO / "docs" / "decisions"


def _load_index() -> ModuleType:
    path = _REPO / "tools" / "decisions" / "index.py"
    spec = importlib.util.spec_from_file_location("decisions_index", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_index = _load_index()

# The fifteen one-way Amends edges (amender, target) open when this gate
# landed — every earlier record's header predates the bidirectional rule.
# Frozen: repairing a target's Amended-by header deletes its entry here.
MISSING_BACKPOINTERS: frozenset[tuple[int, int]] = frozenset(
    {
        (18, 17),
        (19, 18),
        (20, 16),
        (20, 18),
        (21, 17),
        (21, 18),
        (21, 19),
        (22, 18),
        (24, 19),
        (25, 21),
        (26, 24),
        (27, 24),
        (32, 18),
        (32, 27),
        (33, 27),
    }
)

# Amends edges whose two Date: headers fall under one day apart, each with
# the reason the churn was legitimate. The registry records churn; it does
# not forbid it.
SAME_DAY_AMENDMENTS: dict[tuple[int, int], str] = {
    (18, 17): (
        "Both records carry Date: 2026-08-09 — ADR-0017 landed 10:05 on "
        "#220's lane; ADR-0018 amended it 17:35 the same day via PR #228."
    ),
    (26, 25): (
        "ADR-0025 landed 2026-08-13 14:58 via PR #247; ADR-0026 amended it "
        "22:37 the same day on #249's lane, PR #250."
    ),
}


def _records(directory: Path) -> list[Any]:
    return list(_index.parse_records(directory))


def _duplicate_numbers(records: list[Any]) -> set[int]:
    counts = collections.Counter(record.file_number for record in records)
    return {number for number, count in counts.items() if count > 1}


def _title_mismatches(records: list[Any]) -> set[str]:
    return {
        record.filename
        for record in records
        if record.title_number != record.file_number
    }


def _one_way_edges(records: list[Any]) -> set[tuple[int, int]]:
    """Amends edges whose target does not point back (or does not exist)."""
    by_number: dict[int, Any] = {record.file_number: record for record in records}
    return {
        (record.file_number, target)
        for record in records
        for target in record.amends
        if target not in by_number
        or record.file_number not in by_number[target].amended_by
    }


def _same_day_edges(records: list[Any]) -> set[tuple[int, int]]:
    """Amends edges whose two Date: headers are under one day apart."""
    dates: dict[int, datetime.date] = {}
    for record in records:
        try:
            dates[record.file_number] = datetime.date.fromisoformat(record.date)
        except ValueError:
            continue
    return {
        (record.file_number, target)
        for record in records
        for target in record.amends
        if record.file_number in dates
        and target in dates
        and abs((dates[record.file_number] - dates[target]).days) < 1
    }


# --- the corpus as it stands -------------------------------------------------


def test_each_number_is_claimed_once_and_titles_agree() -> None:
    records = _records(DECISIONS)
    assert records, "the decision corpus is missing"
    assert _duplicate_numbers(records) == set()
    assert _title_mismatches(records) == set()


def test_every_record_file_is_inside_the_gate() -> None:
    """A record the 0*.md glob misses is a record no check reads."""
    all_md = {path.name for path in DECISIONS.glob("*.md")}
    gated = {path.name for path in DECISIONS.glob("0*.md")}
    assert all_md - gated == {"INDEX.md"}


def test_every_record_date_parses() -> None:
    """An unreadable Date: header would silently exempt its record from the
    same-day check."""
    assert {r.filename for r in _records(DECISIONS) if r.date == "(none)"} == set()


def test_amendment_edges_are_bidirectional_or_allowlisted() -> None:
    assert _one_way_edges(_records(DECISIONS)) == MISSING_BACKPOINTERS


def test_same_day_amendments_are_declared_with_reasons() -> None:
    assert _same_day_edges(_records(DECISIONS)) == set(SAME_DAY_AMENDMENTS)
    assert all(reason.strip() for reason in SAME_DAY_AMENDMENTS.values())


# --- canaries: each check shown to reject ------------------------------------


def _write_record(
    directory: Path,
    stem: str,
    *,
    title_number: str | None = None,
    date: str = "2026-08-01",
    amends: str = "none",
    amended_by: str | None = None,
) -> None:
    number = title_number if title_number is not None else stem[:4]
    lines = [
        f"# ADR-{number} — a synthetic record",
        "",
        "Status: Accepted",
        f"Amends: {amends}",
    ]
    if amended_by is not None:
        lines.append(f"Amended-by: {amended_by}")
    lines.extend([f"Date: {date}", "", "## Context", "", "Synthetic."])
    (directory / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_canary_duplicated_number_is_refused(tmp_path: Path) -> None:
    _write_record(tmp_path, "0001-first")
    _write_record(tmp_path, "0001-second")
    _write_record(tmp_path, "0002-honest")
    _write_record(tmp_path, "0003-wrong-title", title_number="0004")
    records = _records(tmp_path)
    assert _duplicate_numbers(records) == {1}
    assert _title_mismatches(records) == {"0003-wrong-title.md"}


def test_canary_one_way_edge_is_refused(tmp_path: Path) -> None:
    # 0001 points back at 0002 only, so 0003's edge is one-way.
    _write_record(tmp_path, "0001-target", amended_by="ADR-0002 (2026-08-01)")
    _write_record(tmp_path, "0002-mirrored", amends="ADR-0001 (why)")
    _write_record(tmp_path, "0003-unmirrored", amends="ADR-0001 (why)")
    assert _one_way_edges(_records(tmp_path)) == {(3, 1)}


def test_canary_undeclared_same_day_pair_is_refused(tmp_path: Path) -> None:
    _write_record(tmp_path, "0001-target", date="2026-08-05")
    _write_record(tmp_path, "0002-same-day", date="2026-08-05", amends="ADR-0001 (why)")
    _write_record(tmp_path, "0003-next-day", date="2026-08-06", amends="ADR-0001 (why)")
    assert _same_day_edges(_records(tmp_path)) == {(2, 1)}


# --- the generated index -----------------------------------------------------


def test_index_is_deterministic_and_check_rejects_drift(tmp_path: Path) -> None:
    corpus = tmp_path / "decisions"
    corpus.mkdir()
    _write_record(corpus, "0001-first")
    _write_record(corpus, "0002-second", date="2026-08-02", amends="ADR-0001 (why)")
    out = tmp_path / "INDEX.md"
    argv = ["--directory", str(corpus), "--out", str(out)]
    assert _index.main(argv) == 0
    first = out.read_bytes()
    assert _index.main(argv) == 0
    assert out.read_bytes() == first
    assert _index.INDEX_MARKER.encode() in first
    assert _index.main(["--check", *argv]) == 0
    out.write_bytes(first.replace(b"index", b"Index", 1))
    assert _index.main(["--check", *argv]) == 1
