import itertools
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.runs import workload

# cores-2026-09-01 vLLM co-residency driver.
# args: pairtag  util  maxlen  seqs  kvdtype  levels  tag=model [tag=model ...]
#
#   python tools/runs/drivers/vllm_cores.py s2-q15q3 0.45 2048 128 fp8 8,32 \
#       s2-q15=Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ \
#       s2-q3=Qwen/Qwen2.5-Coder-3B-Instruct-AWQ
#
# WHY A SEPARATE DRIVER. vllm_sweep.py runs one container at a time
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

# THE DOOR'S TWO REFUSALS, before argv is read and before docker is touched.
# A bare run of this file printed byte-compatible rows with no stamps — no rig
# state, no round, no workload digest — and nothing downstream could tell them
# from a run that passed every gate (BRIEF "The problem being solved"). So:
# (1) RUN_ID is minted by the door, python -m mcgyvr.serving.run (gate 5), and
# only there; without it this process was not started by the door and exits 2
# having done nothing.
# (2) VLLM_IMG must be a DIGEST (`repo@sha256:<hex>` or `sha256:<hex>`),
# resolved once by `image_digest` in tools/runs/_common.sh (gate 3). A tag is
# a pointer: the same `img=` on two rows can name two images a week apart,
# which is the floating `:server-cuda` mistake the pin only half ended. There
# is no default image — a default is a tag by another name.
# THE DOOR'S PROOF, before either refusal below. Both variables they read can
# be typed into a shell, and a driver that took them on faith reached a real
# `ssh srv1` by hand with no shim on PATH to stop it. gatelib.door_required
# reads the parent chain from /proc, which nothing can set; a gatelib that
# will not import is a refusal too, not a pass.
try:
    from mcgyvr.serving import gatelib
except ImportError:
    print(
        "vllm_cores: mcgyvr.serving.gatelib will not import, so the door cannot be "
        "proved and nothing is started — this driver runs under the door, "
        "python -m mcgyvr.serving.run, on the interpreter that has mcgyvr",
        file=sys.stderr,
    )
    sys.exit(2)
gatelib.door_required("vllm_cores")
RUN_ID = os.environ.get("RUN_ID", "")
if not RUN_ID:
    print(
        "vllm_cores: RUN_ID is unset — this driver is started by the door, "
        "python -m mcgyvr.serving.run, never bare; a bare run prints unstamped "
        "rows nothing can file",
        file=sys.stderr,
    )
    sys.exit(2)
IMG = os.environ.get("VLLM_IMG", "")
if not ("@sha256:" in IMG or IMG.startswith("sha256:")):
    print(
        f"vllm_cores: VLLM_IMG={IMG!r} is not an image digest (repo@sha256:<hex> "
        "or sha256:<hex>). A tag is resolved ONCE, by image_digest in "
        "tools/runs/_common.sh (gate 3), and the digest is what this driver "
        "runs; it will not resolve one itself and it will not run a pointer",
        file=sys.stderr,
    )
    sys.exit(2)
# The daemon is the `docker` the door put first on PATH, which lands on --host;
# there is no variable that names a substitute.
PAIR, UTIL, MAXLEN, SEQS, KV = sys.argv[1:6]
LEVELS = [int(x) for x in sys.argv[6].split(",")]
# tag=model, or tag=model=util to override the shared util for one server.
# "small beside large" is the interesting pair and a symmetric split cannot
# express it: q15 needs ~1.4 GiB of weights and q7 needs ~5.3, so an even
# half-card each starves the large one while wasting the small one's share.
SPECS = [s.split("=") for s in sys.argv[7:]]
# The rig, exported by the door (gate 5). The container runs THERE, so the host
# column, the health poll and the card reading all name it; the machine this
# process runs on is nobody's row.
H = os.environ.get("RUN_HOST", "")
if not H:
    print(
        "vllm_cores: RUN_HOST is unset — the door exports the rig a run serves on "
        "(gate 5); without it there is no host to poll and no host column",
        file=sys.stderr,
    )
    sys.exit(2)
BASE_PORT = 8100
# Attempts per server before a refusal is believed. See the RETRY note below.
LAUNCH_TRIES = 3


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def rig(c):
    """A command on the rig, through the one ssh in the product: gatelib.ssh
    refuses outside the door and to any host but the door's."""
    return gatelib.ssh(H, c).stdout.strip()


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
        if not rig("nvidia-smi --query-compute-apps=pid --format=csv,noheader"):
            return
        time.sleep(2)


def batch(n):
    """The same n (prompt, want) pairs for every server, every phase.

    Rebinding `workload.UID` resets the sequence; `mkprompt` reads it as a
    global of its own module, so the hashed workload module is untouched and
    its digest still matches what vllm_sweep.py draws.
    """
    workload.UID = itertools.count()
    return [workload.mkprompt() for _ in range(n)]


def post(port, model, item, out, idx):
    prompt, want = item
    b = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": workload.SYSTEM},
                {"role": "user", "content": prompt[len(workload.SYSTEM) :]},
            ],
            "max_tokens": want,
            "temperature": 0,
        }
    ).encode()
    r = urllib.request.Request(
        f"http://{H}:{port}/v1/chat/completions",
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
if int(MAXLEN) < workload.MAXLEN_NEED:
    print(
        f"{H}\t{PAIR}\tSKIP\tmax-model-len {MAXLEN} < {workload.MAXLEN_NEED}",
        flush=True,
    )
    sys.exit(0)

# ONE AT A TIME, EACH FULLY UP BEFORE THE NEXT STARTS. vLLM profiles LIVE free
# memory during init, so two servers starting together race: each sees memory
# the other is mid-way through taking, and one of them dies on a util that
# works perfectly when it launches alone. Measured 2026-09-01 on srv1 -- q15 at
# 0.40 came up solo with 24,560 KV tokens and REFUSED at the same 0.40 when
# launched alongside q3. This loop used to start every container and only then
# wait for health, which is that race by construction.
#
# ORDER IS THE CALLER'S, AND IT SHOULD BE SMALL-FIRST. util is a per-server
# share of the whole card -- a resident neighbour does NOT shrink it, proven by
# co-resident q3 at 0.55 getting 14,448 KV tokens, byte-identical to its solo
# run at 0.55. What a neighbour does is raise the floor under the free-memory
# precondition, capping how high a LATER server's util may be set. So give the
# small model its share first; large-first leaves the second server a budget
# smaller than the first already occupies, and it gets nothing.
servers, alive = [], []
for i, spec in enumerate(SPECS):
    tag, model = spec[0], spec[1]
    util = spec[2] if len(spec) > 2 else UTIL
    # The container carries the run's name so gate 7 (07-teardown.py) can find
    # what this process left behind (`docker ps --filter name=^<RUN_ID>-`).
    name, port = f"{RUN_ID}-vcore{i}", BASE_PORT + i
    sh(f"docker rm -f {name}")
    kvflag = f"--kv-cache-dtype {KV}" if KV != "auto" else ""
    sh(
        f"docker run -d --name {name} --runtime=nvidia --gpus all "
        f"-v $HOME/.cache/huggingface:/root/.cache/huggingface "
        f"-v $HOME/models:/models:ro -p {port}:8000 --ipc=host {IMG} {model} "
        f"--port 8000 --gpu-memory-utilization {util} --max-model-len {MAXLEN} "
        f"--max-num-seqs {SEQS} {kvflag}"
    )
    s = {"tag": tag, "model": model, "name": name, "port": port, "util": util}
    servers.append(s)

    # RETRY: a launch near the memory edge fails INTERMITTENTLY. Measured on
    # srv1 2026-09-01 -- the identical command on a verified-empty card, three
    # times: one died at memory profiling, two came up with byte-identical
    # 24,560 KV tokens. So a single refusal is a coin flip, not a capacity
    # limit, and reading one as the other cost most of a day: `q3 at 0.46 came
    # up` and `q15 at 0.40 refused` were both lucky draws, minutes apart, on
    # settings that had already worked.
    ok, attempts = False, 0
    probe = f"curl -sf -m 3 http://{H}:{s['port']}/health >/dev/null && echo Y"
    for attempts in range(1, LAUNCH_TRIES + 1):
        for _ in range(450):
            if sh(probe) == "Y":
                ok = True
                break
            if s["name"] not in sh("docker ps --format '{{.Names}}'"):
                break
            time.sleep(2)
        if ok or attempts == LAUNCH_TRIES:
            break
        sh(f"docker rm -f {s['name']}")
        for _ in range(30):
            if not rig("nvidia-smi --query-compute-apps=pid --format=csv,noheader"):
                break
            time.sleep(2)
        sh(
            f"docker run -d --name {name} --runtime=nvidia --gpus all "
            f"-v $HOME/.cache/huggingface:/root/.cache/huggingface "
            f"-v $HOME/models:/models:ro -p {port}:8000 --ipc=host {IMG} {model} "
            f"--port 8000 --gpu-memory-utilization {util} --max-model-len {MAXLEN} "
            f"--max-num-seqs {SEQS} {kvflag}"
        )
    s["attempts"] = attempts
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
            f"{H}\t{PAIR}\t{s['tag']}\tREFUSED\tafter {attempts} attempts: "
            f"{' | '.join(why.splitlines())[:360]}",
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

vram = rig("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
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
        f"\twarm_ptok={w[0][2]}\tpair_vram={vram}\ttries={s['attempts']}",
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
