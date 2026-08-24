#!/usr/bin/env python3
"""Serving-sweep runner for sweep-spec-2026-08-24 (blocks a, e, b, c, d, re-takes; no f).

Stdlib only. One process per rig:

    python3 runner.py --cells cells.json --out out/srv2 --rig srv2
    python3 runner.py --cells cells.json --out out/srv1 --rig srv1
    python3 runner.py --cells cells.json --rig srv2 --restore-only
    python3 runner.py --cells cells.json --out /tmp/x --rig srv2 --dry-run

Everything the rig does goes over `ssh <rig> <cmd>`; requests go straight to
http://<rig>:<port>. Every row is appended to <out>/rows.jsonl the moment it is
known; <out>/<cell>.launch.log holds the last 40 launch-log lines per cell;
<out>/run.json holds start/end, rig facts, image digests, repo head and this
file's sha256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/home/adaramir/claude/mcgyvr")
SWEEP_PY = REPO / "tools" / "bench" / "serving" / "sweep.py"

TOKENS = 475
CAP_TOKENS = 470  # a request that reached >= this counts as capped (cap fraction)
PROMPT = "Write a Python function that merges two sorted lists.\n\n"  # sweep.py's PROMPT
NUM_CTX = 1024
WARMUP_TOKENS = 475
IDLE_GPU_MIB = 500

OLLAMA_PORT = 11434
DROPIN = "/etc/systemd/system/ollama.service.d/parallel.conf"
RESTORE_LINES = [
    "[Service]",
    'Environment="OLLAMA_NUM_PARALLEL=0"',
    'Environment="OLLAMA_MAX_LOADED_MODELS=0"',
    'Environment="OLLAMA_KEEP_ALIVE=-1"',
]
RESTORE_READBACK = (
    "OLLAMA_NUM_PARALLEL=0 OLLAMA_MAX_LOADED_MODELS=0 OLLAMA_KEEP_ALIVE=-1 OLLAMA_HOST=0.0.0.0:11434"
)

PORTS = {"ollama": OLLAMA_PORT, "llamacpp": 8080, "lmdeploy": 23333, "vllm": 8000}
CONTAINER = {"llamacpp": "sweep-llamacpp", "lmdeploy": "sweep-lmdeploy", "vllm": "sweep-vllm",
             "batched-bench": "sweep-llamacpp"}
READY_TIMEOUT = {"llamacpp": 300, "lmdeploy": 900, "ollama": 120}

STATE_CMD = (
    "echo __MEM; nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits; "
    "echo __ID; nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap "
    "--format=csv,noheader,nounits; "
    "echo __CARD; timeout 10 nvidia-smi --query-gpu=temperature.gpu,power.draw,clocks.sm,"
    "clocks_throttle_reasons.active --format=csv,noheader,nounits; "
    "echo __LOAD; cat /proc/loadavg; "
    "echo __DOCKER; docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}'; "
    "echo __OLLAMAPS; ollama ps 2>&1; "
    "echo __ENV; systemctl show ollama -p Environment; "
    "echo __ACTIVE; systemctl is-active ollama; echo __END"
)


# ----------------------------------------------------------------------------- utils
def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def p50(xs):
    return round(statistics.median(xs), 3) if xs else None


class Rig:
    """ssh + http to one rig. --dry-run turns every rig action into a printed plan."""

    def __init__(self, host: str, dry: bool):
        self.host, self.dry = host, dry

    def ssh(self, cmd: str, timeout: int = 600, check: bool = False) -> tuple[str, int]:
        if self.dry:
            print(f"    [dry ssh {self.host}] {cmd[:220]}")
            return "", 0
        try:
            r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", self.host, cmd],
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            if check:
                raise RuntimeError(f"ssh {self.host} timed out after {timeout}s: {cmd[:120]}")
            return f"ssh timeout after {timeout}s", 124
        out = (r.stdout + ("\n" + r.stderr if r.stderr.strip() else "")).strip()
        if check and r.returncode != 0:
            raise RuntimeError(f"ssh {self.host} rc={r.returncode}: {cmd[:120]} :: {out[-400:]}")
        return out, r.returncode

    def http(self, port: int, path: str, body=None, timeout: float = 30.0) -> tuple[int, str]:
        url = f"http://{self.host}:{port}{path}"
        if self.dry:
            print(f"    [dry http] {'POST' if body is not None else 'GET'} {url} {json.dumps(body)[:160] if body is not None else ''}")
            return 200, "{}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def state(self) -> dict:
        out, _ = self.ssh(STATE_CMD, timeout=60)
        if self.dry:
            return {"dry": True}
        sec, cur = {}, None
        for line in out.splitlines():
            if line.startswith("__"):
                cur = line[2:]
                sec[cur] = []
            elif cur:
                sec[cur].append(line)
        mem = (sec.get("MEM") or [""])[0].strip()
        ident = [x.strip() for x in (sec.get("ID") or [""])[0].split(",")]
        card = [x.strip() for x in (sec.get("CARD") or [""])[0].split(",")]
        env = " ".join(sec.get("ENV") or []).replace("Environment=", "", 1)
        return {
            "gpu_mem_used_mib": int(mem) if mem.isdigit() else mem,
            "gpu_name": ident[0] if len(ident) > 0 else None,
            "gpu_total_mib": ident[1] if len(ident) > 1 else None,
            "driver_version": ident[2] if len(ident) > 2 else None,
            "compute_capability": ident[3] if len(ident) > 3 else None,
            "card": dict(zip(("temperature_c", "power_w", "sm_clock_mhz", "throttle_reasons"), card)),
            "loadavg": (sec.get("LOAD") or [""])[0],
            "docker_ps_a": sec.get("DOCKER") or [],
            "ollama_ps": sec.get("OLLAMAPS") or [],
            "ollama_env": env,
            "ollama_env_ollama_pairs": " ".join(t for t in env.split() if t.startswith("OLLAMA_")),
            "ollama_active": (sec.get("ACTIVE") or [""])[0].strip(),
        }

    def gpu_used(self) -> int:
        out, _ = self.ssh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits", timeout=30)
        return int(out.strip()) if out.strip().isdigit() else -1

    def container_exists(self, name: str) -> bool:
        out, _ = self.ssh(f"docker ps -a --format '{{{{.Names}}}}' | grep -x {shlex.quote(name)} || true", timeout=60)
        return bool(out.strip())

    def container_running(self, name: str) -> bool:
        out, _ = self.ssh(f"docker inspect -f '{{{{.State.Running}}}}' {shlex.quote(name)} 2>/dev/null || echo gone", timeout=60)
        return out.strip() == "true"

    def image_present(self, image: str) -> bool:
        out, rc = self.ssh(f"docker image inspect {shlex.quote(image)} >/dev/null 2>&1 && echo yes || echo no", timeout=60)
        return self.dry or out.strip().endswith("yes")

    def logs_tail(self, name: str, n: int = 40) -> str:
        out, _ = self.ssh(f"docker logs --tail {n} {shlex.quote(name)} 2>&1 | tail -{n}", timeout=60)
        return out


# ----------------------------------------------------------------------------- output
class Out:
    def __init__(self, d: Path, dry: bool):
        self.dir, self.dry = d, dry
        if not dry:
            d.mkdir(parents=True, exist_ok=True)
        self.rows = d / "rows.jsonl"

    def row(self, r: dict) -> None:
        r = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **r}
        if self.dry:
            print("    [dry row] " + json.dumps(r)[:200])
            return
        with open(self.rows, "a") as f:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    def text(self, name: str, content: str) -> None:
        if self.dry:
            return
        (self.dir / name).write_text(content)

    def json(self, name: str, obj) -> None:
        if self.dry:
            return
        (self.dir / name).write_text(json.dumps(obj, indent=2, sort_keys=True))


# ----------------------------------------------------------------------------- requests
class LevelResult(dict):
    pass


def one_request(rig: Rig, cell: dict, cap_s: float, n_tokens: int = TOKENS) -> dict:
    eng = cell["engine"]
    port = PORTS[eng]
    rec = {"start": None, "end": None, "status": None, "tokens": 0, "error": None}
    if eng == "ollama":
        opts = {"num_ctx": NUM_CTX, "num_predict": n_tokens, "temperature": 0}
        opts.update(cell.get("request_options") or {})
        body = {"model": cell["model"], "prompt": PROMPT, "stream": False, "options": opts}
        path = "/api/generate"
    else:
        body = {"prompt": PROMPT, "max_tokens": n_tokens, "temperature": 0}
        if eng == "llamacpp":
            body["ignore_eos"] = True
        if eng == "lmdeploy":
            body["model"] = cell["model"]
        path = "/v1/completions"
    rec["start"] = time.time()
    try:
        code, text = rig.http(port, path, body, timeout=cap_s)
        rec["end"] = time.time()
        rec["status"] = code
        if rig.dry:
            rec["tokens"] = n_tokens
            rec["latency_s"] = 0.0
            return rec
        d = json.loads(text)
        if code != 200:
            rec["error"] = text[:300]
        elif eng == "ollama":
            rec["tokens"] = int(d.get("eval_count") or 0)
            rec["eval_duration_ns"] = d.get("eval_duration")
            rec["prompt_eval_count"] = d.get("prompt_eval_count")
            rec["prompt_eval_duration_ns"] = d.get("prompt_eval_duration")
            rec["load_duration_ns"] = d.get("load_duration")
            rec["total_duration_ns"] = d.get("total_duration")
            rec["done_reason"] = d.get("done_reason")
        else:
            rec["tokens"] = int(d["usage"]["completion_tokens"])
            rec["prompt_tokens"] = d["usage"].get("prompt_tokens")
            rec["finish_reason"] = (d.get("choices") or [{}])[0].get("finish_reason")
    except Exception as e:  # timeout, connection refused, bad json
        rec["end"] = time.time()
        rec["error"] = repr(e)[:300]
        rec["status"] = rec["status"] or "exception"
    rec["latency_s"] = round(rec["end"] - rec["start"], 3)
    return rec


def run_level(rig: Rig, cell: dict, n: int, cap_s: float) -> dict:
    results: list[dict | None] = [None] * n

    def worker(i):
        results[i] = one_request(rig, cell, cap_s)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=cap_s + 30)
    reqs = [r if r is not None else {"status": "no-result", "error": "thread did not finish", "tokens": 0,
                                     "start": None, "end": None, "latency_s": None} for r in results]
    ok = [r for r in reqs if r["status"] == 200 and not r["error"]]
    starts = [r["start"] for r in reqs if r["start"]]
    ends = [r["end"] for r in reqs if r["end"]]
    wall = (max(ends) - min(starts)) if starts and ends else cap_s
    tokens = sum(r["tokens"] for r in ok)
    capped_hit = wall >= cap_s or any(r["error"] and "timed out" in str(r["error"]) for r in reqs)
    if rig.dry:
        wall = max(wall, 0.001)
    return {
        "n": n,
        "wall_s": round(wall, 3),
        "tokens": tokens,
        "agg_tok_s": round(tokens / wall, 2) if wall > 0 else None,
        "ok_requests": len(ok),
        "failed_requests": n - len(ok),
        "p50_latency_s": p50([r["latency_s"] for r in ok]),
        "max_latency_s": max([r["latency_s"] for r in ok], default=None),
        "cap_fraction": round(sum(1 for r in ok if r["tokens"] >= CAP_TOKENS) / n, 3),
        "hit_level_cap": capped_hit,
        "floor_tok_s_if_capped": round(TOKENS * n / cap_s, 2) if capped_hit else None,
        "requests": reqs,
    }


# ----------------------------------------------------------------------------- metrics
def scrape_metrics(rig: Rig, port: int) -> dict[str, float]:
    try:
        code, text = rig.http(port, "/metrics", timeout=20)
    except Exception:
        return {}
    if code != 200 or rig.dry:
        return {}
    vals: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        try:
            vals[parts[0]] = float(parts[1])
        except ValueError:
            pass
    return vals


def metrics_delta(before: dict, after: dict, wall: float) -> dict:
    d = {k: after[k] - before.get(k, 0.0) for k in after if k in before and after[k] != before[k]}
    out = {"changed": {k: round(v, 3) for k, v in sorted(d.items())[:80]}}
    for key in ("llamacpp:tokens_predicted_total", "vllm:generation_tokens_total"):
        if key in d:
            out["engine_tokens"] = d[key]
            out["engine_tok_s"] = round(d[key] / wall, 2) if wall else None
    gen = [k for k in d if "generation_tokens" in k or "tokens_predicted" in k or "output_tokens" in k]
    if gen and "engine_tokens" not in out:
        out["engine_tokens"] = d[gen[0]]
        out["engine_tokens_metric"] = gen[0]
        out["engine_tok_s"] = round(d[gen[0]] / wall, 2) if wall else None
    return out


# ----------------------------------------------------------------------------- ollama
class Ollama:
    def __init__(self, rig: Rig):
        self.rig = rig
        self.touched = False

    def is_active(self) -> bool:
        out, _ = self.rig.ssh("systemctl is-active ollama", timeout=30)
        return self.rig.dry or out.strip() == "active"

    def wait_ready(self, timeout: int = 120) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                code, _ = self.rig.http(OLLAMA_PORT, "/api/tags", timeout=5)
                if code == 200:
                    return True
            except Exception:
                pass
            if self.rig.dry:
                return True
            time.sleep(2)
        return False

    def resident_models(self) -> list[str]:
        out, _ = self.rig.ssh("ollama ps 2>/dev/null | tail -n +2 | awk '{print $1}'", timeout=30)
        return [x for x in out.split() if x]

    def unload_all(self) -> None:
        for m in self.resident_models():
            self.rig.http(OLLAMA_PORT, "/api/generate", {"model": m, "keep_alive": 0}, timeout=60)

    def write_dropin(self, num_parallel: int, extra: list[str]) -> None:
        lines = ["[Service]",
                 f'Environment="OLLAMA_NUM_PARALLEL={num_parallel}"',
                 'Environment="OLLAMA_MAX_LOADED_MODELS=0"',
                 'Environment="OLLAMA_KEEP_ALIVE=-1"'] + [f'Environment="{e}"' for e in extra]
        content = "\n".join(lines) + "\n"
        self.rig.ssh(f"printf %s {shlex.quote(content)} | sudo -n tee {DROPIN} >/dev/null", timeout=60, check=True)
        self.touched = True

    def restart(self) -> None:
        self.rig.ssh("sudo -n systemctl daemon-reload && sudo -n systemctl restart ollama", timeout=120, check=True)
        if not self.wait_ready():
            raise RuntimeError("ollama did not answer /api/tags within 120 s after restart")

    def stop(self) -> None:
        self.rig.ssh("sudo -n systemctl stop ollama", timeout=120, check=True)

    def start(self) -> None:
        self.rig.ssh("sudo -n systemctl start ollama", timeout=120, check=True)
        if not self.wait_ready():
            raise RuntimeError("ollama did not answer /api/tags within 120 s after start")

    def env_readback(self) -> str:
        out, _ = self.rig.ssh("systemctl show ollama -p Environment", timeout=30)
        return " ".join(t for t in out.replace("Environment=", "", 1).split() if t.startswith("OLLAMA_"))

    def configure(self, num_parallel: int, extra: list[str]) -> dict:
        """Unload, rewrite the drop-in, restart, verify the readback."""
        if not self.is_active():
            self.start()
        self.unload_all()
        epoch, _ = self.rig.ssh("date +%s", timeout=30)
        self.write_dropin(num_parallel, extra)
        self.restart()
        rb = self.env_readback()
        want = [f"OLLAMA_NUM_PARALLEL={num_parallel}", "OLLAMA_HOST=0.0.0.0:11434"] + extra
        missing = [w for w in want if w not in rb.split()]
        if missing and not self.rig.dry:
            raise RuntimeError(f"drop-in did not take: readback {rb!r} lacks {missing}")
        return {"env_readback": rb, "journal_since_epoch": epoch.strip() or None}

    def child_argv(self, since_epoch: str | None) -> str:
        # journalctl needs sudo -n here: adaramir is not in adm/systemd-journal on the rigs.
        since = f"--since @{since_epoch}" if since_epoch else "-n 2000"
        out, _ = self.rig.ssh(
            f"sudo -n journalctl -u ollama {since} --no-pager 2>/dev/null | grep 'starting llama-server' | tail -1",
            timeout=60)
        m = re.search(r'cmd="([^"]*)"', out)
        return (m.group(1) if m else out).strip()

    def ps(self) -> str:
        out, _ = self.rig.ssh("ollama ps 2>&1", timeout=30)
        return out

    def restore(self) -> dict:
        """Three original lines, restart, assert the readback. Safe to call any number of times."""
        if not self.is_active():
            try:
                self.rig.ssh("sudo -n systemctl start ollama", timeout=120)
            except Exception:
                pass
        try:
            self.unload_all()
        except Exception:
            pass
        content = "\n".join(RESTORE_LINES) + "\n"
        self.rig.ssh(f"printf %s {shlex.quote(content)} | sudo -n tee {DROPIN} >/dev/null", timeout=60, check=True)
        self.rig.ssh("sudo -n systemctl daemon-reload && sudo -n systemctl restart ollama", timeout=120, check=True)
        ready = self.wait_ready()
        rb = self.env_readback()
        ok = self.rig.dry or rb == RESTORE_READBACK
        self.touched = False
        res = {"restored": ok, "env_readback": rb, "expected": RESTORE_READBACK, "api_ready": ready}
        if not ok:
            log(f"!! RESTORE READBACK MISMATCH on {self.rig.host}: {rb!r}")
        else:
            log(f"restore ok on {self.rig.host}: {rb}")
        return res


# ----------------------------------------------------------------------------- engines
def docker_run_cmd(cell: dict, rig_host: str) -> str:
    eng = cell["engine"]
    name = CONTAINER[eng]
    if eng == "llamacpp":
        vols = [f"{cell['blobs_dir']}:/models:ro"] + cell.get("extra_volumes", [])
        envs = cell.get("env", {})
        args = (f"docker run --rm -d --pull=never --gpus all -p 8080:8080 " + " ".join(f"-v {v}" for v in vols) + " " +
                " ".join(f"-e {k}={v}" for k, v in envs.items()) +
                f" --name {name} {cell['image']} -m /models/{cell['blob']} --host 0.0.0.0 --port 8080 " +
                " ".join(cell["launch_args"]))
        return args
    if eng == "lmdeploy":
        vols = ["/home/adaramir/.cache/huggingface:/root/.cache/huggingface",
                "/home/adaramir/sweep-2026-08-24:/sweep"]
        envs = {"HF_HUB_OFFLINE": "1", "TM_LOG_LEVEL": "INFO"}  # spec v2 (d) common line: cache-only, C++ logger prints tuning lines
        envs.update(cell.get("env", {}))
        # 2026-08-24 20:40 correction: HF_HUB_OFFLINE=1 + an "incomplete snapshot" (vLLM's download skipped
        # .gitattributes/LICENSE/README.md) makes lmdeploy's snapshot_download refuse the hub id. Hand it the
        # local snapshot directory (resolved on the rig) and keep the hub id as the served --model-name so
        # /v1/completions requests are unchanged. No --rm: a container that dies keeps its log for logs_tail;
        # teardown does docker rm -f by name.
        hub_dir = "models--" + cell["model"].replace("/", "--")
        snap = (f"SNAP=$(ls /home/adaramir/.cache/huggingface/hub/{hub_dir}/snapshots 2>/dev/null | head -1); "
                f"[ -n \"$SNAP\" ] || {{ echo 'no snapshot for {cell['model']}' >&2; exit 3; }}; ")
        local_path = f"/root/.cache/huggingface/hub/{hub_dir}/snapshots/$SNAP"
        return (snap + f"docker run -d --pull=never --gpus all --ipc=host -p 23333:23333 " + " ".join(f"-v {v}" for v in vols) + " " +
                " ".join(f"-e {k}={v}" for k, v in envs.items()) +
                f" --name {name} {cell['image']} lmdeploy serve api_server {local_path} --model-name {cell['model']} "
                f"--backend turbomind --model-format awq --tp 1 --session-len {NUM_CTX} --server-port 23333 --log-level WARNING " +
                " ".join(cell["launch_args"]))
    if eng == "batched-bench":
        return (f"docker run --rm --pull=never --gpus all -v {cell['blobs_dir']}:/models:ro --name {name} "
                f"--entrypoint /app/llama-batched-bench {cell['image']} -m /models/{cell['blob']} " +
                " ".join(cell["launch_args"]))
    raise ValueError(eng)


def wait_http(rig: Rig, port: int, path: str, timeout: int, name: str, want_code: int = 200) -> tuple[bool, float, str]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            code, text = rig.http(port, path, timeout=5)
            if code == want_code:
                return True, round(time.time() - t0, 1), text
        except Exception:
            pass
        if rig.dry:
            return True, 0.0, "{}"
        if not rig.container_running(name):
            return False, round(time.time() - t0, 1), "container exited"
        time.sleep(5)
    return False, round(time.time() - t0, 1), "timeout"


# ----------------------------------------------------------------------------- runner
class Runner:
    def __init__(self, rig: Rig, out: Out, cap_s: float, only: set[str] | None):
        self.rig, self.out, self.cap_s, self.only = rig, out, cap_s, only
        self.ollama = Ollama(rig)
        self.results: dict[str, dict] = {}       # cell id -> summary
        self.skip_engine: dict[str, str] = {}    # engine -> reason (block aborted)
        self.spilled_models: set[str] = set()    # ollama model names that spilled (do not raise N)
        self.rig_stopped: str | None = None      # control failed -> reason
        self.lmdeploy_gemm: set[str] = set()
        self.lmdeploy_dead_models: set[str] = set()  # rule (d)3: a model that does not load on srv1; the other model's cells still run

    # ---- state
    def capture(self, cell_id: str, phase: str) -> dict:
        st = self.rig.state()
        self.out.row({"kind": "state", "cell": cell_id, "phase": phase, "rig": self.rig.host, **st})
        return st

    def post_state_violations(self, st: dict, expect_ollama_env: bool) -> list[str]:
        v = []
        if self.rig.dry:
            return v
        running = [l for l in st["docker_ps_a"] if l.split("\t")[0] in CONTAINER.values() and "Up" in l]
        if running:
            v.append(f"our container running: {running}")
        if isinstance(st["gpu_mem_used_mib"], int) and st["gpu_mem_used_mib"] >= IDLE_GPU_MIB:
            v.append(f"gpu memory {st['gpu_mem_used_mib']} MiB >= {IDLE_GPU_MIB}")
        if any(l.strip() and not l.startswith("NAME") for l in st["ollama_ps"]) and "could not connect" not in " ".join(st["ollama_ps"]):
            v.append("a model is resident in ollama")
        if expect_ollama_env and st["ollama_env_ollama_pairs"] != RESTORE_READBACK:
            v.append(f"ollama env {st['ollama_env_ollama_pairs']!r} != restore target")
        return v

    # ---- ensure ollama running / stopped around docker engines
    def ensure_ollama_stopped(self) -> None:
        if self.ollama.is_active():
            log("stopping ollama (docker engine cell)")
            self.ollama.stop()

    def ensure_ollama_started(self) -> None:
        if not self.ollama.is_active():
            log("starting ollama")
            self.ollama.start()

    # ---- levels
    def levels(self, cell: dict, levels: list[int], repeats: int, pre_metrics_port: int | None) -> tuple[list[dict], str | None]:
        rows, stop_reason = [], None
        for n in levels:
            attempts = []
            for r in range(repeats):
                before = scrape_metrics(self.rig, pre_metrics_port) if pre_metrics_port else {}
                lv = run_level(self.rig, cell, n, self.cap_s)
                after = scrape_metrics(self.rig, pre_metrics_port) if pre_metrics_port else {}
                if before or after:
                    lv["engine_metrics"] = metrics_delta(before, after, lv["wall_s"])
                lv["attempt"] = r + 1
                attempts.append(lv)
                if lv["hit_level_cap"]:
                    break
            best = max(attempts, key=lambda a: a["agg_tok_s"] or 0)
            best["attempts"] = len(attempts)
            if repeats > 1:
                best["all_attempts_agg_tok_s"] = [a["agg_tok_s"] for a in attempts]
            row = {"kind": "level", "cell": cell["id"], "rig": self.rig.host, "engine": cell["engine"],
                   "model": cell["model"], "block": cell["block"], **best}
            if not self.rig.dry:
                card, _ = self.rig.ssh("timeout 10 nvidia-smi --query-gpu=temperature.gpu,power.draw,clocks.sm,"
                                       "clocks_throttle_reasons.active --format=csv,noheader,nounits; cat /proc/loadavg", timeout=30)
                row["card_state"] = card
            self.out.row(row)
            rows.append(best)
            log(f"  {cell['id']} n={n:<4} {best['agg_tok_s']} tok/s  p50 {best['p50_latency_s']}s  "
                f"cap_frac {best['cap_fraction']}  fail {best['failed_requests']}"
                + ("  ** CAP HIT" if best["hit_level_cap"] else ""))
            if best["hit_level_cap"]:
                stop_reason = f"level n={n} hit the {self.cap_s}s cap; higher levels skipped (floor {best['floor_tok_s_if_capped']} tok/s)"
                break
            if best["ok_requests"] == 0:
                stop_reason = f"level n={n}: every request failed; higher levels skipped"
                break
        return rows, stop_reason

    # ---- per-engine cells
    def cell_ollama(self, cell: dict, summary: dict) -> None:
        N = int(cell["num_parallel"])
        if cell["model"] in self.spilled_models and N > 1:
            summary["status"] = "skipped"
            summary["reason"] = f"{cell['model']} spilled at a lower slot count; rule (a)1: do not raise N"
            return
        self.ensure_ollama_started()
        extra = list(cell.get("env_extra", []))
        conf = self.ollama.configure(N, extra)
        summary["configure"] = conf
        # warm-up loads the model
        warm = one_request(self.rig, cell, max(self.cap_s, 300), WARMUP_TOKENS)
        summary["warmup"] = {k: warm.get(k) for k in ("status", "tokens", "latency_s", "error", "load_duration_ns")}
        if warm.get("error") and not self.rig.dry:
            raise RuntimeError(f"warm-up failed: {warm['error']}")
        ps = self.ollama.ps()
        argv = self.ollama.child_argv(conf.get("journal_since_epoch"))
        summary["ollama_ps"] = ps
        summary["child_argv"] = argv
        self.out.text(f"{cell['id']}.launch.log", f"ollama ps:\n{ps}\n\nchild argv:\n{argv}\n")
        if not self.rig.dry:
            if "100% GPU" not in ps:
                summary["status"] = "spilled"
                summary["reason"] = f"ollama ps PROCESSOR is not 100% GPU: {ps.strip().splitlines()[-1:]}"
                self.spilled_models.add(cell["model"])
                return
            want_np = f"-np {N}" in argv or f"--parallel {N}" in argv
            want_c = f"-c {NUM_CTX * N}" in argv or f"--ctx-size {NUM_CTX * N}" in argv
            if not (want_np and want_c):
                if not cell.get("_retried"):
                    log(f"  argv lacks -np {N} -c {NUM_CTX*N}; rewriting drop-in once and retrying")
                    cell["_retried"] = True
                    return self.cell_ollama(cell, summary)
                summary["status"] = "aborted"
                summary["reason"] = f"child argv lacks -np {N} -c {NUM_CTX*N} after retry: {argv!r}; rule (a)2 aborts the ollama block"
                self.skip_engine["ollama"] = "rule (a)2: drop-in did not reach the child"
                return
            if "OLLAMA_FLASH_ATTENTION=0" in extra and "--flash-attn off" not in argv:
                summary["status"] = "aborted"
                summary["reason"] = f"rule (c)2: journal argv does not show --flash-attn off: {argv!r}"
                return
            m = re.search(r"(?:^|\s)(?:-b|--batch-size) (\d+)", argv)
            summary["child_batch"] = int(m.group(1)) if m else None
            m = re.search(r"--flash-attn (\w+)", argv)
            summary["child_flash_attn"] = m.group(1) if m else None
            want_b = (cell.get("request_options") or {}).get("num_batch")
            if want_b is not None and summary["child_batch"] != int(want_b):
                summary["status"] = "aborted"
                summary["reason"] = f"rule (c)3: request num_batch={want_b} but the child argv shows -b {summary['child_batch']}: {argv!r}; the pair is not compared"
                return
        rows, stop = self.levels(cell, cell["levels"], cell.get("repeats", 1), None)
        summary["levels"] = [{k: v for k, v in r.items() if k != "requests"} for r in rows]
        summary["stop_reason"] = stop
        summary["status"] = "ok"

    def cell_docker(self, cell: dict, summary: dict) -> None:
        eng = cell["engine"]
        name = CONTAINER[eng]
        port = PORTS.get(eng)
        self.ensure_ollama_stopped()
        if self.rig.container_exists(name):
            raise RuntimeError(f"refusing to start: a container named {name} already exists on {self.rig.host}")
        if not self.rig.image_present(cell["image"]):
            summary["status"] = "refused"
            summary["reason"] = f"image {cell['image']} is not present on {self.rig.host}; the runner never pulls"
            return
        if eng == "lmdeploy":
            snap = f"/home/adaramir/.cache/huggingface/hub/models--{cell['model'].replace('/', '--')}/snapshots"
            out, rc = self.rig.ssh(f"ls {snap} 2>/dev/null | head -1", timeout=30)
            if rc != 0 or (not out.strip() and not self.rig.dry):
                summary["status"] = "skipped"
                summary["reason"] = f"no snapshot dir for {cell['model']} on {self.rig.host} ({snap})"
                return
            self.rig.ssh("mkdir -p /home/adaramir/sweep-2026-08-24", timeout=30)
            gemm = f"/sweep/gemm-{cell['model'].split('/')[-1]}.txt"
            host_gemm = gemm.replace("/sweep/", "/home/adaramir/sweep-2026-08-24/")
            _, rc = self.rig.ssh(f"test -s {host_gemm}", timeout=30)
            cell.setdefault("env", {})
            cell["env"]["TM_GEMM_IMPORT" if rc == 0 and not self.rig.dry else "TM_GEMM_EXPORT"] = gemm
            summary["tm_gemm"] = dict(cell["env"])
        if eng == "llamacpp" and cell.get("extra_volumes"):
            for v in cell["extra_volumes"]:
                self.rig.ssh(f"mkdir -p {shlex.quote(v.split(':')[0])}", timeout=30)
        launch_variants = [cell["launch_args"]] + cell.get("fallback_launch_args", [])
        for vi, args in enumerate(launch_variants):
            cell["launch_args"] = args
            cmd = docker_run_cmd(cell, self.rig.host)
            summary["launch_command"] = cmd
            summary["launch_variant"] = vi
            log(f"  launch: {cmd[:160]}...")
            t0 = time.time()
            self.rig.ssh(cmd, timeout=180, check=True)
            timeout = cell.get("ready_timeout_s", READY_TIMEOUT[eng])
            if eng == "llamacpp":
                ok, secs, text = wait_http(self.rig, port, "/health", timeout, name)
            else:
                ok, secs, text = wait_http(self.rig, port, "/v1/models", timeout, name)
            summary["start_seconds"] = round(time.time() - t0, 1)
            tail = self.rig.logs_tail(name)
            self.out.text(f"{cell['id']}{'' if vi == 0 else f'.fallback{vi}'}.launch.log", tail)
            if ok:
                break
            reason = "timeout" if text == "timeout" else text
            if text == "timeout":
                self.rig.ssh(f"docker stop {name} >/dev/null 2>&1; true", timeout=120)
            summary.setdefault("launch_failures", []).append({"variant": vi, "reason": reason, "start_seconds": summary["start_seconds"]})
            log(f"  launch variant {vi} failed: {reason} after {summary['start_seconds']}s")
            time.sleep(3)
            if self.rig.container_exists(name):
                self.rig.ssh(f"docker rm -f {name} >/dev/null 2>&1; true", timeout=120)
        else:
            summary["status"] = "refused"
            summary["reason"] = "launch failed on every variant: " + json.dumps(summary.get("launch_failures"))
            if eng == "lmdeploy" and self.rig.host == "srv1" and not cell.get("refusal_is_result"):
                self.lmdeploy_dead_models.add(cell["model"])
                summary["note_d3"] = f"rule (d)3: {cell['model']} does not load on srv1; its later cells are skipped, the other model's still run"
            return
        if summary["launch_variant"] > 0:
            summary["config_note"] = f"ran on fallback launch args (variant {summary['launch_variant']}) -- a different config"
        # engine identity + slot check
        if eng == "llamacpp":
            code, props = self.rig.http(port, "/props", timeout=20)
            try:
                pj = json.loads(props)
            except Exception:
                pj = {}
            summary["props"] = {k: pj.get(k) for k in ("total_slots", "build_info", "default_generation_settings")}
            np_ = int(cell["np"])
            if not self.rig.dry and pj.get("total_slots") != np_:
                summary["status"] = "refused"
                summary["reason"] = f"rule (b)2: /props total_slots={pj.get('total_slots')} != np {np_}"
                return
        if eng == "lmdeploy":
            code, models = self.rig.http(port, "/v1/models", timeout=20)
            summary["models"] = models[:400]
        warm = one_request(self.rig, cell, max(self.cap_s, 300), WARMUP_TOKENS)
        summary["warmup"] = {k: warm.get(k) for k in ("status", "tokens", "latency_s", "error")}
        if warm.get("error") and not self.rig.dry:
            raise RuntimeError(f"warm-up failed: {warm['error']}")
        summary["gpu_mem_used_mib_after_warmup"] = self.rig.gpu_used()
        rows, stop = self.levels(cell, cell["levels"], cell.get("repeats", 1), port)
        summary["levels"] = [{k: v for k, v in r.items() if k != "requests"} for r in rows]
        summary["stop_reason"] = stop
        summary["status"] = "ok"
        if eng == "lmdeploy" and self.rig.host == "srv1" and len(rows) >= 2 and rows[0]["n"] == 1 and rows[1]["n"] == 2:
            if (rows[1]["agg_tok_s"] or 0) <= (rows[0]["agg_tok_s"] or 0):
                summary["note_d3"] = "rule (d)3: n=2 aggregate <= n=1 -- the head GEMM cliff is present in TurboMind too"

    def cell_batched_bench(self, cell: dict, summary: dict) -> None:
        name = CONTAINER["batched-bench"]
        self.ensure_ollama_stopped()
        if self.rig.container_exists(name):
            raise RuntimeError(f"refusing to start: a container named {name} already exists")
        if not self.rig.image_present(cell["image"]):
            summary["status"] = "refused"
            summary["reason"] = f"image {cell['image']} is not present on {self.rig.host}; the runner never pulls"
            return
        cmd = docker_run_cmd(cell, self.rig.host)
        summary["launch_command"] = cmd
        log(f"  run: {cmd[:160]}...")
        t0 = time.time()
        out, rc = self.rig.ssh(cmd, timeout=int(cell.get("timeout_s", 600)))
        summary["wall_s"] = round(time.time() - t0, 1)
        summary["rc"] = rc
        self.out.text(f"{cell['id']}.launch.log", "\n".join(out.splitlines()[-40:]))
        self.out.text(f"{cell['id']}.stdout.txt", out)
        table = []
        for line in out.splitlines():
            if line.startswith("|") and not line.startswith("|-") and "PP" not in line:
                cells_ = [c.strip() for c in line.strip("|").split("|")]
                try:
                    table.append([float(c) for c in cells_])
                except ValueError:
                    pass
        summary["table_header"] = "PP TG B N_KV T_PP S_PP T_TG S_TG T S (llama-batched-bench columns)"
        summary["table_rows"] = table
        for r in table:
            self.out.row({"kind": "batched-bench", "cell": cell["id"], "rig": self.rig.host, "values": r})
        summary["status"] = "ok" if rc == 0 or self.rig.dry else "error"
        summary["reason"] = None if summary["status"] == "ok" else out[-400:]

    def cell_vllm(self, cell: dict, summary: dict) -> None:
        """Block (e): shell out to the repo's sweep.py with a one-cell matrix."""
        self.ensure_ollama_stopped()
        name = CONTAINER["vllm"]
        if self.rig.container_exists(name):
            raise RuntimeError(f"refusing to start: a container named {name} already exists on {self.rig.host} (rule (e)2)")
        repeats = cell.get("repeats", 1)
        levels = list(cell["levels"]) * repeats  # sweep.py runs its levels in order; duplicates = repeat passes within one launch
        matrix = [{"id": cell["id"], "axis": cell.get("axis", "control"), "flags": cell["flags"], "cap": max(cell["levels"]),
                   "levels": levels}]
        mpath = self.out.dir / f"{cell['id']}.matrix.json"
        jpath = self.out.dir / f"{cell['id']}.vllm.jsonl"
        argv = [sys.executable, str(SWEEP_PY), self.rig.host, cell["model"], str(mpath), str(jpath)]
        summary["sweep_py_invocation"] = " ".join(shlex.quote(a) for a in argv)
        summary["sweep_py_matrix"] = matrix
        if self.rig.dry:
            print(f"    [dry exec] {summary['sweep_py_invocation']}")
            summary["status"] = "ok"
            summary["levels"] = [{"n": n, "agg_tok_s": None} for n in cell["levels"]]
            return
        mpath.write_text(json.dumps(matrix))
        t0 = time.time()
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
        summary["sweep_py_rc"] = proc.returncode
        self.out.text(f"{cell['id']}.launch.log", "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-40:]))
        summary["wall_s"] = round(time.time() - t0, 1)
        recs = [json.loads(l) for l in jpath.read_text().splitlines() if l.strip()] if jpath.exists() else []
        if not recs:
            summary["status"] = "error"
            summary["reason"] = f"sweep.py produced no record (rc={proc.returncode}): {proc.stderr[-300:]}"
            return
        rec = recs[-1]
        summary["launch"] = rec.get("launch")
        summary["resolved"] = rec.get("resolved")
        if not rec.get("launch", {}).get("ok"):
            summary["status"] = "refused"
            summary["reason"] = rec.get("launch", {}).get("reason")
            return
        best_by_n: dict[int, dict] = {}
        for lv in rec.get("levels", []):
            n = lv["n"]
            if "agg_tok_s" not in lv:
                best_by_n.setdefault(n, {"n": n, "agg_tok_s": None, "error": lv.get("error")})
                continue
            if n not in best_by_n or (best_by_n[n].get("agg_tok_s") or 0) < lv["agg_tok_s"]:
                best_by_n[n] = dict(lv)
            best_by_n[n].setdefault("all_attempts_agg_tok_s", []).append(lv["agg_tok_s"])
        rows = [best_by_n[n] for n in sorted(best_by_n)]
        for r in rows:
            r["hit_level_cap"] = False
            r["cap_fraction"] = 1.0 if r.get("tokens") == TOKENS * r["n"] else (round(r["tokens"] / (TOKENS * r["n"]), 3) if r.get("tokens") else None)
            r["p50_latency_s"] = r.get("latency_mean_s")  # sweep.py reports mean, not p50
            self.out.row({"kind": "level", "cell": cell["id"], "rig": self.rig.host, "engine": "vllm", "model": cell["model"],
                          "block": cell["block"], "source": "sweep.py", **r})
            log(f"  {cell['id']} n={r['n']:<4} {r.get('agg_tok_s')} tok/s (sweep.py, mean lat {r.get('latency_mean_s')})")
        summary["levels"] = rows
        summary["status"] = "ok"
        ctl = cell.get("control_min")
        if ctl:
            got = next((r.get("agg_tok_s") for r in rows if r["n"] == ctl["n"]), None)
            summary["control_check"] = {"n": ctl["n"], "min": ctl["agg_ge"], "got": got}
            if got is None or got < ctl["agg_ge"]:
                self.rig_stopped = f"rule (e)1: control {cell['id']} read {got} at n={ctl['n']} < {ctl['agg_ge']}; rig state changed, remaining blocks stopped"
                summary["control_failed"] = True

    def cell_retake(self, cell: dict, summary: dict) -> None:
        n_head = cell["headline_n"]
        best_id, best_v = None, -1.0
        for cid, s in self.results.items():
            if s.get("status") != "ok" or s.get("engine") in ("batched-bench", "retake"):
                continue
            for lv in s.get("levels", []):
                if lv.get("n") == n_head and (lv.get("agg_tok_s") or 0) > best_v and (lv.get("cap_fraction") or 0) >= 0.9:
                    best_id, best_v = cid, lv["agg_tok_s"]
        if best_id is None:
            summary["status"] = "skipped"
            summary["reason"] = f"no completed cell has a level at n={n_head}"
            return
        src = json.loads(json.dumps(self.results[best_id]["cell"]))
        src["id"] = cell["id"]
        src["block"] = cell["block"]
        src["repeats"] = 2
        src["purpose"] = f"re-take of {best_id} ({best_v} tok/s at n={n_head}), better-of-two"
        src.pop("_retried", None)
        summary["retakes"] = best_id
        summary["winner_first_pass_tok_s"] = best_v
        log(f"  re-take: winner at n={n_head} is {best_id} ({best_v} tok/s)")
        sub = self.run_cell(src, nested=True)
        summary.update({k: v for k, v in sub.items() if k not in ("id",)})

    # ---- dispatcher
    def run_cell(self, cell: dict, nested: bool = False) -> dict:
        cid = cell["id"]
        eng = cell["engine"]
        summary = {"kind": "cell", "cell": cid, "rig": self.rig.host, "engine": eng, "model": cell.get("model"),
                   "block": cell.get("block"), "purpose": cell.get("purpose"), "status": None, "reason": None,
                   "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "cell": cid}
        log(f"=== {self.rig.host} {cid} [{eng}] {cell.get('purpose', '')[:80]}")
        t0 = time.time()
        # skip rules that need no rig action
        if self.rig_stopped:
            summary.update(status="skipped", reason=self.rig_stopped)
        elif eng in self.skip_engine:
            summary.update(status="skipped", reason=self.skip_engine[eng])
        elif eng == "lmdeploy" and cell.get("model") in self.lmdeploy_dead_models:
            summary.update(status="skipped", reason=f"rule (d)3: {cell['model']} did not load on {self.rig.host} earlier in the block")
        elif cell.get("requires"):
            for req in cell["requires"]:
                if self.results.get(req, {}).get("status") != "ok":
                    summary.update(status="skipped", reason=f"requires {req} to have run ok; it is {self.results.get(req, {}).get('status')}")
        if summary["status"] is None and cell.get("skip_if"):
            si = cell["skip_if"]
            s = self.results.get(si["cell"], {})
            got = next((lv.get("agg_tok_s") for lv in s.get("levels", []) if lv.get("n") == si["n"]), None)
            if got is not None and got >= si["agg_ge"]:
                summary.update(status="skipped", reason=f"rule {si.get('rule','')}: {si['cell']} read {got} >= {si['agg_ge']} at n={si['n']}")
        if summary["status"] is not None:
            log(f"  skipped: {summary['reason']}")
            summary["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            summary["cell_def"] = cell
            self.out.row(summary)
            self.results[cid] = {**summary, "cell": cell}
            return summary
        pre = self.capture(cid, "pre")
        summary["pre_state"] = {k: pre.get(k) for k in ("gpu_mem_used_mib", "gpu_name", "gpu_total_mib", "driver_version",
                                                        "compute_capability", "card", "loadavg", "ollama_env_ollama_pairs", "ollama_active")}
        name = CONTAINER.get(eng)
        try:
            if eng == "ollama":
                self.cell_ollama(cell, summary)
            elif eng in ("llamacpp", "lmdeploy"):
                self.cell_docker(cell, summary)
            elif eng == "batched-bench":
                self.cell_batched_bench(cell, summary)
            elif eng == "vllm":
                self.cell_vllm(cell, summary)
            elif eng == "retake":
                self.cell_retake(cell, summary)
            else:
                raise ValueError(f"unknown engine {eng}")
        except Exception as e:
            summary["status"] = "error"
            summary["reason"] = repr(e)[:400]
            summary["traceback"] = traceback.format_exc()[-1500:]
            log(f"  !! {cid} error: {e!r}")
            if eng == "ollama":
                try:
                    summary["restore_after_error"] = self.ollama.restore()
                except Exception as e2:
                    summary["restore_after_error"] = {"restored": False, "error": repr(e2)}
        finally:
            # teardown
            if eng in ("llamacpp", "lmdeploy", "batched-bench") and name:
                if self.rig.container_exists(name):
                    self.rig.ssh(f"docker stop {name} >/dev/null 2>&1; docker rm -f {name} >/dev/null 2>&1; true", timeout=180)
                for _ in range(20):
                    if self.rig.dry or self.rig.gpu_used() < IDLE_GPU_MIB:
                        break
                    time.sleep(2)
            if eng == "vllm" and name and self.rig.container_exists(name):
                self.rig.ssh(f"docker rm -f {name} >/dev/null 2>&1; true", timeout=180)
        # ollama block end: restore when the next cell is not ollama (decided by caller via end_block)
        summary["wall_s"] = round(time.time() - t0, 1)
        summary["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not nested:
            post = self.capture(cid, "post")
            summary["post_state"] = {k: post.get(k) for k in ("gpu_mem_used_mib", "ollama_env_ollama_pairs", "ollama_active", "docker_ps_a", "ollama_ps")}
        summary["cell_def"] = {k: v for k, v in cell.items() if not k.startswith("_")}
        self.out.row(summary)
        self.results[cid] = {**summary, "cell": cell}
        return summary

    def run(self, cells: list[dict]) -> dict:
        if self.only:
            cells = [c for c in cells if c["id"] in self.only]
        notes = []
        for i, cell in enumerate(cells):
            self.run_cell(cell)
            nxt = cells[i + 1]["engine"] if i + 1 < len(cells) else None
            if cell["engine"] == "ollama" and nxt != "ollama":
                log("ollama block end -> restore")
                self.out.row({"kind": "restore", "rig": self.rig.host, "after": cell["id"], **self.ollama.restore()})
            docker_engines = ("llamacpp", "lmdeploy", "batched-bench", "vllm")
            if cell["engine"] in docker_engines and nxt not in docker_engines:
                log("docker-engine block end -> start ollama, re-read env (rule (b)5)")
                try:
                    self.ensure_ollama_started()
                    self.out.row({"kind": "ollama-start", "rig": self.rig.host, "after": cell["id"],
                                  "env_readback": self.ollama.env_readback(), "active": self.ollama.is_active()})
                except Exception as e:
                    self.out.row({"kind": "ollama-start", "rig": self.rig.host, "after": cell["id"], "error": repr(e)[:300]})
        # final: ollama up and restored, readback asserted
        log("final restore + readback")
        fin = self.ollama.restore()
        self.out.row({"kind": "restore", "rig": self.rig.host, "after": "END", **fin})
        post = self.capture("END", "post")
        viol = self.post_state_violations(post, expect_ollama_env=True)
        self.out.row({"kind": "post-state-check", "rig": self.rig.host, "violations": viol})
        # rule (a)4 note: control at n=8 vs slot cell at n=8
        for ctl, slot in (("A2-1", "A2-3"), ("A1-1", "A1-2")):
            a = self.results.get(ctl, {}); b = self.results.get(slot, {})
            ga = next((lv.get("agg_tok_s") for lv in a.get("levels", []) if lv.get("n") == 8), None)
            gb = next((lv.get("agg_tok_s") for lv in b.get("levels", []) if lv.get("n") == 8), None)
            if ga and gb:
                notes.append({"rule": "(a)4", "control": ctl, "slots": slot, "n": 8, "control_tok_s": ga, "slots_tok_s": gb,
                              "slots_buy_nothing": ga >= 0.9 * gb})
        return {"final_restore": fin, "post_state_violations": viol, "notes": notes,
                "cells": {cid: {"status": s.get("status"), "reason": s.get("reason"),
                                "levels": [(lv.get("n"), lv.get("agg_tok_s")) for lv in s.get("levels", [])]}
                          for cid, s in self.results.items()}}


# ----------------------------------------------------------------------------- main
def rig_facts(rig: Rig, images: list[str]) -> dict:
    st = rig.state()
    digests = {}
    for im in images:
        out, _ = rig.ssh(f"docker inspect --format '{{{{index .RepoDigests 0}}}}' {shlex.quote(im)} 2>&1", timeout=60)
        digests[im] = out.strip()
    ver, _ = rig.ssh("ollama --version 2>&1 | tail -1; docker --version", timeout=30)
    return {"state": st, "image_digests": digests, "versions": ver}


def safe_restore(runner: "Runner") -> dict:
    """Crash/interrupt path: stop our own containers, then restore the drop-in; never raise."""
    res: dict = {}
    try:
        for name in sorted(set(CONTAINER.values())):
            if runner.rig.container_exists(name):
                runner.rig.ssh(f"docker stop {name} >/dev/null 2>&1; docker rm -f {name} >/dev/null 2>&1; true", timeout=180)
                res.setdefault("containers_removed", []).append(name)
    except Exception as e:
        res["container_cleanup_error"] = repr(e)[:300]
    try:
        res.update(runner.ollama.restore())
    except Exception as e:
        res.update({"restored": False, "error": repr(e)[:300]})
        log(f"!! RESTORE FAILED on {runner.rig.host}: {e!r} -- run `--restore-only` by hand")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None, help="comma-separated cell ids")
    ap.add_argument("--rig", choices=["srv1", "srv2"], default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--levels-cap-s", type=float, default=180.0)
    ap.add_argument("--restore-only", action="store_true")
    a = ap.parse_args()

    spec = json.loads(Path(a.cells).read_text())
    rigs = [a.rig] if a.rig else list(spec["rigs"].keys())
    if a.restore_only:
        for host in rigs:
            res = Ollama(Rig(host, a.dry_run)).restore()
            print(json.dumps({"rig": host, **res}))
        return 0
    if not a.out:
        ap.error("--out is required unless --restore-only")
    only = set(a.only.split(",")) if a.only else None
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rc = 0
    for host in rigs:
        out = Out(Path(a.out) / host if not a.rig else Path(a.out), a.dry_run)
        rig = Rig(host, a.dry_run)
        cells = spec["rigs"][host]
        run = {"rig": host, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec": spec.get("spec"),
               "levels_cap_s": a.levels_cap_s, "only": sorted(only) if only else None, "dry_run": a.dry_run,
               "repo_head": head, "runner_sha256": sha256_file(Path(__file__)), "cells_sha256": sha256_file(Path(a.cells)),
               "prompt": PROMPT, "tokens": TOKENS, "num_ctx": NUM_CTX, "cap_tokens": CAP_TOKENS}
        images = sorted({c["image"] for c in cells if c.get("image")} | {"vllm/vllm-openai:v0.26.0"})
        run["rig_facts"] = rig_facts(rig, images)
        out.json("run.json", run)
        log(f"run start {host}: {len(cells)} cells, cap {a.levels_cap_s}s, out {out.dir}")
        runner = Runner(rig, out, a.levels_cap_s, only)
        try:
            run["result"] = runner.run(cells)
        except KeyboardInterrupt:
            log("interrupted -> restore")
            run["result"] = {"interrupted": True, "final_restore": safe_restore(runner)}
            rc = 130
        except Exception as e:
            log(f"runner crashed: {e!r} -> restore")
            run["result"] = {"crash": repr(e), "traceback": traceback.format_exc()[-2000:],
                             "final_restore": safe_restore(runner)}
            rc = 1
        run["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        run["post_state"] = rig.state()
        out.json("run.json", run)
        log(f"run end {host}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
