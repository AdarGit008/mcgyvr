import itertools
import json
import os
import random
import socket
import subprocess
import sys
import threading
import time
import urllib.request

# sweep-2026-08-31 vLLM driver.  Supersedes vllmsweep28.py.
# args: tag model_ref cells...   cell = util:maxlen:seqs:kvdtype:levels
# model_ref may be a HF repo id (HF cache) or /models/... (mounts ~/models).
#
# ---------------------------------------------------------------------------
# Workload, derived from measurements/**/results.jsonl (n=21342 dedup'd rows):
#   prompt_tokens      mean 719, p50 688
#   completion_tokens  mean 236, p50 189
# Prior drivers sent ONE shared 11-token prompt and a flat 475-token reply
# (1:43 in:out). Real traffic is ~3:1 in:out. This driver reproduces the
# measured distribution instead of a single point.
#
# SHARED PREFIX: bench-scaffold-ablation-3b-2026-08-11 gives the scaffold size
# directly -- stock p50 929 vs noscaffold p50 739 (py), 936 vs 729 (ts)
# => ~190-207 tokens of system prompt IDENTICAL on every request.
# So each prompt is SYSTEM (constant, cacheable) + a unique task body.
# Prefix caching then gets the hits it gets in production: not zero
# (unique-at-head, too pessimistic), not total (one fixed prompt, the old bug).
#
# Lengths are sampled per request from the empirical deciles, seeded by request
# id, so request k always gets the same length -- reproducible across levels and
# across reruns without collapsing to a constant.
#
# NOTE: ignore_eos is GONE. Output length is the sampled max_tokens, and the
# model may stop earlier on its own, exactly as in production.
# ---------------------------------------------------------------------------
TAG, MODEL = sys.argv[1], sys.argv[2]
CELLS = sys.argv[3:]
# Pinned. Override deliberately with VLLM_IMG=..., never by editing this line.
IMG = os.environ.get("VLLM_IMG", "vllm/vllm-openai:v0.26.0")
PORT, H = 8095, socket.gethostname()

PROMPT_DECILES = [588, 608, 624, 653, 688, 719, 746, 799, 887]  # p10..p90
COMPL_DECILES = [78, 101, 130, 158, 189, 230, 281, 346, 460]  # p10..p90
SYS_TOK = 190  # measured scaffold size; the shared, cacheable prefix
TOK_PER_FIELD = 32  # calibration knob: tune until reported ptok= ~= 688
HDR_TOK = 60  # approx tokens in the task-body header lines
MAXLEN_NEED = 887 + 460  # worst sampled prompt + worst sampled reply

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
        {"model": MODEL, "prompt": prompt, "max_tokens": want, "temperature": 0}
    ).encode()
    r = urllib.request.Request(
        f"http://localhost:{PORT}/v1/completions",
        data=b,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=3600) as f:
            d = json.load(f)
        out[idx] = (
            d["usage"]["completion_tokens"],
            time.time() - t0,
            d["usage"]["prompt_tokens"],
            want,
        )
    except Exception:
        out[idx] = (0, time.time() - t0, 0, want)


for cell in CELLS:
    util, maxlen, seqs, kv, lv = cell.split(":")
    levels = [int(x) for x in lv.split(",")]
    sh("docker rm -f vsweep")
    kvflag = f"--kv-cache-dtype {kv}" if kv != "auto" else ""
    cmd = (
        f"docker run -d --name vsweep --runtime=nvidia --gpus all "
        f"-v $HOME/.cache/huggingface:/root/.cache/huggingface "
        f"-v $HOME/models:/models:ro "
        f"-v $HOME/ggufs:/ggufs:ro "
        f"-p {PORT}:8000 --ipc=host {IMG} {MODEL} --port 8000 "
        f"--gpu-memory-utilization {util} --max-model-len {maxlen} "
        f"--max-num-seqs {seqs} {kvflag}"
    )
    sh(cmd)
    lab = f"{TAG} util={util} len={maxlen} seqs={seqs} kv={kv}"
    if int(maxlen) < MAXLEN_NEED:
        print(
            f"{H}\t{lab}\tSKIP\tmax-model-len {maxlen} < {MAXLEN_NEED} "
            f"(worst sampled prompt+reply); raise it or the tail truncates",
            flush=True,
        )
        sh("docker rm -f vsweep")
        continue
    probe = f"curl -sf -m 3 http://localhost:{PORT}/health >/dev/null && echo Y"
    ok = False
    for _ in range(450):
        if sh(probe) == "Y":
            ok = True
            break
        if "vsweep" not in sh("docker ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    if not ok:
        why = sh(
            "docker logs vsweep 2>&1 | "
            "grep -iE 'error|not supported|memory|architect' | tail -2"
        )
        why = " | ".join(why.splitlines())[:400]
        print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
        sh("docker rm -f vsweep")
        continue
    vram = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    warm = [None]
    post(warm, 0)
    if warm[0][0] == 0:
        print(f"{H}\t{lab}\tREFUSED\twarmup request failed", flush=True)
        sh("docker rm -f vsweep")
        continue
    print(
        f"{H}\t{lab}\tCONFIG\timg={IMG}\tvram={vram}\twarm_ptok={warm[0][2]}",
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
    sh("docker rm -f vsweep")
    time.sleep(2)
