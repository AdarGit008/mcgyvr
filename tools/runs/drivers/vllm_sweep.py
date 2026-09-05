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

# sweep-2026-08-31 vLLM driver.  Supersedes vllmsweep28.py.
# args: tag model_ref cells...   cell = util:maxlen:seqs:kvdtype:levels[:extra]
# model_ref may be a HF repo id (HF cache) or /models/... (mounts ~/models).
#
# `extra` is optional and is appended VERBATIM to the engine's argv, with `+`
# read as a space so a cell stays one shell word:
#
#     0.90:2048:8:auto:1,2,4,8:--cpu-offload-gb+6+--cpu-offload-params+experts
#
# It exists because a model larger than the card is a real workload on these
# rigs and the cell had no way to say so. Measured 2026-08-31 on srv1: with
# `--cpu-offload-params experts` the engine printed `Total CPU offloaded
# parameters: 6.01` and host Shmem rose to 8.8 GB -- but ONLY under the V1
# model runner. The V2 runner accepts the flag, hashes it into the compile
# cache key, and ignores it, then dies allocating expert weights on a card
# that cannot hold them. So any cell whose `extra` asks for offload also gets
# VLLM_USE_V2_MODEL_RUNNER=0, here, rather than in every caller.
#
# ---------------------------------------------------------------------------
# The workload -- deciles, SYSTEM, mkprompt -- is `tools/runs/workload.py`,
# imported and never copied. Its docstring carries the derivation from
# measurements/**/results.jsonl and the shared-prefix argument.
# ---------------------------------------------------------------------------

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
RUN_ID = os.environ.get("RUN_ID", "")
if not RUN_ID:
    print(
        "vllm_sweep: RUN_ID is unset — this driver is started by the door, "
        "python -m mcgyvr.serving.run, never bare; a bare run prints unstamped "
        "rows nothing can file",
        file=sys.stderr,
    )
    sys.exit(2)
IMG = os.environ.get("VLLM_IMG", "")
if not ("@sha256:" in IMG or IMG.startswith("sha256:")):
    print(
        f"vllm_sweep: VLLM_IMG={IMG!r} is not an image digest (repo@sha256:<hex> "
        "or sha256:<hex>). A tag is resolved ONCE, by image_digest in "
        "tools/runs/_common.sh (gate 3), and the digest is what this driver "
        "runs; it will not resolve one itself and it will not run a pointer",
        file=sys.stderr,
    )
    sys.exit(2)
# The daemon is the `docker` the door put first on PATH, which lands on --host;
# there is no variable that names a substitute.
# The container carries the run's name so gate 7 (07-teardown.py) can find what
# this process left behind (`docker ps --filter name=^<RUN_ID>-`).
NAME = f"{RUN_ID}-vsweep"
TAG, MODEL = sys.argv[1], sys.argv[2]
CELLS = sys.argv[3:]
PORT = 8095
# The rig, exported by the door (gate 5). The container runs THERE, so the host
# column, the health poll and the card reading all name it; the machine this
# process runs on is nobody's row.
H = os.environ.get("RUN_HOST", "")
if not H:
    print(
        "vllm_sweep: RUN_HOST is unset — the door exports the rig a run serves on "
        "(gate 5); without it there is no host to poll and no host column",
        file=sys.stderr,
    )
    sys.exit(2)


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def post(out, idx):
    prompt, want = workload.mkprompt()
    # CHAT, not raw completion. The raw endpoint applies no chat template, and
    # on 2026-09-01 that cost 20 of 60 measured rows: Qwen3.6-35B emitted a stop
    # token on the first step of an untemplated prompt, so every one of its
    # cells reported otok=1 with `failed=0/n` beside it. The split is by prefix,
    # not by changing mkprompt -- SYSTEM stays the shared cacheable head and the
    # workload digest is unmoved.
    b = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": workload.SYSTEM},
                {"role": "user", "content": prompt[len(workload.SYSTEM) :]},
            ],
            "max_tokens": want,
            "temperature": 0,
        }
    ).encode()
    r = urllib.request.Request(
        f"http://{H}:{PORT}/v1/chat/completions",
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
    util, maxlen, seqs, kv, lv, *rest = cell.split(":")
    levels = [int(x) for x in lv.split(",")]
    extra = rest[0].replace("+", " ") if rest else ""
    # The runner rule, applied here so no caller has to remember it. Offload is
    # a V1-runner feature; under V2 the flag is accepted and silently dropped.
    env = "-e VLLM_USE_V2_MODEL_RUNNER=0 " if "--cpu-offload" in extra else ""
    sh(f"docker rm -f {NAME}")
    kvflag = f"--kv-cache-dtype {kv}" if kv != "auto" else ""
    cmd = (
        f"docker run -d --name {NAME} --runtime=nvidia --gpus all "
        f"-v $HOME/.cache/huggingface:/root/.cache/huggingface "
        f"-v $HOME/models:/models:ro "
        f"-v $HOME/ggufs:/ggufs:ro "
        f"-p {PORT}:8000 --ipc=host {env}{IMG} {MODEL} --port 8000 "
        f"--gpu-memory-utilization {util} --max-model-len {maxlen} "
        f"--max-num-seqs {seqs} {kvflag} {extra}"
    )
    lab = f"{TAG} util={util} len={maxlen} seqs={seqs} kv={kv}"
    if extra:
        lab += f" extra={extra.replace(' ', '+')}"
    # Launch AFTER the SKIP gate below, not before: the old order started a
    # container, printed SKIP, and killed it -- paying a model load to say no.
    if int(maxlen) < workload.MAXLEN_NEED:
        print(
            f"{H}\t{lab}\tSKIP\tmax-model-len {maxlen} < {workload.MAXLEN_NEED} "
            f"(worst sampled prompt+reply); raise it or the tail truncates",
            flush=True,
        )
        continue
    sh(cmd)
    probe = f"curl -sf -m 3 http://{H}:{PORT}/health >/dev/null && echo Y"
    ok = False
    for _ in range(450):
        if sh(probe) == "Y":
            ok = True
            break
        if NAME not in sh("docker ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    if not ok:
        # Take the last ERROR, not the last matching line. The old pattern
        # matched bare `memory` and `architect`, which vLLM's `non-default args`
        # INFO banner contains (gpu_memory_utilization, Resolved architecture),
        # so on 2026-09-01 a refusal was recorded with a startup banner as its
        # reason. Drop the levelled INFO/DEBUG/WARNING lines first, and fall
        # back to the raw tail so the field is never blank.
        why = sh(
            f"docker logs {NAME} 2>&1 | "
            "grep -vE '(INFO|DEBUG|WARNING) [0-9]{2}-[0-9]{2} ' | "
            "grep -iE 'error|traceback|not supported|out of memory|"
            "no such file|capability|assert' | tail -2"
        )
        if not why:
            why = sh(f"docker logs {NAME} 2>&1 | tail -3")
        why = " | ".join(why.splitlines())[:400]
        print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
        sh(f"docker rm -f {NAME}")
        continue
    vram = sh(
        f"ssh {H} nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
    )
    warm = [None]
    post(warm, 0)
    if warm[0][0] == 0:
        print(f"{H}\t{lab}\tREFUSED\twarmup request failed", flush=True)
        sh(f"docker rm -f {NAME}")
        continue
    # A cell that stops on the first token measures nothing, and the old code
    # let it through: it only refused otok==0, so an immediate stop produced a
    # full ladder of agg=0.1-0.6 rows that read as a throughput collapse. Refuse
    # the cell here, once, with the warmup's own numbers in the reason.
    if warm[0][0] <= 1:
        print(
            f"{H}\t{lab}\tDEGENERATE\tmodel stopped at otok={warm[0][0]} "
            f"against a {warm[0][3]}-token budget (ptok={warm[0][2]}); "
            f"measuring this cell would record artifacts",
            flush=True,
        )
        sh(f"docker rm -f {NAME}")
        continue
    # **Asserted, not assumed.** `nvidia-smi memory.used` cannot see an
    # offload -- gpu_memory_utilization backfills the freed weight space with
    # KV cache, so the card reads the same either way. The engine's own line is
    # the only honest signal, and a cell that asked for offload and did not get
    # it is measuring a different experiment than its label claims.
    offl = ""
    if "--cpu-offload" in extra:
        offl = sh(
            f"docker logs {NAME} 2>&1 | "
            "grep -oE 'Total CPU offloaded parameters:.*' | head -1"
        )
        if not offl:
            print(
                f"{H}\t{lab}\tREFUSED\tasked for offload and the engine "
                f"printed no `Total CPU offloaded parameters` line",
                flush=True,
            )
            sh(f"docker rm -f {NAME}")
            continue
    # WIDTH READBACK. `--max-num-seqs` is a scheduler cap, not an allocation:
    # under `--gpu-memory-utilization` the KV pool is sized from whatever VRAM
    # is left after weights, so a cell can declare 128 and hold 12. Requests
    # past that queue, and a queue produces a flat aggregate with climbing
    # latency -- indistinguishable from saturation, which is the exact false
    # result 62f0ab65 closed on the harness path. vLLM has no /props, but it
    # states the pool it allocated, so read that instead of trusting the flag.
    kvlog = sh(
        f"docker logs {NAME} 2>&1 | grep -oE "
        "'(GPU KV cache size: [0-9,]+ tokens|"
        "Maximum concurrency for [0-9,]+ tokens per request: [0-9.]+x)' | tail -2"
    )
    kvtok = re.search(r"GPU KV cache size: ([\d,]+) tokens", kvlog)
    conc = re.search(r"per request: ([\d.]+)x", kvlog)
    kvtok = int(kvtok.group(1).replace(",", "")) if kvtok else None
    # Prefer the engine's own concurrency line; fall back to the pool arithmetic.
    maxconc = float(conc.group(1)) if conc else (kvtok / int(maxlen) if kvtok else None)
    dropped = []
    if maxconc is not None:
        # Drop only the rungs the pool cannot hold, and say so. Refusing the
        # whole cell would throw away the rungs that are honest; measuring the
        # tail anyway would record a queue as a plateau.
        keep = [n for n in levels if n <= maxconc]
        dropped = [n for n in levels if n > maxconc]
        if dropped:
            print(
                f"{H}\t{lab}\tWIDTH\tdropped n={','.join(str(n) for n in dropped)}: "
                f"pool holds {kvtok} tokens = {maxconc:.1f} concurrent requests at "
                f"len={maxlen}, so those rungs would queue, not saturate",
                flush=True,
            )
        levels = keep
    print(
        f"{H}\t{lab}\tCONFIG\timg={IMG}\tvram={vram}"
        f"\tkv_tok={kvtok}\tmaxconc={maxconc if maxconc is None else round(maxconc, 1)}"
        f"\twarm_ptok={warm[0][2]}\t{offl or 'offload=none'}",
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
    sh(f"docker rm -f {NAME}")
    time.sleep(2)
