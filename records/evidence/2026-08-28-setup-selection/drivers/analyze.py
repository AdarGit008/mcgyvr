#!/usr/bin/env python3
"""Analyze sweep results -> DoD table + key scores (setup selection 2026-08-28)."""
import re, sys, json, os
from collections import defaultdict

MODELS = {
    # tag -> (name, type, total_B, active_B, quant)
    "15b-Q4":   ("qwen2.5-coder-1.5b", "dense", 1.54, 1.54, "Q4_K_M"),
    "3b-Q4":    ("qwen2.5-coder-3b",  "dense", 3.09, 3.09, "Q4_K_M"),
    "q3-4b-Q4": ("qwen3-4b",          "dense", 4.02, 4.02, "Q4_K_M"),
    "q3-8b-Q4": ("qwen3-8b",          "dense", 8.24, 8.24, "Q4_K_M"),
    "7b-IQ4XS": ("qwen2.5-coder-7b",  "dense", 7.61, 7.61, "IQ4_XS"),
    "nemotron7b-Q4": ("nemotron-7b",  "dense", 7.60, 7.60, "Q4_K_M"),
    "14b-Q4":   ("qwen2.5-coder-14b", "dense", 14.70, 14.70, "Q4_K_M"),
    "32b-Q4":   ("qwen2.5-coder-32b", "dense", 32.50, 32.50, "Q4_K_M"),
    "30b-Q4":   ("qwen3-coder-30b-a3b", "moe", 30.50, 3.30, "Q4_K_M"),
    "30b-IQ3XXS": ("qwen3-coder-30b-a3b", "moe", 30.50, 3.30, "IQ3_XXS"),
    "35B-IQ3XXS": ("qwen3.6-35b-a3b", "moe", 35.00, 3.00, "IQ3_XXS"),
    "nem30b-IQ2XXS": ("nemotron-3-nano-30b-a3b", "moe", 30.00, 3.00, "IQ2_XXS"),
    "nextud-80B-Q3XL": ("qwen3-coder-next-80b-a3b", "moe", 80.00, 3.30, "Q3_K_XL"),
    "dscv2-16b": ("deepseek-coder-v2-lite", "moe", 15.70, 2.40, "Q4_0"),
    "gptoss-20b": ("gpt-oss-20b", "moe", 20.50, 3.60, "Q3_K_M"),
    "gptoss-4b": ("gpt-oss-4b", "dense", 4.20, 4.20, "Q4_K_M"),
    "mxfp4-20b": ("gpt-oss-20b", "moe", 20.50, 3.60, "MXFP4"),
    "30b-IQ3XXS-kvu": ("qwen3-coder-30b-a3b", "moe", 30.50, 3.30, "IQ3_XXS"),
    "vllm-15b": ("qwen2.5-coder-1.5b", "dense", 1.54, 1.54, "AWQ"),
    "vllm-3b":  ("qwen2.5-coder-3b",  "dense", 3.09, 3.09, "AWQ"),
    "vllm-q3-4b": ("qwen3-4b",        "dense", 4.02, 4.02, "AWQ"),
    "vllm-7b":  ("qwen2.5-coder-7b",  "dense", 7.61, 7.61, "AWQ"),
    "vllm-14b": ("qwen2.5-coder-14b", "dense", 14.70, 14.70, "AWQ"),
    "vllm-nem30b-awq": ("nemotron-30b-a3b", "moe", 30.00, 3.00, "AWQ"),
    "vllm-nem4b-fp8": ("nemotron-4b",  "dense", 4.00, 4.00, "fp8"),
}

FILES = sys.argv[1:]
cells = defaultdict(list)  # (rig, engine, tag) -> [ (n, agg) ]
refused = defaultdict(list)  # (rig, engine, tag) -> [reason]

for path in FILES:
    if not os.path.exists(path):
        print(f"missing: {path}", file=sys.stderr)
        continue
    for line in open(path):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            continue
        host, lab = parts[0], parts[1]
        kind = parts[2]
        rest = parts[3]
        tag = lab.split()[0]
        tag = re.sub(r"-(s\d+)$", "", tag)
        engine = "vllm" if tag.startswith("vllm-") else "llamacpp"
        if tag.startswith("ctrl-"):
            engine = "llamacpp-ctrl-b10481"
        n = re.search(r"n=(\d+)\b", kind)
        agg = re.search(r"agg=([\d.]+)", rest)
        if n and agg:
            cells[(host, engine, tag)].append((int(n.group(1)), float(agg.group(1))))
        elif "REFUSED" in kind:
            refused[(host, engine, tag)].append(rest[:160])

# build table
print("\n=== per (rig, engine, model): n=1 tok/s, best tok/s x n ===\n")
rows = []
for (rig, eng, tag), pts in sorted(cells.items()):
    if tag not in MODELS:
        continue
    name, typ, total, active, quant = MODELS[tag]
    n1 = next((a for n, a in pts if n == 1), None)
    best = max(pts, key=lambda p: p[1] * p[0])
    rows.append(dict(rig=rig, eng=eng, tag=tag, name=name, typ=typ, total=total,
                     active=active, quant=quant, n1=n1, bestn=best[0], bestagg=best[1],
                     prod=best[1] * best[0]))

print(f"{'rig':5} {'engine':10} {'model':24} {'typ':5} {'totB':>6} {'actB':>5} {'n1':>7} {'bestN':>5} {'bestTok/s':>9} {'prod':>8} {'tok/sxn1*size':>14}")
for r in rows:
    print(f"{r['rig']:5} {r['eng']:10} {r['name'][:24]:24} {r['typ']:5} {r['total']:6.1f} {r['active']:5.1f} "
          f"{r['n1'] if r['n1'] is not None else '-':>7} {r['bestn']:5d} {r['bestagg']:9.1f} {r['prod']:8.0f} "
          f"{r['n1']*r['total'] if r['n1'] else 0:14.0f}")

print("\n=== refusals ===")
for (rig, eng, tag), rs in sorted(refused.items()):
    print(f"{rig} {eng} {tag}: {rs[0][:110]}")

# keys: 1 = max n1*total ; 2,3 = max prod = bestagg*bestn*total
print("\n=== KEY 1: (tok/s @ n=1) x total_params (one user, fast+smart) ===")
k1 = sorted([r for r in rows if r['n1']], key=lambda r: -r['n1'] * r['total'])
for r in k1[:8]:
    print(f"  {r['rig']:5} {r['eng']:10} {r['name']:24} n1={r['n1']:7.1f}  score={r['n1']*r['total']:9.0f}")

print("\n=== KEY 2/3: max over n of (tok/s x total x n) ===")
k2 = sorted(rows, key=lambda r: -r['prod'] * r['total'])
for r in k2[:10]:
    print(f"  {r['rig']:5} {r['eng']:10} {r['name']:24} n={r['bestn']:4d} tok/s={r['bestagg']:8.1f}  score={r['prod']*r['total']:11.0f}")

json.dump(rows, open("/tmp/sweep28/table.json", "w"), indent=1)
print("\ntable.json written")
