#!/usr/bin/env python3
"""Read what the product dispatched: the prompt, the reply and how it landed.

The whole reason the live journal keeps text (:mod:`mcgyvr.telemetry`, *the
text is kept*) is that someone can read what a rung was asked and what it
answered and judge whether the answer was any good — a number says a rung
answered, and only the prompt beside the reply says whether it should have
been accepted. This is that reader: one prompt/reply/outcome triple per
matching attempt, straight out of the journal directory — the ``*.jsonl``
files folded and the blobs joined by hash — with no index built first,
because a review must not depend on a second artifact being up to date.

**The filter is the point as much as the printing.** A reviewer asking for
the rejected attempts who is handed the accepted ones too has to redo the
filter by eye over prompts that run to pages, and a review nobody can narrow
is a review nobody runs. ``--outcome`` keeps the attempts whose *folded*
outcome — the latest correction, as ``fold`` decides — is the word given;
``--orchestrator`` keeps one writer's. An attempt nobody has corrected has no
outcome and is printed and filtered as ``uncorrected``, so the word on the
screen is the word that selects it.

**Absent is printed as absent.** A raised attempt has no reply and says so
with its error; a blob the row names and the store lacks is reported as
missing. Neither is printed as an empty reply, which is a thing a model can
actually produce.

**The header says which product answered.** A row written inside the checkout
names its ``round`` and the digest of the tree that dispatched, and
:mod:`mcgyvr.telemetry` records an off-round tree rather than refusing it —
the reader flags it. So each header carries one word from ``index.off_round``:
``on-round``, ``off-round``, or ``round-unknown`` for a row with no round to
check against or one the rounds file never opened. A reviewer judging a reply
is judging a product revision, and the word says which one it was.

Usage::

    uv run --no-sync python tools/live/review.py DIR [--outcome X] [--orchestrator ID]
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

#: The word printed, and accepted by ``--outcome``, for an attempt no
#: correction has named yet. A word rather than an empty field so the screen
#: and the filter agree.
UNCORRECTED = "uncorrected"

#: The word printed for each answer ``index.off_round`` can give. A row nobody
#: can check is ``round-unknown`` and not ``on-round``: absent-is-honest.
ROUND_WORDS: dict[int | None, str] = {
    0: "on-round",
    1: "off-round",
    None: "round-unknown",
}


def _live_index() -> types.ModuleType:
    """``tools/live/index.py`` by path — ``tools/`` is not a package.

    The folding and blob-joining are its; this tool prints. One reader of the
    journal directory, not two that could disagree about what a row is.
    """
    cached = sys.modules.get("live_index")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("live_index", HERE / "index.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


index = _live_index()


def selected(
    rows: list[dict[str, Any]],
    *,
    outcome: str | None,
    orchestrator: str | None,
) -> list[dict[str, Any]]:
    """The attempts a reviewer asked for, and none of the others."""
    kept: list[dict[str, Any]] = []
    for row in rows:
        if outcome is not None and row.get("outcome", UNCORRECTED) != outcome:
            continue
        if orchestrator is not None and row.get("orchestrator") != orchestrator:
            continue
        kept.append(row)
    return kept


def render(directory: Path, row: dict[str, Any]) -> str:
    """One attempt as a reviewer reads it: a header, the prompt, the reply."""
    lines = [
        f"=== {row.get('attempt_id', '<no attempt_id>')}  "
        f"orchestrator={row.get('orchestrator', '<none>')}  "
        f"rung={row.get('rung', '<none>')}  "
        f"outcome={row.get('outcome', UNCORRECTED)}  "
        f"round={row.get('round', '<none>')}  {ROUND_WORDS[index.off_round(row)]}"
    ]
    if row.get("session_file"):
        lines.append(f"    session={row['session_file']}")
    if row.get("detail"):
        lines.append(f"    detail: {row['detail']}")
    lines.append(
        _section(
            "prompt", directory, row.get("prompt_sha256"), absent="no prompt recorded"
        )
    )
    if row.get("ok") is False:
        error = f"{row.get('error', '<unnamed>')}: {row.get('error_detail', '')}"
        lines.append(f"--- reply: none — the attempt raised {error.rstrip(': ')}")
    else:
        lines.append(
            _section(
                "reply",
                directory,
                row.get("reply_sha256"),
                absent="no reply recorded (the attempt returned no completion)",
            )
        )
    return "\n".join(lines) + "\n"


def _section(name: str, directory: Path, digest: object, *, absent: str) -> str:
    """The blob ``digest`` names, under a heading, or a line saying why not."""
    if digest is None:
        return f"--- {name}: {absent}"
    text = index.blob_text(directory, digest)
    if text is None:
        return (
            f"--- {name}: blob {digest} is named by the row and missing from "
            f"{directory / index.BLOB_DIR}"
        )
    return f"--- {name} ({str(digest)[:12]})\n{text}"


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
    parser.add_argument(
        "--outcome",
        metavar="X",
        default=None,
        help=(
            f"keep the attempts whose folded outcome is X; {UNCORRECTED!r} "
            f"selects the ones nobody has corrected"
        ),
    )
    parser.add_argument(
        "--orchestrator",
        metavar="ID",
        default=None,
        help="keep the attempts one writer recorded",
    )
    args = parser.parse_args(argv)
    directory: Path = args.directory
    if not directory.is_dir():
        print(
            f"error: {directory} is not a directory. A review reads DIR/*.jsonl "
            f"and DIR/blobs/, and there is nothing here to read.",
            file=sys.stderr,
        )
        return 2
    rows = index.attempts(directory)
    shown = selected(rows, outcome=args.outcome, orchestrator=args.orchestrator)
    for row in shown:
        sys.stdout.write(render(directory, row))
    print(f"{len(shown)} of {len(rows)} attempts shown", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
