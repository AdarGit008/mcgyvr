"""What a sleeping vLLM co-resident leaves on the card, and what level 1 keeps.

**M6 / O13.** `emit` sizes a placement against an *idle* card. The runtime case
it cannot express is a card with sleepers on it, and the only figure anyone has
is one point: both units at level 2 leave 11,409 MiB, and `emit`'s 80B at
`--n-cpu-moe 35` asks 11,960 and fails to create a context. This walks the
whole matrix — each unit asleep alone and both together, at each level — so
what a co-resident leaves is a table rather than a datum.

**M7 / O14.** Level 1 was measured on 2026-09-09 never to return host RAM: not
on wake, not after idle, and a level-2 sleep does not release what level 1
took. That is a *decision* — the owner is being asked to ban it — so this
re-runs it on the current build to confirm the finding reproduces, and records
the three things a ban has to be written against: which endpoint, how much, and
whether anything short of a container restart recovers it.

Order matters. Every level-2 arm runs **before** any level-1 arm, because a
level-1 sleep contaminates host RAM for the process's lifetime and would
otherwise sit under the level-2 figures.

Run against a pair brought up on `compose.srv2.sleepmode.yml`.
"""

from __future__ import annotations

import json
import time

import rig

HOST = "srv2"
UNITS = {"3b": (8001, "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"),
         "7b": (8002, "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ")}
LOG: list[dict] = []
OUT = rig.SCR / "m6-m7-sleep-matrix.json"


def procs() -> str:
    return rig.rig(
        HOST,
        "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader || true",
    ).replace("\n", " | ")


def sleeping(port: int) -> str:
    code, body = rig.http(HOST, port, "/is_sleeping", timeout=20)
    return f"{code}:{body.strip()[:40]}"


def note(step: str, **kw) -> dict:
    g, m = rig.gpu(HOST), rig.meminfo(HOST)
    row = {
        "step": step,
        "vram_used_mib": g["used"],
        "vram_free_mib": g["free"],
        "vram_reserved_mib": g["reserved"],
        "mem_avail_gib": round(m["MemAvailable"], 2),
        "mem_free_gib": round(m["MemFree"], 2),
        "cached_gib": round(m["Cached"], 2),
        "sleeping": {n: sleeping(p) for n, (p, _) in UNITS.items()},
        "gpu_procs": procs(),
        **kw,
    }
    LOG.append(row)
    OUT.write_text(json.dumps(LOG, indent=2))
    print(f"  [{step:30s}] card {g['used']:5d} used /{g['free']:6d} free   "
          f"avail {row['mem_avail_gib']:6.2f}G   {row['sleeping']}   "
          + " ".join(f"{k}={v}" for k, v in kw.items()), flush=True)
    return row


def call(label: str, port: int, path: str) -> float:
    t0 = time.time()
    code, body = rig.http(HOST, port, path, method="POST", timeout=300)
    dt = round(time.time() - t0, 2)
    print(f"    {label}: {dt:6.2f} s   http {code}  {body.strip()[:90]}", flush=True)
    return dt


def decode(name: str) -> float | None:
    port, model = UNITS[name]
    got = rig.decode_vllm(HOST, port, model)
    return round(got["tok_s"], 2) if got else None


def main() -> None:
    print("=== baseline ===", flush=True)
    note("baseline-both-serving", decode_3b=decode("3b"), decode_7b=decode("7b"))

    # ---- M6: the level-2 matrix, taken before level 1 touches anything ----
    print("\n=== M6: level 2, every combination ===", flush=True)
    for name in ("3b", "7b"):
        port, _ = UNITS[name]
        dt = call(f"sleep {name} L2", port, "/sleep?level=2")
        note(f"L2-{name}-alone-asleep", sleep_s=dt)
        other = "7b" if name == "3b" else "3b"
        note(f"L2-{name}-asleep-{other}-serving", decode_other=decode(other))
        dt = call(f"wake {name}", port, "/wake_up")
        note(f"L2-{name}-alone-awake", wake_s=dt, decode=decode(name))

    print("\n=== M6: both asleep at level 2 — the case that funds an 80B ===", flush=True)
    s = {n: call(f"sleep {n} L2", UNITS[n][0], "/sleep?level=2") for n in ("3b", "7b")}
    row = note("L2-both-asleep", sleep_s=s)
    print(f"\n>>> both asleep: {row['vram_free_mib']} MiB free. `emit` asks 11,960 "
          f"at --n-cpu-moe 35; one expert block is 732 MiB.\n", flush=True)
    # The trap: a sleeping unit answers /v1/models with 200 and hangs on a
    # real request. Confirm both halves rather than repeating the claim.
    for n in ("3b", "7b"):
        code, _ = rig.http(HOST, UNITS[n][0], "/v1/models", timeout=20)
        note(f"L2-both-asleep-probe-{n}", v1_models_http=code)
    w = {n: call(f"wake {n}", UNITS[n][0], "/wake_up") for n in ("3b", "7b")}
    note("L2-both-awake", wake_s=w, decode_3b=decode("3b"), decode_7b=decode("7b"))

    # ---- M7: level 1, which is where the host RAM goes and does not come back ----
    print("\n=== M7: level 1 ===", flush=True)
    for name in ("3b", "7b"):
        port, _ = UNITS[name]
        before = note(f"L1-{name}-before")
        dt = call(f"sleep {name} L1", port, "/sleep?level=1")
        asleep = note(f"L1-{name}-asleep", sleep_s=dt)
        dt2 = call(f"wake {name}", port, "/wake_up")
        awake = note(f"L1-{name}-awake", wake_s=dt2, decode=decode(name))
        print(f"    >>> {name}: avail {before['mem_avail_gib']} -> "
              f"{asleep['mem_avail_gib']} asleep -> {awake['mem_avail_gib']} awake  "
              f"(kept {before['mem_avail_gib'] - awake['mem_avail_gib']:+.2f} GiB)",
              flush=True)

    print("\n=== M7: does a level-2 sleep release what level 1 took? ===", flush=True)
    for name in ("3b", "7b"):
        port, _ = UNITS[name]
        dt = call(f"sleep {name} L2", port, "/sleep?level=2")
        note(f"L1then2-{name}-asleep-L2", sleep_s=dt)
    note("L1then2-both-asleep-L2")
    time.sleep(60)
    note("L1then2-both-asleep-L2-after-60s-idle")
    for name in ("3b", "7b"):
        call(f"wake {name}", UNITS[name][0], "/wake_up")
    note("L1then2-both-awake", decode_3b=decode("3b"), decode_7b=decode("7b"))

    print("\n=== M7: a second level-1 cycle — bounded buffer, or a leak? ===", flush=True)
    for name in ("3b", "7b"):
        port, _ = UNITS[name]
        call(f"sleep {name} L1 (2nd)", port, "/sleep?level=1")
        call(f"wake {name}", port, "/wake_up")
    note("L1-second-cycle-both-awake", decode_3b=decode("3b"), decode_7b=decode("7b"))

    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
