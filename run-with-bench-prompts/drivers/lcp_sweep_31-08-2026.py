import itertools
import json
import os
import random
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

# sweep-2026-08-31 llama.cpp driver.  Supersedes lcpsweep28.py.
# args: model_path mount_dir tag cells...   cell = np:ctx_slot:ncpumoe:levels
# -c is computed as np * ctx_slot, because llama.cpp DIVIDES -c across slots.
#
# Workload block is IDENTICAL to vllm_sweep_31-08-2026.py -- same deciles, same
# SYSTEM text, same seeding -- so the two engines are compared on one workload.
# See that file's header for the derivation from measurements/**/results.jsonl.
#
# TWO DELIBERATE CHANGES FROM lcpsweep28.py:
#  1. cache_prompt: False -> True.  The old driver disabled prompt reuse while
#     the vLLM driver left automatic prefix caching ON -- the engines were not
#     measured under the same caching rules. Production wants the shared
#     scaffold cached, so both sides now cache.
#  2. ignore_eos is GONE. Output length is the sampled n_predict and the model
#     may stop earlier, exactly as in production.
PROMPT_DECILES = [588, 608, 624, 653, 688, 719, 746, 799, 887]  # p10..p90
COMPL_DECILES = [78, 101, 130, 158, 189, 230, 281, 346, 460]  # p10..p90
SYS_TOK = 190  # measured scaffold size; the shared, cacheable prefix
TOK_PER_FIELD = 32  # calibration knob: tune until reported ptok= ~= 688
HDR_TOK = 60  # approx tokens in the task-body header lines
MAXLEN_NEED = 887 + 460  # worst sampled prompt + worst sampled reply

MODEL, MDIR, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
CELLS = sys.argv[4:]
# Pinned to the build the 2026-08-28 setup-selection sweep ran (run-srv1.sh /
# run-srv2.sh). lcpsweep28.py used the floating :server-cuda tag, so two runs a
# month apart could not be compared. Override with LCP_IMG=..., never by edit.
IMG = os.environ.get("LCP_IMG", "ghcr.io/ggml-org/llama.cpp:server-cuda-b10644")
PORT, H = 8094, socket.gethostname()

UID = itertools.count()
UIDLOCK = threading.Lock()

SYSTEM = (
    "You are a worker in an automated coding ladder. You receive one scoped\n"
    "task contract at a time and return exactly one artifact: the requested\n"
    "code, in a single fenced block, with no prose and no restatement of the\n"
    "contract. Follow the contract literally. Do not invent requirements it\n"
    "does not state, and do not omit any it does. Use type hints on every\n"
    "parameter and return. Include a docstring naming the arguments and the\n"
    "error conditions. Handle every error path the contract enumerates,\n"
    "raising the exact exception type named. Your output is checked by an\n"
    "automated gate that runs the contract's tests verbatim; prose outside\n"
    "the fenced block fails the gate.\n\n"
)


def mkprompt():
    """SYSTEM (shared, cacheable) + a unique body sized from the real deciles."""
    with UIDLOCK:
        i = next(UID)
    rnd = random.Random(i)
    want_prompt = rnd.choice(PROMPT_DECILES)
    want_out = rnd.choice(COMPL_DECILES)
    nfield = max(1, (want_prompt - SYS_TOK - HDR_TOK) // TOK_PER_FIELD)
    fields = "\n".join(
        f"  - arg_{k:02d}: bounded by {(i * 31 + k) % 10000:04d}; on violation "
        f"raise ValueError(f'arg_{k:02d} out of range') and log the input."
        for k in range(nfield)
    )
    body = (
        f"CONTRACT option_pairs_{i % 100000:05d} / req {(i * 7919) % (16**8):08x}\n"
        f"Signature: def option_pairs(rows: list[dict], strict: bool = False) -> dict\n"
        f"Fields:\n{fields}\n\n"
        f"Implement it now.\n"
    )
    return SYSTEM + body, want_out


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def post(out, idx):
    prompt, want = mkprompt()
    b = json.dumps(
        {"prompt": prompt, "n_predict": want, "temperature": 0, "cache_prompt": True}
    ).encode()
    r = urllib.request.Request(
        f"http://localhost:{PORT}/completion",
        data=b,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=3600) as f:
            d = json.load(f)
        tm = d.get("timings", {})
        out[idx] = (
            tm.get("predicted_n", 0),
            time.time() - t0,
            tm.get("prompt_n", d.get("tokens_evaluated", 0)),
            want,
        )
    except Exception:
        out[idx] = (0, time.time() - t0, 0, want)


for cell in CELLS:
    np_, ctxslot, ncm, lv = cell.split(":")
    levels = [int(x) for x in lv.split(",")]
    total_c = int(np_) * int(ctxslot)
    lab = f"{TAG} np={np_} ctx_slot={ctxslot} c={total_c} ncmoe={ncm}"
    if int(ctxslot) < MAXLEN_NEED:
        print(
            f"{H}\t{lab}\tSKIP\tctx_slot {ctxslot} < {MAXLEN_NEED} "
            f"(worst sampled prompt+reply); raise it or the tail truncates",
            flush=True,
        )
        continue
    sh("docker rm -f lcps")
    extra = f"--n-cpu-moe {ncm}" if ncm != "0" else ""
    sh(
        f"docker run -d --name lcps --gpus all -v {MDIR}:/models:ro "
        f"-p {PORT}:8080 {IMG} "
        f"-m /models/{MODEL.split('/')[-1]} -ngl 99 -np {np_} -c {total_c} {extra} "
        f"-fa on --no-warmup --host 0.0.0.0 --port 8080"
    )
    probe = f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y"
    ok = False
    for _ in range(400):
        if sh(probe) == "Y":
            ok = True
            break
        if "lcps" not in sh("docker ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    if not ok:
        why = sh("docker logs lcps 2>&1 | grep -iE 'error|out of memory' | tail -1")[
            :110
        ]
        print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
        sh("docker rm -f lcps")
        continue
    log = sh("docker logs lcps 2>&1")
    real_slot = re.search(r"n_ctx_slot = (\d+)", log)
    vram = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    warm = [None]
    post(warm, 0)
    if warm[0][0] == 0:
        print(f"{H}\t{lab}\tREFUSED\twarmup request failed", flush=True)
        sh("docker rm -f lcps")
        continue
    print(
        f"{H}\t{lab}\tCONFIG\timg={IMG}"
        f"\treal_ctx_slot={real_slot.group(1) if real_slot else '?'}"
        f"\tvram={vram}\twarm_ptok={warm[0][2]}",
        flush=True,
    )
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
        pin = sum(o[2] for o in out)
        short = sum(1 for o in out if 0 < o[0] < o[3])
        fail = sum(1 for o in out if o[0] == 0)
        lat = sorted(o[1] for o in out)
        print(
            f"{H}\t{lab}\tn={n}\tagg={gen / wall:.1f}\tp50={lat[len(lat) // 2]:.2f}"
            f"\tprefill={pin / wall:.1f}\tptok={pin // n}\totok={gen // n}"
            f"\tearly_stop={short}/{n}\tfailed={fail}/{n}"
            f"\twall={wall:.1f}",
            flush=True,
        )
    sh("docker rm -f lcps")
    time.sleep(2)
