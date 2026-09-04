#!/usr/bin/env python3
"""A reviewer's table over the live journal — folded and joined, never the journal.

The journal ``mcgyvr run`` writes (under the config's ``journal.dir``, or
``--record DIR``) is append-only
for two reasons :mod:`mcgyvr.telemetry` states — several orchestrators can write
one directory, and a crash mid-write loses one line — and both hold only as
long as nothing else opens a ``.jsonl`` for writing. A reviewer wants the
opposite shape: one row per attempt with its final outcome already applied and
the prompt and the reply beside it as text, in something that takes a
``WHERE``. This tool builds that shape as a separate artifact,
``DIR/index.sqlite``, and leaves the journal exactly as it found it — the
``.jsonl`` files are opened read-only and are byte-identical before and after.

**Rebuilt from scratch, every run.** An index that updated in place would need
to know which lines it had already seen, which is state kept beside a journal
that keeps none, and the first orchestrator to append after a partial build
would leave rows the index silently lacked. Folding a directory of ``.jsonl``
is cheap: the index is a cache of ``telemetry.fold``, and a cache that is
rebuilt cannot be stale. Running it twice yields the same rows.

**One row per folded attempt.** ``fold`` applies corrections latest-wins in
file order and returns orphan corrections — a correction naming no attempt —
verbatim after the attempts. Here a correction is a column (``outcome``,
``detail``, ``applied_by`` — the winning verdict, its words and the writer who
gave it) and not a row, and an orphan is dropped: ``fold`` surfaces it for
a reader of the journal, but it is not an attempt, and a table of attempts
that listed it would count a mistake as a dispatch.

**The blobs are joined as text, not as names.** ``prompt_text`` and
``reply_text`` are the bytes of ``DIR/blobs/<sha>``, decoded; the digests stay
beside them so a row can still be checked against the store. A blob that is
missing is ``NULL``, never ``""`` — an empty reply is a blob of zero bytes
with a name, and the two must not read the same.

**Every column is nullable**, because every key on a journal row is optional:
``reply_sha256`` is absent on an attempt that raised, ``round`` and
``product_sha256`` are absent outside a checkout, ``outcome`` is absent until
someone corrects. ``NULL`` is the SQL spelling of absent-is-honest.

**``off_round`` is the reader's verdict, and the one derived column.** A row
written inside the checkout carries ``round`` and ``product_sha256`` — the
open round's id and the digest of the tree that dispatched — and the digest is
the tree's whether or not that tree was the round's: :mod:`mcgyvr.telemetry`
records off-round rather than refusing it, so the journal does not go dark on
the days the product is changing, and leaves the flagging to the reader. This
is the reader. ``off_round`` is ``0`` when the row's digest is the one
``tools/bench/rounds.json`` pins for the row's round, ``1`` when it differs,
and ``NULL`` when nothing can be said — the row has no round (an install that
is not this checkout) or names one the file has never opened. Never ``0`` for
a digest nobody can check: a comparison that did not happen is not one that
passed. It is judged at build time against the rounds file of the checkout
that builds, which is one more reason the index is rebuilt rather than
updated — a round opened after a row was written is found by the next build.

Usage::

    uv run --no-sync python tools/live/index.py DIR
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import os
import re
import sqlite3
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mcgyvr.telemetry import ATTEMPT_KIND, BLOB_DIR, fold

HERE = Path(__file__).resolve().parent
INDEX_NAME = "index.sqlite"
TABLE = "attempts"

#: The ``sys.modules`` slot ``tools/bench/product.py`` is loaded into — the one
#: :mod:`mcgyvr.telemetry` and ``tools/breadth/measure.py`` use, so a process
#: that already holds the module is not handed a second copy that could
#: disagree with the first about what the rounds file pins.
PRODUCT_SLOT = "bench_product"

#: The table: one column per journal key a reviewer filters or reads on, the
#: two joined blob texts, the reader's ``off_round`` verdict, and the journal
#: file the row came from. Every column is nullable — see the module docstring.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("attempt_id", "TEXT"),
    ("orchestrator", "TEXT"),
    ("session_file", "TEXT"),
    ("task_type", "TEXT"),
    ("rung", "TEXT"),
    ("ok", "INTEGER"),
    ("ts", "REAL"),
    ("elapsed_s", "REAL"),
    ("latency_s", "REAL"),
    ("input_tokens", "INTEGER"),
    ("output_tokens", "INTEGER"),
    ("model", "TEXT"),
    ("endpoint", "TEXT"),
    ("protocol", "TEXT"),
    ("condition", "TEXT"),
    ("round", "TEXT"),
    ("product_sha256", "TEXT"),
    ("off_round", "INTEGER"),
    ("bundle_sha256", "TEXT"),
    ("prompt_sha256", "TEXT"),
    ("reply_sha256", "TEXT"),
    ("prompt_text", "TEXT"),
    ("reply_text", "TEXT"),
    ("outcome", "TEXT"),
    ("detail", "TEXT"),
    ("applied_by", "TEXT"),
    ("error", "TEXT"),
    ("error_detail", "TEXT"),
    ("journal", "TEXT"),
)

# What a name in a content-addressed store looks like. A row is data written
# by somebody else's process; a value that is not a digest names nothing in
# the store and is never turned into a path.
_DIGEST = re.compile(r"[0-9a-f]{64}")


def journals(directory: Path) -> list[Path]:
    """The ``*.jsonl`` files directly under ``directory``, in name order."""
    return sorted(p for p in directory.glob("*.jsonl") if p.is_file())


def attempts(directory: Path) -> list[dict[str, Any]]:
    """Every folded attempt under ``directory``, tagged with the journal it came from.

    ``fold`` is the only reader of a journal's lines this tool has, so a
    correction is applied exactly as the product applies it — latest-wins, in
    file order — and the file is only ever read. Orphan corrections come back
    from ``fold`` after the attempts and are dropped here: they are not
    attempts.
    """
    rows: list[dict[str, Any]] = []
    for journal in journals(directory):
        for record in fold(path=journal):
            if record.get("record_kind") != ATTEMPT_KIND:
                continue
            rows.append({**record, "journal": journal.name})
    return rows


def blob_text(directory: Path, digest: object) -> str | None:
    """The text of ``DIR/blobs/<digest>``, or ``None`` when there is no such blob.

    ``None`` and not ``""``: an empty reply is a blob of zero bytes with a
    name, a missing blob is a row naming evidence that does not exist, and the
    two must not read the same. Decoded with replacement rather than strictly
    because a blob holds what was sent, surrogates and all, and a reviewer is
    better served by one replacement character than by no text.
    """
    if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
        return None
    try:
        data: bytes = (directory / BLOB_DIR / digest).read_bytes()
    except FileNotFoundError:
        return None
    return data.decode("utf-8", "replace")


def _bench_product() -> types.ModuleType:
    """``tools/bench/product.py`` by path — ``tools/`` is not a package.

    The rounds file and its reader are the bench's; this tool asks it what a
    round pins rather than parsing the file itself, so there is one reading of
    ``rounds.json`` and not two that could disagree.
    """
    cached = sys.modules.get(PRODUCT_SLOT)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        PRODUCT_SLOT, HERE.parent / "bench" / "product.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@functools.cache
def pinned_digests() -> dict[str, str]:
    """Each round's id to the ``product_sha256`` the rounds file pins for it.

    Read once per process: the file is the checkout's, not any row's, and a
    build asks for every row.
    """
    return {
        str(entry["id"]): entry["product_sha256"]
        for entry in _bench_product().load_rounds()
        if isinstance(entry.get("product_sha256"), str)
    }


def off_round(row: Mapping[str, Any]) -> int | None:
    """Whether the tree that wrote ``row`` was off its round: ``1``, ``0`` or ``None``.

    ``0`` when the row's ``product_sha256`` is the digest the rounds file pins
    for the row's ``round``, ``1`` when it differs. ``None`` when there is
    nothing to compare — the row has no round or no digest, or names a round
    the file has never opened — and never ``0`` in its place: a digest nobody
    can check is not a digest that checked out.
    """
    round_id = row.get("round")
    digest = row.get("product_sha256")
    if not isinstance(round_id, str) or not isinstance(digest, str):
        return None
    pinned = pinned_digests().get(round_id)
    if pinned is None:
        return None
    return int(digest != pinned)


def _cell(directory: Path, row: dict[str, Any], column: str) -> Any:
    """One column's value for ``row``: its key, a joined blob, a verdict or ``NULL``."""
    if column == "off_round":
        return off_round(row)
    if column == "prompt_text":
        return blob_text(directory, row.get("prompt_sha256"))
    if column == "reply_text":
        return blob_text(directory, row.get("reply_sha256"))
    value = row.get(column)
    if value is None or isinstance(value, str | int | float):
        return value  # a bool is an int, and sqlite keeps True as 1
    return json.dumps(value)


def build(directory: Path) -> int:
    """Rebuild ``DIR/index.sqlite`` from every journal under ``DIR``; return the count.

    Built in a staging file and moved into place, so a reviewer holding the
    previous index keeps a whole table and never a half-built one, and a build
    that fails leaves the previous index standing.
    """
    rows = attempts(directory)
    index = directory / INDEX_NAME
    staging = directory / f".{INDEX_NAME}.part"
    staging.unlink(missing_ok=True)
    columns = ", ".join(f'"{name}" {kind}' for name, kind in COLUMNS)
    names = ", ".join(f'"{name}"' for name, _ in COLUMNS)
    marks = ", ".join("?" for _ in COLUMNS)
    db = sqlite3.connect(staging)
    try:
        with db:
            db.execute(f'CREATE TABLE "{TABLE}" ({columns})')
            db.executemany(
                f'INSERT INTO "{TABLE}" ({names}) VALUES ({marks})',
                [
                    tuple(_cell(directory, row, name) for name, _ in COLUMNS)
                    for row in rows
                ],
            )
    finally:
        db.close()
    os.replace(staging, index)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "directory",
        metavar="DIR",
        type=Path,
        help="the journal directory: DIR/*.jsonl and DIR/blobs/",
    )
    args = parser.parse_args(argv)
    directory: Path = args.directory
    if not directory.is_dir():
        print(
            f"error: {directory} is not a directory. The index is built over "
            f"DIR/*.jsonl and DIR/blobs/, and nothing was written.",
            file=sys.stderr,
        )
        return 2
    count = build(directory)
    print(
        f"{directory / INDEX_NAME}: {count} attempts from "
        f"{len(journals(directory))} journal(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
