import json, subprocess, sys, time, urllib.request, threading, socket, re

# args: model_path mount_dir tag cells...   cell = np:ctx_slot:ncpumoe:levels
# -c is computed as np * ctx_slot, because llama.cpp DIVIDES -c across slots.
MODEL, MDIR, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
CELLS = sys.argv[4:]
IMG = "ghcr.io/ggml-org/llama.cpp:server-cuda-b10481"
PORT, NPRED, H = 8094, 475, socket.gethostname()
PROMPT = "Write a Python function that merges two sorted lists."


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def post(out, idx):
    b = json.dumps({"prompt": PROMPT, "n_predict": NPRED, "temperature": 0,
                    "cache_prompt": False, "ignore_eos": True}).encode()
    r = urllib.request.Request(f"http://localhost:{PORT}/completion", data=b,
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=3600) as f:
            d = json.load(f)
        out[idx] = (d["timings"]["predicted_n"], time.time() - t0)
    except Exception:
        out[idx] = (0, time.time() - t0)


for cell in CELLS:
    np_, ctxslot, ncm, lv = cell.split(":")
    levels = [int(x) for x in lv.split(",")]
    total_c = int(np_) * int(ctxslot)
    sh("docker rm -f lcps")
    extra = f"--n-cpu-moe {ncm}" if ncm != "0" else ""
    sh(f'docker run -d --name lcps --gpus all -v {MDIR}:/models:ro -p {PORT}:8080 {IMG} '
       f'-m /models/{MODEL.split("/")[-1]} -ngl 99 -np {np_} -c {total_c} {extra} '
       f'-fa on --no-warmup --host 0.0.0.0 --port 8080')
    ok = False
    for _ in range(400):
        if sh(f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y") == "Y":
            ok = True
            break
        if "lcps" not in sh("docker ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    lab = f"{TAG} np={np_} ctx_slot={ctxslot} c={total_c} ncmoe={ncm}"
    if not ok:
        why = sh("docker logs lcps 2>&1 | grep -iE 'error|out of memory' | tail -1")[:110]
        print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
        sh("docker rm -f lcps")
        continue
    log = sh("docker logs lcps 2>&1")
    real_slot = re.search(r"n_ctx_slot = (\d+)", log)
    vram = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    print(f"{H}\t{lab}\tCONFIG\treal_ctx_slot={real_slot.group(1) if real_slot else '?'}"
          f"\tvram={vram}", flush=True)
    post([None], 0)
    for n in levels:
        out = [None] * n
        th = [threading.Thread(target=post, args=(out, i)) for i in range(n)]
        t0 = time.time()
        for t in th:
            t.start()
        for t in th:
            t.join()
        wall = time.time() - t0
        gen = sum(o[0] for o in out)
        if gen == 0:
            print(f"{H}\t{lab}\tn={n}\tERR", flush=True)
            break
        short = sum(1 for o in out if o[0] < NPRED)
        lat = sorted(o[1] for o in out)
        print(f"{H}\t{lab}\tn={n}\tagg={gen / wall:.1f}\tp50={lat[len(lat) // 2]:.2f}"
              f"\ttruncated={short}/{n}\twall={wall:.1f}", flush=True)
    sh("docker rm -f lcps")
    time.sleep(2)
