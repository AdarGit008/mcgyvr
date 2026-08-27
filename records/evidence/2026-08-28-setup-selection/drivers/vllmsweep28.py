import json, subprocess, sys, time, urllib.request, threading, socket, re

# sweep-2026-08-28 vLLM driver: 475 tokens, ignore_eos, temp 0, one fixed prompt.
# args: tag model_ref cells...   cell = util:maxlen:seqs:kvdtype:levels
# model_ref may be a HF repo id (HF cache) or /models/... (mounts ~/models).
TAG, MODEL = sys.argv[1], sys.argv[2]
CELLS = sys.argv[3:]
IMG = "vllm/vllm-openai:v0.26.0"
PORT, NPRED, H = 8095, 475, socket.gethostname()
PROMPT = "Write a Python function that merges two sorted lists."


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def post(out, idx):
    b = json.dumps({"model": MODEL, "prompt": PROMPT, "max_tokens": NPRED,
                    "temperature": 0, "ignore_eos": True}).encode()
    r = urllib.request.Request(f"http://localhost:{PORT}/v1/completions", data=b,
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=3600) as f:
            d = json.load(f)
        out[idx] = (d["usage"]["completion_tokens"], time.time() - t0)
    except Exception:
        out[idx] = (0, time.time() - t0)


for cell in CELLS:
    util, maxlen, seqs, kv, lv = cell.split(":")
    levels = [int(x) for x in lv.split(",")]
    sh("docker rm -f vsweep")
    kvflag = f"--kv-cache-dtype {kv}" if kv != "auto" else ""
    cmd = (f'docker run -d --name vsweep --runtime=nvidia --gpus all '
           f'-v $HOME/.cache/huggingface:/root/.cache/huggingface '
           f'-v $HOME/models:/models:ro '
           f'-v $HOME/ggufs:/ggufs:ro '
           f'-p {PORT}:8000 --ipc=host {IMG} {MODEL} --port 8000 '
           f'--gpu-memory-utilization {util} --max-model-len {maxlen} '
           f'--max-num-seqs {seqs} {kvflag}')
    sh(cmd)
    lab = f"{TAG} util={util} len={maxlen} seqs={seqs} kv={kv}"
    ok = False
    for _ in range(450):
        if sh(f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y") == "Y":
            ok = True
            break
        if "vsweep" not in sh("docker ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    if not ok:
        why = sh("docker logs vsweep 2>&1 | grep -iE 'error|not supported|memory|architect' | tail -2")
        why = " | ".join(why.splitlines())[:400]
        print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
        sh("docker rm -f vsweep")
        continue
    vram = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    print(f"{H}\t{lab}\tCONFIG\tvram={vram}", flush=True)
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
    sh("docker rm -f vsweep")
    time.sleep(2)
