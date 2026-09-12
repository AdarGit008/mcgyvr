"""Per-parameter, per-unit statistics over observations.csv."""
import csv
import os
import re
import statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, "observations.csv"))))
VRAM = {"srv1": 6144, "srv2": 12288}
RAM_GIB = {"srv1": 15.0323, "srv2": 45.9750}  # MemTotal read 2026-09-09 (ram-headroom sweep-results*.json mem_after)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def stats(vals):
    v = sorted(vals)
    return len(v), v[0], st.median(v), v[-1], v[-1] - v[0]


def unit(r, extra=()):
    keys = ["host", "engine", "image", "model", "n_cpu_moe", "width", "ctx", "ubatch", "load_mode", "cache_type",
            "gpu_mem_util", "sleep_mode", "depends_on", "co_residents", *extra]
    return " | ".join(f"{k}={r[k]}" for k in keys if r[k])


def show(title, groups, unitname, pct=None, minn=1):
    print(f"\n### {title}")
    for key, items in sorted(groups.items()):
        vals = [f(r["value"]) for r in items if f(r["value"]) is not None]
        if len(vals) < minn:
            continue
        n, lo, med, hi, sp = stats(vals)
        extra = ""
        if pct:
            host = items[0]["host"]
            tot = pct(host)
            if tot:
                extra = f" ({100 * sp / tot:.2f}% of {tot})"
        srcs = sorted({f"{r['source'].split('/')[-1]}:{r['row_key']}" for r in items})
        print(f"n={n} min={lo:.3f} med={med:.3f} max={hi:.3f} spread={sp:.3f}{unitname}{extra} :: {key} :: dates={sorted({r['date'] for r in items})}")
        if len(srcs) <= 8:
            print("     rows:", "; ".join(srcs))
        else:
            print("     rows:", "; ".join(srcs[:4]), f"... +{len(srcs) - 4}")


P = defaultdict(list)
for r in rows:
    P[r["parameter"]].append(r)

# 1. Shmem over geometry
print("## 1 SHMEM unmapped: residual = Shmem - spilled experts (vramfit.experts_on_card)")
for r in P["shmem_unmapped_gib"]:
    print(f"  {r['host']} {r['model'][:40]} ncmoe={r['n_cpu_moe']} ctx={r['ctx']} np={r['width']} shmem={r['value']} pred={r['predicted'][:6]} resid={r['residual'][:6]} "
          f"bal={r['balloon_gib']} swp={r['swappiness'][:2]} {r['date']} {r['source'].split('/')[-1]}:{r['row_key']} {r['note'][:60]}")
g = defaultdict(list)
for r in P["shmem_unmapped_gib"]:
    if r["residual"]:
        g[unit(r)].append(dict(r, value=r["residual"]))
show("Shmem residual per unit (GiB)", g, " GiB", pct=lambda h: RAM_GIB[h])
print("\n### Shmem of a MAPPED unit (baseline the geometry never predicts)")
g = defaultdict(list)
for r in P["shmem_mapped_unit_gib"]:
    g[f"{r['host']} {r['model']}"].append(r)
show("mapped Shmem", g, " GiB")

# 2. Card C per group: step across placements vs repeat noise
print("\n## 2 CARD C = net card - experts on card; group = everything but n_cpu_moe")
g = defaultdict(list)
for r in P["card_C_mib"]:
    k = unit(dict(r, n_cpu_moe="", co_residents="")) + f" | arch={r['arch']}"
    g[k].append(r)
for k, items in sorted(g.items()):
    by_n = defaultdict(list)
    for r in items:
        by_n[int(r["n_cpu_moe"])].append(f(r["value"]))
    rep = max((max(v) - min(v)) for v in by_n.values())
    means = {n: st.mean(v) for n, v in by_n.items()}
    probe = min(means)
    step = {n: round(m - means[probe], 2) for n, m in sorted(means.items())}
    host = items[0]["host"]
    print(f"  {k}\n     placements={sorted(by_n)} n={len(items)} repeat-noise={rep:.2f} MiB step-vs-lowest-ncmoe={step} "
          f"span={max(means.values()) - min(means.values()):.2f} MiB ({100 * (max(means.values()) - min(means.values())) / VRAM[host]:.2f}% of {VRAM[host]}) dates={sorted({r['date'] for r in items})}")
print("\n### card vs stored prediction")
for r in P["card_vs_prediction_mib"]:
    print(f"  {r['host']} {r['arch']} {r['model']} ncmoe={r['n_cpu_moe']} measured={r['value']} pred={r['predicted']} resid={r['residual']} {r['source'].split('/')[-1]}:{r['row_key']}")
print("\n### card steady repeatability at identical knobs (all engines)")
g = defaultdict(list)
for r in P["card_steady_mib"]:
    g[unit(r) + f" | src={r['source'].split('/')[-2]}"].append(r)
show("card_steady_mib", g, " MiB", pct=lambda h: VRAM[h], minn=2)
print("\n### card after door (envelopes), grouped by knobs")
g = defaultdict(list)
for r in P["card_after_door_mib"]:
    g[unit(r)].append(r)
show("card_after_door_mib", g, " MiB", pct=lambda h: VRAM[h], minn=2)

# 3. vLLM per-unit cold card
print("\n## 3 vLLM per-unit card after cold start (per pid)")
g = defaultdict(list)
for r in P["vllm_unit_card_cold_mib"]:
    g[unit(r)].append(r)
show("vllm_unit_card_cold_mib", g, " MiB", pct=lambda h: VRAM[h])
for p in ("vllm_L2_residual_mib", "vllm_L1_residual_mib", "vllm_cold_minus_wake_card_mib", "vllm_host_ram_gib",
          "vllm_nontorch_gib", "vllm_kv_tokens", "vllm_negative_kv_attempts", "card_peak_minus_steady_mib", "start_offset_s", "ttft_s"):
    g = defaultdict(list)
    for r in P[p]:
        g[unit(r) + (f" | note={r['note'][:40]}" if r['engine'] == 'vllm' else "")].append(r)
    show(p, g, "", pct=(lambda h: VRAM[h]) if p.endswith("mib") else ((lambda h: RAM_GIB[h]) if p.endswith("gib") else None))

# 4. swap and faults
print("\n## 4 SWAP / FAULTS")
for p in ("pswpout_wake", "pswpin_wake", "majfault_wake", "majfault_decode", "pswpout_decode", "pswpin_decode", "swap_used_delta_gib"):
    g = defaultdict(list)
    for r in P[p]:
        bal = "balloon" if f(r["balloon_gib"]) else "no-balloon"
        g[f"{r['host']} {r['engine']} load={r['load_mode']} {bal} swp={r['swappiness'][:10]} co={bool(r['co_residents'])}"].append(r)
    show(p, g, " pages")
    zero = [r for r in P[p] if f(r["value"]) == 0]
    print(f"   {p}: {len(zero)}/{len(P[p])} rows are exactly 0")

# 5. restarts
print("\n## 5 RESTARTS")
g = defaultdict(list)
for r in P["restarts"]:
    g[f"{r['host']} {r['engine']} {r['model']} depends={r['depends_on']} sleep={r['sleep_mode']} co={r['co_residents']} note={r['note'].split(';')[0][:40]}"].append(r)
for k, items in sorted(g.items()):
    vals = [int(float(r["value"])) for r in items]
    print(f"  n={len(vals)} nonzero={sum(1 for v in vals if v)} values={vals} :: {k} :: {sorted({r['source'].split('/')[-1] for r in items})}")

# 6. decode
print("\n## 6 DECODE warm (arm means) per unit")
g = defaultdict(list)
for r in P["decode_tok_s"]:
    if r["cold_warm"].startswith("warm"):
        g[unit(r, extra=("balloon_gib",)) + f" | {r['cold_warm'][:5]} | note={'verbose' if 'verbose' in r['note'] else ''}"].append(r)
print("unit spread % = (max-min)/median")
for k, items in sorted(g.items()):
    vals = [f(r["value"]) for r in items]
    n, lo, med, hi, sp = stats(vals)
    within = []
    for r in items:
        m = re.search(r"samples=\[([^\]]*)\]", r["note"])
        if m:
            s = [float(x) for x in m.group(1).split(",")]
            within.append((max(s) - min(s)) / st.median(s) * 100)
    print(f"  n={n} min={lo:.2f} med={med:.2f} max={hi:.2f} spread={100 * sp / med:.1f}% within-arm-max={max(within) if within else 0:.1f}% :: {k} :: {sorted({r['date'] for r in items})} {sorted({r['source'].split('/')[-1] + ':' + r['row_key'] for r in items})[:6]}")
print("\n### cold / warm ratio on arms that took both")
pairs = defaultdict(dict)
for r in P["decode_tok_s"]:
    key = (r["source"], r["row_key"], r["model"])
    if r["cold_warm"].startswith("cold"):
        pairs[key]["cold"] = f(r["value"])
    elif r["cold_warm"].startswith("warm"):
        pairs[key]["warm"] = f(r["value"])
by = defaultdict(list)
for (s, k, m), v in pairs.items():
    if "cold" in v and "warm" in v:
        by[m].append(v["cold"] / v["warm"])
for m, v in sorted(by.items()):
    print(f"  {m}: n={len(v)} cold/warm min={min(v):.2f} max={max(v):.2f}")
print("\n### single-sample vLLM decode (Q15 cycles / M6 / Q16b)")
g = defaultdict(list)
for r in P["decode_tok_s"]:
    if r["cold_warm"].startswith("single"):
        g[f"{r['host']} {r['model']} {r['cold_warm'][:40]}"].append(r)
show("vLLM single", g, " tok/s")
print("\n### unstated / concurrency")
for r in P["decode_tok_s"]:
    if not (r["cold_warm"].startswith("warm") or r["cold_warm"].startswith("cold") or r["cold_warm"].startswith("single")):
        print(f"  {r['host']} {r['engine']} {r['model']} {r['value']} {r['cold_warm']} {r['source'].split('/')[-1]}:{r['row_key']}")

# 7. wake
print("\n## 7 WAKE")
for p in ("wake_s", "wake_s_door", "wake_s_mcgyvr", "wake_s_vllm_L2", "wake_s_vllm_L1", "sleep_s_vllm_L2", "sleep_s_vllm_L1", "door_overhead_s"):
    g = defaultdict(list)
    for r in P[p]:
        g[unit(r, extra=("balloon_gib",)) + f" | swp={r['swappiness'][:2]} | {r['instrument'][:30]}"].append(r)
    show(p, g, " s")
