"""Parse the ctx-probe logs off-rig. Second loader pass only; nothing dropped."""
import re, sys, json
from pathlib import Path
from collections import defaultdict

PATS = {
 "cuda_model":  r"load_tensors:\s+CUDA0 model buffer size =\s+([\d.]+)",
 "cpu_model":   r"load_tensors:\s+CPU_Mapped model buffer size =\s+([\d.]+)",
 "cuda_kv":     r"llama_kv_cache:\s+CUDA0 KV buffer size =\s+([\d.]+)",
 "cuda_compute":r"sched_reserve:\s+CUDA0 compute buffer size =\s+([\d.]+)",
 "host_compute":r"sched_reserve:\s+CUDA_Host compute buffer size =\s+([\d.]+)",
 "output":      r"llama_context:\s+CUDA_Host\s+output buffer size =\s+([\d.]+)",
 "cuda_rs":     r"llama_memory_recurrent:\s+CUDA0 RS buffer size =\s+([\d.]+)",
}
KVSIZE = re.compile(r"llama_kv_cache: size =\s+([\d.]+) MiB \(\s*(\d+) cells,\s*(\d+) layers,\s*(\d+)/(\d+) seqs\), K \(\w+\):\s*([\d.]+) MiB, V \(\w+\):\s*([\d.]+)")
NCTXSEQ = re.compile(r"llama_context: n_ctx_seq\s+=\s+(\d+)")

def parse(p: Path):
    txt = p.read_text(errors="replace")
    # the loader runs twice: a fit pass (all zeros) then the real one. Split on
    # the LAST occurrence of the model-buffer line and keep what follows.
    idx = [m.start() for m in re.finditer(r"load_tensors:.*model buffer size", txt)]
    real = txt[idx[len(idx)//2]:] if len(idx) > 1 else txt
    out = {}
    for k, pat in PATS.items():
        m = re.findall(pat, real)
        # An SWA model creates TWO device KV caches (llama_kv_cache_iswa) and
        # each prints its own line. Summing is the only correct reduction;
        # `tail -1` kept the SWA cache alone and hid the other in the residue.
        if k == "cuda_kv":
            out[k] = sum(float(x) for x in m) if m else None
            out["n_kv_caches"] = len(m)
        else:
            out[k] = float(m[-1]) if m else None
    ms = list(KVSIZE.finditer(real))
    if ms:
        out.update(kv_total=sum(float(m.group(1)) for m in ms),
                   cells=[int(m.group(2)) for m in ms],
                   kv_k=sum(float(m.group(6)) for m in ms),
                   kv_v=sum(float(m.group(7)) for m in ms))
    m = NCTXSEQ.search(real)
    if m: out["n_ctx_seq"] = int(m.group(1))
    return out

def table(d: Path, title: str):
    print(f"\n=== {title} ===")
    read = {}
    for line in (d/"readings.tsv").read_text().splitlines():
        f = line.split("\t")
        if len(f) >= 8 and f[0].isdigit(): read[(int(f[0]), int(f[1]))] = f
    rows = []
    for log in sorted(d.glob("c*-r*.log")):
        ctx, rep = re.match(r"c(\d+)-r(\d+)", log.name).groups()
        r = parse(log); r["ctx"] = int(ctx); r["rep"] = int(rep)
        k = (int(ctx), int(rep))
        r["vram"] = int(read[k][3]) if k in read else None
        r["idle"] = int(read[k][2]) if k in read else None
        rows.append(r)
    rows.sort(key=lambda r: (r["ctx"], r["rep"]))
    hdr = f"{'ctx':>6s} {'rep':>3s} {'n_ctx_seq':>9s} {'cuda_model':>10s} {'cpu_model':>10s} {'kv':>9s} {'#c':>3s} {'cells':>12s} {'rs':>7s} {'compute':>8s} {'sum_dev':>9s} {'vram':>6s} {'residue':>8s}"
    print(hdr)
    for r in rows:
        dev = sum(x or 0 for x in (r["cuda_model"], r["cuda_kv"], r.get("cuda_rs"), r["cuda_compute"]))
        res = (r["vram"] - r["idle"]) - dev if r["vram"] else float("nan")
        print(f"{r['ctx']:6d} {r['rep']:3d} {r.get('n_ctx_seq',0):9d} {r['cuda_model'] or 0:10.2f} {r['cpu_model'] or 0:10.2f} "
              f"{r['cuda_kv'] or 0:9.2f} {r.get('n_kv_caches',0):3d} {str(r.get('cells','')):>12s} {r.get('cuda_rs') or 0:7.2f} "
              f"{r['cuda_compute'] or 0:8.2f} {dev:9.2f} {r['vram'] or 0:6d} {res:8.2f}")
    # determinism
    by = defaultdict(set)
    for r in rows:
        by[r["ctx"]].add((r["cuda_model"], r["cuda_kv"], r["cuda_compute"], r.get("cuda_rs"), r["vram"]))
    bad = {c: v for c, v in by.items() if len(v) > 1}
    print("  determinism:", "IDENTICAL across all reps" if not bad else f"VARIES: {bad}")
    return rows

for d, t in [(Path(p), Path(p).name) for p in sys.argv[1:]]:
    table(d, t)
