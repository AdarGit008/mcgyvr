#!/usr/bin/env python3
"""Generate rows.jsonl from all sweep result files (setup selection 2026-08-28)."""
import re, json, sys, os

OUT = "/home/adaramir/claude/mcgyvr/records/evidence/2026-08-28-setup-selection/rows.jsonl"

FILES = sys.argv[1:]
rows = []
for path in FILES:
    if not os.path.exists(path):
        continue
    for line in open(path):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            continue
        host, lab = parts[0], parts[1]
        kind, rest = parts[2], parts[3]
        tag = lab.split()[0]
        engine = "vllm" if tag.startswith(("vllm", "vllmL")) else "llamacpp"
        if tag.startswith("ctrl-"):
            engine = "llamacpp-b10481-control"
        row = dict(rig=host, tag=tag, engine=engine, label=lab, date="2026-08-28",
                   workload="475-tok, ignore_eos, temp0, fixed prompt")
        m = re.search(r"n=(\d+)\b", kind)
        agg = re.search(r"agg=([\d.]+)", rest)
        p50 = re.search(r"p50=([\d.]+)", rest)
        wall = re.search(r"wall=([\d.]+)", rest)
        if m and agg:
            row.update(kind="level", n=int(m.group(1)), agg_tok_s=float(agg.group(1)),
                       p50_s=float(p50.group(1)) if p50 else None,
                       wall_s=float(wall.group(1)) if wall else None)
        elif kind == "CONFIG":
            vram = re.search(r"vram=(\d+)", rest)
            row.update(kind="config", vram_mib=int(vram.group(1)) if vram else None)
        elif "REFUSED" in kind:
            row.update(kind="refused", reason=rest[:200])
        else:
            continue
        rows.append(row)

with open(OUT, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
print(f"{len(rows)} rows -> {OUT}")
