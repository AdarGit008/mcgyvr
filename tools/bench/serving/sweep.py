#!/usr/bin/env python3
"""Maximum throughput per (rig, model, engine CONFIGURATION).

**Why this exists beside `calibrate.py` rather than inside it.** `calibrate`'s
serve dict is hardcoded (`calibrate.py:594-602`): `max_model_len 8192`,
`gpu_memory_utilization 0.85`, `flags: ["--enforce-eager"]`. That is deliberate
-- a campaign's columns have to stay reproducible, and a pinned config is what
makes them so. The consequence is that **the entire configuration axis is
invisible to that instrument.** An 11-hour campaign over two rigs never varied a
flag, and a flag worth 5.02x on srv2 sat inside the constant it holds fixed
(`records/evidence/2026-08-24-config-sweep/`).

So: two instruments, different jobs. `calibrate` measures WITHIN a configuration
and holds it still. This measures ACROSS configurations and varies exactly what
`calibrate` pins. Folding them together would put a hole in the pin that makes
`calibrate`'s record trustworthy.

**What one cell is.** Launch vLLM in the container with an arbitrary flag list;
wait for `/health` AND a card allocation, because /health answers before the
weights are on the card; scrape what the engine RESOLVED (`/server_info` plus the
startup lines naming the attention backend, the linear kernel, the sampler path
and the KV cache size); ramp concurrency; tear down. One JSON record per cell,
refusals included with the engine's own log beside them -- a config that will not
launch is a result, and on these rigs 36 of 140 cells were refusals.

**Why the resolved config and not the requested one.** Identical flags resolve
differently per card: srv1 gets `TRITON_ATTN` + torch sampler + `float16`, srv2
gets `FLASH_ATTN` + FlashInfer + `bfloat16`, from the same image digest and the
same arguments. `serving_build` cannot see it -- it reads `vllm 0.26.0` either
way. #358 is the issue that puts this into `identity.KEY`.

**Every request is the same length**: `ignore_eos=True` with `max_tokens=475`,
temperature 0, one fixed prompt, so a level's aggregate is not a function of how
early the model chose to stop.

Known defects, both demonstrated:

1. **Only the last 25 log lines were kept on a refusal, until #357.** That was
   not enough to reach a root cause: 26 of the 2026-08-24 sweep's 36 refusals
   recorded a `RuntimeError: Engine core initialization failed` and the actual
   cause had scrolled past, so `knobs.py` labels them `refused_reason_lost`
   rather than attributing them. A refusal now keeps the whole log (capped at
   `LOG_LINES`), and the record carries the image digest the cell ran on.
2. **No tests.** This module has none. A prior version joined flags with a plain
   space and passed them through `ssh`, so `--speculative-config`'s JSON was
   word-split by the shell and three cells per rig were recorded as REFUSED when
   they were untested. Fixed with `shlex.quote` (see `launch`), and the stage-1
   records that carry those false refusals are kept as they were written --
   `knobs.py` reads them as `harness_defect`, by comparing the value the engine
   quoted with the value the record holds.

Usage::

    python3 tools/bench/serving/sweep.py <host> <model> <matrix.json> <out.jsonl>

where `matrix.json` is a list of `{"id", "axis", "flags", "cap", "levels",
"tokens"}` -- `tokens` is the per-request budget, default 475 (#356).
"""

import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

IMAGE = "vllm/vllm-openai:v0.26.0"
NAME = "sweep-vllm"
PORT = 8000
TOKENS = 475  # same budget as every prior measurement
LEVELS = [1, 2, 4, 8, 16, 32, 64, 128]
#: Log lines kept on a refusal. 25 lost the cause 26 times in one sweep (#357);
#: a vLLM startup log to the point of a refusal is a few hundred lines.
LOG_LINES = 2000
PROMPT = "Write a Python function that merges two sorted lists.\n\n"


def ssh(host, cmd, timeout=600):
    r = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", host, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return r.stdout.strip(), r.returncode


def release(host):
    ssh(host, f"docker rm -f {NAME} >/dev/null 2>&1; true", timeout=120)
    for _ in range(30):
        used, _ = ssh(
            host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
        )
        if used.isdigit() and int(used) < 500:
            return True
        time.sleep(2)
    return False


def digest(host):
    out, code = ssh(
        host, f"docker image inspect --format '{{{{index .RepoDigests 0}}}}' {IMAGE}"
    )
    return out if code == 0 and out else None


def launch(host, model, flags):
    release(host)
    args = " ".join(shlex.quote(f) for f in flags)
    cmd = (
        f"docker run -d --name {NAME} --runtime=nvidia --gpus all "
        f"-v $HOME/.cache/huggingface:/root/.cache/huggingface -p {PORT}:{PORT} "
        f"--ipc=host -e VLLM_SERVER_DEV_MODE=1 -e FLASHINFER_DISABLE_VERSION_CHECK=1 "
        f"{IMAGE} {model} --port {PORT} {args}"
    )
    ssh(host, cmd, timeout=180)
    began = time.time()
    for _ in range(120):  # up to 20 min
        code, _ = ssh(
            host,
            f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' "
            f"http://127.0.0.1:{PORT}/health",
        )
        mib, _ = ssh(
            host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
        )
        if code == "200" and mib.isdigit() and int(mib) > 500:
            return {
                "ok": True,
                "start_seconds": round(time.time() - began, 1),
                "command": cmd,
                "image_digest": digest(host),
            }
        alive, _ = ssh(
            host,
            f"docker inspect -f '{{{{.State.Running}}}}' {NAME} "
            "2>/dev/null || echo gone",
        )
        if alive != "true":
            log, _ = ssh(host, f"docker logs --tail {LOG_LINES} {NAME} 2>&1")
            return {
                "ok": False,
                "reason": "container exited",
                "log": log,
                "log_lines_kept": LOG_LINES,
                "image_digest": digest(host),
                "start_seconds": round(time.time() - began, 1),
            }
        time.sleep(10)
    log, _ = ssh(host, f"docker logs --tail {LOG_LINES} {NAME} 2>&1")
    return {
        "ok": False,
        "reason": "timeout",
        "log": log,
        "log_lines_kept": LOG_LINES,
        "image_digest": digest(host),
    }


def one_request(host):
    body = json.dumps(
        {
            "model": MODEL,
            "prompt": PROMPT,
            "max_tokens": TOKENS,
            "temperature": 0.0,
            "ignore_eos": True,
        }
    ).encode()
    req = urllib.request.Request(
        f"http://{host}:{PORT}/v1/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    t = time.time()
    with urllib.request.urlopen(req, timeout=1200) as r:
        d = json.loads(r.read())
    return time.time() - t, d["usage"]["completion_tokens"]


def ramp(host, cap):
    out = []
    for n in [x for x in LEVELS if x <= cap]:
        try:
            with ThreadPoolExecutor(max_workers=n) as ex:
                t = time.time()
                res = list(ex.map(lambda _: one_request(host), range(n)))
                wall = time.time() - t
            toks = sum(c for _, c in res)
            lat = [seconds for seconds, _ in res]
            out.append(
                {
                    "n": n,
                    "wall_s": round(wall, 3),
                    "tokens": toks,
                    "agg_tok_s": round(toks / wall, 1),
                    "per_stream_tok_s": round(toks / wall / n, 2),
                    "latency_mean_s": round(sum(lat) / len(lat), 3),
                    "latency_max_s": round(max(lat), 3),
                }
            )
            print(
                f"      n={n:<4} {out[-1]['agg_tok_s']:>8.1f} tok/s  "
                f"lat {out[-1]['latency_mean_s']:.2f}s",
                flush=True,
            )
        except Exception as e:
            out.append({"n": n, "error": repr(e)[:300]})
            print(f"      n={n:<4} ERROR {repr(e)[:120]}", flush=True)
            break
    return out


def resolved(host):
    info = {}
    try:
        with urllib.request.urlopen(
            f"http://{host}:{PORT}/server_info?config_format=json", timeout=30
        ) as r:
            info["server_info"] = json.loads(r.read())
    except Exception as e:
        info["server_info_error"] = repr(e)[:200]
    log, _ = ssh(
        host,
        f"docker logs {NAME} 2>&1 | grep -E "
        f"'attention backend|LinearMethod|FlashInfer for top|KV cache size|"
        f"Maximum concurrency|Using FlashAttention|torch.compile|Capturing|"
        f"Available KV cache|GPU KV cache' | tail -20",
    )
    info["log_lines"] = log.splitlines()
    return info


def main():
    global MODEL
    host, MODEL, matrix_path, out_path = sys.argv[1:5]
    with open(matrix_path) as handle:
        matrix = json.load(handle)
    out = open(out_path, "a")  # noqa: SIM115 -- held open for the whole sweep
    for i, cell in enumerate(matrix, 1):
        print(
            f"\n[{i}/{len(matrix)}] {host} {cell['id']}  {' '.join(cell['flags'])}",
            flush=True,
        )
        rec = {
            "host": host,
            "model": MODEL,
            "cell": cell["id"],
            "flags": cell["flags"],
            "axis": cell.get("axis"),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        st = launch(host, MODEL, cell["flags"])
        rec["launch"] = st
        if st.get("ok"):
            rec["resolved"] = resolved(host)
            global LEVELS, TOKENS
            LEVELS = cell.get("levels", [1, 2, 4, 8, 16, 32, 64, 128])
            # #356: a cell may set its own per-request budget, so the budget
            # itself can be an axis. Recorded on the row, because a level's
            # `tokens` is the level's TOTAL and does not say what each
            # request was capped at.
            TOKENS = cell.get("tokens", 475)
            rec["tokens_per_request"] = TOKENS
            rec["levels"] = ramp(host, cell.get("cap", max(LEVELS)))
            best = max(
                (lv for lv in rec["levels"] if "agg_tok_s" in lv),
                key=lambda lv: lv["agg_tok_s"],
                default=None,
            )
            rec["max_agg_tok_s"] = best["agg_tok_s"] if best else None
            rec["max_at_n"] = best["n"] if best else None
            print(
                f"   -> MAX {rec['max_agg_tok_s']} tok/s at n={rec['max_at_n']}",
                flush=True,
            )
        else:
            print(f"   -> REFUSED: {st.get('reason')}", flush=True)
        out.write(json.dumps(rec) + "\n")
        out.flush()
    release(host)
    print("\ndone; rig released", flush=True)


if __name__ == "__main__":
    main()
