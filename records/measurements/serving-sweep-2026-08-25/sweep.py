#!/usr/bin/env python3
"""Phase A sweep harness for docs/plans/serving-sweep-2026-08-25.

Records exactly the fields P0.1/P0.2 demand: build_info from GET /props, the full
server argv, the model file's sha256, peak VRAM and RSS. Writes JSONL; does not
touch the repository's recorder.
"""
import json, subprocess, sys, time, urllib.request, statistics as st
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "a1-results.jsonl"
IMAGE = "ghcr.io/ggml-org/llama.cpp:server-cuda-b10481"
CTR = "llama-sweep"
N_PRED, N_MEAS, N_WARM, N_BURST = 160, 5, 2, 8

# A representative prompt: a real task contract from the corpus, so prompt length
# sits near the measured median (688 tokens) instead of the 21-token toy used for
# the arrival baseline.
CONTRACT = (Path(__file__).parents[5] / "home/adaramir/pi_agent/projects/mcgyvr"
            / "tools/bench/tasks/py/b002-option-pairs/contract.yaml")
try:
    spec = Path("/home/adaramir/pi_agent/projects/mcgyvr/tools/bench/tasks/py/b002-option-pairs/contract.yaml").read_text()
except Exception:
    spec = "Write a Python function that merges two sorted lists.\n"
PROMPT = (
    "You are implementing a single Python function to a written contract.\n"
    "Return only the function body in a fenced code block, no prose.\n\n"
    "CONTRACT:\n" + spec + "\n"
    "Implement it now, with type hints and a docstring, handling every error path "
    "the contract names.\n"
)

def sh(host, cmd, timeout=600):
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", host, cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def post(host, payload, timeout=600):
    req = urllib.request.Request(f"http://{host}:8080/completion",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def gen(host, n=N_PRED):
    return post(host, {"prompt": PROMPT, "n_predict": n, "temperature": 0,
                       "cache_prompt": False})

def start(host, model_path, mounts, args):
    sh(host, f"docker rm -f {CTR} llama-moe 2>/dev/null; true")
    m = " ".join(f"-v {s}:{d}" for s, d in mounts)
    cmd = (f"docker run -d --name {CTR} --gpus all -p 8080:8080 {m} {IMAGE} "
           f"-m {model_path} {args} --host 0.0.0.0 --port 8080")
    return sh(host, cmd)

def wait_healthy(host, limit=420):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            with urllib.request.urlopen(f"http://{host}:8080/health", timeout=5) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            pass
        time.sleep(4)
    return False

def probe(host):
    vram = sh(host, "nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits")
    rss = sh(host, "ps -eo comm,rss --sort=-rss | awk '/llama-server/{print $2; exit}'")
    free = sh(host, "free -m | awk '/^Mem:/{print $7}'")
    props = json.loads(urllib.request.urlopen(f"http://{host}:8080/props", timeout=10).read())
    slots = json.loads(urllib.request.urlopen(f"http://{host}:8080/slots", timeout=10).read())
    argv = sh(host, "tr '\\0' ' ' < /proc/$(pgrep -f llama-server | head -1)/cmdline")
    return {
        "vram_mib": int(vram.split("\n")[0]) if vram.strip().split() else None,
        "rss_kb": int(rss) if rss.isdigit() else None,
        "free_mb_after_load": int(free) if free.isdigit() else None,
        "build_info": props.get("build_info"),
        "total_slots": props.get("total_slots"),
        "n_ctx_per_slot": slots[0].get("n_ctx") if slots else None,
        "argv": argv.strip(),
    }

def run_cell(cell):
    host, label = cell["host"], cell["label"]
    rec = {"cell": label, "host": host, "model": cell["model"],
           "model_sha256": cell.get("sha256"), "params_b": cell["params_b"],
           "gguf_bytes": cell.get("bytes"), "flags": cell["args"],
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print(f"[{rec['ts']}] {label} on {host}: starting", flush=True)
    try:
        start(host, cell["model_path"], cell["mounts"], cell["args"])
        if not wait_healthy(host):
            rec.update(status="skipped", reason="never became healthy",
                       docker_log=sh(host, f"docker logs --tail 15 {CTR} 2>&1")[-1200:])
            return rec
        for _ in range(N_WARM):
            gen(host)
        rows = [gen(host) for _ in range(N_MEAS)]
        t = [r["timings"] for r in rows]
        rec["prompt_n"] = t[0]["prompt_n"]
        rec["S1_tok_s"] = round(st.median(x["predicted_per_second"] for x in t), 2)
        rec["S1_all"] = [round(x["predicted_per_second"], 2) for x in t]
        rec["prompt_tok_s"] = round(st.median(x["prompt_per_second"] for x in t), 1)
        rec["ttft_s"] = round(st.median(x["prompt_ms"] for x in t) / 1000, 2)
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=N_BURST) as ex:
            burst = list(ex.map(lambda _: gen(host, 120), range(N_BURST)))
        wall = time.time() - t0
        toks = sum(b["timings"]["predicted_n"] for b in burst)
        rec["S8_tok_s"] = round(toks / wall, 2)
        rec["S8_wall_s"] = round(wall, 1)
        rec.update(probe(host))
        rec["score_S1"] = round(rec["S1_tok_s"] * cell["params_b"])
        rec["score_S8"] = round(rec["S8_tok_s"] * cell["params_b"])
        rec["status"] = "ok"
        print(f"    S1={rec['S1_tok_s']} S8={rec['S8_tok_s']} "
              f"vram={rec['vram_mib']}MiB free={rec['free_mb_after_load']}MB", flush=True)
    except Exception as e:
        rec.update(status="error", reason=f"{type(e).__name__}: {e}",
                   docker_log=sh(host, f"docker logs --tail 15 {CTR} 2>&1")[-1200:])
        print(f"    ERROR {rec['reason']}", flush=True)
    return rec

if __name__ == "__main__":
    cells = json.loads(Path(sys.argv[1]).read_text())
    with OUT.open("a") as fh:
        for c in cells:
            fh.write(json.dumps(run_cell(c)) + "\n")
            fh.flush()
    print("done", flush=True)
