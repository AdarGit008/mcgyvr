import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.runs import workload

# sweep-2026-08-31 llama.cpp driver.  Supersedes lcpsweep28.py.
# args: model_path mount_dir tag cells...   cell = np:ctx_slot:ncpumoe:levels
# -c is computed as np * ctx_slot, because llama.cpp DIVIDES -c across slots.
#
# The workload is `tools/runs/workload.py`, imported and never copied -- same
# deciles, same SYSTEM text, same seeding as vllm_sweep.py -- so the two engines
# are compared on one workload. See that module's docstring for the derivation
# from measurements/**/results.jsonl.
#
# TWO DELIBERATE CHANGES FROM lcpsweep28.py:
#  1. cache_prompt: False -> True.  The old driver disabled prompt reuse while
#     the vLLM driver left automatic prefix caching ON -- the engines were not
#     measured under the same caching rules. Production wants the shared
#     scaffold cached, so both sides now cache.
#  2. ignore_eos is GONE. Output length is the sampled n_predict and the model
#     may stop earlier, exactly as in production.

# THE DOOR'S TWO REFUSALS, before argv is read and before docker is touched.
# A bare run of this file printed byte-compatible rows with no stamps — no rig
# state, no round, no workload digest — and nothing downstream could tell them
# from a run that passed every gate (BRIEF "The problem being solved"). So:
# (1) RUN_ID is minted by tools/runs/run.sh and only there; without it this
# process was not started by the door and exits 2 having done nothing.
# (2) LCP_IMG must be a DIGEST (`repo@sha256:<hex>` or `sha256:<hex>`),
# resolved once by `image_digest` in tools/runs/_common.sh (gate 3). A tag is
# a pointer: the same `img=` on two rows can name two images a week apart,
# which is the floating `:server-cuda` mistake the pin only half ended. There
# is no default image — a default is a tag by another name.
RUN_ID = os.environ.get("RUN_ID", "")
if not RUN_ID:
    print(
        "lcp_sweep: RUN_ID is unset — this driver is started by tools/runs/run.sh, "
        "never bare; a bare run prints unstamped rows nothing can file",
        file=sys.stderr,
    )
    sys.exit(2)
IMG = os.environ.get("LCP_IMG", "")
if not ("@sha256:" in IMG or IMG.startswith("sha256:")):
    print(
        f"lcp_sweep: LCP_IMG={IMG!r} is not an image digest (repo@sha256:<hex> "
        "or sha256:<hex>). A tag is resolved ONCE, by image_digest in "
        "tools/runs/_common.sh (gate 3), and the digest is what this driver "
        "runs; it will not resolve one itself and it will not run a pointer",
        file=sys.stderr,
    )
    sys.exit(2)
# The daemon, behind the one seam a test may replace it with (RUN_DOCKER).
DOCKER = os.environ.get("RUN_DOCKER", "docker")
# The container carries the run's name so gate 7 of run.sh can find what this
# process left behind (`docker ps --filter name=^<RUN_ID>-`).
NAME = f"{RUN_ID}-lcps"
MODEL, MDIR, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
CELLS = sys.argv[4:]
PORT, H = 8094, socket.gethostname()


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def post(out, idx):
    prompt, want = workload.mkprompt()
    # CHAT, not `/completion`. The raw endpoint applies no chat template, and on
    # 2026-09-01 that cost 20 of 60 measured rows: Qwen3.6-35B emitted a stop
    # token on the first step of an untemplated prompt, so every one of its
    # cells reported otok=1 with `failed=0/n` beside it. The split is by prefix,
    # not by changing mkprompt -- SYSTEM stays the shared cacheable head and the
    # workload digest is unmoved. `cache_prompt` is passed through by
    # llama-server's OAI handler, so both engines still cache the scaffold.
    b = json.dumps(
        {
            "messages": [
                {"role": "system", "content": workload.SYSTEM},
                {"role": "user", "content": prompt[len(workload.SYSTEM) :]},
            ],
            "max_tokens": want,
            "temperature": 0,
            "cache_prompt": True,
        }
    ).encode()
    r = urllib.request.Request(
        f"http://localhost:{PORT}/v1/chat/completions",
        data=b,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=3600) as f:
            d = json.load(f)
        # The OAI handler reports `usage`; `timings` is only present on some
        # builds. Read usage first and keep the timings path as the fallback so
        # a build that omits one still records the row.
        us = d.get("usage") or {}
        tm = d.get("timings") or {}
        out[idx] = (
            us.get("completion_tokens", tm.get("predicted_n", 0)),
            time.time() - t0,
            us.get("prompt_tokens", tm.get("prompt_n", d.get("tokens_evaluated", 0))),
            want,
        )
    except Exception:
        out[idx] = (0, time.time() - t0, 0, want)


for cell in CELLS:
    np_, ctxslot, ncm, lv = cell.split(":")
    levels = [int(x) for x in lv.split(",")]
    total_c = int(np_) * int(ctxslot)
    lab = f"{TAG} np={np_} ctx_slot={ctxslot} c={total_c} ncmoe={ncm}"
    if int(ctxslot) < workload.MAXLEN_NEED:
        print(
            f"{H}\t{lab}\tSKIP\tctx_slot {ctxslot} < {workload.MAXLEN_NEED} "
            f"(worst sampled prompt+reply); raise it or the tail truncates",
            flush=True,
        )
        continue
    sh(f"{DOCKER} rm -f {NAME}")
    extra = f"--n-cpu-moe {ncm}" if ncm != "0" else ""
    sh(
        f"{DOCKER} run -d --name {NAME} --gpus all -v {MDIR}:/models:ro "
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
        if NAME not in sh(DOCKER + " ps --format '{{.Names}}'"):
            break
        time.sleep(2)
    if not ok:
        # Drop llama.cpp's `I` (info) lines before matching, keep more of the
        # line than 110 chars, and fall back to the raw tail rather than
        # printing an empty reason. On 2026-09-01 two REFUSED rows were a
        # dangling HF-blob symlink -- a `no such file` the truncated reason did
        # not show -- and were read as a capability limit.
        why = sh(
            f"{DOCKER} logs {NAME} 2>&1 | grep -vE '^[0-9.]+ I ' | "
            "grep -iE 'error|out of memory|no such file|failed|cannot' | tail -2"
        )
        if not why:
            why = sh(f"{DOCKER} logs {NAME} 2>&1 | tail -3")
        why = " | ".join(why.splitlines())[:240]
        print(f"{H}\t{lab}\tREFUSED\t{why}", flush=True)
        sh(f"{DOCKER} rm -f {NAME}")
        continue
    log = sh(f"{DOCKER} logs {NAME} 2>&1")
    real_slot = re.search(r"n_ctx_slot = (\d+)", log)
    vram = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    warm = [None]
    post(warm, 0)
    if warm[0][0] == 0:
        print(f"{H}\t{lab}\tREFUSED\twarmup request failed", flush=True)
        sh(f"{DOCKER} rm -f {NAME}")
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
        sh(f"{DOCKER} rm -f {NAME}")
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
    sh(f"{DOCKER} rm -f {NAME}")
    time.sleep(2)
