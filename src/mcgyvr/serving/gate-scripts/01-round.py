#!/usr/bin/env python3
"""gate 1 — name the round this run is measured under, opening one if needed.

Runs first and reaches no rig, so the round is settled before any rig time is
spent. A measurement taken against an unpinned tree is not comparable with any
other measurement, which makes it worse than no measurement: it looks like
evidence — so every run is stamped with a round that pins the tree it ran on.

It gets there by drawing the boundary rather than demanding it (owner,
2026-09-06). A round is a boundary in the record, not a permission to work: a
tree that has moved gets the next round opened for it here, pinned to the
revision about to run, and the run proceeds. What the pin is for is untouched —
two revisions never share a round — and this is exactly why the new round is
appended and the one that was open keeps the digest its own arms ran against.
"""

from __future__ import annotations

import importlib.util
import sys

from mcgyvr.serving.gatelib import door_required, export, refuse, root


def main() -> int:
    door_required("gate 1")
    # tools/ is not a package, so product.py is reached by path. Loaded here and
    # not at module scope: a gate that failed to import would refuse with a
    # traceback instead of a rule.
    path = root() / "tools" / "bench" / "product.py"
    if not path.is_file():
        refuse(f"gate 1: {path} is missing; the round cannot be checked")
    spec = importlib.util.spec_from_file_location("bench_product", path)
    assert spec is not None and spec.loader is not None
    product = importlib.util.module_from_spec(spec)
    sys.modules["bench_product"] = product
    spec.loader.exec_module(product)

    try:
        round_id, digest = product.ensure_open()
    except product.ProductError as error:
        # What is left to refuse on is a rounds file that cannot be read or a
        # surface that cannot be digested — the run has no round to be stamped
        # with either way, and a run nobody can trace to a revision is the
        # thing this gate exists to prevent.
        refuse(f"gate 1: {error}. Nothing is measured against a round it has not got")

    if not round_id or not digest:
        refuse(
            f"gate 1: ensure_open() returned round={round_id!r} "
            f"digest={digest!r}; a round it cannot name is not a round it checked"
        )
    export("RUN_ROUND", round_id)
    export("RUN_PRODUCT_SHA256", digest)
    print(f"gate 1: round={round_id} product_sha256={digest[:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
