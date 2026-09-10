"""The primitives every arm in this campaign shares.

Lifted from `records/measurements/ram-headroom-2026-09-09/sweep.py` so the
figures are comparable: the same door, the same `calendar.timegm` reading of
`StartedAt`, the same envelope-move-aside dance before every `serve`.

Two things are new here and both are instruments the earlier campaign did not
need:

* :func:`sample_start` runs a 1 Hz sampler on the rig for the whole of a load,
  so a *peak* card figure is available and not only a steady-state one. The
  loading mode's cost (G1) is a load-time CUDA allocation, and a steady-state
  read cannot see it.
* :func:`vllm` talks to the vLLM dev endpoints (`/sleep`, `/wake_up`,
  `/is_sleeping`), which only answer on a unit launched
  `--enable-sleep-mode` with `VLLM_SERVER_DEV_MODE=1`.
"""

from __future__ import annotations

import calendar
import json
import subprocess
import time
from pathlib import Path

REPO = Path("/home/adaramir/claude/mcgyvr")
SCR = Path(__file__).resolve().parent
LOGS = SCR / "logs"
LOGS.mkdir(exist_ok=True)


def sh(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def rig(host: str, script: str, timeout: int = 300) -> str:
    out = sh(["ssh", "-o", "BatchMode=yes", host, script], timeout=timeout)
    return out.stdout.strip()


def meminfo(host: str) -> dict[str, float]:
    raw = rig(host, "cat /proc/meminfo")
    got: dict[str, float] = {}
    for line in raw.splitlines():
        k, _, v = line.partition(":")
        if k in (
            "MemTotal",
            "MemFree",
            "MemAvailable",
            "Cached",
            "Shmem",
            "SwapFree",
            "SwapTotal",
        ):
            got[k] = int(v.split()[0]) / (1 << 20)
    return got


def vmstat(host: str) -> dict[str, int]:
    raw = rig(host, "cat /proc/vmstat")
    got: dict[str, int] = {}
    for line in raw.splitlines():
        k, _, v = line.partition(" ")
        if k in ("pgmajfault", "pswpin", "pswpout"):
            got[k] = int(v)
    return got


def gpu(host: str) -> dict[str, int]:
    raw = rig(
        host,
        "nvidia-smi --query-gpu=memory.total,memory.used,memory.reserved,"
        "memory.free --format=csv,noheader,nounits",
    )
    total, used, reserved, free = (int(x) for x in raw.split(","))
    return {"total": total, "used": used, "reserved": reserved, "free": free}


def drop_caches(host: str) -> None:
    rig(host, "sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'; sleep 2")


def balloon_down(host: str) -> None:
    rig(host, "sudo pkill -f /tmp/balloon.py; sleep 2; true")


def balloon_up(host: str, gib: float) -> str:
    if gib <= 0.05:
        return "none"
    rig(
        host,
        f"sudo nohup python3 /tmp/balloon.py {gib:.2f} > /tmp/balloon.log 2>&1 &"
        " sleep 1; true",
    )
    for _ in range(180):
        log = rig(host, "cat /tmp/balloon.log 2>/dev/null; true")
        if "READY" in log:
            return log.replace("\n", " | ")
        time.sleep(1)
    raise SystemExit(f"{host}: balloon of {gib:.2f} GiB never reported READY")


# --- the 1 Hz sampler -------------------------------------------------------

# The sampler is stopped by **pid file**, never by `pkill -f`. `pkill -f
# mcg-sample.sh` matches the ssh command line that contains those characters
# and kills the invoking shell instead of the sampler — which is how the first
# run of this campaign collected zero samples across a 141 s load.
SAMPLER = r"""
cat > /tmp/mcg-sample.sh <<'EOF'
#!/bin/sh
while true; do
  g=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits | tr -d ' ')
  m=$(awk '/^MemAvailable:/{a=$2}/^Shmem:/{s=$2}END{print a","s}' /proc/meminfo)
  echo "$(date -u +%s),$g,$m"
  sleep 1
done
EOF
chmod +x /tmp/mcg-sample.sh
if [ -f /tmp/mcg-sample.pid ]; then kill "$(cat /tmp/mcg-sample.pid)" 2>/dev/null; fi
rm -f /tmp/mcg-sample.csv
setsid /tmp/mcg-sample.sh > /tmp/mcg-sample.csv 2>/dev/null < /dev/null &
echo $! > /tmp/mcg-sample.pid
sleep 2
wc -l < /tmp/mcg-sample.csv
"""


def sample_start(host: str) -> None:
    got = rig(host, SAMPLER)
    if got.strip() in ("", "0"):
        raise SystemExit(f"{host}: the 1 Hz sampler wrote no rows in 2 s")


def sample_stop(host: str, name: str) -> list[dict[str, int]]:
    rig(host, 'if [ -f /tmp/mcg-sample.pid ]; then kill "$(cat /tmp/mcg-sample.pid)"; fi; true')
    raw = rig(host, "cat /tmp/mcg-sample.csv")
    rows = []
    for line in raw.splitlines():
        parts = line.split(",")
        if len(parts) != 5:
            continue
        try:
            rows.append(
                {
                    "t": int(parts[0]),
                    "vram_used_mib": int(parts[1]),
                    "vram_free_mib": int(parts[2]),
                    "avail_kib": int(parts[3]),
                    "shmem_kib": int(parts[4]),
                }
            )
        except ValueError:
            continue
    (LOGS / f"sample-{name}.json").write_text(json.dumps(rows, indent=1))
    return rows


# --- the door ---------------------------------------------------------------


#: Two doors on two different rigs take two different rig leases and never
#: collide there — but gate 1 writes `tools/bench/rounds.json` in *this*
#: checkout whenever the product hash has moved, and this campaign runs beside
#: an agent that is editing `src/`, so the hash moves. One local lock, so the
#: srv1 and srv2 arms can run in parallel without racing that file.
DOOR_LOCK = "/tmp/claude-1000/mcgyvr-door.lock"


def door(direction: str, host: str, compose: str, suffix: str, timeout: int = 1800):
    """`serve up|down` through the door, with the envelope moved aside first."""
    ev = REPO / "records" / "evidence" / f"2026-09-09-live-{host}"
    stale = ev / f"serve-{direction}.json"
    if stale.exists():
        stale.rename(ev / f"serve-{direction}-{suffix}.json")
    proc = sh(
        [
            "flock", DOOR_LOCK,
            "uv", "run", "--no-sync", "python", "-m", "mcgyvr.serving.run",
            "serve", direction, "--host", host, "--compose", compose,
            "--suffix", suffix,
        ],
        timeout=timeout,
    )
    (LOGS / f"door-{direction}-{suffix}.log").write_text(
        proc.stdout + "\n--- stderr ---\n" + proc.stderr
    )
    return proc


def door_or_die(direction: str, host: str, compose: str, suffix: str, timeout=1800):
    proc = door(direction, host, compose, suffix, timeout)
    if proc.returncode != 0:
        raise SystemExit(
            f"DOOR FAILED {direction}/{suffix} rc={proc.returncode}\n"
            + proc.stdout[-2000:] + proc.stderr[-2000:]
        )
    return proc


def note_up(host: str, compose: str) -> None:
    """Remember the file a host was last brought up with.

    Three arms were lost on 2026-09-09 to tearing a host down with the wrong
    compose. Container *names* are not enough to pick the file when two
    composes name the same containers with different argv — the sleep-mode
    pair and the production pair do exactly that — so the file that started a
    unit is the file that stops it, and it is written down rather than
    inferred.
    """
    (LOGS / f"last-up-{host}.txt").write_text(compose)


def last_up(host: str) -> str | None:
    path = LOGS / f"last-up-{host}.txt"
    return path.read_text().strip() if path.exists() else None


def started_at(host: str, container: str) -> str:
    return rig(host, f"docker inspect {container} --format '{{{{.State.StartedAt}}}}'")


def restarts(host: str, container: str) -> int:
    """How many times docker has restarted this container.

    `StartedAt` is the *last* start, so a container that crashed and was
    restarted by `restart: unless-stopped` reports a wake shorter than the one
    the door measured — which is how a 171.7 s pair start read as 89.8 s in
    this campaign's first arm. Anything timing a wake off `StartedAt` has to
    read this beside it.
    """
    raw = rig(host, f"docker inspect {container} --format '{{{{.RestartCount}}}}' || echo -1")
    try:
        return int(raw.strip())
    except ValueError:
        return -1


def wake_from(host: str, container: str, t_up_done: float) -> float:
    """Seconds from the container's own StartedAt (UTC!) to health.

    `time.mktime` reads the UTC stamp as local and adds the 10,800 s offset
    here. `calendar.timegm` is the one that is right.
    """
    sa = started_at(host, container)
    epoch = calendar.timegm(time.strptime(sa[:19], "%Y-%m-%dT%H:%M:%S"))
    return t_up_done - epoch


# --- talking to the units ---------------------------------------------------

LLAMA_PROMPT = "Write a Python function that merges two sorted lists."


def decode_llamacpp(host: str, port: int, n: int = 160) -> float | None:
    body = json.dumps(
        {"prompt": LLAMA_PROMPT, "n_predict": n, "temperature": 0, "cache_prompt": False}
    )
    proc = sh(
        ["curl", "-s", "-m", "900", f"http://{host}:{port}/completion",
         "-H", "Content-Type: application/json", "-d", body],
        timeout=960,
    )
    try:
        return json.loads(proc.stdout)["timings"]["predicted_per_second"]
    except Exception:
        return None


def decode_llamacpp_warm(
    host: str, port: int, n: int = 160, samples: int = 3
) -> dict | None:
    """The `ram-headroom` decode instrument: one discarded warm-up, then a mean.

    The campaign and the headroom sweep disagree about the 80B by 2.3x —
    29.71 tok/s against 13.46 — on composes that are byte-identical apart from
    one offload block. One extra block cannot cost 56%, so the difference is
    either the instrument or it is real, and no arm has ever taken both
    readings. Every arm here takes both: :func:`decode_llamacpp` is the cold
    single sample the campaign used, this is the warm mean the sweep used, and
    the gap between them on one arm is the answer.
    """
    decode_llamacpp(host, port, n)  # discarded warm-up
    got = [decode_llamacpp(host, port, n) for _ in range(samples)]
    good = [x for x in got if x is not None]
    if not good:
        return None
    return {
        "mean": sum(good) / len(good),
        "samples": good,
        "n": len(good),
    }


def decode_vllm(host: str, port: int, model: str, n: int = 160) -> dict | None:
    """Decode rate for a vLLM unit, timed client-side over a streamed reply.

    vLLM's OpenAI surface does not return llama.cpp's `timings` block, so the
    rate is (completion_tokens - 1) / (last token - first token): the
    time-to-first-token is prefill and is reported separately rather than
    folded into a decode figure.
    """
    body = json.dumps(
        {
            "model": model,
            "prompt": LLAMA_PROMPT,
            "max_tokens": n,
            "temperature": 0,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    )
    t0 = time.time()
    proc = subprocess.Popen(
        ["curl", "-sN", "-m", "300", f"http://{host}:{port}/v1/completions",
         "-H", "Content-Type: application/json", "-d", body],
        stdout=subprocess.PIPE, text=True,
    )
    first = last = None
    tokens = 0
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
        for ch in obj.get("choices") or []:
            if ch.get("text"):
                now = time.time()
                if first is None:
                    first = now
                last = now
                tokens += 1
    proc.wait(timeout=30)
    if first is None or last is None or tokens < 2 or last == first:
        return None
    return {
        "ttft_s": first - t0,
        "tok_s": (tokens - 1) / (last - first),
        "tokens": tokens,
        "usage": usage,
    }


def http(host: str, port: int, path: str, method: str = "GET", timeout: int = 120):
    cmd = ["curl", "-s", "-m", str(timeout), "-o", "-", "-w", "\n%{http_code}"]
    if method == "POST":
        cmd += ["-X", "POST"]
    cmd.append(f"http://{host}:{port}{path}")
    proc = sh(cmd, timeout=timeout + 30)
    body, _, code = proc.stdout.rpartition("\n")
    return code.strip(), body
