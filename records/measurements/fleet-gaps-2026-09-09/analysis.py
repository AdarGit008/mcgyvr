"""Every table in the README, computed from the raw result files."""
import json, math
from pathlib import Path
D = Path(__file__).resolve().parent

def load(name):
    p = D / name
    return json.loads(p.read_text()) if p.exists() else []

def fit(points):
    """Least squares y = a + b x, and the proportional fit y = x / r."""
    n = len(points)
    if n < 2: return None
    sx = sum(x for x, _ in points); sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points); sxy = sum(x * y for x, y in points)
    b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    a = (sy - b * sx) / n
    # proportional through the origin
    bp = sxy / sxx
    ss = sum((y - (a + b * x)) ** 2 for x, y in points)
    ssp = sum((y - bp * x) ** 2 for x, y in points)
    tot = sum((y - sy / n) ** 2 for x, y in points)
    return {"intercept_s": a, "slope_s_per_gib": b, "rate_gib_s": 1 / b if b else None,
            "r2_affine": 1 - ss / tot if tot else None,
            "prop_slope_s_per_gib": bp, "prop_rate_gib_s": 1 / bp,
            "r2_proportional": 1 - ssp / tot if tot else None,
            "n": n}

def show(title, rows):
    print(f"\n### {title}")
    for r in rows: print("  " + r)

srv1 = load("results-arms-srv1-rate.json") + load("results-arms-srv1-m1-m3.json")
srv2 = load("results-arms-srv2-rate.json")
for name, rows in (("srv1", srv1), ("srv2", srv2)):
    ok = [r for r in rows if "wake_s" in r]
    show(f"{name} llama.cpp wakes", [
        f"{r['label']:28s} blob {r['blob_gib']:6.2f} GiB  wake {r['wake_s']:7.1f} s  "
        f"{r['blob_gib']/r['wake_s']:.4f} GiB/s  clearance {r.get('clearance_vs_blob_gib', 0):+6.2f}  "
        f"decode {r.get('decode_tok_s') or float('nan'):.2f}  peak {r.get('vram_peak_used_mib')} MiB"
        for r in ok])

def mean(xs): return sum(xs) / len(xs)

print("\n### fits (ample-clearance mapped arms only)")
for name, rows, extra in (
    ("srv1", srv1, [(8.29, 85.7), (12.30, 140.8)]),
    ("srv2", srv2, [(35.67, 102.9)]),
):
    got = {}
    for r in rows:
        if "wake_s" not in r or r.get("balloon_gib") or "unmapped" in r["label"]:
            continue
        got.setdefault(r["blob_gib"], []).append(r["wake_s"])
    pts = [(b, mean(v)) for b, v in sorted(got.items())]
    print(f"  {name} new points: {[(round(b,2), round(y,1)) for b,y in pts]}")
    allpts = sorted(pts + extra)
    print(f"  {name} with the 2026-09-09 points: {[(round(b,2), round(y,1)) for b,y in allpts]}")
    f = fit(allpts)
    if f:
        print(f"  {name} affine:        wake = {f['intercept_s']:.1f} + {f['slope_s_per_gib']:.2f} s/GiB "
              f"(r = {f['rate_gib_s']:.4f} GiB/s)   R2 {f['r2_affine']:.4f}   n={f['n']}")
        print(f"  {name} proportional:  wake = {f['prop_slope_s_per_gib']:.2f} s/GiB "
              f"(r = {f['prop_rate_gib_s']:.4f} GiB/s)   R2 {f['r2_proportional']:.4f}")

v = load("results-vllm.json")
show("vLLM arms", [
    f"{r['label']:20s} wake {r.get('wake_s', float('nan')):7.1f} s  "
    f"ram {r.get('ram_cost_gib', float('nan')):5.2f} GiB  card {r.get('vram_steady_used_mib')} MiB  "
    + "  ".join(f"{k}={u['mean_tok_s']:.1f}" for k, u in (r.get('per_unit') or {}).items()
                if u.get('mean_tok_s'))
    for r in v if "wake_s" in r])

m2 = load("m2-coresidency.json")
show("M2 co-residency", [
    f"{r['label']:22s} Shmem +{r['shmem_delta_gib']:5.2f} GiB (experts {r['experts_gib']:5.2f})  "
    f"avail -{r['avail_delta_gib']:5.2f}  card {r['vram_used_mib']} MiB  wake {r['wake_s']:.1f} s"
    for r in m2 if "shmem_delta_gib" in r])

m1 = load("m1-srv1-mode-vram.json")
show("M1 srv1 mode vs card", [
    f"{r['label']:22s} peak {r.get('vram_peak_used_mib')} MiB  steady {r.get('vram_steady_used_mib')} MiB  "
    f"wake {r.get('wake_s', float('nan')):.1f} s  Shmem {r.get('shmem_steady_gib', float('nan')):.2f} GiB"
    for r in m1 if "wake_s" in r])

# --- M5 / M6 / M7 -----------------------------------------------------------
sm = load("m6-m7-sleep-matrix.json")
if sm:
    print("\n### M6/M7 sleep matrix")
    for r in sm:
        extra = " ".join(f"{k}={v}" for k, v in r.items()
                         if k in ("sleep_s", "wake_s", "decode", "decode_3b", "decode_7b",
                                  "decode_other", "v1_models_http"))
        print(f"  {r['step']:34s} card {r['vram_used_mib']:5d}/{r['vram_free_mib']:6d}  "
              f"avail {r['mem_avail_gib']:6.2f}G  {r['sleeping']}  {extra}")

print("\n### M5: what --enable-sleep-mode costs")
byl = {}
for r in load("results-vllm.json") + load("results-vllm-2.json"):
    if "wake_s" not in r: continue
    key = r["label"].rstrip("0123456789-")
    byl.setdefault(key, []).append(r)
for key, rows in sorted(byl.items()):
    print(f"  {key:16s} n={len(rows)}  wake {[round(r['wake_s'],1) for r in rows]}  "
          f"card {[r['vram_steady_used_mib'] for r in rows]} MiB  "
          f"ram {[round(r['ram_cost_gib'],2) for r in rows]} GiB")
    for r in rows:
        for u, d in (r.get("per_unit") or {}).items():
            if d.get("mean_tok_s"):
                print(f"      {r['label']} {u}: {d['mean_tok_s']:.2f} tok/s  "
                      f"ttft {d['ttft_s']}  restarts={d.get('restart_count')}")

print("\n### the door's own clock, every arm")
try:
    doorf = json.loads((D / "door-up-after.json").read_text())
    for k, v in doorf.items():
        print(f"  {k:34s} " + "  ".join(f"{h['port']}:{h['up_after_s']:.1f}s" for h in v))
except FileNotFoundError:
    pass
