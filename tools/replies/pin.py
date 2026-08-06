#!/usr/bin/env python3
"""#184 — pin every captured worker reply as the parser's golden corpus.

The corpus is the raw reply files the measurement rigs already write —
``candidates/`` under a breadth run, ``replies/`` under a bundle run — left
exactly where they landed. This tool does not copy or curate them; per
ADR-0016 a curation step is a step that gets skipped, and the population the
parser is measured against must be the one it actually faces. What this
writes is ``golden.json``: for each captured reply, the inputs the parser was
given (the stop reason from the run's own row, the output schema) and the
outcome it produced, so the whole set replays to the same verdicts or the
suite says which reply moved.

**Parse failures are pinned as gold, not excluded.** A reply the parser
refuses is the expected outcome for that input until someone improves the
parser and re-pins deliberately — the refused shapes are exactly the ones a
hand-authored fixture set is bounded away from (#174 is the receipt).

**Provenance is the join, and it must hold.** Every reply file is joined to
its row in the run's ``results.jsonl`` — that is where the stop reason lives,
and the parser's verdict depends on it. A reply with no row, or whose bytes
disagree with the sha the row recorded, is an error rather than an entry: a
fixture that cannot say where it came from is the thing this corpus exists
to replace.

Usage::

    # re-pin after a run added replies (the diff shows in git)
    uv run --no-sync python tools/replies/pin.py

    # recompute and compare against the pinned copy, changing nothing
    uv run --no-sync python tools/replies/pin.py --check

``tests/test_reply_corpus.py`` runs the same recomputation offline on every
suite run, so drift is caught without anyone remembering ``--check``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from mcgyvr.runner import StopReason  # noqa: E402
from mcgyvr.worker.reply import WHOLE_FILE, ReplyError, parse_reply  # noqa: E402

MEASUREMENTS = REPO / "records" / "measurements"
GOLDEN = REPO / "records" / "corpora" / "worker-replies" / "golden.json"


class PinError(Exception):
    """A reply that cannot be pinned: no row, or bytes the row disagrees with."""


def _rows(run: Path) -> list[dict[str, Any]]:
    rows = []
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _join_candidate(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """A breadth capture: ``candidates/<task>/<arm>-<draw>.txt``."""
    task = path.parent.name
    arm, _, draw = path.stem.rpartition("-")
    for row in rows:
        if (row["task"], row.get("arm"), str(row.get("draw"))) == (task, arm, draw):
            return {
                "stop_reason": row["stop_reason"],
                "model": row["model"],
                "row_sha": row.get("candidate_sha256"),
            }
    raise PinError(f"{path}: no row for (task={task}, arm={arm}, draw={draw})")


def _join_reply(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """A bundle capture: ``replies/<task>-<condition>-<attempt>.txt``."""
    task, condition, attempt = path.stem.rsplit("-", 2)
    for row in rows:
        if (row["task"], row["condition"]) == (task, condition):
            if attempt == "1":
                return {
                    "stop_reason": row["stop_reason"],
                    "model": row["model"],
                    "row_sha": row.get("reply_sha256"),
                }
            if "retry_stop_reason" not in row:
                raise PinError(
                    f"{path}: the row records no retry_stop_reason, so this "
                    "retry cannot be replayed with the reason it was parsed with"
                )
            return {
                "stop_reason": row["retry_stop_reason"],
                "model": row["model"],
                "row_sha": row.get("retry_sha256"),
            }
    raise PinError(f"{path}: no row for (task={task}, condition={condition})")


def _entry(run: Path, path: Path, joined: dict[str, Any]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if joined["row_sha"] is not None and joined["row_sha"] != sha:
        raise PinError(
            f"{path}: file bytes disagree with the sha its row recorded "
            f"({sha} != {joined['row_sha']})"
        )
    parsed = parse_reply(
        text,
        output_schema=WHOLE_FILE,
        stop_reason=StopReason(joined["stop_reason"]),
    )
    if isinstance(parsed, ReplyError):
        expect: dict[str, Any] = {"refusal": parsed.code}
    else:
        expect = {
            "content_sha256": hashlib.sha256(
                parsed.content.encode("utf-8")
            ).hexdigest(),
            "info_string": parsed.info_string,
        }
    return {
        "run": run.relative_to(MEASUREMENTS).as_posix(),
        "file": path.relative_to(run).as_posix(),
        "sha256": sha,
        "model": joined["model"],
        "stop_reason": joined["stop_reason"],
        "output_schema": WHOLE_FILE,
        "expect": expect,
    }


def compute() -> dict[str, Any]:
    """The golden document, recomputed from what is on disk right now."""
    entries: list[dict[str, Any]] = []
    for results in sorted(MEASUREMENTS.rglob("results.jsonl")):
        run = results.parent
        rows = _rows(run)
        for path in sorted(run.glob("candidates/*/*.txt")):
            entries.append(_entry(run, path, _join_candidate(path, rows)))
        for path in sorted(run.glob("replies/*.txt")):
            entries.append(_entry(run, path, _join_reply(path, rows)))
    entries.sort(key=lambda e: (e["run"], e["file"]))
    refusals = sum(1 for e in entries if "refusal" in e["expect"])
    return {
        "record": "reply-corpus/1",
        "issue": 184,
        "totals": {
            "replies": len(entries),
            "parses": len(entries) - refusals,
            "refusals": refusals,
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare against the pinned golden file, writing nothing",
    )
    args = parser.parse_args()

    try:
        doc = compute()
    except PinError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(doc, indent=2) + "\n"
    if args.check:
        pinned = GOLDEN.read_text(encoding="utf-8") if GOLDEN.is_file() else ""
        if pinned == rendered:
            print(f"golden matches: {doc['totals']['replies']} replies")
            return 0
        print(
            "golden drifts from what is on disk; re-pin deliberately",
            file=sys.stderr,
        )
        return 1

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(rendered, encoding="utf-8")
    print(
        f"pinned {doc['totals']['replies']} replies "
        f"({doc['totals']['refusals']} refusals kept as gold) -> "
        f"{GOLDEN.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
