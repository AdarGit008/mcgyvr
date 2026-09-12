#!/usr/bin/env python3
"""Derive the fleet-identity PREFILL tolerances from `raw-prefill.json`.

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

#: vLLM rows key their samples by container; map that to the model name.
VLLM_MODELS = {
    "mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001": "Qwen2.5-Coder-3B-Instruct-AWQ",
    "mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002": "Qwen2.5-Coder-7B-Instruct-AWQ",
}


def main() -> None:
    raw = json.loads((SCR / "raw-prefill.json").read_text())

    per_unit: dict[str, dict[str, Any]] = {}
    for r in raw:
        if r.get("failed"):
            continue
        if r["engine"] == "vllm":
            for c, p in r.get("prefill", {}).items():
                e = per_unit.setdefault(c, {"class": "vllm", "model": VLLM_MODELS.get(c, c), "xs": []})
                e["xs"].extend(s["tok_s"] for s in p["samples"])
        else:
            key = r.get("unit") or r["label"]
            e = per_unit.setdefault(key, {"class": r.get("class", "llamacpp"),
                                          "model": key, "xs": []})
            e["xs"].extend(s["tok_s"] for s in r.get("samples", []))

    worst: dict[str, float] = {}
    detail: dict[str, Any] = {}
    for key, e in per_unit.items():
        xs = e["xs"]
        if not xs:
            continue
        m = statistics.median(xs)
        shortfall = max((m - v) / m for v in xs)
        detail[key] = {"model": e["model"], "class": e["class"], "n": len(xs),
                       "median_tok_s": round(m, 2), "min_tok_s": round(min(xs), 2),
                       "max_tok_s": round(max(xs), 2),
                       "shortfall_pct": round(100 * shortfall, 2),
                       "samples": [round(x, 2) for x in xs]}
        worst[e["class"]] = max(worst.get(e["class"], 0.0), shortfall)

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
