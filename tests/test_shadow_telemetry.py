"""W1 — shadow telemetry for the candidate-set -> jev top-1 decision loop.

:mod:`mcgyvr.orchestrator.telemetry` measures one per-field jev decision: the
candidate ids shown, in order; the id jev picked; the enumerator's rank-0 id; and
how the decision landed (abstained, failed to parse, confidence, latency). A
``DecisionRecord`` freezes that one decision, a ``ShadowSink`` appends one JSON
line per record to a path (and is inert until it is given one), and a set of pure
helpers answer the wave-2 metric questions over any iterable of records: recall@k,
override rate, abstain rate, parse-fail rate, per-letter distribution and
per-field confidence.

Nothing here dispatches. The records are hand-built, because what the module must
measure is a property of the decision loop, not of how a decision was produced.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mcgyvr.orchestrator.telemetry import (
    DecisionRecord,
    ShadowSink,
    abstain_rate,
    confidence_by_field,
    override_rate,
    parse_fail_rate,
    per_letter_distribution,
    read,
    recall_at_k,
)


def _rec(**overrides: Any) -> DecisionRecord:
    """A decision record with every field a real one has, overridable per test."""
    fields: dict[str, Any] = {
        "field": "price",
        "candidates": ("a", "b", "c"),
        "pick": None,
        "rank1": "a",
        "abstain": False,
        "confidence": 0.9,
        "parse_fail": False,
        "latency_ms": 12,
        "model": "jev-1",
        "seed": "0",
        "ts": "2024-01-01T00:00:00+00:00",
    }
    fields.update(overrides)
    return DecisionRecord(**fields)


def test_override_is_true_only_when_jev_picks_a_different_rank1() -> None:
    # No pick means no override: jev did not choose anything to disagree with.
    assert _rec(pick=None).override is False
    # Picking the enumerator's rank-0 id agrees with it.
    assert _rec(pick="a", rank1="a").override is False
    # Picking any other id overrides it.
    assert _rec(pick="b", rank1="a").override is True


def test_ts_defaults_to_an_iso_timestamp() -> None:
    record = DecisionRecord(
        field="price",
        candidates=("a",),
        pick="a",
        rank1="a",
        abstain=False,
        confidence=1.0,
        parse_fail=False,
        latency_ms=0,
        model="m",
        seed="s",
    )
    # Defaults to now, spelled as an ISO timestamp a reader can parse back.
    datetime.fromisoformat(record.ts)


def test_jsonl_round_trip(tmp_path: Path) -> None:
    sink_path = tmp_path / "nested" / "decisions.jsonl"
    records = [
        _rec(
            field="price",
            candidates=("a", "b", "c"),
            pick="b",
            rank1="a",
            confidence=0.7,
        ),
        _rec(
            field="scope",
            candidates=("x", "y"),
            pick=None,
            rank1="x",
            abstain=True,
        ),
    ]
    sink = ShadowSink(sink_path)
    for record in records:
        sink.append(record)

    # One JSON object per line, each equal to the record's own dict. The parent
    # directory was created on the way.
    lines = [
        json.loads(line) for line in sink_path.read_text().splitlines() if line.strip()
    ]
    assert lines == [record.to_dict() for record in records]

    # The reader reconstructs the same records, oldest first.
    assert read(sink_path) == records


def test_sink_is_inert_until_given_a_path() -> None:
    sink = ShadowSink()
    assert sink.path is None
    # Appending to an unwired sink is a no-op, not an error.
    sink.append(_rec())


def test_read_of_a_missing_file_is_empty(tmp_path: Path) -> None:
    assert read(tmp_path / "nope.jsonl") == []


def test_recall_at_k_counts_rank1_within_the_top_k(tmp_path: Path) -> None:
    del tmp_path  # pure function; nothing touches the disk
    records = [
        _rec(candidates=("a", "b", "c"), rank1="a"),  # rank1 at position 0
        _rec(candidates=("b", "a", "c"), rank1="a"),  # rank1 at position 1
        _rec(candidates=("b", "c", "a"), rank1="a"),  # rank1 at position 2
        _rec(candidates=("x", "y"), rank1="a"),  # rank1 not among the candidates
    ]
    assert recall_at_k(records, 1) == 0.25
    assert recall_at_k(records, 2) == 0.5
    assert recall_at_k(records, 3) == 0.75


def test_rates_are_fractions_of_the_records(tmp_path: Path) -> None:
    del tmp_path
    records = [
        _rec(pick="b", rank1="a"),  # override
        _rec(pick="a", rank1="a"),  # agrees
        _rec(pick=None, abstain=True),  # abstained, no pick
        _rec(pick="c", rank1="a", parse_fail=True),  # override and unparseable
    ]
    assert override_rate(records) == 0.5
    assert abstain_rate(records) == 0.25
    assert parse_fail_rate(records) == 0.25


def test_per_letter_distribution_counts_picks_by_position(tmp_path: Path) -> None:
    del tmp_path
    records = [
        _rec(candidates=("a", "b", "c"), pick="a"),  # A
        _rec(candidates=("a", "b", "c"), pick="b"),  # B
        _rec(candidates=("a", "b", "c"), pick="b"),  # B
        _rec(candidates=("a", "b", "c"), pick=None),  # abstained: no letter
    ]
    assert per_letter_distribution(records) == {"A": 1, "B": 2}


def test_confidence_by_field_averages_each_fields_confidence(tmp_path: Path) -> None:
    del tmp_path
    records = [
        _rec(field="price", confidence=0.8),
        _rec(field="price", confidence=0.6),
        _rec(field="scope", confidence=0.5),
    ]
    assert confidence_by_field(records) == {"price": 0.7, "scope": 0.5}


def test_aggregations_over_no_records_are_empty() -> None:
    assert recall_at_k([], 1) == 0.0
    assert override_rate([]) == 0.0
    assert abstain_rate([]) == 0.0
    assert parse_fail_rate([]) == 0.0
    assert per_letter_distribution([]) == {}
    assert confidence_by_field([]) == {}
