"""Does a sleeping vLLM unit hand its card back well enough to fund an 80B wake?

The question this answers is not "is vLLM's sleep fast" in the abstract. It is
the owner's layout: srv2's 3B and 7B asleep, `/is_sleeping` true, while a
llama.cpp 80B serves on the same card. That only works if a sleeping vLLM
process releases *nearly all* of its VRAM -- the 80B wants 11.68 GiB of an
11.91 GiB card, so two live CUDA contexts are enough to refuse it.

Level 1 parks the weights in host RAM; level 2 discards them. Both are measured,
per unit and together, because level 1's RAM cost lands on the resource
`records/measurements/ram-headroom-2026-09-09/` shows is the dangerous one to
overcommit.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

SCR = Path(__file__).resolve().parent
HOST = "srv2"
UNITS = {"3B": 8001, "7B": 8002}
LOG: list[dict] = []


def sh(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def rig(script: str, timeout: int = 120) -> str:
    return sh(["ssh", "-o", "BatchMode=yes", HOST, script], timeout=timeout).stdout.strip()


def vram() -> tuple[int, int]:
    """(used_mib, free_mib) off the card itself."""
    raw = rig("nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits")
    used, free = (int(x.strip()) for x in raw.split(","))
    return used, free


def ram_gib() -> float:
    raw = rig("awk '/^MemAvailable/{print $2}' /proc/meminfo")
    return int(raw) / (1 << 20)


def gpu_procs() -> str:
    return rig(
        "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader || true"
    ).replace("\n", " | ")


def http(method: str, port: int, path: str, timeout: int = 300) -> tuple[int, str]:
    cmd = ["curl", "-s", "-m", str(timeout), "-o", "-", "-w", "\n%{http_code}",
           "-X", method, f"http://{HOST}:{port}{path}"]
    out = sh(cmd, timeout=timeout + 30).stdout
    body, _, code = out.rpartition("\n")
    return (int(code) if code.strip().isdigit() else 0), body.strip()[:200]


def is_sleeping(port: int) -> str:
    code, body = http("GET", port, "/is_sleeping", timeout=20)
    return f"{code}:{body}" if code else "unreachable"


def answers(port: int) -> bool:
    code, _ = http("GET", port, "/v1/models", timeout=20)
    return code == 200


def note(step: str, **kw) -> None:
    used, free = vram()
    row = {"step": step, "vram_used_mib": used, "vram_free_mib": free,
           "ram_avail_gib": round(ram_gib(), 2),
           "sleeping": {n: is_sleeping(p) for n, p in UNITS.items()},
           "answers": {n: answers(p) for n, p in UNITS.items()}, **kw}
    LOG.append(row)
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f"  [{step:34s}] vram {used:5d} used / {free:5d} free   "
          f"ram {row['ram_avail_gib']:5.2f}G   "
          f"sleeping={row['sleeping']}  answers={row['answers']}  {extra}", flush=True)
    (SCR / "logs" / "vllm-sleep-results.json").write_text(json.dumps(LOG, indent=2))


def timed(label: str, method: str, port: int, path: str) -> float:
    t0 = time.time()
    code, body = http(method, port, path)
    dt = time.time() - t0
    print(f"    {label}: {dt:.2f} s  http {code} {body[:80]}", flush=True)
    return round(dt, 2)


def main() -> None:
    print("=== baseline: both vLLM units serving ===", flush=True)
    note("baseline-both-serving", procs=gpu_procs())

    for level in (1, 2):
        for name, port in UNITS.items():
            print(f"\n=== level {level}: sleep {name} alone ===", flush=True)
            dt = timed(f"sleep {name} L{level}", "POST", port, f"/sleep?level={level}")
            note(f"L{level}-{name}-asleep", sleep_s=dt, procs=gpu_procs())
            dt = timed(f"wake {name}", "POST", port, "/wake_up")
            note(f"L{level}-{name}-awake", wake_s=dt)

    print("\n=== level 2: both asleep — the case that funds the 80B ===", flush=True)
    both = {}
    for name, port in UNITS.items():
        both[name] = timed(f"sleep {name} L2", "POST", port, "/sleep?level=2")
    note("L2-both-asleep", sleep_s=both, procs=gpu_procs())

    print(f"\n>>> card with both vLLM units asleep: "
          f"{vram()[1]} MiB free; the 80B wants 11960 MiB", flush=True)

    print("\n=== wake both back ===", flush=True)
    back = {}
    for name, port in UNITS.items():
        back[name] = timed(f"wake {name}", "POST", port, "/wake_up")
    note("L2-both-awake", wake_s=back)

    print(f"\nwrote {SCR / 'logs' / 'vllm-sleep-results.json'}", flush=True)


if __name__ == "__main__":
    main()
