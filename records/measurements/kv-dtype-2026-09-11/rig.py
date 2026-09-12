"""The primitives every arm of the fleet identity run shares.

Lifted from `records/measurements/measuring-gaps-2026-09-10/rig.py`, itself from
`ram-headroom-2026-09-09/sweep.py`, so the figures stay comparable. Five things
are new, and each is an instrument this run needs and the earlier ones did not:

* :func:`door` times the door the way the Waker does. It takes the local door
  lock first, then times `python -m mcgyvr.serving.run serve ...` with
  `time.monotonic()`, using this checkout's interpreter. That is the span
  `src/mcgyvr/wake.py` `_run_door` measures, with the argv `door_argv` builds.
  The lock wait is outside the clock, where `flock` in the earlier campaigns
  put it inside.
* :class:`ReadyPoller` asks each unit's `/v1/models` every 0.5 s from the moment
  the door is spawned. For a pair this gives a per-unit clock, which the door's
  own 3.0 s sequential poll cannot.
* :func:`clock_offset` reads the rig's clock against this machine's, so a
  `StartedAt` stamped by the rig's daemon can be subtracted from a time taken
  here.
* The sampler also records `pswpout`, `pgmajfault` and per-process card memory.
* The decode instruments ask `/v1/chat/completions` for exactly 256 tokens with
  `ignore_eos`, so every sample decodes the same length.
"""

from __future__ import annotations

import calendar
import fcntl
import json
import os
import re
import statistics
import subprocess
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCR = Path(__file__).resolve().parent
REPO = SCR.parents[2]
PY = REPO / ".venv" / "bin" / "python"
LOGS = SCR / "logs"
LOGS.mkdir(exist_ok=True)

DOOR_LOCK = "/tmp/claude-1000/mcgyvr-door.lock"
DECODE_TOKENS = 256
WARM_SAMPLES = 5
SYSTEM = "You are a careful Python programmer. Answer with code only."
PROMPT = (
    "Write a Python function that merges two sorted lists into one sorted list, "
    "with a docstring and three doctest examples."
)


def sh(cmd: list[str], timeout: float = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def rig(host: str, script: str, timeout: float = 300) -> str:
    out = sh(["ssh", "-o", "BatchMode=yes", host, script], timeout=timeout)
    return out.stdout.strip()


def rig_or_die(host: str, script: str, timeout: float = 300) -> str:
    out = sh(["ssh", "-o", "BatchMode=yes", host, script], timeout=timeout)
    if out.returncode != 0:
        raise SystemExit(f"{host}: `{script}` rc={out.returncode}: {out.stderr[-800:]}")
    return out.stdout.strip()


# --- host readings ----------------------------------------------------------


def meminfo(host: str) -> dict[str, float]:
    """`/proc/meminfo` in GiB (SwapTotal in MiB is `swap_total_mib`)."""
    got: dict[str, float] = {}
    for line in rig(host, "cat /proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        if k in ("MemTotal", "MemFree", "MemAvailable", "Cached", "Shmem",
                 "SwapFree", "SwapTotal"):
            got[k] = int(v.split()[0]) / (1 << 20)
    return got


def swap_total_mib(host: str) -> int:
    raw = rig(host, "awk '/^SwapTotal:/{print $2}' /proc/meminfo")
    return int(raw) // 1024


def vmstat(host: str) -> dict[str, int]:
    got: dict[str, int] = {}
    for line in rig(host, "cat /proc/vmstat").splitlines():
        k, _, v = line.partition(" ")
        if k in ("pgmajfault", "pswpin", "pswpout"):
            got[k] = int(v)
    return got


def uptime_since(host: str) -> str:
    """The boot, as `rig-snapshot.sh` names it: `/proc/stat` btime in UTC."""
    raw = rig_or_die(host, "awk '/^btime /{print $2; exit}' /proc/stat")
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(raw)))


def gpu(host: str) -> dict[str, Any]:
    raw = rig_or_die(
        host,
        "nvidia-smi --query-gpu=name,memory.total,memory.used,memory.reserved,"
        "memory.free,compute_cap,driver_version --format=csv,noheader,nounits",
    )
    name, total, used, reserved, free, cc, driver = (x.strip() for x in raw.split(","))
    return {"name": name, "total": int(total), "used": int(used),
            "reserved": int(reserved), "free": int(free), "cc": cc, "driver": driver}


def gpu_apps(host: str) -> str:
    raw = rig(host, "nvidia-smi --query-compute-apps=pid,used_memory "
                    "--format=csv,noheader,nounits")
    rows = [line.replace(" ", "") for line in raw.splitlines() if line.strip()]
    return ";".join(rows) or "none"


def drop_caches(host: str) -> None:
    rig_or_die(host, "sudo -n sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'; sleep 2")


def swapoff(host: str) -> None:
    rig_or_die(host, "sudo -n swapoff -a", timeout=900)
    if swap_total_mib(host) != 0:
        raise SystemExit(f"{host}: swapoff -a left swap configured")


def swapon(host: str) -> None:
    rig_or_die(host, "sudo -n swapon -a")
    if swap_total_mib(host) == 0:
        raise SystemExit(f"{host}: swapon -a left no swap")


def clock_offset(host: str) -> float:
    """Rig clock minus this machine's clock, in seconds (the median of three)."""
    got = []
    for _ in range(3):
        t0 = time.time()
        raw = rig_or_die(host, "date +%s.%N")
        t1 = time.time()
        got.append(float(raw) - (t0 + t1) / 2)
    return statistics.median(got)


# --- the 1 Hz sampler -------------------------------------------------------

#: Stopped by pid file, never `pkill -f`, which matches its own ssh command line.
SAMPLER = r"""
cat > /tmp/mcg-fid-sample.sh <<'EOF'
#!/bin/sh
while true; do
  g=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits | tr -d ' ')
  a=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | tr -d ' ' | tr '\n' ';')
  m=$(awk '/^MemAvailable:/{a=$2}/^Shmem:/{s=$2}END{print a","s}' /proc/meminfo)
  v=$(awk '/^pswpout /{o=$2}/^pgmajfault /{f=$2}END{print o","f}' /proc/vmstat)
  echo "$(date -u +%s),$g,$m,$v,${a:-none}"
  sleep 1
done
EOF
chmod +x /tmp/mcg-fid-sample.sh
if [ -f /tmp/mcg-fid-sample.pid ]; then kill "$(cat /tmp/mcg-fid-sample.pid)" 2>/dev/null; fi
rm -f /tmp/mcg-fid-sample.csv
setsid /tmp/mcg-fid-sample.sh > /tmp/mcg-fid-sample.csv 2>/dev/null < /dev/null &
echo $! > /tmp/mcg-fid-sample.pid
sleep 2
wc -l < /tmp/mcg-fid-sample.csv
"""


def sample_start(host: str) -> None:
    if rig(host, SAMPLER).strip() in ("", "0"):
        raise SystemExit(f"{host}: the 1 Hz sampler wrote no rows in 2 s")


def sample_stop(host: str, name: str) -> list[dict[str, Any]]:
    rig(host, 'if [ -f /tmp/mcg-fid-sample.pid ]; then kill "$(cat /tmp/mcg-fid-sample.pid)"; '
              "rm -f /tmp/mcg-fid-sample.pid; fi; true")
    rows = []
    for line in rig(host, "cat /tmp/mcg-fid-sample.csv").splitlines():
        parts = line.split(",", 7)
        if len(parts) != 8:
            continue
        try:
            apps: dict[str, int] = {}
            for item in parts[7].strip(";").split(";"):
                if item and item != "none":
                    pid, _, mib = item.partition(",")
                    apps[pid] = int(mib)
            rows.append({
                "t": int(parts[0]), "vram_used_mib": int(parts[1]),
                "vram_free_mib": int(parts[2]), "avail_kib": int(parts[3]),
                "shmem_kib": int(parts[4]), "pswpout": int(parts[5]),
                "pgmajfault": int(parts[6]), "apps_mib": apps,
            })
        except ValueError:
            continue
    (LOGS / f"sample-{name}.json").write_text(json.dumps(rows, indent=1))
    return rows


# --- the door ---------------------------------------------------------------


def door(direction: str, host: str, compose: Path, suffix: str,
         timeout: float = 1800) -> tuple[subprocess.CompletedProcess[str], float, dict[str, Any] | None]:
    """`serve up|down` through the door, timed as the Waker times it.

    Returns the process, the door-process seconds, and the `serve-<direction>.json`
    the door wrote (read before the next door on this host moves it aside).
    """
    # Gate 5 mints RUN_ID from the suffix and never reuses one, not even after a
    # refused attempt, so every attempt carries its own clock reading.
    suffix = f"{suffix}-{int(time.time())}"
    ev = REPO / "records" / "evidence" / f"{datetime.now(UTC).strftime('%Y-%m-%d')}-live-{host}"
    stale = ev / f"serve-{direction}.json"
    if stale.exists():
        stale.rename(ev / f"serve-{direction}-before-{suffix}.json")
    argv = [str(PY), "-m", "mcgyvr.serving.run", "serve", direction,
            "--host", host, "--compose", str(compose), "--suffix", suffix]
    with open(DOOR_LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        started = time.monotonic()
        # The gate scripts run as `#!/usr/bin/env python3`, so the checkout's venv
        # must lead PATH, as `uv run` arranges; the interpreter alone is not enough.
        env = {**os.environ, "PATH": f"{PY.parent}:{os.environ.get('PATH', '')}"}
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              cwd=REPO, env=env)
        seconds = time.monotonic() - started
    (LOGS / f"door-{direction}-{suffix}.log").write_text(
        proc.stdout + "\n--- stderr ---\n" + proc.stderr)
    envelope = None
    fresh = ev / f"serve-{direction}.json"
    if fresh.exists():
        envelope = json.loads(fresh.read_text())
    return proc, seconds, envelope


def door_or_die(direction: str, host: str, compose: Path, suffix: str):
    proc, seconds, envelope = door(direction, host, compose, suffix)
    if proc.returncode != 0:
        raise SystemExit(f"DOOR FAILED {direction}/{suffix} rc={proc.returncode}\n"
                         + proc.stdout[-2000:] + proc.stderr[-2000:])
    return proc, seconds, envelope


def note_up(host: str, compose: Path) -> None:
    """The file that started a unit is the file that stops it."""
    (LOGS / f"last-up-{host}.txt").write_text(str(compose))


def last_up(host: str) -> Path | None:
    path = LOGS / f"last-up-{host}.txt"
    return Path(path.read_text().strip()) if path.exists() else None


def forget_up(host: str) -> None:
    (LOGS / f"last-up-{host}.txt").unlink(missing_ok=True)


def teardown(host: str) -> None:
    """Empty the rig through the door with the compose that started it."""
    names = [n for n in rig(host, f"docker ps -a --format '{{{{.Names}}}}' | grep '^mcgyvr-{host}-' || true").split() if n]
    if not names:
        forget_up(host)
        return
    compose = last_up(host)
    if compose is None:
        raise SystemExit(f"{host}: {names} are up and no last-up file names their compose")
    door_or_die("down", host, compose, f"td-{int(time.time() * 10) % 10**9}")
    left = [n for n in rig(host, f"docker ps -a --format '{{{{.Names}}}}' | grep '^mcgyvr-{host}-' || true").split() if n]
    if left:
        raise SystemExit(f"{host}: still present after serve down: {left}")
    forget_up(host)


# --- containers -------------------------------------------------------------


def inspect(host: str, container: str, field: str) -> str:
    return rig(host, f"docker inspect {container} --format '{{{{{field}}}}}' 2>/dev/null || true")


def started_at(host: str, container: str) -> float:
    """`State.StartedAt` (UTC, nanoseconds) as a rig-clock epoch."""
    raw = inspect(host, container, ".State.StartedAt")
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z", raw)
    if not m:
        raise SystemExit(f"{host}: {container} StartedAt unreadable: {raw!r}")
    return calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")) + float(m.group(2) or 0)


def restarts(host: str, container: str) -> int:
    raw = inspect(host, container, ".RestartCount")
    return int(raw) if raw.strip().isdigit() else -1


def engine_log(host: str, container: str, label: str) -> str:
    log = rig(host, f"docker logs {container} 2>&1 || true", timeout=300)
    (LOGS / f"{label}.log").write_text(log)
    return log


def process_rss_gib(host: str, container: str) -> float:
    """Σ RssAnon + RssShmem over the container's processes."""
    script = (
        f"for p in $(docker top {container} -eo pid | tail -n +2); do "
        "awk '/^(RssAnon|RssShmem):/{s+=$2}END{print s+0}' /proc/$p/status 2>/dev/null; done"
    )
    kib = sum(int(x) for x in rig(host, script).split() if x.isdigit())
    return kib / (1 << 20)


# --- readiness --------------------------------------------------------------


class ReadyPoller:
    """First 200 from each unit's `/v1/models`, polled every 0.5 s from here."""

    def __init__(self, host: str, ports: dict[str, int]) -> None:
        self.host = host
        self.ports = ports
        self.ready: dict[str, float] = {}
        self._stop = threading.Event()
        self._threads = [threading.Thread(target=self._poll, args=(name, port), daemon=True)
                         for name, port in ports.items()]

    def _poll(self, name: str, port: int) -> None:
        while not self._stop.is_set():
            proc = sh(["curl", "-s", "-m", "1", "-o", "/dev/null", "-w", "%{http_code}",
                       f"http://{self.host}:{port}/v1/models"], timeout=5)
            if proc.stdout.strip() == "200":
                self.ready[name] = time.time()
                return
            time.sleep(0.5)

    def __enter__(self) -> ReadyPoller:
        for t in self._threads:
            t.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)


def http_get(host: str, port: int, path: str, timeout: int = 10) -> tuple[str, str]:
    proc = sh(["curl", "-s", "-m", str(timeout), "-w", "\n%{http_code}",
               f"http://{host}:{port}{path}"], timeout=timeout + 30)
    body, _, code = proc.stdout.rpartition("\n")
    return code.strip(), body


def http_post(host: str, port: int, path: str, body: dict[str, Any],
              timeout: int = 120) -> tuple[str, str]:
    proc = sh(["curl", "-s", "-m", str(timeout), "-w", "\n%{http_code}",
               "-H", "Content-Type: application/json", "-d", json.dumps(body),
               f"http://{host}:{port}{path}"], timeout=timeout + 30)
    body_out, _, code = proc.stdout.rpartition("\n")
    return code.strip(), body_out


# --- decode -----------------------------------------------------------------


def _body(model: str | None, max_tokens: int, stream: bool) -> str:
    body: dict[str, Any] = {
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": PROMPT}],
        "max_tokens": max_tokens, "temperature": 0, "ignore_eos": True,
    }
    if model:
        body["model"] = model
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return json.dumps(body)


def decode_llamacpp(host: str, port: int) -> dict[str, Any] | None:
    proc = sh(["curl", "-s", "-m", "900", f"http://{host}:{port}/v1/chat/completions",
               "-H", "Content-Type: application/json", "-d", _body(None, DECODE_TOKENS, False)],
              timeout=960)
    try:
        doc = json.loads(proc.stdout)
        timings = doc["timings"]
        return {"tok_s": float(timings["predicted_per_second"]),
                "completion_tokens": int(doc["usage"]["completion_tokens"]),
                "predicted_n": int(timings["predicted_n"])}
    except (ValueError, KeyError, TypeError):
        (LOGS / "decode-unparsed.txt").open("a").write(proc.stdout[-2000:] + "\n")
        return None


def decode_vllm(host: str, port: int, model: str, max_tokens: int = DECODE_TOKENS) -> dict[str, Any] | None:
    """Rate over a streamed reply: (completion_tokens - 1) / (last chunk - first chunk)."""
    proc = subprocess.Popen(
        ["curl", "-sN", "-m", "600", f"http://{host}:{port}/v1/chat/completions",
         "-H", "Content-Type: application/json", "-d", _body(model, max_tokens, True)],
        stdout=subprocess.PIPE, text=True)
    t0 = time.time()
    first = last = None
    usage = None
    assert proc.stdout is not None
    for line in proc.stdout:
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except ValueError:
            continue
        if obj.get("usage"):
            usage = obj["usage"]
        for choice in obj.get("choices") or []:
            if (choice.get("delta") or {}).get("content"):
                now = time.time()
                first = first or now
                last = now
    proc.wait(timeout=30)
    if not usage or first is None or last is None or last == first:
        return None
    n = int(usage["completion_tokens"])
    return {"tok_s": (n - 1) / (last - first), "completion_tokens": n, "ttft_s": first - t0}


def warm_decode(fn, *args: Any) -> tuple[list[dict[str, Any]], int]:
    """One discarded warm-up, then WARM_SAMPLES samples of exactly DECODE_TOKENS."""
    fn(*args)
    samples = []
    for _ in range(WARM_SAMPLES + 3):
        got = fn(*args)
        if got and got["completion_tokens"] == DECODE_TOKENS:
            samples.append(got)
        if len(samples) == WARM_SAMPLES:
            break
    if len(samples) < WARM_SAMPLES:
        raise SystemExit(f"only {len(samples)} decode samples of {DECODE_TOKENS} tokens")
    return samples, 1
