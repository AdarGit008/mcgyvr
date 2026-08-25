#!/usr/bin/env python3
"""footprints.csv from the survey journal: one row per phase-0 cell.

Two engines, two shapes, one table (ADR-0040). An ollama cell fills `size`,
`size_vram` and `fraction`; a vLLM cell fills `process_mib` and leaves
`fraction` EMPTY with `fraction_refused_reason` carrying the engine's own
words. A field an engine cannot state is empty here and is never a zero: a
zero would read as a measurement.

`card_mib_before` and `card_mib_after_load` are readings of the CARD; the
per-process figure is a different field and neither substitutes for the other
(4-9 MiB is held on these rigs and attributed to nobody).

Usage:  python3 footprints.py cells.jsonl footprints.csv
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

COLUMNS = (
    "host",
    "engine",
    "model",
    "card_mib_before",
    "card_mib_after_load",
    "process_mib",
    "size",
    "size_vram",
    "fraction",
    "fraction_refused_reason",
    "outcome",
    "refusal_reason",
)


def blank(value: Any) -> Any:
    """`None` becomes an empty cell. Never a zero standing in for an unknown."""
    return "" if value is None else value


def engine_reasons(journal: Path) -> dict[str, Any]:
    """The ENGINE's own words for each refused cell, by label, if they were kept.

    The harness records `reasons: ["unknown"]` for a vLLM launch that never
    reached health: the process it waited on died on the RIG and its exception
    was never on the wire. The campaign's third `void_if` is that a refusal
    counted without its reason cannot be told from a harness bug, so the reason
    is read off the server's log on the host and carried here beside the
    harness's own. Absent file, absent column -- never a fabricated reason.
    """
    path = journal.parent / "engine-refusals" / "reasons.json"
    if not path.is_file():
        return {}
    return (json.loads(path.read_text(encoding="utf-8")) or {}).get("cells") or {}


def refusal_of(row: dict[str, Any], engine_said: dict[str, Any]) -> str:
    refusal = row.get("refusal") or {}
    if not refusal and row.get("outcome") == "ok":
        return ""
    reasons = ",".join(str(r) for r in (refusal.get("reasons") or []))
    stage = refusal.get("stage") or ""
    prose = refusal.get("prose") or row.get("refused") or row.get("incomplete") or ""
    said = engine_said.get(str(row.get("label"))) or {}
    engine = " ".join(
        str(said[key])
        for key in ("declared_kv", "kv_tokens", "exception", "terminal")
        if said.get(key)
    )
    if not (reasons or stage or prose or engine):
        return ""
    out = f"harness reasons=[{reasons}] stage={stage}: {prose}"
    if engine:
        out += f" || ENGINE ({said.get('source_file')}): {engine}"
    return out


def card_before(row: dict[str, Any], engine: str) -> Any:
    """The card TOTAL immediately before this cell's load.

    ollama states it on the attempt itself (`card_used_mib_before_load`, read
    after its own release). vLLM's claim has no such field, so it is taken from
    the exclusion loop's release of the OTHER engine -- the last reading of the
    card before this engine started. The config alternates engines per host so
    that reading is never taken while a previous vLLM server still held the
    card.
    """
    attempts = (row.get("claim") or {}).get("attempts") or (
        row.get("refusal") or {}
    ).get("attempts")
    if engine == "ollama" and attempts:
        return attempts[-1].get("card_used_mib_before_load")
    yielded = row.get("yielded") or {}
    for other, evidence in yielded.items():
        if other != engine and isinstance(evidence, dict):
            return evidence.get("card_used_mib")
    return None


def ollama_cell(row: dict[str, Any]) -> dict[str, Any]:
    attempts = (
        (row.get("claim") or {}).get("attempts")
        or (row.get("refusal") or {}).get("attempts")
        or []
    )
    last = attempts[-1] if attempts else {}
    return {
        "card_mib_before": blank(card_before(row, "ollama")),
        "card_mib_after_load": blank(last.get("card_used_mib_after_load")),
        # This engine states no per-process card attribution anywhere, so the
        # column is empty rather than filled from a different quantity.
        "process_mib": "",
        "size": blank(last.get("size")),
        "size_vram": blank(last.get("size_vram")),
        "fraction": blank(last.get("vram_fraction")),
        "fraction_refused_reason": "",
    }


def vllm_cell(row: dict[str, Any]) -> dict[str, Any]:
    checks = (row.get("claim") or {}).get("checks") or {}
    placements = checks.get("resident_placements") or []
    model = row.get("model")
    named = [p for p in placements if p.get("name") == model]
    mine = named[0] if named else None
    refused = ""
    if mine is not None:
        refused = mine.get("fraction_refused") or ""
    elif placements:
        refused = placements[0].get("fraction_refused") or ""
    elif checks.get("resident_placements_refused"):
        refused = f"placements unread: {checks['resident_placements_refused']}"
    else:
        # A refused cell has no placement row at all, so there is no row-level
        # reason to copy. The column still says why the fraction is empty --
        # empty here is REFUSED, not missing, and it is refused for this engine
        # whether or not this particular launch came up (ADR-0040).
        refused = (
            "no placement row: this cell refused before the engine held the "
            "card. The fraction is refused for this engine either way -- it "
            "takes its whole allocation or does not start, so there is no "
            "denominator (ADR-0040)"
        )
    return {
        "card_mib_before": blank(card_before(row, "vllm")),
        "card_mib_after_load": blank(checks.get("gpu_used_mib")),
        "process_mib": blank(mine.get("card_mib")) if mine else "",
        # This engine spills nothing, so it states none of the three.
        "size": "",
        "size_vram": "",
        "fraction": "",
        "fraction_refused_reason": refused,
    }


def rows(journal: Path) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in journal.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("metric") == "phase" or row.get("phase") == "survey":
            continue
        host, label = row.get("host"), row.get("label")
        if not host or not label:
            continue
        out[f"{host}\0{label}"] = row  # last write wins
    said = engine_reasons(journal)
    table = []
    for row in out.values():
        engine = str(row.get("backend"))
        cell = {
            "host": row.get("host"),
            "engine": engine,
            "model": row.get("model"),
            "outcome": row.get("outcome"),
            "refusal_reason": refusal_of(row, said),
        }
        cell.update(ollama_cell(row) if engine == "ollama" else vllm_cell(row))
        table.append({key: cell.get(key, "") for key in COLUMNS})
    order = {"srv1": 0, "srv2": 1}
    table.sort(
        key=lambda r: (order.get(str(r["host"]), 9), str(r["engine"]), str(r["model"]))
    )
    return table


def main(argv: list[str]) -> int:
    journal, out = Path(argv[1]), Path(argv[2])
    table = rows(journal)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        writer.writerows(table)
    print(f"wrote {out} ({len(table)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
