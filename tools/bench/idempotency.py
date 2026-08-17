#!/usr/bin/env python3
"""How much of the bench is language-idempotent, asked of the corpus that exists.

The bench pairs every problem: one prose, a TypeScript rendering and a Python
one. That doubles authoring, which lane/225's record names as the expensive
axis. The question this answers is whether the pairing is *necessary* — whether
the two renderings could be one statement rendered mechanically, or whether the
languages genuinely answer some boundaries differently.

**The detector already exists.** `emit.py`'s divergence screen was built to stop
an author writing a problem whose two arms are not the same problem: `round(4.5)`
is `4` in Python — half-to-even — and `5` in JavaScript, so "a half rounds up" is
two different problems wearing one prose. This tool points that screen backwards,
at the 257 problems already admitted, and counts how many trip it.

**What a finding means here is not what it means at emission.** At emission a
divergence is a defect to fix before the problem lands. Here it is a *census*: a
problem that trips the screen is one whose statement cannot be rendered into both
languages mechanically, so it is evidence against idempotency being free. A
problem that does not trip it is evidence for — bounded by the screen's own
reach, which is a fixed pattern table, not a proof of equivalence.

**The screen is a lower bound and must be read as one.** It knows the divergences
this project has been burned by. A construct nobody has been burned by yet is
absent from the table and passes silently, exactly as `families.py` finds only
the duplicates a stand-in happens to expose.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / "tools" / "bench" / "tasks"


def _emit() -> types.ModuleType:
    """`emit.py` by path: it is a script beside this one, not an installed
    module, and importing it by name depends on how the caller was invoked."""
    spec = importlib.util.spec_from_file_location(
        "emit", Path(__file__).parent / "emit.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover — a broken tree
        raise RuntimeError("tools/bench/emit.py is not importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def spec_of(task: str) -> dict[str, Any]:
    """An admitted problem read back into the shape the screen expects.

    Only the four fields the screen reads are filled. The rest of a spec is
    authoring input — prose, interfaces, the stop condition — and inventing it
    here would put text through a screen that never saw it at emission.
    """
    return {
        "id": task,
        "ref_ts": (TASKS / "ts" / task / "reference.ts").read_text(encoding="utf-8"),
        "ref_py": (TASKS / "py" / task / "reference.py").read_text(encoding="utf-8"),
        "acc_ts": (TASKS / "ts" / task / "accept.mjs").read_text(encoding="utf-8"),
        "acc_py": (TASKS / "py" / task / "accept.py").read_text(encoding="utf-8"),
    }


def census(tasks: list[str] | None = None) -> dict[str, Any]:
    """Every admitted problem through the divergence screen."""
    emit = _emit()
    names = tasks or sorted(p.name for p in (TASKS / "py").iterdir() if p.is_dir())
    flagged: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for task in names:
        found = emit.divergences(spec_of(task))
        if not found:
            continue
        flagged.append(
            {
                "task": task,
                "fatal": any(f.fatal for f in found),
                "findings": [f.detail for f in found],
            }
        )
        for finding in found:
            # The detail carries the offending text; the head of it is the rule.
            reasons[finding.detail.split(":")[0]] += 1
    fatal = sum(1 for row in flagged if row["fatal"])
    return {
        "tasks": len(names),
        "flagged": len(flagged),
        "fatal": fatal,
        "warn_only": len(flagged) - fatal,
        "clean": len(names) - len(flagged),
        "clean_share": round((len(names) - len(flagged)) / len(names), 4)
        if names
        else 0.0,
        "by_rule": dict(reasons.most_common()),
        "detail": flagged,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Language-idempotency census over the admitted bench (#225 "
            "research). Reads files, runs no model, dispatches nothing."
        )
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = census()
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(
        f"{result['tasks']} admitted problems: {result['clean']} clean "
        f"({result['clean_share']:.1%}), {result['flagged']} flagged "
        f"({result['fatal']} fatal, {result['warn_only']} warn-only)"
    )
    for rule, count in result["by_rule"].items():
        print(f"  {count:4}  {rule}")
    print(
        "\nA lower bound: the screen holds the divergences this project has "
        "been burned by, not every divergence."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
