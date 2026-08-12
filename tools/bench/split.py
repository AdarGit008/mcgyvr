#!/usr/bin/env python3
"""#225 — the bench/reserve split rule, committed before anything was read.

One function decides which half of the campaign an admitted problem belongs
to, from its id alone. The rule was declared in
``docs/bench-design-2026-08-10.md`` and committed here before any generated
problem existed — that ordering, not the hash, is what makes the split blind:
no prose, no difficulty figure, no measurement can move a problem across the
line, and nothing that arrives later can have been fitted to it.

Properties the campaign leans on:

* **Stable under pauses.** Assignment depends only on the id string, so a
  spend-limit pause, a refill batch, or a retired id changes nothing already
  assigned (#197's record makes pauses a certainty).
* **A problem moves as a unit.** The id names the problem; both language
  arms travel with it. A one-armed problem is never split — it is deleted.
* **Representative in expectation, reported rather than repaired.** Each
  steering cell splits ~50/50 with binomial noise; the gate reports realized
  counts per cell, and a skewed cell is recorded and lived with, because
  rebalancing after the fact is exactly the fitting this rule exists to
  prevent.

``python tools/bench/split.py b001-ring-buffer …`` prints one ``id<TAB>half``
line per argument; ``--check`` verifies a stream of ``id half`` pairs on
stdin (the manifest audit's seam).
"""

from __future__ import annotations

import argparse
import hashlib
import sys

# The salt is part of the declared rule. Changing it re-splits the campaign,
# so it changes never; a second campaign (there is not meant to be one)
# would declare its own.
SALT = "mcgyvr-bench-split-2026-08-10:"

BENCH = "bench"
RESERVE = "reserve"


def assignment(problem_id: str) -> str:
    """Which half ``problem_id`` belongs to — ``"bench"`` or ``"reserve"``."""
    digest = hashlib.sha256((SALT + problem_id).encode("utf-8")).hexdigest()
    return BENCH if int(digest[:8], 16) % 2 == 0 else RESERVE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="problem ids to assign")
    parser.add_argument(
        "--check",
        action="store_true",
        help="read `id half` pairs from stdin and exit 1 on any mismatch",
    )
    args = parser.parse_args(argv)

    if args.check:
        bad = 0
        for line in sys.stdin:
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 2:
                print(f"unreadable line: {line.rstrip()}", file=sys.stderr)
                bad += 1
                continue
            problem_id, recorded = fields
            actual = assignment(problem_id)
            if recorded != actual:
                print(
                    f"{problem_id}: recorded {recorded!r}, rule says {actual!r}",
                    file=sys.stderr,
                )
                bad += 1
        return 1 if bad else 0

    for problem_id in args.ids:
        print(f"{problem_id}\t{assignment(problem_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
