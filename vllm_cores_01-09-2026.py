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

# cores-2026-09-01 vLLM co-residency driver.
# args: pairtag  util  maxlen  seqs  kvdtype  levels  tag=model [tag=model ...]
#
#   python3 vllm_cores_01-09-2026.py s2-q15q3 0.45 2048 128 fp8 8,32 \
#       s2-q15=Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ \
#       s2-q3=Qwen/Qwen2.5-Coder-3B-Instruct-AWQ
#
# WHY A SEPARATE DRIVER. vllm_sweep_31-08-2026.py runs one container at a time
# (`docker rm -f vsweep` between cells), so it cannot answer what a neighbour
# costs an incumbent. The harness has `coresident_with` and could, but it still
# sends the 11-token prompt this whole line of work exists to replace.
#
# WHAT IT MEASURES. Every model is loaded ONCE and stays resident. Then at each
# level, three measurements against the same loaded pair:
#
#   solo   -- ramp A while B is resident and IDLE      (memory pressure only)
#   solo   -- ramp B while A is resident and IDLE
#   paired -- ramp A and B CONCURRENTLY                (memory + compute)
#
# The plan asked for "solo at the same n, then beside its neighbour". Splitting
# it three ways costs no extra model load and separates the two costs, which a
# straight solo-vs-paired delta conflates: a neighbour that is merely resident
# has already taken VRAM from your KV pool before it serves one token.
#
# UTIL IS A SHARE, PLUS ~980 MiB THE SHARE DOES NOT COVER. Measured on srv2
# 2026-09-01 against a card verified empty between every launch:
#
#     util 0.25 -> 3,925 MiB,  98,032 KV tokens
#     util 0.45 -> 6,333 MiB, 272,272 KV tokens
#     util 0.90 -> 11,709 MiB, 664,320 KV tokens
#
# util x 11,911 gives 2,978 / 5,360 / 10,720 -- every one ~980 MiB under what
# the card actually reports. The budget covers weights + KV + activations; the
# CUDA context is outside it. So co-resident utils must sum to
# 1 - (n_servers x 980 / total), which is ~0.83 for a pair and ~0.75 for three,
# NOT 0.9.
#
# vLLM also refuses at startup if free memory is below util x total -- a
# precondition, not a subtraction:
#
#     ValueError: Free memory on device cuda:0 (1.12/11.63 GiB) on startup is
#     less than desired GPU memory utilization (0.9, 10.47 GiB).
#
# So LAUNCH LARGEST-UTIL FIRST: each server must clear its own precondition
# against what its predecessors already took.
#
# Because the pool is util-sized, a solo run at 0.45 is NOT comparable to the
# 0.9 ladders in 2026-09-01-prompt-realism -- which is why the solo halves are
# re-measured here at the co-resident util rather than read off that run.
#
# IDENTICAL WORK, EVERY TIME. The request counter is reset before each batch is
# built and the same (prompt, want) list is handed to both servers, so a delta
# between any two rows is contention and never a different prompt draw. That is
# the confound `reading-results.md` records for cross-run throughput.
PAIR, UTIL, MAXLEN, SEQS, KV = sys.argv[1:6]
LEVELS = [int(x) for x in sys.argv[6].split(",")]
# tag=model, or tag=model=util to override the shared util for one server.
# "small beside large" is the interesting pair and a symmetric split cannot
# express it: q15 needs ~1.4 GiB of weights and q7 needs ~5.3, so an even
# half-card each starves the large one while wasting the small one's share.
SPECS = [s.split("=") for s in sys.argv[7:]]
IMG = os.environ.get("VLLM_IMG", "vllm/vllm-openai:v0.26.0")
H = socket.gethostname()
BASE_PORT = 8100

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


def teardown(names):
    """Remove the containers AND wait for the card to actually release.

    `docker rm -f` returns before the CUDA context is torn down, and vLLM
    profiles LIVE FREE MEMORY during init -- so a neighbour still releasing
    makes the next launch abort outright:

        AssertionError: Error in memory profiling. Initial free memory 8.43
        GiB, current free memory 8.82 GiB.

    Measured 2026-09-01: the abort path used to skip this wait, and the next
    configuration in the same script refused for that reason alone.
    """
    for n in names:
        sh(f"docker rm -f {n}")
    for _ in range(30):
        if not sh("nvidia-smi --query-compute-apps=pid --format=csv,noheader"):
            return
        time.sleep(2)


def batch(n):
    """The same n (prompt, want) pairs for every server, every phase.

    Rebinding UID resets the sequence; `mkprompt` reads it as a global, so the
    hashed workload block above is untouched and its digest still matches
    vllm_sweep_31-08-2026.py.
    """
    global UID
    UID = itertools.count()
    return [mkprompt() for _ in range(n)]


def post(port, model, item, out, idx):
    prompt, want = item
    b = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt[len(SYSTEM) :]},
            ],
            "max_tokens": want,
            "temperature": 0,
        }
    ).encode()
    r = urllib.request.Request(
        f"http://localhost:{port}/v1/chat/completions",
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


def row(phase, tag, n, out, wall):
    gen = sum(o[0] for o in out)
    if gen == 0:
        print(f"{H}\t{PAIR}\t{tag}\t{phase}\tn={n}\tERR", flush=True)
        return
    pin = sum(o[2] for o in out)
    lat = sorted(o[1] for o in out)
    print(
        f"{H}\t{PAIR}\t{tag}\t{phase}\tn={n}\tagg={gen / wall:.1f}"
        f"\tp50={lat[len(lat) // 2]:.2f}\tprefill={pin / wall:.1f}"
        f"\tptok={pin // n}\totok={gen // n}"
        f"\tearly_stop={sum(1 for o in out if 0 < o[0] < o[3])}/{n}"
        f"\tfailed={sum(1 for o in out if o[0] == 0)}/{n}\twall={wall:.1f}",
        flush=True,
    )


def ramp(srv, items, out):
    th = [
        threading.Thread(target=post, args=(srv["port"], srv["model"], it, out, i))
        for i, it in enumerate(items)
    ]
    for t in th:
        t.start()
    for t in th:
        t.join()


# ---- launch every server, and keep them all resident for the whole run -------
if int(MAXLEN) < MAXLEN_NEED:
    print(f"{H}\t{PAIR}\tSKIP\tmax-model-len {MAXLEN} < {MAXLEN_NEED}", flush=True)
    sys.exit(0)

servers = []
for i, spec in enumerate(SPECS):
    tag, model = spec[0], spec[1]
    util = spec[2] if len(spec) > 2 else UTIL
    name, port = f"vcore{i}", BASE_PORT + i
    sh(f"docker rm -f {name}")
    kvflag = f"--kv-cache-dtype {KV}" if KV != "auto" else ""
    sh(
        f"docker run -d --name {name} --runtime=nvidia --gpus all "
        f"-v $HOME/.cache/huggingface:/root/.cache/huggingface "
        f"-v $HOME/models:/models:ro -p {port}:8000 --ipc=host {IMG} {model} "
        f"--port 8000 --gpu-memory-utilization {util} --max-model-len {MAXLEN} "
        f"--max-num-seqs {SEQS} {kvflag}"
    )
    servers.append(
        {"tag": tag, "model": model, "name": name, "port": port, "util": util}
    )

alive = []
for s in servers:
    ok = False
    probe = f"curl -sf -m 3 http://localhost:{s['port']}/health >/dev/null && echo Y"
    for _ in range(450):
        if sh(probe) == "Y":
            ok = True
            break
        if s["name"] not in sh("docker ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    if not ok:
        # vLLM's last error line is `Engine core initialization failed. See
        # root cause above` -- the wrapper, not the cause. Ask for the cause
        # first and fall back to the general tail only if there is none.
        why = sh(
            f"docker logs {s['name']} 2>&1 | grep -oE "
            "'(ValueError|RuntimeError|OutOfMemoryError|AssertionError): .*' | "
            "grep -viE 'Engine core init|Cannot send a request' | tail -1"
        )
        if not why:
            why = sh(
                f"docker logs {s['name']} 2>&1 | "
                "grep -vE '(INFO|DEBUG|WARNING) [0-9]{2}-[0-9]{2} ' | "
                "grep -iE 'error|traceback|out of memory|no such file|capability' "
                "| tail -2"
            )
        if not why:
            why = sh(f"docker logs {s['name']} 2>&1 | tail -3")
        print(
            f"{H}\t{PAIR}\t{s['tag']}\tREFUSED\t{' | '.join(why.splitlines())[:400]}",
            flush=True,
        )
        continue
    alive.append(s)

# A pair with a dead half is not a co-residency measurement. Say so and stop,
# rather than reporting the survivor's solo numbers under a pair label.
if len(alive) < len(servers):
    print(
        f"{H}\t{PAIR}\tABORT\t{len(alive)}/{len(servers)} servers came up; "
        f"a co-residency row needs every member resident",
        flush=True,
    )
    teardown([x["name"] for x in servers])
    sys.exit(1)

vram = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
for s in alive:
    kvlog = sh(
        f"docker logs {s['name']} 2>&1 | grep -oE "
        "'(GPU KV cache size: [0-9,]+ tokens|"
        "Maximum concurrency for [0-9,]+ tokens per request: [0-9.]+x)' | tail -2"
    )
    kvtok = re.search(r"GPU KV cache size: ([\d,]+) tokens", kvlog)
    conc = re.search(r"per request: ([\d.]+)x", kvlog)
    s["kvtok"] = int(kvtok.group(1).replace(",", "")) if kvtok else None
    s["conc"] = (
        float(conc.group(1))
        if conc
        else (s["kvtok"] / int(MAXLEN) if s["kvtok"] else None)
    )
    w = [None]
    post(s["port"], s["model"], batch(1)[0], w, 0)
    if w[0][0] <= 1:
        print(
            f"{H}\t{PAIR}\t{s['tag']}\tDEGENERATE\twarmup otok={w[0][0]}",
            flush=True,
        )
        teardown([x["name"] for x in servers])
        sys.exit(1)
    print(
        f"{H}\t{PAIR}\t{s['tag']}\tCONFIG\timg={IMG}\tport={s['port']}"
        f"\tutil={s['util']}\tkv={KV}\tkv_tok={s['kvtok']}"
        f"\tmaxconc={s['conc'] if s['conc'] is None else round(s['conc'], 1)}"
        f"\twarm_ptok={w[0][2]}\tpair_vram={vram}",
        flush=True,
    )

for n in LEVELS:
    over = [s["tag"] for s in alive if s["conc"] is not None and n > s["conc"]]
    if over:
        print(
            f"{H}\t{PAIR}\tWIDTH\tdropped n={n}: pool too small on "
            f"{','.join(over)} at len={MAXLEN}, so it would queue, not saturate",
            flush=True,
        )
        continue

    # Phase 1: each server alone, its neighbour resident but idle.
    for s in alive:
        items, out = batch(n), [None] * n
        t0 = time.time()
        ramp(s, items, out)
        row("solo", s["tag"], n, out, time.time() - t0)

    # Phase 2: every server at once, same work as its own solo row.
    items = batch(n)
    outs = {s["tag"]: [None] * n for s in alive}
    th = [threading.Thread(target=ramp, args=(s, items, outs[s["tag"]])) for s in alive]
    t0 = time.time()
    for t in th:
        t.start()
    for t in th:
        t.join()
    wall = time.time() - t0
    for s in alive:
        row("paired", s["tag"], n, outs[s["tag"]], wall)

teardown([s["name"] for s in servers])
