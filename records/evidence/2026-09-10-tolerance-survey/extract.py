"""Extract every memory/speed observation from committed raw rows into observations.csv.

Read-only on the repo. Predictions are recomputed from committed geometry through
src/mcgyvr/serving/vramfit.py (imported, not modified).
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import statistics
import sys

R = "/home/adaramir/claude/mcgyvr-fleet-id/"
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, R + "src")
from mcgyvr.serving import vramfit  # noqa: E402

M = R + "records/measurements/"
EV = R + "records/evidence/"
MIB = 1024 * 1024
GIB = 1024 ** 3
#: nvidia-smi memory.total minus reserved, as headroom.py:43 uses (read 2026-09-10)
USABLE = {"srv1": 5744, "srv2": 11912}

COLS = ["parameter", "value", "unit", "predicted", "residual", "host", "rig_epoch", "engine",
        "image", "model", "arch", "quant", "n_cpu_moe", "width", "ctx", "ubatch", "load_mode",
        "cache_type", "gpu_mem_util", "sleep_mode", "depends_on", "co_residents", "balloon_gib",
        "clearance_gib", "swappiness", "cold_warm", "instrument", "date", "source", "row_key", "note"]
ROWS: list[dict] = []


def rel(p: str) -> str:
    return p.replace(R, "")


def epoch(host: str, date: str) -> str:
    if date >= "2026-09-03":
        return f"{host}@hosts.json-decl-2026-09-03"
    return f"{host}@pre-2026-09-03"


# ---------------------------------------------------------------- geometry
GEOM: dict[str, dict] = {}
for f in glob.glob(M + "**/*.geometry.json", recursive=True):
    g = json.load(open(f))
    g = g[0] if isinstance(g, list) else g
    GEOM.setdefault(os.path.basename(g["file"]), g)


def arch_of(model: str) -> str:
    g = GEOM.get(model)
    return g["arch"] if g else ""


def spilled_gib(model: str, ncmoe: int) -> float | None:
    g = GEOM.get(model)
    if not g:
        return None
    return (g["bytes_experts"] - vramfit.experts_on_card(g, ncmoe)) / GIB


def experts_on_card_mib(model: str, ncmoe: int) -> float | None:
    g = GEOM.get(model)
    return None if not g else vramfit.experts_on_card(g, ncmoe) / MIB


# ---------------------------------------------------------------- compose
def parse_compose_text(text: str) -> dict[str, dict]:
    svcs: dict[str, dict] = {}
    cur = None
    mode = None
    for line in text.splitlines():
        m = re.match(r"^  ([A-Za-z0-9][^:]*):\s*$", line)
        if m:
            cur = m.group(1)
            svcs[cur] = {"cmd": [], "image": "", "container": "", "depends": "", "env": {}, "restart": ""}
            mode = None
            continue
        if cur is None:
            continue
        if re.match(r"^    command:\s*$", line):
            mode = "cmd"
            continue
        if re.match(r"^    [a-z_]+:", line):
            mode = None
        if mode == "cmd" and line.startswith("    - "):
            svcs[cur]["cmd"].append(line[6:].strip().strip("'\""))
            continue
        for key, pat in (("image", r"^    image: (\S+)"), ("container", r"^    container_name: (\S+)"),
                         ("restart", r"^    restart: (\S+)"), ("depends", r"^\s+condition: (\S+)")):
            mm = re.match(pat, line)
            if mm:
                svcs[cur][key] = mm.group(1).strip("'\"")
        mm = re.match(r"^\s+(VLLM_SERVER_DEV_MODE): '?(\w+)'?", line)
        if mm:
            svcs[cur]["env"][mm.group(1)] = mm.group(2)
    return svcs


def flag(cmd: list[str], *names: str):
    for n in names:
        if n in cmd:
            i = cmd.index(n)
            if i + 1 < len(cmd) and not cmd[i + 1].startswith("-"):
                return cmd[i + 1]
            return True
    return None


def quant_of(model: str) -> str:
    m = re.search(r"(UD-)?(IQ\d_[A-Z]+|Q\d_K_[A-Z]+|Q\d_K|Q\d_0|MXFP4|AWQ|GPTQ[-\w]*)", model, re.I)
    return m.group(0) if m else ""


def knobs(svc: dict) -> dict:
    cmd = svc["cmd"]
    img = svc["image"]
    engine = "vllm" if "vllm" in img else "llamacpp"
    if engine == "vllm":
        model = cmd[0] if cmd and not cmd[0].startswith("-") else str(flag(cmd, "--model"))
        width = flag(cmd, "--max-num-seqs")
        ctx = flag(cmd, "--max-model-len")
        return dict(engine=engine, image=img.split("@sha256:")[0] + ("@" + img.split("@sha256:")[1][:12] if "@sha256:" in img else ""),
                    model=model.split("/")[-1], arch="", quant=quant_of(model), n_cpu_moe="", width=width or "",
                    ctx=ctx or "", ubatch="", load_mode="n/a", cache_type=flag(cmd, "--kv-cache-dtype") or "auto",
                    gpu_mem_util=flag(cmd, "--gpu-memory-utilization") or "",
                    sleep_mode="yes" if "--enable-sleep-mode" in cmd else "no",
                    depends_on=svc["depends"], container=svc["container"])
    model = os.path.basename(str(flag(cmd, "--model", "-m")))
    lm = flag(cmd, "--load-mode")
    return dict(engine=engine, image=img, model=model, arch=arch_of(model), quant=quant_of(model),
                n_cpu_moe=flag(cmd, "--n-cpu-moe") or "0", width=flag(cmd, "--parallel", "-np") or "",
                ctx=flag(cmd, "-c", "--ctx-size") or "", ubatch=flag(cmd, "-ub", "--ubatch-size") or "",
                load_mode="none" if lm == "none" else "mapped",
                cache_type=flag(cmd, "--cache-type-k", "-ctk") or "f16", gpu_mem_util="", sleep_mode="n/a",
                depends_on=svc["depends"], container=svc["container"])


def compose_units(path: str) -> list[dict]:
    p = path.replace("/home/adaramir/claude/mcgyvr/", R)
    return [knobs(s) for s in parse_compose_text(open(p).read()).values()]


def unit_for(units: list[dict], hint: str) -> dict:
    for u in units:
        if hint and (hint.lower() in u["model"].lower() or hint == u["container"]):
            return u
    return units[0]


def add(parameter, value, unit, u: dict | None = None, **kw):
    if value is None:
        return
    row = {c: "" for c in COLS}
    if u:
        for c in COLS:
            if c in u:
                row[c] = u[c]
    row.update(parameter=parameter, value=round(value, 4) if isinstance(value, float) else value, unit=unit)
    for k, v in kw.items():
        row[k] = round(v, 4) if isinstance(v, float) else v
    if row["host"] and row["date"]:
        row["rig_epoch"] = epoch(row["host"], row["date"])
    ROWS.append(row)


# ================================================================ 1. llama.cpp single-unit arms
LLAMA = [
    ("flexibility-2026-09-09/results-q1-srv1.json", "2026-09-09", "unrecorded"),
    ("flexibility-2026-09-09/results-q2-ling.json", "2026-09-09", "unrecorded"),
    ("flexibility-2026-09-09/results-q4q5q6-srv1.json", "2026-09-09", "unrecorded"),
    ("flexibility-2026-09-09/results-arms-q10-80b.json", "2026-09-09", "unrecorded"),
    ("flexibility-2026-09-09/results-q13-srv2.json", "2026-09-09", "unrecorded"),
    ("fleet-gaps-2026-09-09/results-arms-srv1-m1-m3.json", "2026-09-09", "60 (METHOD.md:60)"),
    ("fleet-gaps-2026-09-09/results-arms-srv1-m3-experts.json", "2026-09-09", "60 (METHOD.md:60)"),
    ("fleet-gaps-2026-09-09/results-arms-srv1-rate.json", "2026-09-09", "60 (METHOD.md:60)"),
    ("fleet-gaps-2026-09-09/results-arms-srv2-m1-80b.json", "2026-09-09", "60 (METHOD.md:60)"),
    ("fleet-gaps-2026-09-09/results-arms-srv2-rate.json", "2026-09-09", "60 (METHOD.md:60)"),
    ("measuring-gaps-2026-09-10/results-arms-q1-kv-q8.json", "2026-09-10", "unrecorded"),
    ("measuring-gaps-2026-09-10/results-arms-q3-scratch.json", "2026-09-10", "unrecorded"),
    ("measuring-gaps-2026-09-10/results-arms-q4-c-drift.json", "2026-09-10", "unrecorded"),
    ("measuring-gaps-2026-09-10/results-arms-q5-mla.json", "2026-09-10", "unrecorded"),
]
LABEL_COMPOSE: dict[str, str] = {}
for path, date, swp in LLAMA:
    for r in json.load(open(M + path)):
        if r.get("failed"):
            continue
        LABEL_COMPOSE[r["label"]] = r["compose"]
        u = compose_units(r["compose"])[0]
        host = r["host"]
        verbose = "--verbose" in open(r["compose"].replace("/home/adaramir/claude/mcgyvr/", R)).read()
        base = dict(u, host=host, date=date, swappiness=swp, source="records/measurements/" + path,
                    row_key=r["label"], balloon_gib=r.get("balloon_gib") or "",
                    clearance_gib=round(r["clearance_vs_blob_gib"], 3) if r.get("clearance_vs_blob_gib") is not None else "",
                    note="--verbose" if verbose else "")
        add("wake_s", r.get("wake_s"), "s", base, instrument="door-return minus StartedAt (rig.wake_from)", cold_warm="cold start")
        add("card_steady_mib", r.get("vram_steady_used_mib"), "MiB", base, instrument="nvidia-smi memory.used after load")
        if r.get("vram_peak_used_mib") is not None and r.get("vram_steady_used_mib") is not None:
            add("card_peak_minus_steady_mib", r["vram_peak_used_mib"] - r["vram_steady_used_mib"], "MiB", base,
                instrument="1 Hz sampler peak minus steady")
        net = r.get("vram_steady_net_mib")
        if net is None and r.get("vram_idle_free_mib") is not None and r.get("vram_steady_used_mib") is not None:
            net = r["vram_steady_used_mib"] - (USABLE[host] - r["vram_idle_free_mib"])
        eoc = experts_on_card_mib(u["model"], int(u["n_cpu_moe"] or 0)) if u["engine"] == "llamacpp" else None
        if net is not None and eoc is not None:
            add("card_C_mib", net - eoc, "MiB", base, instrument="net card minus vramfit.experts_on_card (headroom.py method)")
        if r.get("predicted_mib") is not None and net is not None:
            add("card_vs_prediction_mib", net, "MiB", base, predicted=r["predicted_mib"], residual=net - r["predicted_mib"],
                instrument="stored vramfit prediction vs net card")
        sh = r.get("shmem_steady_gib")
        if sh is not None:
            if u["load_mode"] == "none":
                sp = spilled_gib(u["model"], int(u["n_cpu_moe"] or 0))
                add("shmem_unmapped_gib", sh, "GiB", base, predicted=sp, residual=(sh - sp) if sp is not None else "",
                    instrument="/proc/meminfo Shmem steady (absolute, idle not subtracted)")
            else:
                add("shmem_mapped_unit_gib", sh, "GiB", base, instrument="/proc/meminfo Shmem steady")
        add("decode_tok_s", r.get("decode_tok_s"), "tok/s", base, cold_warm="cold (first request, 1 sample)",
            instrument="llama.cpp /completion timings.predicted_per_second, n=160")
        dw = r.get("decode_warm")
        if dw:
            s = dw["samples"]
            add("decode_tok_s", dw["mean"], "tok/s", base, cold_warm="warm (1 discarded + mean of 3)",
                instrument="rig.decode_llamacpp_warm", note=(base["note"] + f" samples={[round(x, 2) for x in s]}").strip())
        add("restarts", r.get("restart_count"), "count", base, instrument="docker RestartCount")
        add("majfault_wake", r.get("pgmajfault_wake"), "pages", base, instrument="/proc/vmstat pgmajfault delta over wake")
        add("pswpout_wake", r.get("pswpout_wake"), "pages", base, instrument="/proc/vmstat pswpout delta over wake")
        if r.get("avail_before_gib") is not None and r.get("avail_after_gib") is not None:
            add("memavailable_drop_gib", r["avail_before_gib"] - r["avail_after_gib"], "GiB", base,
                instrument="MemAvailable before minus after (includes page cache)")

# m1-srv1-mode-vram (Step 0 / m1 mapped arm, sampler lost)
for r in json.load(open(M + "fleet-gaps-2026-09-09/m1-srv1-mode-vram.json")):
    u = compose_units(M + "fleet-gaps-2026-09-09/compose.srv1.mapped-emitted.yml")[0]
    base = dict(u, host="srv1", date="2026-09-09", swappiness="60 (METHOD.md:60)",
                source="records/measurements/fleet-gaps-2026-09-09/m1-srv1-mode-vram.json", row_key=r["label"],
                note="compose mapped to compose.srv1.mapped-emitted.yml (README Step 0)")
    add("wake_s", r.get("wake_s"), "s", base, instrument="door-return minus StartedAt", cold_warm="cold start")
    add("card_steady_mib", r.get("vram_steady_used_mib"), "MiB", base)
    add("decode_tok_s", r.get("mean_tok_s"), "tok/s", base, cold_warm="warm per README Step 0 (n=3)", instrument="mean_tok_s")
    add("majfault_wake", r.get("pgmajfault_wake"), "pages", base)
    add("pswpout_wake", r.get("pswpout_wake"), "pages", base)

# ================================================================ 2. ram-headroom sweeps
RH = M + "ram-headroom-2026-09-09/"
RH_SWP = {"sweep-results.json": "0 (README:35)", "sweep-results-arms-srv2.json": "0 (README:35)",
          "sweep-results-arms-deepseek.json": "0 (README:35)", "sweep-results-arms-repeat.json": "0 (README:35)",
          "sweep-results-arms-gate2.json": "60 (README:97)", "sweep-results-arms-gate2b.json": "60 (README:97)"}
RH_COMPOSE = {("srv1", "compose.srv1.mapped.yml"): RH + "compose.srv1-qwen-mapped.yml",
              ("srv2", "compose.srv2.yml"): RH + "compose.srv2-80b.yml"}
for fn, swp in RH_SWP.items():
    for r in json.load(open(RH + fn)):
        if r.get("failed"):
            continue
        cb = os.path.basename(r["compose"])
        cp = RH_COMPOSE.get((r["host"], cb))
        if r["label"].startswith("srv1-deepseek"):
            cp = RH + "compose.srv1-deepseek.yml"
        if cp:
            u = compose_units(cp)[0]
            note = f"compose {rel(cp)} (row cites uncommitted /tmp {cb})"
        else:
            u = dict(engine="llamacpp", model="Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", arch="qwen35moe", quant="UD-IQ3_XXS",
                     load_mode="none", n_cpu_moe="", width="", ctx="")
            note = f"compose uncommitted (/tmp {cb}); knobs unknown beyond model and --load-mode none"
        base = dict(u, host=r["host"], date="2026-09-09", swappiness=swp, source=rel(RH + fn), row_key=r["label"],
                    balloon_gib=r.get("balloon_gib", ""), clearance_gib=round(r.get("actual_clearance_gib", 0), 3), note=note)
        w = r.get("wake_s")
        if w is not None and w > 5000:
            add("wake_s", w - 10800, "s", base, instrument="StartedAt clock, raw minus 10800 s mktime offset (README:264)",
                cold_warm="cold start", note=note + f"; raw {round(w, 1)}")
        else:
            add("wake_s", w, "s", base, instrument="StartedAt clock", cold_warm="cold start")
        if r.get("rates"):
            add("decode_tok_s", statistics.mean(r["rates"]), "tok/s", base, cold_warm="warm (1 discarded + mean of 3)",
                instrument="sweep.py rates", note=note + f"; samples={[round(x, 2) for x in r['rates']]}")
        add("majfault_wake", r.get("majfault_wake"), "pages", base)
        add("majfault_decode", r.get("majfault_decode"), "pages", base, instrument="/proc/vmstat delta over 3 decode samples")
        add("pswpin_decode", r.get("pswpin_decode"), "pages", base)
        add("pswpout_decode", r.get("pswpout_decode"), "pages", base)
        add("pswpin_wake", r.get("pswpin_wake"), "pages", base)
        add("pswpout_wake", r.get("pswpout_wake"), "pages", base)
        sh = r.get("mem_after", {}).get("Shmem")
        if sh is not None:
            if u.get("load_mode") == "none" and u.get("n_cpu_moe"):
                sp = spilled_gib(u["model"], int(u["n_cpu_moe"]))
                add("shmem_unmapped_gib", sh, "GiB", base, predicted=sp, residual=sh - sp)
            elif u.get("load_mode") == "none":
                add("shmem_unmapped_gib", sh, "GiB", base, note=note + "; not scored (ncmoe unknown)")
            else:
                add("shmem_mapped_unit_gib", sh, "GiB", base)

# ================================================================ 3. co-residency (Q7, M2, Q17)
CO = [("flexibility-2026-09-09/results-q7-coresidency.json", "2026-09-10", "unrecorded"),
      ("flexibility-2026-09-09/m2-coresidency.json", "2026-09-09", "unrecorded"),
      ("fleet-gaps-2026-09-09/m2-coresidency.json", "2026-09-09", "60 (METHOD.md:60)")]
for path, date, swp in CO:
    for r in json.load(open(M + path)):
        units = compose_units(r["compose"])
        host = "srv1" if "srv1" in r["compose"] else "srv2"
        pred = 0.0
        for u in units:
            sp = spilled_gib(u["model"], int(u["n_cpu_moe"]))
            pred += sp if sp is not None else float("nan")
        co = "+".join(f"{u['model']}@ncmoe{u['n_cpu_moe']}" for u in units)
        u0 = dict(units[0]) if len(units) == 1 else dict(units[0], model=co, arch="+".join(u["arch"] for u in units),
                                                         n_cpu_moe="+".join(u["n_cpu_moe"] for u in units), quant="", image=units[0]["image"])
        base = dict(u0, host=host, date=date, swappiness=swp, source="records/measurements/" + path, row_key=r["label"],
                    co_residents=co if len(units) > 1 else "")
        add("shmem_unmapped_gib", r["shmem_delta_gib"], "GiB", base, predicted=pred, residual=r["shmem_delta_gib"] - pred,
            instrument="Shmem after minus idle", note=f"runner-declared experts_gib={r.get('experts_gib')}")
        add("card_steady_mib", r.get("vram_used_mib"), "MiB", base)
        add("wake_s", r.get("wake_s"), "s", base, instrument="door-return minus earliest StartedAt", cold_warm="cold start")
        add("memavailable_drop_gib", r.get("avail_delta_gib"), "GiB", base)
        for port, v in (r.get("decode_tok_s") or {}).items():
            uu = next((x for x in units if x["container"].endswith(port)), units[0])
            add("decode_tok_s", v, "tok/s", dict(base, **{k: uu[k] for k in ("model", "arch", "quant", "n_cpu_moe")}),
                cold_warm="cold (first request, 1 sample)")
        for port, v in (r.get("decode_warm") or {}).items():
            uu = next((x for x in units if x["container"].endswith(port)), units[0])
            add("decode_tok_s", v["mean"], "tok/s", dict(base, **{k: uu[k] for k in ("model", "arch", "quant", "n_cpu_moe")}),
                cold_warm="warm (1 discarded + mean of 3)", note=f"samples={[round(x, 2) for x in v['samples']]}")
        add("majfault_wake", r.get("pgmajfault_delta"), "pages", base)
        add("pswpout_wake", r.get("pswpout_delta"), "pages", base)
        add("pswpin_wake", r.get("pswpin_delta"), "pages", base)
        if r.get("swap_used_after_gib") is not None:
            add("swap_used_delta_gib", r["swap_used_after_gib"] - r["swap_used_before_gib"], "GiB", base)

# ================================================================ 4. vLLM cold starts (pairs, alone)
NT = re.compile(r"(\d+\.\d+) GiB for non-torch memory")
KV = re.compile(r"Available KV cache memory: (-?\d+\.\d+) GiB")
KT = re.compile(r"GPU KV cache size: ([\d,]+) tokens")
VL = [("fleet-gaps-2026-09-09/results-vllm.json", "2026-09-09", "60 (METHOD.md:60)"),
      ("flexibility-2026-09-09/results-q9-vllm-srv1.json", "2026-09-10", "unrecorded"),
      ("flexibility-2026-09-09/results-q14-pair-healthy.json", "2026-09-09", "unrecorded"),
      ("flexibility-2026-09-09/results-q15-sleepmode.json", "2026-09-09", "unrecorded")]
for path, date, swp in VL:
    for r in json.load(open(M + path)):
        if r.get("failed"):
            continue
        units = compose_units(r["compose"])
        host = "srv1" if "srv1" in r["compose"] else "srv2"
        shape = "pair" if len(units) > 1 else "alone"
        cp = os.path.basename(r["compose"])
        pb = dict(units[0] if shape == "alone" else dict(units[0], model="+".join(u["model"] for u in units),
                                                         gpu_mem_util="+".join(u["gpu_mem_util"] for u in units),
                                                         depends_on=next((u["depends_on"] for u in units if u["depends_on"]), "")),
                  host=host, date=date, swappiness=swp, source="records/measurements/" + path, row_key=r["label"],
                  co_residents=shape, note=cp)
        add("wake_s", r.get("wake_s"), "s", pb, instrument="door-return minus earliest StartedAt (vllm_arms.py)", cold_warm="cold start")
        add("card_steady_mib", r.get("vram_steady_used_mib"), "MiB", pb, instrument="nvidia-smi memory.used, all units")
        if r.get("vram_peak_used_mib") and r.get("vram_steady_used_mib"):
            add("card_peak_minus_steady_mib", r["vram_peak_used_mib"] - r["vram_steady_used_mib"], "MiB", pb)
        add("vllm_host_ram_gib", r.get("ram_cost_gib"), "GiB", pb, instrument="MemAvailable idle minus after")
        for k, pu in (r.get("per_unit") or {}).items():
            u = unit_for(units, k.upper())
            b = dict(pb, **{c: u[c] for c in ("model", "quant", "gpu_mem_util", "depends_on")},
                     row_key=f"{r['label']}/{k}")
            add("restarts", pu.get("restart_count"), "count", b)
            if pu.get("tok_s"):
                add("decode_tok_s", statistics.mean(pu["tok_s"]), "tok/s", b, cold_warm="warm (1 discarded + mean of 3)",
                    instrument="rig.decode_vllm client-side", note=f"{cp}; samples={pu['tok_s']}")
            if pu.get("ttft_s"):
                add("ttft_s", statistics.mean(pu["ttft_s"]), "s", b, cold_warm="warm")
            add("start_offset_s", pu.get("started_offset_s"), "s", b, instrument="StartedAt minus earliest StartedAt")
            el = pu.get("engine_lines") or ""
            nts = NT.findall(el)
            if nts:
                add("vllm_nontorch_gib", float(nts[-1]), "GiB", b, instrument="engine line gpu_worker.py:857 (last start)")
            kvs = KT.findall(el)
            if kvs:
                add("vllm_kv_tokens", int(kvs[-1].replace(",", "")), "tokens", b, instrument="engine line kv_cache_utils (last start)")
            neg = [float(x) for x in KV.findall(el) if float(x) < 0]
            if neg:
                add("vllm_negative_kv_attempts", len(neg), "count", b, note=f"{cp}; Available KV cache memory {neg} GiB")

# measuring-gaps Q2 (vLLM q34b fp16/fp8)
for r in json.load(open(M + "measuring-gaps-2026-09-10/results-q2-vllm-fp8.json")):
    u = compose_units(r["compose"])[0]
    b = dict(u, host=r["host"], date="2026-09-10", swappiness="unrecorded",
             source="records/measurements/measuring-gaps-2026-09-10/results-q2-vllm-fp8.json", row_key=r["label"], co_residents="alone")
    add("wake_s", r.get("wake_s"), "s", b, cold_warm="cold start", instrument="door-return minus StartedAt")
    add("card_steady_mib", r.get("vram_steady_used_mib"), "MiB", b)
    if r.get("vram_peak_used_mib"):
        add("card_peak_minus_steady_mib", r["vram_peak_used_mib"] - r["vram_steady_used_mib"], "MiB", b)
    add("decode_tok_s", r.get("tok_s"), "tok/s", b, cold_warm="warm (1 discarded + mean)", instrument="vllm_fp8_kv.py:131")
    add("vllm_kv_tokens", r.get("kv_tokens"), "tokens", b)

# ================================================================ 5. Q15 cycles (per process, L2)
SLEEP = M + "flexibility-2026-09-09/compose.srv2.sleepmode.yml"
su = compose_units(SLEEP)
for r in json.load(open(M + "flexibility-2026-09-09/results-q15-cycles.json")):
    pb = dict(su[0], model="+".join(u["model"] for u in su), gpu_mem_util="+".join(u["gpu_mem_util"] for u in su),
              depends_on="service_started", host="srv2", date="2026-09-10", swappiness="unrecorded",
              source="records/measurements/flexibility-2026-09-09/results-q15-cycles.json", row_key=r["label"],
              co_residents="pair", note="compose.srv2.sleepmode.yml")
    add("wake_s", r["wake_s"], "s", pb, cold_warm="cold start", instrument="door-return minus earliest StartedAt")
    add("card_peak_mib", r.get("vram_peak_used_mib"), "MiB", pb)
    for k in ("3b", "7b"):
        u = unit_for(su, k.upper())
        b = dict(pb, model=u["model"], gpu_mem_util=u["gpu_mem_util"], quant=u["quant"])
        add("restarts", r["restart_count"][k], "count", dict(b, row_key=f"{r['label']}/{k}"))
        s0 = r["steps"][0]
        add("vllm_unit_card_cold_mib", s0["per_unit_mib"][k], "MiB", dict(b, row_key=f"{r['label']}/serving-0/{k}"),
            instrument="nvidia-smi per pid, cgroup-attributed", cold_warm="after cold start")
        for step in r["steps"]:
            if step.get("decode") and step["decode"].get(k) is not None:
                add("decode_tok_s", step["decode"][k], "tok/s", dict(b, row_key=f"{r['label']}/{step['step']}/{k}"),
                    cold_warm="single sample, no discard" + (" (first request after cold start)" if step["step"] == "serving-0" else " (first request after L2 wake)"),
                    instrument="sleep_cycles.tok -> rig.decode_vllm")
        for c in r["cycles"]:
            kk = dict(b, row_key=f"{r['label']}/cycle{c['cycle']}/{k}")
            add("vllm_L2_residual_mib", c["asleep_mib"][k], "MiB", kk, instrument="per pid, cgroup-attributed")
            add("vllm_unit_card_after_wake_mib", c["serving_mib"][k], "MiB", kk)
            add("vllm_cold_minus_wake_card_mib", s0["per_unit_mib"][k] - c["serving_mib"][k], "MiB", kk)
            add("wake_s_vllm_L2", c["wake_s"][k], "s", kk, instrument="POST /wake_up round trip", cold_warm="L2 wake")
            add("sleep_s_vllm_L2", c["sleep_s"][k], "s", kk, instrument="POST /sleep?level=2 round trip")

# ================================================================ 6. Q16b off-door three-way
for r in json.load(open(M + "flexibility-2026-09-09/results-q16b-offdoor.json")):
    cp = M + f"flexibility-2026-09-09/compose.srv2-80b-offdoor-ncmoe{r['ncmoe']}.yml"
    u = compose_units(cp)[0]
    b = dict(u, host="srv2", date="2026-09-10", swappiness="unrecorded",
             source="records/measurements/flexibility-2026-09-09/results-q16b-offdoor.json", row_key=r["label"],
             co_residents=f"vLLM 3B+7B pair, {r['asleep']} asleep L2", note=os.path.basename(cp))
    add("card_vs_prediction_mib", r["eighty_b_added_mib"], "MiB", b, predicted=r["predicted_mib"],
        residual=r["eighty_b_added_mib"] - r["predicted_mib"], instrument="card used all three minus with-sleeper vs vramfit.floor prediction")
    add("wake_s", r["wake_s"], "s", b, cold_warm="cold start", instrument="off-door, wait_models")
    add("restarts", r["restart_count"], "count", b)
    add("decode_tok_s", r["decode_80b_cold"], "tok/s", b, cold_warm="cold (first request, 1 sample)")
    add("decode_tok_s", r["decode_80b_warm"]["mean"], "tok/s", b, cold_warm="warm (1 discarded + mean of 3)",
        note=f"{os.path.basename(cp)}; samples={[round(x, 2) for x in r['decode_80b_warm']['samples']]}")
    for k in ("7b", "3b"):
        vu = unit_for(su, k.upper())
        vb = dict(vu, host="srv2", date="2026-09-10", swappiness="unrecorded", co_residents="pair",
                  source=b["source"], row_key=f"{r['label']}/pair_up/{k}", note="compose.srv2.sleepmode.yml")
        add("vllm_unit_card_cold_mib", r["pair_up_per_unit_mib"][k], "MiB", vb, instrument="per pid, cgroup-attributed")
        if r["asleep"] == k:
            add("vllm_L2_residual_mib", r["with_sleeper_per_unit_mib"][k], "MiB", dict(vb, row_key=f"{r['label']}/asleep/{k}"))
    aw = unit_for(su, r["awake"].upper())
    add("decode_tok_s", r["awake_decode"]["tok_s"], "tok/s",
        dict(aw, host="srv2", date="2026-09-10", source=b["source"], row_key=f"{r['label']}/awake/{r['awake']}",
             co_residents="80B + sleeper on card", note="compose.srv2.sleepmode.yml"),
        cold_warm="single sample, no discard (unit long-running)")

# ================================================================ 7. sleep matrices M6/M7 and 09-09
def procs(s: str) -> dict[str, int]:
    return {p.split(",")[0].strip(): int(p.split(",")[1].strip().split()[0]) for p in s.split("|")}


for path, key, date in (("fleet-gaps-2026-09-09/m6-m7-sleep-matrix.json", "gpu_procs", "2026-09-09"),
                        ("vllm-sleep-2026-09-09/vllm-sleep-results.json", "procs", "2026-09-09")):
    steps = json.load(open(M + path))
    base_p = procs(steps[0][key])
    # attribute pids by behaviour: the pid that drops at the first 3B-asleep step is the 3B
    step3 = next(s for s in steps if "3b" in s["step"].lower() and "asleep" in s["step"].lower() and key in s)
    p3 = [p for p, v in procs(step3[key]).items() if v < 1000][0]
    who = {p: ("3b" if p == p3 else "7b") for p in base_p}
    for s in steps:
        lvl = "L1" if s["step"].startswith("L1") and "then2" not in s["step"] else "L2"
        for k in ("3b", "7b"):
            u = unit_for(su, k.upper())
            b = dict(u, host="srv2", date=date, source="records/measurements/" + path, row_key=f"{s['step']}/{k}",
                     co_residents="pair", swappiness="60 (METHOD.md:60)" if "fleet-gaps" in path else "unrecorded",
                     note="compose.srv2.sleepmode.yml (README M6); pid attributed by which drops at 3B-asleep step")
            ws = s.get("wake_s")
            if isinstance(ws, dict):
                ws = ws.get(k) or ws.get(k.upper())
            elif ws is not None and k not in s["step"].lower():
                ws = None
            if ws is not None:
                add(f"wake_s_vllm_{lvl}", ws, "s", b, cold_warm=f"{lvl} wake", instrument="POST /wake_up round trip")
            ss = s.get("sleep_s")
            if isinstance(ss, dict):
                ss = ss.get(k) or ss.get(k.upper())
            elif ss is not None and k not in s["step"].lower():
                ss = None
            if ss is not None:
                add(f"sleep_s_vllm_{lvl}", ss, "s", b)
            if key in s:
                for p, v in procs(s[key]).items():
                    if who.get(p) == k and v < 1000:
                        add("vllm_L2_residual_mib" if lvl == "L2" else "vllm_L1_residual_mib", v, "MiB", b)
            dk = s.get(f"decode_{k}") or (s.get("decode") if k in s["step"].lower() else None)
            if dk:
                add("decode_tok_s", dk, "tok/s", b, cold_warm="single sample (unit long-running)")

# ================================================================ 8. Q8 clocks
for r in json.load(open(M + "flexibility-2026-09-09/results-q8-clocks.json")):
    if r.get("failed"):
        continue
    env = None
    for f in glob.glob(EV + "*-live-srv1/serve-up*.json"):
        d = json.load(open(f))
        if d.get("run_id") == r["envelope"]["run_id"]:
            env = d
    u = knobs(list(parse_compose_text(env["compose"]).values())[0]) if env and env.get("compose") else {}
    b = dict(u, host="srv1", date="2026-09-10", swappiness="unrecorded",
             source="records/measurements/flexibility-2026-09-09/results-q8-clocks.json", row_key=r["label"],
             note="knobs from envelope " + (rel(f) if env else "NOT FOUND; README: live ladder -c 16384 ncmoe 30"))
    add("wake_s", r["clock1_startedat_s"], "s", b, instrument="clock1 StartedAt->answering", cold_warm="cold start")
    add("wake_s_door", r["clock2_door_s"], "s", b, instrument="clock2 door up-after", cold_warm="cold start")
    add("wake_s_mcgyvr", r["clock3_mcgyvr_s"], "s", b, instrument="clock3 Wake.seconds", cold_warm="cold start")
    add("door_overhead_s", r["door_overhead_s"], "s", b)
    add("restarts", r["restart_count"], "count", b)
    add("card_steady_mib", r["envelope"]["card_after"]["used_mib"], "MiB", b, instrument="envelope card_after")

# ================================================================ 9. every live door envelope (door clock + card)
seen = set()
for f in sorted(glob.glob(EV + "*live*/serve-up*.json")):
    d = json.load(open(f))
    if d.get("run_id") in seen or not d.get("compose"):
        continue
    seen.add(d["run_id"])
    host = d["host"]
    date = re.search(r"(2026-\d\d-\d\d)", f).group(1)
    svcs = parse_compose_text(d["compose"])
    units = [knobs(s) for s in svcs.values()]
    first = min((x for x in d["units"] if x.get("seconds") is not None), key=lambda x: x["seconds"], default=None)
    order = sorted(d["units"], key=lambda x: -(x.get("seconds") or 0))
    for i, x in enumerate(order):
        u = next((k for k in units if k["container"] == x["container"]), units[0])
        b = dict(u, host=host, date=date, source=rel(f), row_key=f"{d['run_id']}/{x['port']}",
                 co_residents="+".join(k["model"] for k in units) if len(units) > 1 else "",
                 note="door clock; for multi-unit envelopes only the largest figure is a wake (O8: the rest are 'after the previous')")
        if i == 0:
            add("wake_s_door", x["seconds"], "s", b, instrument="envelope units[].seconds (door up-after)", cold_warm="cold start")
        else:
            add("wake_s_door_increment", x["seconds"], "s", b, instrument="envelope units[].seconds (O8 increment)")
    ca = d.get("card_after") or {}
    if ca.get("used_mib") is not None:
        u = units[0]
        b = dict(u if len(units) == 1 else dict(u, model="+".join(k["model"] for k in units),
                                                gpu_mem_util="+".join(k["gpu_mem_util"] for k in units),
                                                depends_on=next((k["depends_on"] for k in units if k["depends_on"]), "")),
                 host=host, date=date, source=rel(f), row_key=d["run_id"], co_residents="pair" if len(units) > 1 else "")
        add("card_after_door_mib", ca["used_mib"], "MiB", b, instrument="envelope card_after.used_mib (read at door return)")

# ================================================================ 10. load-mode A/B (run.txt)
txt = open(M + "load-mode-2026-09-08/run.txt").read()
envs = {json.load(open(f))["run_id"]: json.load(open(f)) for f in glob.glob(EV + "2026-09-08-live-srv1/serve-up*.json")}
env_m = next(v for k, v in envs.items() if k.endswith("mmap-up"))
env_n = next(v for k, v in envs.items() if k.endswith("none-up"))
for mode in ("mmap", "none", "mmap2", "none2"):
    env = env_m if mode.startswith("mmap") else env_n
    u = knobs(list(parse_compose_text(env["compose"]).values())[0])
    b = dict(u, host="srv1", date="2026-09-08", swappiness="unrecorded",
             source="records/measurements/load-mode-2026-09-08/run.txt", row_key=mode,
             note=f"knobs from {env['run_id']} envelope")
    wu = re.search(rf"^{mode}\s+warm-up \(discarded\)\s+decode\s+([\d.]+)", txt, re.M)
    ss = [float(x) for x in re.findall(rf"^{mode}\s+sample \d\s+decode\s+([\d.]+)", txt, re.M)]
    add("decode_tok_s", float(wu.group(1)), "tok/s", b, cold_warm="cold (first request, discarded warm-up)")
    add("decode_tok_s", statistics.mean(ss), "tok/s", b, cold_warm="warm (1 discarded + mean of 3)", note=b["note"] + f"; samples={ss}")

# ================================================================ 11. serving-concurrency 09-06 and Q12 (width 1)
for fn, host, eng, knobs_note in (("srv2-vllm-3b.json", "srv2", "vllm", "README:28 vllm v0.26.0 len 4096 seqs 8"),
                                  ("srv2-vllm-7b.json", "srv2", "vllm", "README:28 vllm v0.26.0 len 4096 seqs 8"),
                                  ("srv1-llamacpp-qwen36-35b.json", "srv1", "llamacpp", "README:27 b10644-L3 -c 32768 --parallel 8"),
                                  ("srv2-llamacpp-qwen36-35b-cpu-only.json", "srv2", "llamacpp", "README:27 cpu-only")):
    d = json.load(open(M + "serving-concurrency-2026-09-06/" + fn))
    for x in d["results"]:
        if x["width"] == 1:
            add("decode_tok_s", x["per_stream_tps"], "tok/s",
                dict(host=host, engine=eng, model=d.get("model", ""), date="2026-09-06", width="bench width 1",
                     source="records/measurements/serving-concurrency-2026-09-06/" + fn, row_key=f"{d['label']}/width1",
                     note="no compose committed; knobs " + knobs_note),
                cold_warm="unstated (tools/serving/concurrency_sweep.py has no warm-up)", instrument="per_stream_tps")
d = json.load(open(M + "flexibility-2026-09-09/results-q12-lambda.json"))
u = compose_units(M + "flexibility-2026-09-09/compose.srv2-80b-ncmoe36-w4.yml")[0]
for x in d["results"]:
    add("decode_tok_s", x["per_stream_tps"], "tok/s",
        dict(u, host="srv2", date="2026-09-09", source="records/measurements/flexibility-2026-09-09/results-q12-lambda.json",
             row_key=f"q12/width{x['width']}", note=f"concurrency width {x['width']}"),
        cold_warm="width-1 is a cold first request per README:205" if x["width"] == 1 else "concurrent, unstated warm-up",
        instrument="concurrency_sweep per_stream_tps")

with open(os.path.join(OUT, "observations.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS)
    w.writeheader()
    for row in ROWS:
        w.writerow(row)
print(len(ROWS), "rows")
from collections import Counter
print(Counter(r["parameter"] for r in ROWS).most_common())
