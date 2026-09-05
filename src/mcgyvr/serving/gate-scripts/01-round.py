#!/usr/bin/env python3
"""gate 1 — the tree is on the open product round.

Runs first and reaches no rig, so a tree that is not pinned costs no rig time.
A measurement taken against an unpinned tree is not comparable with any other
measurement, which makes it worse than no measurement: it looks like evidence.
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
        round_id, digest = product.require_pinned()
    except product.ProductError as error:
        refuse(
            f"gate 1: {error}. The tree is not on the open round and nothing "
            "is measured on it"
        )

    if not round_id or not digest:
        refuse(
            f"gate 1: require_pinned() returned round={round_id!r} "
            f"digest={digest!r}; a round it cannot name is not a round it checked"
        )
    export("RUN_ROUND", round_id)
    export("RUN_PRODUCT_SHA256", digest)
    print(f"gate 1: round={round_id} product_sha256={digest[:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
