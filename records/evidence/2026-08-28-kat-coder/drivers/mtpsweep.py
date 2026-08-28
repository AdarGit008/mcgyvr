import json, subprocess, sys, time, urllib.request, threading, socket

# mtpsweep.py: baseline vs native MTP (--spec-type draft-mtp) on the grafted-MTP GGUF.
# usage: mtpsweep.py MODEL MDIR TAG NCMOE "nmax_list"  (nmax=0 => baseline, no spec)
MODEL, MDIR, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
NCMOE = int(sys.argv[4])
NMAX_LIST = [int(x) for x in sys.argv[5].split(",")]
IMG = "ghcr.io/ggml-org/llama.cpp:server-cuda"
PORT, NPRED, H = 8096, 475, socket.gethostname()
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

for nmax in NMAX_LIST:
    sh("docker rm -f mtps")
    spec = f"--spec-type draft-mtp --spec-draft-n-max {nmax}" if nmax > 0 else ""
    extra = f"--n-cpu-moe {NCMOE}" if NCMOE > 0 else ""
    sh(f"docker run -d --name mtps --gpus all -v {MDIR}:/models:ro -p {PORT}:8080 {IMG} "
       f"-m /models/{MODEL.split(chr(47))[-1]} -ngl 99 -np 1 -c 2048 {extra} {spec} "
       f"-fa on --no-warmup --host 0.0.0.0 --port 8080")
    ok = False
    for _ in range(400):
        if sh(f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y") == "Y":
            ok = True
            break
        if "mtps" not in sh("docker ps --format \"{{.Names}}\""):
            break
        time.sleep(2)
    lab = f"{TAG} nmax={nmax} ncmoe={NCMOE}"
    if not ok:
        why = " | ".join(sh("docker logs mtps 2>&1 | grep -iE \"error|memory|mtp|architect\" | tail -2").splitlines())[:220]
        print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
        sh("docker rm -f mtps")
        continue
    post([None], 0)
    for run in range(3):
        out = [None]
        t0 = time.time()
        post(out, 0)
        wall = time.time() - t0
        gen = out[0][0]
        print(f"{H}\t{lab}\trun{run+1}\ttok/s={gen/wall:.1f}\twall={wall:.1f}\tgen={gen}", flush=True)
    sh("docker rm -f mtps")
    time.sleep(2)
