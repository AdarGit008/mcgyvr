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

**And provenance now includes which instrument a run belongs to (#230).** This
corpus is walked by ``tools/finetune/build_dataset.py`` on its way to a
training set, so a run over a measurement set joins the training path at the
moment it lands — that is how #189 came to train on 622 examples drawn from
``d1``, the set it was then scored on. The guard belongs here, at the point of
entry, and it is a **stamp rather than an exclusion**: every run is classified
against ``tools/instruments.json`` and the verdict is written into the
document, so the training path can refuse what the parser corpus must keep.

Keeping it is not a compromise. ADR-0016 is explicit that the population the
parser is measured against must be the one it actually faces, and 8,432 of
these replies came from ``d1``; dropping them to protect a *different*
consumer would curate the parser's corpus down to the shapes that happen to be
safe for fine-tuning. A stamp serves both readers. What it must not be is
optional: a run whose provenance cannot be decided at all is a ``PinError``,
not a clean run, because an unstamped run reaches the builder as material.

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
import importlib.util
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
DECLARATION = REPO / "tools" / "instruments.json"


class PinError(Exception):
    """A reply that cannot be pinned: no row, or bytes the row disagrees with."""


def _instruments() -> Any:
    """The instrument declaration, imported by path — ``tools/`` is no package.

    Loaded once per process and shared: the declaration is meant to be one
    object with one answer, so a second copy with its own cache is exactly
    the drift this module exists to prevent.
    """
    cached = sys.modules.get("instruments")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "instruments", REPO / "tools" / "instruments.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_label(run: Path) -> str:
    """A run's key in this document: its path under ``records/measurements/``."""
    try:
        return run.relative_to(MEASUREMENTS).as_posix()
    except ValueError:
        return run.as_posix()


def _provenance(run: Path, task_ids: set[str]) -> dict[str, Any]:
    """Which declared instrument this run's material belongs to, and why.

    The run's own ``run.json`` is the evidence — the tier it named and the
    contract digests it pinned — supplemented by the task ids its captures
    carry, which is all a run that recorded neither leaves behind. An
    unreadable or absent ``run.json`` is not an acquittal: without it there is
    nothing to classify, and this raises.
    """
    instruments = _instruments()
    meta: dict[str, Any] = {}
    manifest = run / "run.json"
    if manifest.is_file():
        meta = json.loads(manifest.read_text(encoding="utf-8"))
    where = _run_label(run)
    try:
        verdict = instruments.classify(meta, where=where, task_ids=task_ids)
    except instruments.InstrumentError as exc:
        raise PinError(
            f"{where}: {exc}. Every run under records/measurements/ is walked "
            "into this corpus and from there into the training path, so a run "
            "that cannot be classified against tools/instruments.json cannot "
            "be pinned"
        ) from exc
    return {
        "sets": list(verdict.sets),
        "primary": verdict.primary,
        "why": verdict.why,
    }


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
    # Read bytes, not text: ``read_text`` translates CRLF to LF, so a reply
    # whose model emitted Windows line endings gets hashed as bytes it never
    # sent and rejected against its own row — and, worse, reaches the parser
    # in a shape nobody measured. The row's sha is taken over the raw
    # completion, so this one must be too.
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
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
        "run": _run_label(run),
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
    instruments: dict[str, dict[str, Any]] = {}
    for results in sorted(MEASUREMENTS.rglob("results.jsonl")):
        run = results.parent
        rows = _rows(run)
        found: list[dict[str, Any]] = []
        for path in sorted(run.glob("candidates/*/*.txt")):
            found.append(_entry(run, path, _join_candidate(path, rows)))
        for path in sorted(run.glob("replies/*.txt")):
            found.append(_entry(run, path, _join_reply(path, rows)))
        if not found:
            continue
        # Classified from the task ids that actually produced captures, so a
        # run is judged on the material it contributed rather than on the set
        # it was configured with.
        task_ids = {str(row["task"]) for row in rows}
        instruments[_run_label(run)] = _provenance(run, task_ids)
        entries.extend(found)
    entries.sort(key=lambda e: (e["run"], e["file"]))
    refusals = sum(1 for e in entries if "refusal" in e["expect"])
    tainted = sum(1 for e in entries if instruments[e["run"]]["sets"])
    return {
        # /2: every run carries its instrument verdict (#230). Entries are
        # unchanged — the verdict is a property of the run, so it is recorded
        # once per run rather than repeated on each of its replies.
        "record": "reply-corpus/2",
        "issue": 184,
        "totals": {
            "replies": len(entries),
            "parses": len(entries) - refusals,
            "refusals": refusals,
            "instrument_replies": tainted,
        },
        "instruments": {
            "declared": DECLARATION.relative_to(REPO).as_posix(),
            "runs": dict(sorted(instruments.items())),
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
