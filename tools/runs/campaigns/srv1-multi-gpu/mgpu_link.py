"""The two-card link, measured from inside the vLLM image on the rig.

SHIPPED, NEVER RUN HERE. 1-link.sh pipes this file into a container started
from the campaign's vLLM digest (`bash -c 'cat > /tmp/mgpu_link.py && python3
/tmp/mgpu_link.py'`): torch.multiprocessing re-imports its main module by path,
so `python3 -` would not do. It opens no ssh and starts no container.

Every result is one line, `MGPU<TAB>{json}`, so the step can pick them out of
NCCL's INFO chatter, which it keeps for the transport NCCL chose.

  PEER  torch.cuda.can_device_access_peer both ways, and a 256 MiB copy
        cuda:0 -> cuda:1 timed five times: the peer path, or the host bounce
        when there is none
  H2D   a 256 MiB pinned host -> card copy per card: what the bounce is
        bounded by
  LINK  each card's PCIe generation and width, max and current, read while
        the H2D copies keep the link awake (an idle card trains down to gen1)
  AR    NCCL all_reduce of fp16 buffers from 4 KiB to 64 MiB between the two
        cards: p50/p90 latency and bus bandwidth. A decode step moves
        hidden_size x 2 bytes per token per all-reduce (7 KiB for a 7B, 10 KiB
        for a 14B/32B), twice a layer — the small sizes are the ones TP pays

`NCCL_P2P_DISABLE` is the step's to set; this file only reports what it got.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import threading
import time
from typing import Any

import torch
import torch.distributed as dist
import torch.multiprocessing as mp

SIZES = [2**k for k in range(12, 27, 1)]  # 4 KiB .. 64 MiB
COPY_BYTES = 256 * 2**20
#: A file store, so the rendezvous names no address at all.
INIT = "file:///tmp/mgpu-link-rdzv"


def say(kind: str, **fields: Any) -> None:
    print(f"MGPU\t{json.dumps({'kind': kind, **fields})}", flush=True)


def timed_copy(src: torch.Tensor, device: str, reps: int = 5) -> float:
    """GiB/s of the median of ``reps`` blocking copies of ``src`` to ``device``."""
    lat = []
    for _ in range(reps):
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        src.to(device, non_blocking=False)
        torch.cuda.synchronize()
        lat.append(time.perf_counter() - t0)
    return float(src.numel() * src.element_size() / statistics.median(lat) / 2**30)


def link(stop: threading.Event) -> None:
    """Each card's link while the copies run; the widest reading is kept."""
    try:
        import pynvml
    except ImportError:
        say("LINK", error="pynvml is not in this image")
        return
    pynvml.nvmlInit()
    seen: dict[int, dict[str, int]] = {}
    while not stop.is_set():
        for i in range(pynvml.nvmlDeviceGetCount()):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            now = {
                "gen": pynvml.nvmlDeviceGetCurrPcieLinkGeneration(h),
                "width": pynvml.nvmlDeviceGetCurrPcieLinkWidth(h),
            }
            best = seen.setdefault(i, now)
            if (now["gen"], now["width"]) > (best["gen"], best["width"]):
                seen[i] = now
        time.sleep(0.2)
    for i, best in sorted(seen.items()):
        h = pynvml.nvmlDeviceGetHandleByIndex(i)
        say(
            "LINK",
            gpu=i,
            gen_max=pynvml.nvmlDeviceGetMaxPcieLinkGeneration(h),
            width_max=pynvml.nvmlDeviceGetMaxPcieLinkWidth(h),
            gen_loaded=best["gen"],
            width_loaded=best["width"],
        )


def copies() -> None:
    say(
        "PEER",
        p2p_0_to_1=torch.cuda.can_device_access_peer(0, 1),
        p2p_1_to_0=torch.cuda.can_device_access_peer(1, 0),
        copy_0_to_1_gibs=round(
            timed_copy(
                torch.ones(COPY_BYTES, dtype=torch.uint8, device="cuda:0"), "cuda:1"
            ),
            2,
        ),
    )
    host = torch.ones(COPY_BYTES, dtype=torch.uint8).pin_memory()
    for i in range(torch.cuda.device_count()):
        say("H2D", gpu=i, gibs=round(timed_copy(host, f"cuda:{i}"), 2))


def worker(rank: int, world: int) -> None:
    torch.cuda.set_device(rank)
    dist.init_process_group("nccl", init_method=INIT, rank=rank, world_size=world)
    for nbytes in SIZES:
        t = torch.ones(nbytes // 2, dtype=torch.float16, device=f"cuda:{rank}")
        for _ in range(10):
            dist.all_reduce(t)
        torch.cuda.synchronize()
        reps = 300 if nbytes <= 2**20 else 30
        lat = []
        for _ in range(reps):
            t0 = time.perf_counter()
            dist.all_reduce(t)
            torch.cuda.synchronize()
            lat.append(time.perf_counter() - t0)
        if rank == 0:
            lat.sort()
            mid = statistics.median(lat)
            say(
                "AR",
                bytes=nbytes,
                reps=reps,
                lat_ms_p50=round(mid * 1000, 4),
                lat_ms_p90=round(lat[int(0.9 * (reps - 1))] * 1000, 4),
                # busbw for a ring of n is algbw * 2(n-1)/n, which is algbw at n=2
                busbw_gibs=round(nbytes / mid / 2**30, 3),
            )
    dist.destroy_process_group()


def main() -> int:
    n = torch.cuda.device_count()
    say(
        "ENV",
        cards=n,
        nccl_p2p_disable=os.environ.get("NCCL_P2P_DISABLE", "unset"),
        torch=torch.__version__,
        nccl=".".join(map(str, torch.cuda.nccl.version())),
    )
    if n != 2:
        say("ERROR", why=f"{n} cards visible; this probe is for two")
        return 1
    stop = threading.Event()
    watcher = threading.Thread(target=link, args=(stop,))
    watcher.start()
    try:
        copies()
    finally:
        stop.set()
        watcher.join()
    if os.path.exists(INIT.removeprefix("file://")):
        os.remove(INIT.removeprefix("file://"))
    mp.spawn(worker, args=(n,), nprocs=n, join=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
