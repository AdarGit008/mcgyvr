#!/usr/bin/env python3
"""Concurrency sweep: what one served unit does as N requests run at once.

Sends N identical-shaped but distinct requests simultaneously to an
OpenAI-compatible endpoint, with `ignore_eos` so every stream generates
exactly `--tokens` tokens. Distinct prompts, so no stream is served from
another's prefix cache.

Reports per-stream tok/s and aggregate tok/s at each width. The pair is the
point: aggregate says what the machine produces, per-stream says how long one
caller waits, and a width that raises the first while sinking the second is a
throughput/latency trade rather than a free win.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def one(url: str, model: str, prompt: str, tokens: int, timeout: float) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": tokens,
        "min_tokens": tokens,
        "ignore_eos": True,
        "temperature": 0.0,
        "stream": False,
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except Exception as exc:  # a failed stream is a datum, not a crash
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed": time.monotonic() - started,
        }
    elapsed = time.monotonic() - started
    usage = payload.get("usage") or {}
    return {
        "ok": True,
        "elapsed": elapsed,
        "started": started,
        "finished": time.monotonic(),
        "out": usage.get("completion_tokens"),
        "in": usage.get("prompt_tokens"),
    }


def sweep(url: str, model: str, width: int, tokens: int, timeout: float) -> dict:
    prompts = [
        f"Write a short technical note, number {i}, about list slicing. "
        f"Be verbose and keep writing prose until you are stopped."
        for i in range(width)
    ]
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=width) as pool:
        rows = list(pool.map(lambda p: one(url, model, p, tokens, timeout), prompts))
    wall = time.monotonic() - t0

    good = [r for r in rows if r["ok"]]
    failed = [r for r in rows if not r["ok"]]
    if not good:
        return {
            "width": width,
            "ok": 0,
            "failed": len(failed),
            "error": failed[0]["error"] if failed else "",
            "wall": wall,
        }

    produced = sum(r["out"] or 0 for r in good)
    per = [(r["out"] or 0) / r["elapsed"] for r in good if r["elapsed"] > 0]
    return {
        "width": width,
        "ok": len(good),
        "failed": len(failed),
        "wall": wall,
        "tokens_out": produced,
        "per_stream_tps": statistics.median(per) if per else 0.0,
        "per_stream_min": min(per) if per else 0.0,
        "per_stream_max": max(per) if per else 0.0,
        "aggregate_tps": produced / wall if wall else 0.0,
        "latency_p50": statistics.median(r["elapsed"] for r in good),
        "latency_max": max(r["elapsed"] for r in good),
        "error": failed[0]["error"] if failed else "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True, help="base url, e.g. http://srv1:8080")
    ap.add_argument("--model", required=True)
    ap.add_argument("--widths", default="1,2,4,8")
    ap.add_argument("--tokens", type=int, default=256)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    url = args.url.rstrip("/") + "/v1/chat/completions"
    # Warm: load whatever caches exist so width 1 is not paying for them.
    one(url, args.model, "hello", 8, args.timeout)

    results = []
    print(
        f"{'width':>5} {'ok':>3} {'fail':>4} {'per-stream t/s':>15} "
        f"{'aggregate t/s':>14} {'p50 lat':>9} {'max lat':>9}"
    )
    for width in [int(w) for w in args.widths.split(",")]:
        r = sweep(url, args.model, width, args.tokens, args.timeout)
        r["label"] = args.label
        results.append(r)
        if r.get("tokens_out") is None:
            print(
                f"{width:>5} {r['ok']:>3} {r['failed']:>4}   {r.get('error', '')[:60]}"
            )
        else:
            print(
                f"{width:>5} {r['ok']:>3} {r['failed']:>4} "
                f"{r['per_stream_tps']:>15.2f} {r['aggregate_tps']:>14.2f} "
                f"{r['latency_p50']:>9.1f} {r['latency_max']:>9.1f}"
            )
        sys.stdout.flush()

    if args.out:
        payload = {
            "url": args.url,
            "model": args.model,
            "tokens": args.tokens,
            "label": args.label,
            "results": results,
        }
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
