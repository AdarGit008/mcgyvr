#!/usr/bin/env python3
"""Derive the fleet-identity PREFILL tolerance from `raw-prefill.json`.

Applies the M1 frozen rule (`derive.py` `tolerances()`): pool every warm sample
of a unit across its cold starts, take the median, and the tolerance is the
worst single-sample shortfall from that median, ceiling'd to a whole percent,
floored at 1%. The class worst is the largest shortfall across the class's units.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

SCR = Path(__file__).resolve().parent

#: container -> (model, class) for the fleet units this run measures.
VLLM_UNITS = {
    "mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001": ("Qwen2.5-Coder-3B-Instruct-AWQ", "vllm"),
    "mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002": ("Qwen2.5-Coder-7B-Instruct-AWQ", "vllm"),
}


def main() -> None:
    raw = json.loads((SCR / "raw-prefill.json").read_text())

    # Pool samples per unit (all cold starts). llama.cpp rows carry `samples`;
    # vLLM rows carry `prefill` keyed by container.
    per_unit: dict[str, list[float]] = {}
    for r in raw:
        if r.get("failed"):
            continue
        if r["engine"] == "vllm":
            for c, p in r.get("prefill", {}).items():
                per_unit.setdefault(c, []).extend(s["tok_s"] for s in p["samples"])
        else:
            unit = r.get("unit")
            per_unit.setdefault(unit, []).extend(s["tok_s"] for s in r.get("samples", []))

    worst: dict[str, float] = {}
    detail: dict[str, Any] = {}
    for key, xs in per_unit.items():
        model, cls = VLLM_UNITS.get(key, (key, "vllm"))
        if not xs:
            continue
        m = statistics.median(xs)
        shortfall = max((m - v) / m for v in xs)
        detail[key] = {"model": model, "class": cls, "n": len(xs),
                       "median_tok_s": round(m, 2), "min_tok_s": round(min(xs), 2),
                       "max_tok_s": round(max(xs), 2),
                       "shortfall_pct": round(100 * shortfall, 2),
                       "samples": [round(x, 2) for x in xs]}
        worst[cls] = max(worst.get(cls, 0.0), shortfall)

    classes = {
        cls: {"tolerance_pct": max(1, math.ceil(100 * w - 1e-9)), "worst_shortfall_pct": round(100 * w, 2)}
        for cls, w in worst.items()
    }

    out = {
        "rule": "M1 tolerance rule (worst single-sample shortfall from the unit median, "
                "ceiling'd to a whole percent, floored at 1%)",
        "swap": "off (no-NVMe)",
        "classes": classes,
        "per_unit": detail,
    }
    (SCR / "results-prefill.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
