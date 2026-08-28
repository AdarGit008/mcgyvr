import json, subprocess, sys, time, urllib.request, threading, socket

# mtp_sweep2.py — native MTP (--spec-type draft-mtp) baseline-vs-draft.
# Extends the 2026-08-28 mtpsweep.py with concurrency and long-context support.
#
# Mode 'conc':  mtp_sweep2.py conc MODEL MDIR TAG NCMOE "n_list" "nmax_list"
#   For each concurrency n in n_list: launch -np n -c n*1024, short 475-token prompt.
#   Run baseline (nmax=0) and each nmax (fire n concurrent requests each).
#   Reports agg tok/s (predicted/wall) + draft acceptance (draft_n_accepted/draft_n).
#
# Mode 'long':  mtp_sweep2.py long MODEL MDIR TAG NCMOE PROMPT_FILE CTX NPRED "nmax_list"
#   Single-slot (-np 1 -c CTX), long prompt from PROMPT_FILE. 3 runs per config.
#   Reports generation tok/s from timings.predicted_per_second (prefill excluded)
#   + draft acceptance + prefill ms.

IMG = "ghcr.io/ggml-org/llama.cpp:server-cuda"
PORT, H = 8098, socket.gethostname()
SHORT = "Write a Python function that merges two sorted lists."


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def post(prompt, npred, out, idx):
    b = json.dumps({"prompt": prompt, "n_predict": npred, "temperature": 0,
                    "cache_prompt": False, "ignore_eos": True}).encode()
    r = urllib.request.Request(f"http://localhost:{PORT}/completion", data=b,
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=3600) as f:
            d = json.load(f)
        t = d.get("timings", {})
        out[idx] = (t.get("predicted_n", 0), t.get("draft_n", 0),
                    t.get("draft_n_accepted", 0), time.time() - t0,
                    t.get("predicted_per_second", 0.0), t.get("prompt_ms", 0.0))
    except Exception:
        out[idx] = (0, 0, 0, time.time() - t0, 0.0, 0.0)


def run_container(model, np_, c_, ncmoe, nmax):
    sh("docker rm -f mtps2")
    spec = f"--spec-type draft-mtp --spec-draft-n-max {nmax}" if nmax > 0 else ""
    extra = f"--n-cpu-moe {ncmoe}" if ncmoe > 0 else ""
    sh(f"docker run -d --name mtps2 --gpus all -v {MDIR}:/models:ro -p {PORT}:8080 {IMG} "
       f"-m /models/{model.split('/')[-1]} -ngl 99 -np {np_} -c {c_} {extra} {spec} "
       f"-fa on --no-warmup --host 0.0.0.0 --port 8080")
    for _ in range(400):
        if sh(f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y") == "Y":
            return True
        if "mtps2" not in sh("docker ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    return False


def refuse(lab):
    why = " | ".join(sh("docker logs mtps2 2>&1 | grep -iE 'error|memory|mtp|architect|out of' | tail -2").splitlines())[:200]
    print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
    sh("docker rm -f mtps2")


def accept_agg(rows):
    dn = sum(r[1] for r in rows)
    da = sum(r[2] for r in rows)
    return da, dn


mode = sys.argv[1]
MODEL, MDIR, TAG = sys.argv[2], sys.argv[3], sys.argv[4]
NCMOE = int(sys.argv[5])

if mode == "conc":
    N_LIST = [int(x) for x in sys.argv[6].split(",")]
    NMAX_LIST = [int(x) for x in sys.argv[7].split(",")]
    for n in N_LIST:
        for nmax in NMAX_LIST:
            lab = f"{TAG} conc n={n} nmax={nmax} ncmoe={NCMOE}"
            if not run_container(MODEL, n, n * 1024, NCMOE, nmax):
                refuse(lab)
                continue
            post(SHORT, 475, [None], 0)  # warm slot
            out = [None] * n
            th = [threading.Thread(target=post, args=(SHORT, 475, out, i)) for i in range(n)]
            t0 = time.time()
            for t in th:
                t.start()
            for t in th:
                t.join()
            wall = time.time() - t0
            gen = sum(o[0] for o in out)
            da, dn = accept_agg(out)
            acc = f"{da}/{dn}={da/dn:.3f}" if dn else "n/a"
            if gen == 0:
                print(f"{H}\t{lab}\tERR", flush=True)
            else:
                print(f"{H}\t{lab}\tagg={gen/wall:.1f}\twall={wall:.1f}\tgen={gen}"
                      f"\taccept={acc}", flush=True)
            sh("docker rm -f mtps2")
            time.sleep(2)
elif mode == "long":
    PROMPT_FILE, CTX, NPRED = sys.argv[6], int(sys.argv[7]), int(sys.argv[8])
    NMAX_LIST = [int(x) for x in sys.argv[9].split(",")]
    long_prompt = open(PROMPT_FILE).read().strip()
    for nmax in NMAX_LIST:
        lab = f"{TAG} long nmax={nmax} ncmoe={NCMOE} ctx={CTX}"
        if not run_container(MODEL, 1, CTX, NCMOE, nmax):
            refuse(lab)
            continue
        post(long_prompt, 1, [None], 0)  # warm slot
        for run in range(3):
            out = [None]
            post(long_prompt, NPRED, out, 0)
            r = out[0]
            da, dn = accept_agg([r])
            acc = f"{da}/{dn}={da/dn:.3f}" if dn else "n/a"
            print(f"{H}\t{lab}\trun{run+1}\tgen_tok_s={r[4]:.1f}\tprefill_ms={r[5]:.0f}"
                  f"\taccept={acc}\tgen={r[0]}", flush=True)
        sh("docker rm -f mtps2")
        time.sleep(2)
else:
    print("unknown mode", flush=True)
