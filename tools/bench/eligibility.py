"""Which cells a lever can act on, and whether that set has room to move.

Issue: `#266 <https://github.com/AdarGit008/mcgyvr/issues/266>`_.

A lever's eligible set is decided by the contract, not by the run: ``noscaffold``
and ``planonly`` both write ``target_content``, so a task carrying none is a
no-op by construction and contributes a concordant pair. ``matrix.json`` states
that rule; this module counts it.

**Eligibility is the cheap half.** The half that decides whether a contrast can
be read is *headroom*: a cell that passes under no condition cannot produce a
discordant pair whatever the lever does, so the count of eligible cells is an
upper bound on ``m`` only if those cells can pass at all. ADR-0026's consequence
is the rule this module exists to apply — *"a stratum with no headroom is
excluded, not reported as null. 'No effect where nothing passes' is absent
resolution, not absent effect."* — and ADR-0019's ``m >= 6`` wall is what the
answer is measured against.

Both numbers are computed from the corpus and the committed runs rather than
stated, because #243's record is four cases of a quoted figure surviving until
someone re-derived it by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
TASKS = Path(__file__).resolve().parent / "tasks"
MEASUREMENTS = REPO / "records" / "measurements"

ARMS = ("py", "ts")

# The slot each lever writes, from ``matrix.json``. A lever is eligible on a task
# whose contract carries that slot; the matrix's ``why`` states the rest of the
# rule, including why ``bug_fix`` is ineligible for the two capacity levers even
# though it carries the slot — its ``target_content`` *is* the buggy file, so
# ablating it deletes the task rather than lightening it.
CAPACITY_LEVERS = ("noscaffold", "planonly")


class EligibilityError(Exception):
    """The corpus or a run directory cannot be read."""


def contracts(arm: str) -> Iterator[dict[str, Any]]:
    """Every contract on one arm, in id order."""
    root = TASKS / arm
    if not root.is_dir():
        raise EligibilityError(f"{root} is not a task root")
    for path in sorted(root.glob("*/contract.yaml")):
        yield yaml.safe_load(path.read_text(encoding="utf-8"))


def strata(arm: str) -> dict[str, tuple[str, bool]]:
    """Task id -> (task_type, carries target_content).

    The pair is the stratum a lever's eligibility is decided on: the capacity
    levers are live on ``function_implementation`` carrying ``target_content``
    and nowhere else.
    """
    return {
        c["id"]: (c.get("task_type", "?"), bool(c.get("target_content")))
        for c in contracts(arm)
    }


def eligible(arm: str) -> set[str]:
    """The ids the capacity levers can act on, per ``matrix.json``'s rule."""
    return {
        task
        for task, (kind, has) in strata(arm).items()
        if kind == "function_implementation" and has
    }


def greedy(directory: Path, arm: str) -> dict[str, bool]:
    """Task id -> passed, over the greedy arm of one run directory."""
    path = directory / f"bench-{arm}" / "results.jsonl"
    if not path.is_file():
        raise EligibilityError(f"{path} is not a results file")
    out: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("arm") == "greedy":
            out[row["task"]] = bool(row.get("passed"))
    return out


def headroom(
    stock: dict[str, bool], ablated: dict[str, bool], subset: set[str]
) -> dict[str, int]:
    """What a paired contrast over ``subset`` could and did resolve.

    ``ceiling`` is the count of cells that pass under *either* condition — the
    arithmetic maximum ``m`` can reach on this material, because a cell failing
    both ways is concordant whatever the lever does. ``m`` is what the pair
    actually discorded on. A ceiling below ADR-0019's wall settles the question
    without any appeal to effect size.
    """
    paired = sorted(t for t in subset if t in stock and t in ablated)
    return {
        "n": len(paired),
        "stock_passes": sum(stock[t] for t in paired),
        "ablated_passes": sum(ablated[t] for t in paired),
        "ceiling": sum(1 for t in paired if stock[t] or ablated[t]),
        "m": sum(1 for t in paired if stock[t] != ablated[t]),
    }


def _report(stock_dir: Path, ablated_dir: Path, label: str) -> list[str]:
    lines = [f"## {label}", ""]
    lines.append("| arm | stratum | n | stock | ablated | ceiling | m |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for arm in ARMS:
        stock = greedy(stock_dir, arm)
        ablated = greedy(ablated_dir, arm)
        by_stratum = strata(arm)
        groups: dict[str, set[str]] = {}
        for task, (kind, has) in by_stratum.items():
            key = f"{kind}{' +scaffold' if has else ''}"
            groups.setdefault(key, set()).add(task)
        groups["ALL"] = set(by_stratum)
        for key in sorted(groups):
            h = headroom(stock, ablated, groups[key])
            if not h["n"]:
                continue
            lines.append(
                f"| bench-{arm} | {key} | {h['n']} | {h['stock_passes']} | "
                f"{h['ablated_passes']} | {h['ceiling']} | {h['m']} |"
            )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Eligible cells per lever and the headroom that bounds m (#266). "
            "With no run directories it reports eligibility from the corpus "
            "alone; with a pair it reports the ceiling m could have reached."
        )
    )
    parser.add_argument(
        "--stock", type=Path, help="run directory of the baseline condition"
    )
    parser.add_argument(
        "--ablated", type=Path, help="run directory of the ablated condition"
    )
    parser.add_argument("--label", default="paired contrast")
    args = parser.parse_args(argv)

    print("## Eligibility, from the corpus\n")
    print("| arm | stratum | tasks | capacity levers live |")
    print("|---|---|---:|---:|")
    for arm in ARMS:
        by_stratum = strata(arm)
        kinds: dict[str, int] = {}
        for kind, has in by_stratum.values():
            kinds[f"{kind}{' +scaffold' if has else ''}"] = (
                kinds.get(f"{kind}{' +scaffold' if has else ''}", 0) + 1
            )
        live = eligible(arm)
        for key in sorted(kinds):
            mark = "yes" if key == "function_implementation +scaffold" else "no"
            print(f"| bench-{arm} | {key} | {kinds[key]} | {mark} |")
        print(f"| bench-{arm} | **eligible total** | **{len(live)}** | — |")

    if args.stock and args.ablated:
        print()
        for line in _report(args.stock, args.ablated, args.label):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
