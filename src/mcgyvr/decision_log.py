"""Shadow telemetry for the candidate-set -> jev top-1 decision loop.

One :class:`DecisionRecord` freezes a single per-field jev decision: the field
being decided, the candidate ids shown (in order), the id jev picked (or
``None`` when it abstained or its reply could not be read), the enumerator's
rank-0 id, whether jev abstained, its confidence, whether its reply failed to
parse, the round-trip latency, and the model and seed that produced it. A
:class:`ShadowSink` appends one JSON line per record to a path it is given.
Its one writer is ``mcgyvr PROMPT`` (:mod:`mcgyvr.cli.commands.delegate`), and
only under ``--log PATH`` with the fill authoring strategy: the typed
fill proposer then records to ``<PATH>.decisions.jsonl``. Otherwise no
sink is built and nothing is written. The pure helpers below answer the
wave-2 metric questions over any iterable of records: ``recall_at_k``,
``override_rate``, ``abstain_rate``, ``parse_fail_rate``,
``per_letter_distribution`` and ``confidence_by_field``. No mcgyvr command
reads them: they are the analysis API over the shadow log, for a script or an
outside tool that folds ``<PATH>.decisions.jsonl``.

This module is a shadow: it observes the decision loop and writes beside it.
It never feeds a decision back into the pipeline, and ``mcgyvr.gate.jev`` does
not call it.

The sink's line discipline is the dispatch journal's, from :mod:`mcgyvr.jsonl`:
one JSON object per line, appended under an exclusive lock so concurrent
writers append whole lines rather than interleaving them, with a torn trailing
line terminated before the next record so a crash mid-write cannot glue two
records into one unreadable line. The record vocabulary is this module's own.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr import jsonl
from mcgyvr.decision import CHOICE_LABELS

#: Labels a lettered candidate list may use, by position: the 62-label alphabet
#: :mod:`mcgyvr.decision` holds for a Choice, so a candidate shown at position 0
#: is the letter "A" in both places.
_LETTERS = CHOICE_LABELS


def _now_iso() -> str:
    """The current wall-clock time as an ISO 8601 timestamp, in UTC."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class DecisionRecord:
    """One per-field jev decision over a candidate set.

    ``candidates`` are the candidate ids in the order they were shown, so a
    record can say which *position* jev chose, not only which id. ``pick`` is
    the id jev chose, or ``None`` when its reply was unusable or absent.
    ``abstain`` covers two distinct phenomena that share the flag: (a) jev
    explicitly chose the "none" option (``pick`` is the option's id,
    ``abstain=True``), and (b) the reply was unusable or absent (``pick=None``,
    ``abstain=True``). A consumer should read ``pick is None`` / ``parse_fail``
    to separate them. ``rank1`` is the enumerator's rank-0 id — the candidate
    the enumerator itself would have chosen — against which ``pick`` is
    compared.
    """

    field: str
    candidates: tuple[str, ...]
    pick: str | None
    rank1: str
    abstain: bool
    confidence: float
    parse_fail: bool
    latency_ms: int
    model: str
    seed: str
    ts: str = dataclass_field(default_factory=_now_iso)

    @property
    def override(self) -> bool:
        """Whether jev's pick disagrees with the enumerator's rank-0 id.

        ``pick is None`` (abstained or unreadable) is not an override: jev did
        not choose anything to disagree with.
        """
        return self.pick is not None and self.pick != self.rank1

    def to_dict(self) -> dict[str, Any]:
        """The record as a plain JSON object: its fields, candidates as a list.

        ``override`` is left out on purpose — it is derived from ``pick`` and
        ``rank1`` and can be recomputed, so storing it would be a second,
        driftable spelling of the same fact.
        """
        return {
            "field": self.field,
            "candidates": list(self.candidates),
            "pick": self.pick,
            "rank1": self.rank1,
            "abstain": self.abstain,
            "confidence": self.confidence,
            "parse_fail": self.parse_fail,
            "latency_ms": self.latency_ms,
            "model": self.model,
            "seed": self.seed,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionRecord:
        """Rebuild a record from a JSON object, as ``read`` produced it.

        A ``KeyError``/``TypeError``/``ValueError`` escapes when ``data`` does
        not hold the fields a record needs; ``read`` catches those and skips the
        line, so one foreign or damaged row cannot hide the rest of the file.
        """
        return cls(
            field=str(data["field"]),
            candidates=tuple(data["candidates"]),
            pick=data.get("pick"),
            rank1=str(data["rank1"]),
            abstain=bool(data["abstain"]),
            confidence=float(data["confidence"]),
            parse_fail=bool(data["parse_fail"]),
            latency_ms=int(data["latency_ms"]),
            model=str(data["model"]),
            seed=str(data["seed"]),
            ts=str(data["ts"]),
        )


class ShadowSink:
    """Append one JSON line per :class:`DecisionRecord` to a path.

    Inert until constructed with a path: a sink built with none is a no-op, so
    telemetry is off unless a caller wires it to a file. The path's parent
    directories are created on first append.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = None if path is None else Path(path)

    @property
    def path(self) -> Path | None:
        """The sink's file, or ``None`` when it is unwired."""
        return self._path

    def append(self, record: DecisionRecord) -> None:
        """Append ``record`` as one JSON line; a no-op when unwired."""
        if self._path is None:
            return
        line = (json.dumps(record.to_dict()) + "\n").encode("utf-8")
        jsonl.append_line(self._path, line)


def read(path: Path | str) -> list[DecisionRecord]:
    """The decision records at ``path``, oldest first.

    Lines that are blank, undecodable, not JSON, or not a record are skipped,
    so one damaged line cannot hide the rest of the file. A missing file reads
    as no records at all.
    """
    records: list[DecisionRecord] = []
    for _, parsed in jsonl.read_lines(Path(path)):
        try:
            records.append(DecisionRecord.from_dict(parsed))
        except (KeyError, TypeError, ValueError):
            continue
    return records


def recall_at_k(records: Iterable[DecisionRecord], k: int) -> float:
    """The fraction of records whose ``rank1`` is within the top-``k`` candidates.

    ``k`` is a position count, not an index: ``k == 1`` asks whether the
    enumerator's rank-0 id was shown first. A record whose ``rank1`` is not
    among its candidates is a miss, as is any record when ``k <= 0``. With no
    records the recall is ``0.0``.
    """
    if k <= 0:
        return 0.0
    total = 0
    hits = 0
    for record in records:
        total += 1
        if record.rank1 in record.candidates[:k]:
            hits += 1
    return hits / total if total else 0.0


def override_rate(records: Iterable[DecisionRecord]) -> float:
    """The fraction of records where jev's pick overrode the enumerator's rank1."""
    total = 0
    overrides = 0
    for record in records:
        total += 1
        if record.override:
            overrides += 1
    return overrides / total if total else 0.0


def abstain_rate(records: Iterable[DecisionRecord]) -> float:
    """The fraction of records where jev abstained."""
    total = 0
    abstains = 0
    for record in records:
        total += 1
        if record.abstain:
            abstains += 1
    return abstains / total if total else 0.0


def parse_fail_rate(records: Iterable[DecisionRecord]) -> float:
    """The fraction of records whose reply could not be read as a decision."""
    total = 0
    failures = 0
    for record in records:
        total += 1
        if record.parse_fail:
            failures += 1
    return failures / total if total else 0.0


def per_letter_distribution(records: Iterable[DecisionRecord]) -> dict[str, int]:
    """How many picks fell on each letter position of the candidate list.

    A pick at position 0 is the letter ``A``, position 1 ``B``, and so on
    through the 62-label alphabet. A record with no pick (abstained or
    unreadable) contributes nothing, so the counts sum to the number of picks,
    not the number of records.
    """
    counts: dict[str, int] = {}
    for record in records:
        letter = _letter_of(record)
        if letter is not None:
            counts[letter] = counts.get(letter, 0) + 1
    return counts


def confidence_by_field(records: Iterable[DecisionRecord]) -> dict[str, float]:
    """The mean jev confidence per field, keyed by field name."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for record in records:
        totals[record.field] = totals.get(record.field, 0.0) + record.confidence
        counts[record.field] = counts.get(record.field, 0) + 1
    return {field_: totals[field_] / counts[field_] for field_ in totals}


def _letter_of(record: DecisionRecord) -> str | None:
    """The letter position of ``record.pick``, or ``None`` when it has none or
    lies beyond the 62-label alphabet.
    """
    if record.pick is None:
        return None
    try:
        index = record.candidates.index(record.pick)
    except ValueError:
        return None
    if index >= len(_LETTERS):
        return None
    return _LETTERS[index]
