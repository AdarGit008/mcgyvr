#!/usr/bin/env python3
"""Table of the quick elimination check: passes per task type, per arm, per model, per rig."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("bench-py", "bench-ts")
TYPES = ("function_implementation", "bug_fix")


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def cell(rs: list[dict], kind: str) -> str:
    typed = [r for r in rs if r.get("type") == kind]
    if not typed:
        return "—"
    return f"{sum(bool(r.get('passed')) for r in typed)}/{len(typed)}"


def main() -> int:
    print("| rig | model | py fi | py bug | ts fi | ts bug | total | parse refused | overran cap | rejected before acceptance | mean tokens | mean s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for host in ("srv1", "srv2"):
        base = HERE / host
        if not base.is_dir():
            continue
        for model in sorted(p for p in base.iterdir() if p.is_dir()):
            per_arm = {arm: rows(model / arm / "results.jsonl") for arm in ARMS}
            every = [r for rs in per_arm.values() for r in rs]
            if not every:
                continue
            cells = [cell(per_arm[arm], kind) for arm in ARMS for kind in TYPES]
            passed = sum(bool(r.get("passed")) for r in every)
            refused = sum(r.get("parse_error") is not None for r in every)
            overran = sum(bool(r.get("overran_cap")) for r in every)
            early = sum(bool(r.get("rejected_before_acceptance")) for r in every)
            tokens = [r["completion_tokens"] for r in every if r.get("completion_tokens") is not None]
            latency = [r["latency_s"] for r in every if r.get("latency_s") is not None]
            print(
                f"| {host} | {model.name} | " + " | ".join(cells)
                + f" | {passed}/{len(every)} | {refused} | {overran} | {early}"
                + f" | {sum(tokens) / len(tokens):.0f}" if tokens else " | —",
                end="",
            )
            print(f" | {sum(latency) / len(latency):.1f} |" if latency else " | — |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
